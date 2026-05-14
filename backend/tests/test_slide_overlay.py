"""
Regression test for the slide-PNG CV/RT overlay.

The bug this prevents: prior to this fix, the Server Performance
Snapshot PNG/PDF showed `CV = 0.0` and `RT = 0` for every server when
a snapshot was created from a POS-only upload — the canonical
`current_metrics` had zeros and the slide never consulted `employees_v2`
where the actual CV/RT data lived.

Locks down:
  1. `_hydrate_snapshot_employees` falls back to `employees_v2` for
     CV/RT/metric_bonus fields when the canonical `current_metrics`
     is missing those values (zeros count as missing).
  2. The merge is field-level: canonical fields (e.g. metric_bonus)
     and v2 fields (e.g. cv_score) can both flow through the same row.
  3. The on-the-fly RT bonus / CV score recompute uses the overlaid
     inputs so the snapshot PNG renders the same numbers as /rankings.
  4. Finalized snapshots do NOT get the overlay (historical downloads
     must match the moment-in-time when frozen).
"""

import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from snapshot_routes import _hydrate_snapshot_employees


TEST_DB = os.environ["DB_NAME"] + "_slide_overlay_test"


async def _seed(db, *, finalized: bool):
    eid = "test-employee-id-" + uuid.uuid4().hex[:8]
    await db.employees.insert_one({
        "id": eid, "name": "Test Server", "display_name": "Test Server",
        "status": "active",
        "current_metrics": {
            "cv_score": 0, "rt_mentions": 0,
            "total_metric_bonus": 4.5,  # partial canonical overlay
        },
    })
    await db.employees_v2.insert_one({
        "id": eid, "name": "Test Server",
        "quarter": "Q2", "year": 2026,
        "cv_score": 22.0, "nps_score": 100, "cv_promoters": 1,
        "rt_mentions": 18, "review_tracker_bonus": 5.4,
        "total_metric_bonus": 4.5,
    })
    snap_id = "snap-" + uuid.uuid4().hex[:8]
    await db.snapshot_workflow.insert_one({
        "id": snap_id, "name": "Test Snap",
        "quarter": "Q2", "year": 2026,
        "is_current": True,
        "status": "finalized" if finalized else "completed",
        "rows": [{
            "employee_id": eid,
            "frozen_display_name": "Test Server",
            "frozen_report_name": "Test Server",
            "frozen_metrics": {
                "quarter": "Q2", "year": 2026,
                "score_ppa": 90, "score_lbw": 80, "score_glass": 100, "score_lsc": 110,
                "cv_score": 0, "rt_mentions": 0,
                "total_metric_bonus": 4.5,
                "weighted_score": 70, "total_score": 70,
            },
        }],
    })


async def _run_case(finalized: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[TEST_DB]
    try:
        # Always start fresh per case so the asserts don't leak across runs.
        await client.drop_database(TEST_DB)
        await _seed(db, finalized=finalized)
        snap = await db.snapshot_workflow.find_one({}, {"_id": 0})
        rows = await _hydrate_snapshot_employees(db, snap)
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        return rows[0]
    finally:
        await client.drop_database(TEST_DB)
        client.close()


def test_v2_overlay_fills_canonical_zeros():
    row = asyncio.run(_run_case(finalized=False))
    assert row["rt_mentions"] == 18, f"Expected rt=18 from v2 overlay, got {row.get('rt_mentions')}"
    assert abs(row["review_tracker_bonus"] - 5.4) < 0.01
    assert abs(row["cv_score"] - 11.0) < 0.01, f"Expected cv=11.0 from recompute, got {row.get('cv_score')}"


def test_v2_overlay_merges_with_canonical():
    row = asyncio.run(_run_case(finalized=False))
    # total_metric_bonus came from canonical (4.5)
    assert abs(row["total_metric_bonus"] - 4.5) < 0.01
    # nps_score + cv_promoters came from v2 (they're zero/missing in canonical)
    assert row["nps_score"] == 100
    assert row["cv_promoters"] == 1


def test_finalized_snapshot_skips_overlay():
    row = asyncio.run(_run_case(finalized=True))
    assert (row.get("cv_score") or 0) == 0
    assert (row.get("rt_mentions") or 0) == 0
    assert (row.get("review_tracker_bonus") or 0) == 0


if __name__ == "__main__":
    test_v2_overlay_fills_canonical_zeros(); print("OK v2 overlay fills zeros")
    test_v2_overlay_merges_with_canonical(); print("OK merge canonical + v2")
    test_finalized_snapshot_skips_overlay(); print("OK finalized skips")
