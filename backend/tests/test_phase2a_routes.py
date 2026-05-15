"""
Integration sanity for Phase 2A:
- `GET /v2/employees` returns the canonical-backed flat list.
- `DELETE /v2/employees/{id}` triggers the full delete_completely flow
  (canonical soft-delete + employees_v2 mirror removal + snapshot pull
  + blocklist add).
- Repeated deletes are idempotent.

Uses the real `EmployeeService` against the isolated test DB so we
exercise the actual code path the production routes use.
"""

import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_phase2a_routes_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_canonical_list_filters_terminated():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        svc = EmployeeService(db)

        a = await svc.create_employee({"name": "Alice"})
        b = await svc.create_employee({"name": "Bob"})
        # Seed quarter metrics on both
        await svc.upsert_current_metrics(a["id"], {"quarter": "Q2", "year": 2026, "cv_score": 12.0})
        await svc.upsert_current_metrics(b["id"], {"quarter": "Q2", "year": 2026, "cv_score": 8.0})

        actives = await svc.list_active(quarter="Q2", year=2026)
        assert len(actives) == 2

        # Terminate Bob and confirm only Alice remains in the active list.
        await svc.terminate(b["id"])
        actives = await svc.list_active(quarter="Q2", year=2026)
        assert len(actives) == 1
        assert actives[0]["id"] == a["id"]
        await db.employees.drop(); c.close()
    _run(runner())


def test_delete_completely_writes_blocklist_and_clears_legacy():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.employees_v2.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        # Seed a canonical employee + legacy v2 mirror + snapshot embed.
        emp = await svc.create_employee({"name": "Carla Castro"})
        await db.employees_v2.insert_one({
            "id": emp["id"],
            "name": "Carla Castro",
            "display_name": "Carla",
            "quarter": "Q2", "year": 2026,
            "cv_score": 5,
        })
        await db.snapshot_workflow.insert_one({
            "id": "snap-test",
            "is_current": True,
            "status": "completed",
            "year": 2026, "quarter": "Q2",
            "employees": [{
                "id": emp["id"],
                "name": "Carla Castro",
                "display_name": "Carla",
                "total_score": 90.0,
            }],
            "deleted_names": [],
        })

        # Trigger the canonical full delete.
        result = await svc.delete_completely(emp["id"])
        assert result["success"]
        assert result["employees_v2_removed"] >= 1
        # Canonical status flipped to terminated.
        rec = await svc.get_by_id(emp["id"])
        assert rec["status"] == "terminated"
        # v2 mirror gone.
        v2 = await db.employees_v2.find_one({"id": emp["id"]})
        assert v2 is None
        # snapshot embedded employee gone.
        snap = await db.snapshot_workflow.find_one({"id": "snap-test"}, {"_id": 0})
        assert all(e["id"] != emp["id"] for e in snap.get("employees", []))
        # blocklist populated.
        assert "Carla Castro" in (snap.get("deleted_names") or [])

        # Re-running delete is a no-op (still success).
        again = await svc.delete_completely(emp["id"])
        assert again["success"]

        await db.employees.drop()
        await db.employees_v2.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())


def test_delete_then_recreate_reuses_canonical_id():
    """Phase 2A guarantee: deleting then re-adding the same person by
    name must reuse the original canonical id, not mint a new one."""
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        svc = EmployeeService(db)

        a = await svc.create_employee({"name": "Diane Peterson"})
        original_id = a["id"]
        await svc.delete_completely(original_id)

        b = await svc.create_employee({"name": "Diane Peterson"})
        assert b["id"] == original_id
        assert b["status"] == "active"
        await db.employees.drop(); c.close()
    _run(runner())
