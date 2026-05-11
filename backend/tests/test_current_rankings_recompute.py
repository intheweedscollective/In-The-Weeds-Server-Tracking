"""
Regression: `/v2/snapshot-workflow/current-rankings` must recompute the
three drift-prone derived fields on every row before returning them.

  - review_tracker_bonus = min(rt_mentions × rt_points_per_mention, rt_max_points)
  - cv_score = clamp(nps_score, 0, 100)/10 + cv_promoters − 2 × cv_detractors
    (unless `nps_manual_override` is set on the row)
  - total_metric_bonus = bonus_ppa + bonus_lbw + bonus_glass + bonus_lsc

The historical bug: each of these fields was stored on
`snapshot.employees[]` and never recomputed when inputs (mentions,
promoters, sub-bonuses) changed via uploads. Result was visible drift
between the leaderboard columns and their inputs.
"""

import asyncio
import os
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_current_rankings_recomputes_rt_cv_metric_bonus_from_inputs():
    """Seed a snapshot with deliberately-stale derived fields and
    confirm `current-rankings` returns the correct freshly-computed
    values."""
    from fastapi.testclient import TestClient
    from server import app

    async def setup():
        c, db = _client()
        # Park whatever's currently flagged is_current so our fake doc wins.
        await db.snapshot_workflow.update_many(
            {"is_current": True},
            {"$set": {"is_current": False, "_test_was_current": True}},
        )

        snap_id = f"_test_drift_{uuid.uuid4()}"
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "is_current": True,
            "status": "completed",
            "year": 2099, "quarter": "Q9",
            "name": "drift-test",
            "employees": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Stale Stan",
                    "tier_label": "A-Server",
                    "total_score": 90,
                    # RT inputs/output diverge (should refresh to 35×0.3=10.5)
                    "rt_mentions": 35,
                    "review_mentions": 35,
                    "review_tracker_bonus": 4.2,   # stale
                    # CV inputs/output diverge
                    #   nps=80, promoters=3, detractors=1
                    #   expected = 80/10 + 3 - 2*1 = 9.0
                    "nps_score": 80,
                    "cv_promoters": 3,
                    "cv_detractors": 1,
                    "cv_score": 1.0,               # stale
                    # Metric bonus subtotals don't match aggregate
                    "bonus_ppa": 2.0,
                    "bonus_lbw": 1.5,
                    "bonus_glass": 1.0,
                    "bonus_lsc": 0.5,
                    "total_metric_bonus": 0.0,     # stale (real sum = 5.0)
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Pinned Pam",
                    "tier_label": "A-Server",
                    "total_score": 88,
                    "rt_mentions": 10,
                    "review_tracker_bonus": 999,   # stale
                    # Manual override: CV must be left alone
                    "nps_manual_override": True,
                    "nps_score": 80,
                    "cv_promoters": 3,
                    "cv_detractors": 1,
                    "cv_score": 42.0,              # respected (override)
                    "bonus_ppa": 0,
                    "bonus_lbw": 0,
                    "bonus_glass": 0,
                    "bonus_lsc": 0,
                    "total_metric_bonus": 999,     # stale
                },
            ],
        })
        await db.quarter_settings.insert_one({
            "id": str(uuid.uuid4()),
            "year": 2099, "quarter": "Q9",
            "rt_points_per_mention": 0.3, "rt_max_points": 20.0,
            "benchmark_ppa": 55, "benchmark_lbw": 8,
            "benchmark_glass": 1, "benchmark_lsc": 100, "benchmark_cv": 5,
            "weight_ppa": 0.25, "weight_lbw": 0.20, "weight_glass": 0.15,
            "weight_lsc": 0.25, "weight_cv": 0.15,
            "bonus_rate": 0.2, "bonus_cap": 5,
            "a_server_min_score": 85, "b_server_min_score": 70,
        })
        c.close()
        return snap_id

    async def teardown(snap_id):
        c, db = _client()
        await db.snapshot_workflow.delete_one({"id": snap_id})
        await db.quarter_settings.delete_one({"year": 2099, "quarter": "Q9"})
        # Restore the snapshots we paused.
        await db.snapshot_workflow.update_many(
            {"_test_was_current": True},
            {"$set": {"is_current": True}, "$unset": {"_test_was_current": ""}},
        )
        c.close()

    snap_id = _run(setup())
    try:
        client = TestClient(app)
        r = client.get("/api/v2/snapshot-workflow/current-rankings",
                       params={"year": 2099, "quarter": "Q9"})
        assert r.status_code == 200, r.text
        body = r.json()
        emps = {e["name"]: e for e in body["employees"]}
        stan = emps["Stale Stan"]
        # RT: 35 × 0.3 = 10.5
        assert stan["review_tracker_bonus"] == 10.5, stan
        # CV: 80/10 + 3 - 2*1 = 9.0
        assert stan["cv_score"] == 9.0, stan
        # Metric bonus sum: 2.0 + 1.5 + 1.0 + 0.5 = 5.0
        assert stan["total_metric_bonus"] == 5.0, stan

        # Pinned row: RT/metric still recomputed, but CV is respected.
        pam = emps["Pinned Pam"]
        assert pam["review_tracker_bonus"] == 3.0  # 10 × 0.3
        assert pam["total_metric_bonus"] == 0.0
        assert pam["cv_score"] == 42.0  # override preserved
    finally:
        _run(teardown(snap_id))
