"""
Regression: `/v2/snapshot-workflow/current-rankings` must recompute the
three drift-prone derived fields on every row before returning them.

  - review_tracker_bonus = min(rt_mentions × rt_points_per_mention, rt_max_points)
  - cv_score = clamp(nps_score, 0, 100)/10 + cv_promoters − 2 × cv_detractors
    (unless `nps_manual_override` is set on the row)
  - total_metric_bonus = bonus_ppa + bonus_lbw + bonus_glass + bonus_lsc

⚠️ Uses an isolated test DB. Preview shares the MongoDB cluster with
production, so we override `database.db` for the route under test and
restore it afterwards.
"""

import asyncio
import os
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_current_rankings_recompute_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_current_rankings_recomputes_rt_cv_metric_bonus_from_inputs():
    """Seed a snapshot with deliberately-stale derived fields and
    confirm `current-rankings` returns the correct freshly-computed
    values."""
    import database as db_module
    import snapshot_routes as snap_module
    from fastapi.testclient import TestClient
    from server import app

    async def setup():
        c, db = _client()
        await db.snapshot_workflow.drop()
        await db.quarter_settings.drop()

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
                    "rt_mentions": 35,
                    "review_mentions": 35,
                    "review_tracker_bonus": 4.2,   # stale
                    "nps_score": 80,
                    "cv_promoters": 3,
                    "cv_detractors": 1,
                    "cv_score": 1.0,               # stale (expected 9.0)
                    "bonus_ppa": 2.0,
                    "bonus_lbw": 1.5,
                    "bonus_glass": 1.0,
                    "bonus_lsc": 0.5,
                    "total_metric_bonus": 0.0,     # stale (expected 5.0)
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Pinned Pam",
                    "tier_label": "A-Server",
                    "total_score": 88,
                    "rt_mentions": 10,
                    "review_tracker_bonus": 999,   # stale
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
        await db.snapshot_workflow.drop()
        await db.quarter_settings.drop()
        c.close()

    snap_id = _run(setup())

    # Swap the process-wide `db` handles so the route reads our test DB.
    _, test_db = _client()
    original_db_module = db_module.db
    original_snap_get_db = snap_module.get_db
    db_module.db = test_db
    snap_module.get_db = lambda: test_db
    try:
        client = TestClient(app)
        r = client.get("/api/v2/snapshot-workflow/current-rankings",
                       params={"year": 2099, "quarter": "Q9"})
        assert r.status_code == 200, r.text
        body = r.json()
        emps = {e["name"]: e for e in body["employees"]}
        stan = emps["Stale Stan"]
        assert stan["review_tracker_bonus"] == 10.5, stan
        assert stan["cv_score"] == 9.0, stan
        assert stan["total_metric_bonus"] == 5.0, stan

        pam = emps["Pinned Pam"]
        assert pam["review_tracker_bonus"] == 3.0
        assert pam["total_metric_bonus"] == 0.0
        assert pam["cv_score"] == 42.0
    finally:
        db_module.db = original_db_module
        snap_module.get_db = original_snap_get_db
        _run(teardown(snap_id))

