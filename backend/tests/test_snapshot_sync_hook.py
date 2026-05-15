"""
Regression test for `EmployeeService.sync_current_metrics_from_snapshot`.

Hook is called from both `confirm_pos_review` and `finalize_snapshot`
to keep canonical `employees.current_metrics` in step with the active
snapshot — eliminating the drift the integrity gate used to surface.

⚠️ Uses an isolated test DB. Preview shares the MongoDB cluster with
production.
"""

import asyncio
import os
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_snapshot_sync_hook_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_sync_writes_canonical_current_metrics_from_snapshot():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        a = await svc.create_employee({"name": "Alice"})
        b = await svc.create_employee({"name": "Bob"})

        await db.snapshot_workflow.insert_one({
            "id": str(uuid.uuid4()),
            "is_current": True, "status": "completed",
            "year": 2099, "quarter": "Q9",
            "employees": [
                {"id": a["id"], "name": "Alice",
                 "cv_score": 12.5, "rt_mentions": 8,
                 "review_tracker_bonus": 2.4, "total_score": 92.1,
                 "tier_label": "A-Server", "rank": 1},
                {"id": b["id"], "name": "Bob",
                 "cv_score": 9.0, "rt_mentions": 3,
                 "review_tracker_bonus": 0.9, "total_score": 78.4,
                 "tier_label": "B-Server", "rank": 2},
            ],
        })

        result = await svc.sync_current_metrics_from_snapshot()
        assert result == {"updated": 2, "unmatched": 0, "total": 2}, result

        a_after = await db.employees.find_one({"id": a["id"]}, {"_id": 0})
        cm = a_after["current_metrics"]
        assert cm["cv_score"] == 12.5
        assert cm["rt_mentions"] == 8
        assert cm["review_tracker_bonus"] == 2.4
        assert cm["total_score"] == 92.1
        assert cm["tier_label"] == "A-Server"
        assert cm["year"] == 2099
        assert cm["quarter"] == "Q9"

        b_after = await db.employees.find_one({"id": b["id"]}, {"_id": 0})
        assert b_after["current_metrics"]["cv_score"] == 9.0

        # Idempotent — re-running yields the same numbers.
        again = await svc.sync_current_metrics_from_snapshot()
        assert again["updated"] == 2

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())


def test_sync_resolves_by_alias_when_id_drifts():
    """The snapshot row's id is a legacy UUID that's listed in the
    canonical record's `legacy_ids[]`. Sync must still resolve it."""
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        canonical = await svc.create_employee({"name": "Carol"})
        legacy_id = str(uuid.uuid4())
        await db.employees.update_one(
            {"id": canonical["id"]},
            {"$addToSet": {"legacy_ids": legacy_id}},
        )

        await db.snapshot_workflow.insert_one({
            "id": str(uuid.uuid4()),
            "is_current": True, "status": "completed",
            "year": 2099, "quarter": "Q9",
            "employees": [
                {"id": legacy_id, "name": "Carol",
                 "cv_score": 7.7, "total_score": 80.0},
            ],
        })

        result = await svc.sync_current_metrics_from_snapshot()
        assert result["updated"] == 1
        assert result["unmatched"] == 0

        c_after = await db.employees.find_one({"id": canonical["id"]}, {"_id": 0})
        assert c_after["current_metrics"]["cv_score"] == 7.7

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())


def test_sync_counts_unmatched_when_no_canonical_record():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()

        await db.snapshot_workflow.insert_one({
            "id": str(uuid.uuid4()),
            "is_current": True, "status": "completed",
            "year": 2099, "quarter": "Q9",
            "employees": [
                {"id": str(uuid.uuid4()), "name": "Ghost", "cv_score": 1.0},
            ],
        })
        result = await EmployeeService(db).sync_current_metrics_from_snapshot()
        assert result == {"updated": 0, "unmatched": 1, "total": 1}, result

        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())
