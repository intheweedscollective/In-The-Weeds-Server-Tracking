"""
Phase 3 Stage A regression tests.

Locks in the materialize / join behaviour that the new thin `rows[]`
schema depends on. Once Stage B switches readers over, these tests
guarantee `rows[]` returns the same data as the legacy `employees[]`
array.

⚠️ Uses an isolated test DB.
"""

import asyncio
import os
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_phase3_stage_a_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_materialize_builds_rows_with_canonical_fk():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        ana = await svc.create_employee({"name": "Ana Acosta"})
        bob = await svc.create_employee({"name": "Bob Brown"})
        # Alias coverage: Bob also has a nickname row in the snapshot
        await svc.col.update_one(
            {"id": bob["id"]},
            {"$addToSet": {"aliases": "Bobby B"}},
        )

        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "is_current": True, "status": "completed",
            "year": 2099, "quarter": "Q9",
            "employees": [
                {"id": ana["id"], "name": "Ana Acosta",
                 "total_score": 92.0, "performance_tier": "A-Server",
                 "peer_rank": 1, "cv_score": 11.0},
                # Resolves to Bob via alias, not id.
                {"id": str(uuid.uuid4()), "name": "Bobby B",
                 "total_score": 78.0, "performance_tier": "B-Server",
                 "peer_rank": 2, "cv_score": 7.0},
            ],
        })

        snap = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        count = await svc.materialize_rows_from_employees(snap)
        assert count == 2

        snap2 = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        rows = snap2["rows"]
        assert snap2["row_count"] == 2
        by_fk = {r["employee_id"]: r for r in rows}
        assert ana["id"] in by_fk
        assert bob["id"] in by_fk
        # Bob's row was matched via alias — frozen display_name is the
        # row's name (the canonical's display name OR the snapshot row's
        # display_name, whichever the resolver picks first).
        bob_row = by_fk[bob["id"]]
        assert bob_row["frozen_display_name"] in ("Bob", "Bobby B", "Bob Brown")
        assert bob_row["frozen_score"] == 78.0
        assert bob_row["frozen_tier"] == "B-Server"
        assert bob_row["frozen_rank"] == 2
        # Frozen metrics carries the rest verbatim.
        assert bob_row["frozen_metrics"]["cv_score"] == 7.0

        # Idempotent — re-run produces same count.
        again = await svc.materialize_rows_from_employees(snap2)
        assert again == 2

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())


def test_get_snapshot_with_join_returns_filtered_active_employees():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        alice = await svc.create_employee({"name": "Alice", "display_name": "Allie"})
        bob = await svc.create_employee({"name": "Bob"})
        await svc.terminate(bob["id"])  # terminated → must be filtered out
        carol = await svc.create_employee({"name": "Carol"})

        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "is_current": True, "status": "completed",
            "year": 2099, "quarter": "Q9",
            "deleted_names": ["Carol"],   # blocklist → must drop Carol too
            "employees": [
                {"id": alice["id"], "name": "Alice", "total_score": 90.0},
                {"id": bob["id"], "name": "Bob", "total_score": 75.0},
                {"id": carol["id"], "name": "Carol", "total_score": 81.0},
            ],
        })
        # Build rows[].
        snap = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        await svc.materialize_rows_from_employees(snap)

        result = await svc.get_snapshot_with_join(snap_id)
        assert result is not None
        names = [e["name"] for e in result["employees"]]
        # Bob filtered (terminated). Carol filtered (blocklist). Alice's
        # display name was overlaid from canonical.
        assert names == ["Allie"]
        # FK is stamped.
        assert result["employees"][0]["canonical_id"] == alice["id"]

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())


def test_get_snapshot_with_join_falls_back_to_employees_when_rows_empty():
    """Stage B will rip out employees[] usage gradually — until then the
    join helper must transparently fall back to the legacy array."""
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        a = await svc.create_employee({"name": "Solo"})

        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "is_current": True, "status": "completed",
            "year": 2099, "quarter": "Q9",
            "employees": [
                {"id": a["id"], "name": "Solo", "total_score": 99.0},
            ],
            # rows[] intentionally missing
        })

        result = await svc.get_snapshot_with_join(snap_id)
        names = [e["name"] for e in result["employees"]]
        assert names == ["Solo"]

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())
