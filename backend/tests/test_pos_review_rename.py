"""
Regression test for inline name editing on the POS Data Review screen.

The user reported needing to rename "Drane" → "Diane" on the review
modal before saving so the snapshot doesn't pick up a misspelled row.
This test exercises confirm_pos_review() end-to-end on a sentinel
snapshot:

  1. Seed a snapshot with one POS row named "Drane Peterson".
  2. POST the row back with name="Diane Peterson" and
     _original_name="Drane Peterson".
  3. Confirm:
     - the existing row was RENAMED (not duplicated)
     - the POS upload's parsed_data.employees list is also renamed
     - exactly one row carries that identity in snapshot.employees
     - the _original_name bookkeeping field is NOT persisted
"""

import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from snapshot_routes import confirm_pos_review  # noqa: E402
import snapshot_routes as snap_module  # noqa: E402


SENTINEL_YEAR = 9097


def _run(coro_factory):
    async def runner():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.snapshot_workflow.delete_many({"year": SENTINEL_YEAR})
        original = snap_module.get_db
        snap_module.get_db = lambda: db
        try:
            await coro_factory(db)
        finally:
            snap_module.get_db = original
            await db.snapshot_workflow.delete_many({"year": SENTINEL_YEAR})
            client.close()
    asyncio.run(runner())


def test_rename_updates_existing_row_in_place():
    """Renaming Drane → Diane must not create a duplicate."""
    async def body(db):
        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "quarter": "Q2",
            "year": SENTINEL_YEAR,
            "is_current": True,
            "status": "draft",
            "name": "Rename Probe",
            "employees": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Drane Peterson",
                    "display_name": "Drane Peterson",
                    "ppa": 50, "guest_count": 100,
                    "liquor_sales": 100, "beer_sales": 50, "wine_sales": 25,
                    "lsc_count": 1, "total_score": 70,
                },
            ],
            "uploads": [
                {
                    "upload_type": "pos_report",
                    "parsed_data": {
                        "employees": [
                            {"name": "Drane Peterson", "ppa": 50, "guest_count": 100},
                        ],
                    },
                },
            ],
        })

        await confirm_pos_review(
            snapshot_id=snap_id,
            data={
                "employees": [
                    {
                        "name": "Diane Peterson",
                        "_original_name": "Drane Peterson",
                        "ppa": 55, "guest_count": 100,
                        "liquor_sales": 120, "beer_sales": 60, "wine_sales": 30,
                        "lsc_count": 1,
                    },
                ],
            },
        )

        snap = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        emps = snap.get("employees", [])
        diane = [e for e in emps if e.get("name") == "Diane Peterson"]
        drane = [e for e in emps if e.get("name") == "Drane Peterson"]
        assert len(diane) == 1, f"expected 1 Diane row, got {len(diane)} (emps={[e.get('name') for e in emps]})"
        assert len(drane) == 0, "Drane row should have been renamed, not stranded"
        assert diane[0]["display_name"] == "Diane Peterson", "display_name not rewritten"
        # _original_name bookkeeping must NOT leak to storage.
        assert "_original_name" not in diane[0], "_original_name should be stripped"
        # POS payload was applied.
        assert diane[0]["ppa"] == 55

        # POS upload's parsed_data should also be renamed.
        pos_emps = snap["uploads"][0]["parsed_data"]["employees"]
        pos_diane = [e for e in pos_emps if e.get("name") == "Diane Peterson"]
        pos_drane = [e for e in pos_emps if e.get("name") == "Drane Peterson"]
        assert len(pos_diane) == 1
        assert len(pos_drane) == 0
    _run(body)


def test_unchanged_name_still_works():
    """A normal POS edit (no rename) must still apply via name match."""
    async def body(db):
        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "quarter": "Q2",
            "year": SENTINEL_YEAR,
            "is_current": True,
            "status": "draft",
            "name": "No-Rename Probe",
            "employees": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Steady Sue", "display_name": "Steady Sue",
                    "ppa": 40, "guest_count": 80,
                    "lsc_count": 1, "total_score": 60,
                },
            ],
            "uploads": [
                {
                    "upload_type": "pos_report",
                    "parsed_data": {"employees": [{"name": "Steady Sue", "ppa": 40, "guest_count": 80}]},
                },
            ],
        })

        await confirm_pos_review(
            snapshot_id=snap_id,
            data={
                "employees": [
                    {
                        "name": "Steady Sue",
                        "_original_name": "Steady Sue",  # unchanged
                        "ppa": 65, "guest_count": 80,
                    },
                ],
            },
        )

        snap = await db.snapshot_workflow.find_one({"id": snap_id}, {"_id": 0})
        emps = [e for e in snap.get("employees", []) if e.get("name") == "Steady Sue"]
        assert len(emps) == 1
        assert emps[0]["ppa"] == 65
    _run(body)


if __name__ == "__main__":
    test_rename_updates_existing_row_in_place()
    test_unchanged_name_still_works()
    print("All POS-review rename tests PASSED")
