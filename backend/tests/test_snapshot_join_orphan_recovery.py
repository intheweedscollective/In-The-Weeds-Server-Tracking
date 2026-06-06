"""
Regression: `EmployeeService.get_snapshot_with_join` was silently
dropping snapshot rows whose `employee_id` didn't resolve to a
canonical employee (or any canonical's `legacy_ids[]`).

Operator reported (production, 2026-02-05): saving snapshot Q2P6W1
caused the dashboard to show 19 of 33 employees. The other 14 were
un-promoted v2 staff (Cory West, Kitti Xavier, Tarek Araman, etc.)
— their POS data was in the snapshot's thin rows but the FK-join
hit `continue` instead of rendering them.

These tests pin the recovery: a thin row with an unmatched
employee_id must still surface, using its own `frozen_display_name`
+ `frozen_metrics`. Terminated/merged canonical filtering must
still work when canonical IS available.
"""

import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from services.employee_service import EmployeeService

load_dotenv("/app/backend/.env")


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


@pytest.fixture
def mixed_snapshot(loop):
    """Build a snapshot whose thin rows include:
      * one row that DOES join to an active canonical
      * one row whose employee_id is NOT in canonical (orphan/un-promoted)
      * one row whose canonical is `terminated` (must be filtered)
      * one row in `deleted_names` (must be filtered)
    """
    db = _db()
    snap_id = f"join-test-{uuid.uuid4().hex[:8]}"
    canon_active   = f"canon-active-{uuid.uuid4().hex[:6]}"
    canon_term     = f"canon-term-{uuid.uuid4().hex[:6]}"
    orphan_v2_id   = str(uuid.uuid4())
    deleted_name   = "Removed Person"

    async def _seed():
        await db.employees.insert_many([
            {"id": canon_active, "name": "Alice Active",
             "display_name": "Alice Active", "status": "active",
             "legacy_ids": [], "aliases": []},
            {"id": canon_term, "name": "Tina Terminated",
             "display_name": "Tina Terminated", "status": "terminated",
             "legacy_ids": [], "aliases": []},
        ])
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"join-test-{snap_id[-8:]}",
            "quarter": "Q9", "year": 2099,
            "status": "completed",
            "is_current": False,
            "deleted_names": [deleted_name],
            "rows": [
                {"employee_id": canon_active,
                 "frozen_display_name": "Alice Active",
                 "frozen_score": 95.5,
                 "frozen_metrics": {"ppa": 30.0, "guests": 500}},
                {"employee_id": orphan_v2_id,
                 "frozen_display_name": "Cory West",
                 "frozen_score": 100.4,
                 "frozen_metrics": {"ppa": 28.5, "guests": 600}},
                {"employee_id": canon_term,
                 "frozen_display_name": "Tina Terminated",
                 "frozen_score": 70.0,
                 "frozen_metrics": {}},
                {"employee_id": str(uuid.uuid4()),
                 "frozen_display_name": deleted_name,
                 "frozen_score": 50.0,
                 "frozen_metrics": {}},
            ],
            "employees": [],
        })
    loop.run_until_complete(_seed())
    yield snap_id, canon_active, canon_term, orphan_v2_id

    async def _wipe():
        await db.snapshot_workflow.delete_one({"id": snap_id})
        await db.employees.delete_many({"id": {"$in": [canon_active, canon_term]}})
    loop.run_until_complete(_wipe())


def test_orphan_row_renders_with_frozen_data(loop, mixed_snapshot):
    """The row whose employee_id doesn't resolve to a canonical must
    still surface on the dashboard, populated from its own frozen
    data — not silently dropped."""
    snap_id, _, _, orphan_v2_id = mixed_snapshot
    res = loop.run_until_complete(
        EmployeeService(_db()).get_snapshot_with_join(snapshot_id=snap_id)
    )
    names = {e.get("name") for e in (res["employees"] or [])}
    assert "Cory West" in names, (
        f"orphan row was silently dropped — names returned: {names}"
    )
    cory = next(e for e in res["employees"] if e.get("name") == "Cory West")
    assert cory["canonical_id"] is None
    assert cory["id"] == orphan_v2_id          # falls back to v2 id
    assert cory["total_score"] == 100.4         # frozen_score preserved
    assert cory["ppa"] == 28.5                  # frozen_metrics preserved


def test_terminated_canonical_still_filtered(loop, mixed_snapshot):
    """Rows whose canonical is terminated/merged must still be filtered
    out — the recovery for orphans must not regress the termination
    filter."""
    snap_id, _, _, _ = mixed_snapshot
    res = loop.run_until_complete(
        EmployeeService(_db()).get_snapshot_with_join(snapshot_id=snap_id)
    )
    names = {e.get("name") for e in (res["employees"] or [])}
    assert "Tina Terminated" not in names


def test_deleted_name_still_filtered(loop, mixed_snapshot):
    """`deleted_names` on the snapshot must still suppress the row
    regardless of canonical status."""
    snap_id, _, _, _ = mixed_snapshot
    res = loop.run_until_complete(
        EmployeeService(_db()).get_snapshot_with_join(snapshot_id=snap_id)
    )
    names = {e.get("name") for e in (res["employees"] or [])}
    assert "Removed Person" not in names


def test_active_canonical_row_still_resolves(loop, mixed_snapshot):
    """The healthy path must still return canonical-linked rows with
    canonical_id stamped."""
    snap_id, canon_active, _, _ = mixed_snapshot
    res = loop.run_until_complete(
        EmployeeService(_db()).get_snapshot_with_join(snapshot_id=snap_id)
    )
    alice = next(e for e in res["employees"] if e.get("name") == "Alice Active")
    assert alice["canonical_id"] == canon_active
    assert alice["id"] == canon_active
