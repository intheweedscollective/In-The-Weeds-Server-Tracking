"""
Regression: per-metric `bonus_*` fields were going stale after a POS
re-upload because `server.unified_pos_upload` updated `score_*` from
the new data but reused the prior `total_metric_bonus` from the
matched employee record. The slide hydrator then displayed the
stale bonus alongside the fresh score (operator-reported, Q2P6W1
2026-02-05: Allen Simmons showed score_glass=134.07 but bonus_glass=1.3
instead of the canonical 5.0).

These tests pin two protections:
  1. `_hydrate_snapshot_employees` recomputes per-metric bonuses
     from current `score_*` values so the slide never displays a
     stale bonus (heals already-frozen snapshots on read).
  2. The bonus formula matches `scoring_engine.calc_bonus`:
       score ≤ 100  → 0
       100 < score < 120 → (score - 100) / 20 * 5  (linear)
       score ≥ 120  → 5.0 (cap)
"""

import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


@pytest.fixture
def stale_bonus_snapshot(loop):
    """Seed a snapshot row that has score_glass=134 (well above the
    +20% cap) but a STALE bonus_glass=1.3 (matching the operator's
    real-world report). The hydrator must heal both fields on read."""
    db = _db()
    snap_id = f"bonus-test-{uuid.uuid4().hex[:8]}"
    canon_id = f"canon-allen-{uuid.uuid4().hex[:6]}"

    async def _seed():
        await db.employees.insert_one({
            "id": canon_id,
            "name": "Allen Test",
            "display_name": "Allen Test",
            "status": "active",
            "legacy_ids": [], "aliases": [],
        })
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"bonus-stale-{snap_id[-8:]}",
            "quarter": "Q9", "year": 2099,
            "status": "completed",
            "is_current": False,
            "rows": [
                {"employee_id": canon_id,
                 "frozen_display_name": "Allen Test",
                 "frozen_score": 74.36,
                 "frozen_metrics": {
                     "score_ppa": 60,
                     "score_lbw": 80,
                     "score_glass": 134.07,
                     "score_lsc": 90,
                     "bonus_ppa": 0.0,
                     "bonus_lbw": 0.0,
                     "bonus_glass": 1.3,        # ← STALE
                     "bonus_lsc": 0.0,
                     "total_metric_bonus": 1.3,  # ← STALE
                 }},
            ],
            "employees": [],
        })
    loop.run_until_complete(_seed())
    yield snap_id, canon_id

    async def _wipe():
        await db.snapshot_workflow.delete_one({"id": snap_id})
        await db.employees.delete_one({"id": canon_id})
    loop.run_until_complete(_wipe())


def test_hydrator_recomputes_stale_bonus_glass(loop, stale_bonus_snapshot):
    """The slide hydrator must overwrite a stale bonus_* on read with
    the canonical value derived from the current score_*."""
    from snapshot_routes import _hydrate_snapshot_employees
    snap_id, _ = stale_bonus_snapshot
    db = _db()

    async def _run():
        snap = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        return await _hydrate_snapshot_employees(db, snap)
    emps = loop.run_until_complete(_run())

    allen = next(e for e in emps if "allen" in (e.get("name") or "").lower())
    # score_glass = 134.07 → bonus capped at 5.0
    assert allen["bonus_glass"] == 5.0, (
        f"hydrator left stale bonus_glass — got {allen['bonus_glass']} "
        f"(expected 5.0 for score_glass=134.07)"
    )
    assert allen["bonus_ppa"]   == 0.0     # score 60 → 0
    assert allen["bonus_lbw"]   == 0.0     # score 80 → 0
    assert allen["bonus_lsc"]   == 0.0     # score 90 → 0
    # total_metric_bonus must reflect the recomputed parts.
    assert allen["total_metric_bonus"] == 5.0


def test_bonus_formula_linear_between_100_and_120(loop, stale_bonus_snapshot):
    """Sanity: a score of 110 must yield exactly 2.5; 105 yields 1.25."""
    from snapshot_routes import _hydrate_snapshot_employees
    snap_id, canon_id = stale_bonus_snapshot
    db = _db()

    # Mutate the snapshot row to score_glass=110, fresh bonus stale at 0.
    async def _mutate():
        await db.snapshot_workflow.update_one(
            {"id": snap_id},
            {"$set": {
                "rows.0.frozen_metrics.score_glass": 110,
                "rows.0.frozen_metrics.bonus_glass": 0,
            }}
        )
    loop.run_until_complete(_mutate())

    async def _run():
        snap = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        return await _hydrate_snapshot_employees(db, snap)
    emps = loop.run_until_complete(_run())
    allen = next(e for e in emps if "allen" in (e.get("name") or "").lower())
    assert allen["bonus_glass"] == 2.5, (
        f"linear midpoint failed — got {allen['bonus_glass']}"
    )


def test_bonus_formula_zero_at_or_below_benchmark(loop, stale_bonus_snapshot):
    """Score of exactly 100 (or anything below) → 0 bonus."""
    from snapshot_routes import _hydrate_snapshot_employees
    snap_id, _ = stale_bonus_snapshot
    db = _db()

    async def _mutate():
        await db.snapshot_workflow.update_one(
            {"id": snap_id},
            {"$set": {
                "rows.0.frozen_metrics.score_glass": 100,
                "rows.0.frozen_metrics.bonus_glass": 4.2,   # stale junk
            }}
        )
    loop.run_until_complete(_mutate())

    async def _run():
        snap = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        return await _hydrate_snapshot_employees(db, snap)
    emps = loop.run_until_complete(_run())
    allen = next(e for e in emps if "allen" in (e.get("name") or "").lower())
    assert allen["bonus_glass"] == 0.0
