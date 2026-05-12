"""
Regression tests for the auto-sync QR pipeline.

Covers:
  - Orphan rows (no canonical match) get archived.
  - Missing canonical employees get fresh QR rows with 0 clicks.
  - Duplicate QR rows (e.g. one matched by name, one matched by alias)
    roll up onto the survivor.
  - Merge flow: post-merge, the merged employee's QR clicks transfer
    onto the survivor's QR row.
  - sync_current_metrics_from_snapshot stamps qr_total_clicks on the
    canonical employee.

⚠️ Uses an isolated test DB.
"""

import asyncio
import os
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_qr_auto_sync_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_orphan_qr_rows_archived_and_missing_ones_added():
    async def runner():
        from services.employee_service import EmployeeService
        from qr_tracking import auto_sync_qr_with_canonical
        c, db = _client()
        await db.employees.drop()
        await db.qr_employees.drop()
        await db.qr_employees_archive.drop()

        svc = EmployeeService(db)
        await svc.create_employee({"name": "Active Andy"})
        await svc.create_employee({"name": "Active Beth"})

        # Seed one QR row that exists in canonical and one orphan.
        await db.qr_employees.insert_one({
            "id": str(uuid.uuid4()), "name": "Active Andy",
            "yelp_clicks": 5, "google_clicks": 3, "tripadvisor_clicks": 0,
        })
        await db.qr_employees.insert_one({
            "id": str(uuid.uuid4()), "name": "Ghost Greg",
            "yelp_clicks": 99, "google_clicks": 0, "tripadvisor_clicks": 0,
        })

        result = await auto_sync_qr_with_canonical(db)
        assert result == {"added": 1, "archived": 1, "merged_clicks": 0}, result

        names_now = sorted(
            [q["name"] async for q in db.qr_employees.find({}, {"_id": 0})]
        )
        assert names_now == ["Active Andy", "Active Beth"]
        # Andy's clicks must NEVER change.
        andy = await db.qr_employees.find_one({"name": "Active Andy"})
        assert andy["yelp_clicks"] == 5 and andy["google_clicks"] == 3
        # Beth was added fresh with zero clicks.
        beth = await db.qr_employees.find_one({"name": "Active Beth"})
        assert beth["yelp_clicks"] == 0
        # Ghost is archived.
        ghost = await db.qr_employees_archive.find_one({"name": "Ghost Greg"})
        assert ghost is not None
        assert ghost["yelp_clicks"] == 99
        assert ghost["archived_reason"] == "no_canonical_match"

        await db.employees.drop()
        await db.qr_employees.drop()
        await db.qr_employees_archive.drop()
        c.close()
    _run(runner())


def test_duplicate_via_alias_rolls_up_clicks_onto_survivor():
    """Two QR rows: one named after canonical, one named after alias.
    Both resolve to the same canonical → clicks merge."""
    async def runner():
        from services.employee_service import EmployeeService
        from qr_tracking import auto_sync_qr_with_canonical
        c, db = _client()
        await db.employees.drop()
        await db.qr_employees.drop()
        await db.qr_employees_archive.drop()

        svc = EmployeeService(db)
        canon = await svc.create_employee({"name": "Lennie Nguyen"})
        await svc.col.update_one(
            {"id": canon["id"]},
            {"$addToSet": {"aliases": "Glennice Nguyen"}},
        )

        await db.qr_employees.insert_one({
            "id": str(uuid.uuid4()), "name": "Lennie Nguyen",
            "yelp_clicks": 1, "google_clicks": 2, "tripadvisor_clicks": 0,
        })
        await db.qr_employees.insert_one({
            "id": str(uuid.uuid4()), "name": "Glennice Nguyen",
            "yelp_clicks": 4, "google_clicks": 0, "tripadvisor_clicks": 9,
        })

        result = await auto_sync_qr_with_canonical(db)
        assert result["archived"] == 1
        assert result["merged_clicks"] == 4 + 0 + 9

        rows = [q async for q in db.qr_employees.find({}, {"_id": 0})]
        assert len(rows) == 1
        assert rows[0]["name"] == "Lennie Nguyen"
        # 1+4 yelp, 2+0 google, 0+9 tripadvisor
        assert rows[0]["yelp_clicks"] == 5
        assert rows[0]["google_clicks"] == 2
        assert rows[0]["tripadvisor_clicks"] == 9

        await db.employees.drop()
        await db.qr_employees.drop()
        await db.qr_employees_archive.drop()
        c.close()
    _run(runner())


def test_sync_current_metrics_stamps_qr_total_clicks():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.qr_employees.drop()
        await db.snapshot_workflow.drop()
        svc = EmployeeService(db)

        canon = await svc.create_employee({"name": "Click Cara"})
        await db.qr_employees.insert_one({
            "id": str(uuid.uuid4()), "name": "Click Cara",
            "yelp_clicks": 3, "google_clicks": 5, "tripadvisor_clicks": 1,
        })
        await db.snapshot_workflow.insert_one({
            "id": str(uuid.uuid4()),
            "is_current": True, "status": "completed",
            "year": 2099, "quarter": "Q9",
            "employees": [{
                "id": canon["id"], "name": "Click Cara",
                "cv_score": 10.0, "total_score": 90.0,
            }],
        })

        await svc.sync_current_metrics_from_snapshot()
        after = await db.employees.find_one({"id": canon["id"]}, {"_id": 0})
        cm = after["current_metrics"]
        assert cm["qr_yelp_clicks"] == 3
        assert cm["qr_google_clicks"] == 5
        assert cm["qr_tripadvisor_clicks"] == 1
        assert cm["qr_total_clicks"] == 9

        await db.employees.drop()
        await db.qr_employees.drop()
        await db.snapshot_workflow.drop()
        c.close()
    _run(runner())
