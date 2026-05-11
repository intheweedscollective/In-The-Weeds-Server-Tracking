"""Unit tests for the canonical EmployeeService (Phase 1).

Uses an isolated test DB (`_employee_service_test_db`) on the same Mongo
cluster so we never touch production data. Each test re-drops the
collections before running so order doesn't matter.
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_employee_service_test_db"


def _new_service():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[TEST_DB]
    from services.employee_service import EmployeeService
    return EmployeeService(db), client


async def _reset(svc):
    await svc.col.drop()
    await svc.snap_col.drop()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_create_employee_assigns_id_and_defaults():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        emp = await svc.create_employee({"name": "Alice Adams"})
        assert emp["id"]
        assert emp["name"] == "Alice Adams"
        assert emp["display_name"] == "Alice"
        assert emp["status"] == "active"
        await _reset(svc); client.close()
    _run(runner())


def test_create_is_idempotent_on_name():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        a1 = await svc.create_employee({"name": "Bob Smith"})
        a2 = await svc.create_employee({"name": "Bob Smith"})
        assert a1["id"] == a2["id"]
        assert await svc.col.count_documents({}) == 1
        await _reset(svc); client.close()
    _run(runner())


def test_rename_keeps_id_and_records_old_name_as_alias():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        emp = await svc.create_employee({"name": "Bobby Brown"})
        renamed = await svc.rename(emp["id"], name="Robert Brown", display_name="Robert")
        assert renamed["id"] == emp["id"]
        assert renamed["name"] == "Robert Brown"
        assert "Bobby Brown" in renamed["aliases"]
        old_lookup = await svc.find_by_name_or_alias("Bobby Brown", include_inactive=True)
        assert old_lookup and old_lookup["id"] == emp["id"]
        await _reset(svc); client.close()
    _run(runner())


def test_terminate_excludes_from_active_list_and_recreate_reactivates():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        e = await svc.create_employee({"name": "Carla Castro"})
        await svc.terminate(e["id"])
        active = await svc.list_active()
        assert all(a["id"] != e["id"] for a in active)
        again = await svc.create_employee({"name": "Carla Castro"})
        assert again["id"] == e["id"]
        assert again["status"] == "active"
        await _reset(svc); client.close()
    _run(runner())


def test_merge_marks_duplicate_and_extends_aliases():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        survivor = await svc.create_employee({"name": "Tad Hashey"})
        duplicate_doc = {
            "id": "dup-1",
            "name": "Thaddeus Hashey",
            "display_name": "Thaddeus",
            "status": "active",
            "aliases": [],
            "current_metrics": {},
        }
        await svc.col.insert_one(duplicate_doc)
        await svc.merge_employees(survivor_id=survivor["id"], duplicate_id="dup-1")
        s = await svc.get_by_id(survivor["id"])
        d = await svc.get_by_id("dup-1")
        assert "Thaddeus Hashey" in s["aliases"]
        assert d["status"] == "merged"
        assert d["merged_into"] == survivor["id"]
        await _reset(svc); client.close()
    _run(runner())


def test_snapshot_rankings_join_uses_frozen_display():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        emp = await svc.create_employee({"name": "Polly Blocker"})
        await svc.snap_col.insert_one({
            "id": "snap-1",
            "rows": [{
                "employee_id": emp["id"],
                "frozen_display_name": "Polly",
                "frozen_metrics": {"ppa": 55.0, "cv_score": 12.0},
                "frozen_score": 92.5,
                "frozen_tier": "B+",
                "frozen_rank": 4,
            }],
        })
        await svc.rename(emp["id"], display_name="Pauline")
        ranked = await svc.get_snapshot_rankings("snap-1")
        assert len(ranked) == 1
        # Frozen wins on display, canonical wins on identity.
        assert ranked[0]["display_name"] == "Polly"
        assert ranked[0]["total_score"] == 92.5
        assert ranked[0]["id"] == emp["id"]
        await _reset(svc); client.close()
    _run(runner())


def test_snapshot_rankings_legacy_fallback_returns_embedded():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        await svc.snap_col.insert_one({
            "id": "legacy-1",
            "rows": [],
            "employees": [{"id": "legacy-id", "name": "Eddie Garcia", "total_score": 88.0}],
        })
        ranked = await svc.get_snapshot_rankings("legacy-1")
        assert ranked == [{"id": "legacy-id", "name": "Eddie Garcia", "total_score": 88.0}]
        await _reset(svc); client.close()
    _run(runner())


def test_write_snapshot_rows_freezes_metrics():
    async def runner():
        svc, client = _new_service()
        await _reset(svc)
        a = await svc.create_employee({"name": "Alice"})
        b = await svc.create_employee({"name": "Bob"})
        await svc.snap_col.insert_one({"id": "snap-X"})
        n = await svc.write_snapshot_rows("snap-X", [
            {"id": a["id"], "name": "Alice", "display_name": "Alice",
             "ppa": 55.0, "cv_score": 12.0, "total_score": 95.0,
             "performance_tier": "A"},
            {"id": b["id"], "name": "Bob", "display_name": "Bob",
             "ppa": 50.0, "cv_score": 10.0, "total_score": 88.0,
             "performance_tier": "B"},
        ])
        assert n == 2
        snap = await svc.snap_col.find_one({"id": "snap-X"}, {"_id": 0})
        assert snap["row_count"] == 2
        assert snap["rows"][0]["frozen_score"] == 95.0
        assert snap["rows"][0]["frozen_metrics"]["ppa"] == 55.0
        # Identity bookkeeping fields should NOT leak into frozen_metrics.
        assert "id" not in snap["rows"][0]["frozen_metrics"]
        assert "display_name" not in snap["rows"][0]["frozen_metrics"]
        await _reset(svc); client.close()
    _run(runner())
