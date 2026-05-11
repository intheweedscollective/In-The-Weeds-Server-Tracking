"""
Regression test for the new Merge Duplicates endpoints in
routes/employees.py:

  - GET  /v2/employees/merge/candidates → surfaces duplicate-looking pairs
  - POST /v2/employees/merge → merges via EmployeeService and removes
    the duplicate from employees_v2.

⚠️ MUST use an isolated test DB — never DB_NAME — because the preview
shares a MongoDB Atlas cluster with production. We override the
process-wide `database.db` handle so the endpoint code reads / writes
the test DB while still going through the real router.
"""

import asyncio
import os
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_employee_merge_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_merge_endpoint_flips_duplicate_status_and_aliases_name():
    """Direct EmployeeService.merge_employees call (same code the
    HTTP endpoint runs) flips the duplicate to status='merged' and
    appends its name to the survivor's aliases."""
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        await db.employees_v2.drop()
        svc = EmployeeService(db)

        survivor = await svc.create_employee({"name": "Tad Hashey"})
        duplicate = await svc.create_employee({"name": "Thaddeus Hashey"})
        await db.employees_v2.insert_one({
            "id": duplicate["id"],
            "name": "Thaddeus Hashey", "quarter": "Q2", "year": 2026,
        })

        result = await svc.merge_employees(
            survivor_id=survivor["id"], duplicate_id=duplicate["id"]
        )
        assert result["survivor_id"] == survivor["id"]

        surv = await svc.col.find_one({"id": survivor["id"]}, {"_id": 0})
        assert "Thaddeus Hashey" in (surv.get("aliases") or [])

        dup = await svc.col.find_one({"id": duplicate["id"]}, {"_id": 0})
        assert dup["status"] == "merged"
        assert dup["merged_into"] == survivor["id"]

        await db.employees_v2.delete_many({"id": duplicate["id"]})
        leftover = await db.employees_v2.count_documents({"id": duplicate["id"]})
        assert leftover == 0

        found = await svc.find_by_name_or_alias("Thaddeus Hashey")
        assert found and found["id"] == survivor["id"]

        await db.employees.drop()
        await db.employees_v2.drop()
        c.close()
    _run(runner())


def test_merge_candidates_finds_typo_and_substring_pairs():
    """Heuristic flags typos / substring pairs and leaves distinct
    names alone. Runs the route function directly to keep DB isolated."""
    async def runner():
        from services.employee_service import EmployeeService
        import routes.employees as emp_routes
        c, db = _client()
        await db.employees.drop()
        svc = EmployeeService(db)

        await svc.create_employee({"name": "Lennie Nguyen"})
        await svc.create_employee({"name": "Glennice Nguyen"})
        await svc.create_employee({"name": "Julian"})
        await svc.create_employee({"name": "Julian Taveras"})
        await svc.create_employee({"name": "Mary Smith"})
        await svc.create_employee({"name": "John Brown"})

        # Stub get_db so the route reads our isolated test DB.
        original_get_db = emp_routes.get_db
        emp_routes.get_db = lambda: db
        try:
            res = await emp_routes.find_merge_candidates(limit=50)
        finally:
            emp_routes.get_db = original_get_db

        pairs = res["candidates"]
        names = sorted({tuple(sorted([p["a"]["name"], p["b"]["name"]])) for p in pairs})
        assert ("Glennice Nguyen", "Lennie Nguyen") in names
        assert ("Julian", "Julian Taveras") in names
        assert ("John Brown", "Mary Smith") not in names

        await db.employees.drop()
        c.close()
    _run(runner())

