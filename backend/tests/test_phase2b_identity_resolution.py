"""
Phase 2B regression tests:
1. `merge_snapshot_data` resolves POS rows through canonical
   `EmployeeService.find_by_name_or_alias`, so a nickname / alias never
   spawns a duplicate row in the snapshot.
2. `/v2/admin/integrity` is callable and returns the 9-check report.

We mock the snapshot upload pipeline with a tiny in-memory fake so we
can run synchronously without spinning up the FastAPI app.
"""

import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_phase2b_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_merge_uses_canonical_alias_for_identity():
    """A POS row carrying a nickname must resolve to the canonical id
    that owns that nickname as an alias — NOT mint a new UUID."""
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        # Seed canonical: Lennie Nguyen has "Glennice" as an alias.
        canonical = await svc.create_employee({"name": "Lennie Nguyen"})
        await svc.rename(canonical["id"], name="Lennie Nguyen", display_name="Lennie")
        await svc.col.update_one(
            {"id": canonical["id"]},
            {"$addToSet": {"aliases": "Glennice Nguyen"}},
        )

        # Simulated snapshot doc with a POS upload that carries the
        # nickname. merge_snapshot_data needs to find the canonical match
        # via alias lookup and reuse the existing id.
        snapshot = {
            "id": "snap-b",
            "quarter": "Q2",
            "year": 2026,
            "deleted_names": [],
            "uploads": [{
                "upload_type": "pos_report",
                "parsed_data": {
                    "employees": [{
                        "name": "Glennice Nguyen",  # the alias
                        "ppa": 55.0, "guests": 100, "net_sales": 5500,
                    }],
                },
            }],
            "employees": [],
        }

        # We need to make snapshot_routes.get_db() point at our test db.
        import snapshot_routes
        original_get_db = snapshot_routes.get_db
        snapshot_routes.get_db = lambda: db
        try:
            result = await snapshot_routes.merge_snapshot_data(snapshot)
        finally:
            snapshot_routes.get_db = original_get_db

        assert len(result) == 1
        assert result[0]["id"] == canonical["id"], (
            f"Expected canonical id {canonical['id']!r}, "
            f"got {result[0]['id']!r}. The merge created a new UUID "
            "instead of resolving the alias to the existing canonical id."
        )

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())


def test_merge_skips_pos_row_when_canonical_terminated():
    """A POS row for a terminated canonical employee must NOT be
    re-created in the snapshot."""
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        canonical = await svc.create_employee({"name": "Chase Ghost"})
        await svc.terminate(canonical["id"])

        snapshot = {
            "id": "snap-bb",
            "quarter": "Q2",
            "year": 2026,
            "deleted_names": [],
            "uploads": [{
                "upload_type": "pos_report",
                "parsed_data": {
                    "employees": [{"name": "Chase Ghost", "ppa": 50.0, "guests": 90}],
                },
            }],
            "employees": [],
        }

        import snapshot_routes
        original_get_db = snapshot_routes.get_db
        snapshot_routes.get_db = lambda: db
        try:
            result = await snapshot_routes.merge_snapshot_data(snapshot)
        finally:
            snapshot_routes.get_db = original_get_db

        assert result == [], (
            "Chase is canonical-terminated. The POS merge MUST NOT re-add him. "
            f"Got: {result}"
        )

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())


def test_admin_integrity_endpoint_callable():
    """The validation suite must run end-to-end and produce a summary
    block with the deploy_gate verdict."""
    async def runner():
        from services.validation_service import EmployeeValidator
        c, db = _client()
        await db.employees.drop()
        await db.snapshot_workflow.drop()
        # Seed an inactive-in-current-snap case to ensure the check fires.
        await db.employees.insert_one({
            "id": "x", "name": "TermedX", "status": "terminated",
            "current_metrics": {},
        })
        await db.snapshot_workflow.insert_one({
            "id": "snap-bc", "is_current": True, "status": "completed",
            "year": 2026, "quarter": "Q2",
            "employees": [{"id": "x", "name": "TermedX"}],
            "rows": [],
        })
        report = await EmployeeValidator(db).run_all()
        # P1 check should now have 1 hit.
        assert len(report["inactive_in_current_snap"]) >= 1
        assert report["summary"]["deploy_gate"] in {"PASS", "FAIL"}
        # And the structural shape is unchanged.
        for k in ("duplicate_canonical_ids", "orphaned_snapshot_refs",
                  "employees_missing_id", "blocklist_violations",
                  "duplicate_active_names", "metric_drift",
                  "legacy_only_employees", "snapshot_only_employees"):
            assert k in report

        await db.employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())
