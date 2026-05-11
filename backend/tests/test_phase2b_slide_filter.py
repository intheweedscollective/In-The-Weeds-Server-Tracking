"""
Phase 2B regression: EmployeeService.filter_active_only is what every
slide generator now calls before rendering. It MUST:
  - drop terminated/merged canonical employees from the output,
  - drop rows whose name is in the snapshot's deleted_names blocklist,
  - stamp canonical_id on surviving rows,
  - overlay the canonical display_name on the row's `name`/`display_name`.
"""

import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_phase2b_slide_filter_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_filter_active_only_drops_terminated_and_overlays_display_name():
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        svc = EmployeeService(db)

        # Seed three canonical: one active, one terminated, one with alias.
        await svc.create_employee({"name": "Alice Active", "display_name": "Alice"})
        bob = await svc.create_employee({"name": "Bob Terminated"})
        await svc.terminate(bob["id"])
        carol = await svc.create_employee({"name": "Carol Smith", "display_name": "Carol"})
        await svc.col.update_one(
            {"id": carol["id"]},
            {"$addToSet": {"aliases": "C. Smith"}},
        )

        # A "legacy" employees_v2-shaped list with all three plus a ghost.
        v2_rows = [
            {"id": "legacy-a", "name": "Alice Active"},
            {"id": bob["id"], "name": "Bob Terminated"},
            {"id": "legacy-c", "name": "C. Smith"},  # alias match
            {"id": "ghost", "name": "DeletedDan"},
        ]
        filtered = await svc.filter_active_only(
            v2_rows,
            snapshot_deleted_names=["DeletedDan"],
        )
        names = {r["name"] for r in filtered}

        # Bob (terminated) and Dan (blocklist) are gone.
        assert "Bob Terminated" not in names
        assert "DeletedDan" not in names

        # Alice + Carol survive.
        assert "Alice" in names  # canonical display_name overlay
        assert "Carol" in names  # alias-matched canonical display_name overlay

        # Each surviving row carries canonical_id.
        for r in filtered:
            assert r.get("canonical_id"), f"row {r!r} missing canonical_id"

        # Carol's row should now point at her canonical id, not the legacy one.
        carol_row = next(r for r in filtered if r["name"] == "Carol")
        assert carol_row["canonical_id"] == carol["id"]

        await db.employees.drop()
        c.close()
    _run(runner())


def test_filter_active_only_keeps_rows_without_canonical_match():
    """A POS-only row with no canonical match must NOT be dropped — it
    just won't have canonical_id stamped. (Phase 2 keeps legacy reads
    working until Phase 3 migrates the schema.)"""
    async def runner():
        from services.employee_service import EmployeeService
        c, db = _client()
        await db.employees.drop()
        svc = EmployeeService(db)

        v2_rows = [
            {"id": "orphan", "name": "Never Heard Of"},
        ]
        filtered = await svc.filter_active_only(v2_rows)
        assert len(filtered) == 1
        # No canonical match → no canonical_id field.
        assert "canonical_id" not in filtered[0]
        # Name is preserved verbatim.
        assert filtered[0]["name"] == "Never Heard Of"

        c.close()
    _run(runner())
