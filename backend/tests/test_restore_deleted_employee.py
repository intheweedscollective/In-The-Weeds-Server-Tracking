"""
Regression: operator accidentally hit `delete_legacy` on a real
canonical (Matt Spath, 2026-06-06). The Reconciliation portal's
delete_legacy action only soft-deletes (canonical→terminated,
v2→inactive), but there was no operator-facing way to reverse it
without a code patch or direct mongo access.

These tests pin the new `POST /admin/restore-deleted-employee/{id}`
endpoint:
  1. Restores both the canonical and ALL its v2 rows (any quarter)
     from terminated/inactive back to active.
  2. Leaves rows that are ALREADY active untouched (idempotent).
  3. Writes a `restore_canonical` row to reconciliation_audit so
     the operation is visible to the audit ledger UI.
  4. 404s on unknown canonical id.
"""

import asyncio
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BASE  = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
from conftest import ADMIN_TOKEN
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


@pytest.fixture
def soft_deleted_canonical(loop):
    """Seed a canonical that was soft-deleted via the recon portal:
       - canonical: status=terminated
       - one v2 row (Q2/2026): status=inactive
       - one extra v2 row (Q1/2026): status=inactive   ← multi-quarter sanity
    Yields (canonical_id, [v2_ids])."""
    db = _db()
    cid    = f"restore-test-{uuid.uuid4().hex[:8]}"
    legacy = f"restore-legacy-{uuid.uuid4().hex[:6]}"

    async def _seed():
        await db.employees.insert_one({
            "id": cid,
            "name": f"Restore Test {cid[-6:]}",
            "status": "terminated",
            "aliases": [],
            "legacy_ids": [legacy],
        })
        await db.employees_v2.insert_many([
            {"id": cid, "name": f"Restore Test {cid[-6:]}",
             "name_normalized": f"restore test {cid[-6:]}",
             "quarter": "Q2", "year": 2026,
             "status": "inactive", "total_score": 88.5},
            {"id": legacy, "name": f"Restore Test {cid[-6:]}",
             "name_normalized": f"restore test {cid[-6:]}",
             "quarter": "Q1", "year": 2026,
             "status": "inactive", "total_score": 91.0},
        ])
    loop.run_until_complete(_seed())
    yield cid, [cid, legacy]

    async def _wipe():
        await db.employees.delete_one({"id": cid})
        await db.employees_v2.delete_many({"id": {"$in": [cid, legacy]}})
        await db.reconciliation_audit.delete_many({"employee_id": cid})
    loop.run_until_complete(_wipe())


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_restore_flips_canonical_and_all_v2_rows(loop, soft_deleted_canonical):
    cid, v2_ids = soft_deleted_canonical
    r = requests.post(
        f"{BASE}/api/v2/admin/restore-deleted-employee/{cid}",
        params={"reason": "regression test"},
        headers=ADMIN,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["canonical_status_before"] == "terminated"
    assert body["canonical_status_after"] == "active"
    assert body["v2_rows_reactivated"] == 2

    async def _check():
        db = _db()
        canon = await db.employees.find_one({"id": cid}, {"_id": 0})
        assert canon["status"] == "active"
        assert canon.get("restored_at")
        v2s = await db.employees_v2.find(
            {"id": {"$in": v2_ids}}, {"_id": 0, "id": 1, "status": 1, "quarter": 1},
        ).to_list(10)
        # Both quarters back to active.
        statuses = {r["status"] for r in v2s}
        assert statuses == {"active"}
    loop.run_until_complete(_check())


def test_restore_writes_audit_row(loop, soft_deleted_canonical):
    cid, _ = soft_deleted_canonical
    requests.post(
        f"{BASE}/api/v2/admin/restore-deleted-employee/{cid}",
        headers=ADMIN, timeout=15,
    ).raise_for_status()

    async def _check_audit():
        db = _db()
        rec = await db.reconciliation_audit.find_one(
            {"employee_id": cid, "kind": "restore_canonical"},
            {"_id": 0},
        )
        assert rec is not None
        assert rec["action"] == "restore_canonical"
        assert rec["before"]["canonical_status"] == "terminated"
        assert rec["after"]["v2_rows_reactivated"] == 2
        assert rec["actor"]  # populated from the auth context
    loop.run_until_complete(_check_audit())


def test_restore_is_idempotent(loop, soft_deleted_canonical):
    """Calling restore twice must not touch already-active rows
    (modified_count stays at 0 on the second call) and must still
    return 200."""
    cid, _ = soft_deleted_canonical
    requests.post(
        f"{BASE}/api/v2/admin/restore-deleted-employee/{cid}",
        headers=ADMIN, timeout=15,
    ).raise_for_status()
    r2 = requests.post(
        f"{BASE}/api/v2/admin/restore-deleted-employee/{cid}",
        headers=ADMIN, timeout=15,
    )
    assert r2.status_code == 200
    assert r2.json()["v2_rows_reactivated"] == 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_restore_unknown_canonical_404():
    r = requests.post(
        f"{BASE}/api/v2/admin/restore-deleted-employee/does-not-exist-xxx",
        headers=ADMIN, timeout=15,
    )
    assert r.status_code == 404
    assert "no canonical" in r.text.lower()


def test_restore_requires_admin_auth():
    r = requests.post(
        f"{BASE}/api/v2/admin/restore-deleted-employee/anything",
        headers={"Content-Type": "application/json"},   # no bearer
        timeout=15,
    )
    assert r.status_code in (401, 403)
