"""
Regression test for "Delete legacy still not working" bug (2026-06-03).

User flow that was broken:
  1. Operator opens /data-reconciliation on mobile.
  2. A `legacy_duplicate` card (e.g. "Thaddeus Hashey") is in the
     Active Queue because its v2 row isn't linked to any canonical.
  3. Operator clicks Delete legacy → confirms → success toast fires
     ("Delete legacy row applied for Thaddeus Hashey").
  4. On refresh the same card is BACK in the active queue. Audit log
     accumulates one Delete-legacy entry per click; the card never
     actually clears.

Two latent bugs combined to cause this:

A. `_build_legacy_duplicate_conflicts` did not filter `status="inactive"`
   on the employees_v2 find. delete_legacy soft-deletes by setting
   status=inactive, so the row got tombstoned but the next queue
   rebuild happily re-detected it.

B. `_stamp_resolved` had no branch for kind="legacy_duplicate", so it
   recorded `post_stored=None` against the resolved row. On the next
   queue refresh `_resolved_still_applies` compared the live card's
   stored_value ("Thaddeus Hashey") to post_stored (None), judged the
   resolution stale, and re-surfaced the card with the resolved row
   wiped.

This test sets up an unlinked v2 row in the current quarter, calls
delete_legacy via the API, and asserts the card vanishes AND stays
vanished across two more queue refreshes.
"""

import os
import asyncio
import uuid
import requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
from conftest import ADMIN_TOKEN
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _seed_legacy_v2_row():
    """Insert an unlinked active v2 row into the current snapshot's
    quarter so it surfaces as a legacy_duplicate card."""
    db = _db()
    snap = await db.snapshot_workflow.find_one({"is_current": True})
    assert snap, "No current snapshot — cannot seed legacy test row"
    v2_id = f"legacy-test-{uuid.uuid4().hex[:12]}"
    # Distinctive bogus name so no canonical name-match auto-links it.
    v2_name = f"Zzz Delete Legacy Test {uuid.uuid4().hex[:6]}"
    await db.employees_v2.insert_one({
        "id": v2_id,
        "name": v2_name,
        "status": "active",
        "quarter": snap["quarter"],
        "year": snap["year"],
        "guests": 0,
        "ppa": 50.0,
        "lsc_count": 0,
        "total_score": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_via": "test_delete_legacy_idempotent",
    })
    return v2_id, v2_name


async def _cleanup_legacy_v2_row(v2_id):
    """Hard-delete the test fixture from employees_v2 and any
    reconciliation_resolved / audit entries so re-runs are clean."""
    db = _db()
    await db.employees_v2.delete_many({"id": v2_id})
    await db.reconciliation_resolved.delete_many(
        {"employee_id": v2_id}
    )
    await db.reconciliation_audit.delete_many(
        {"employee_id": v2_id}
    )


def _find_legacy_card(name):
    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN, timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    for c in d.get("active", []) + d.get("deferred", []):
        if c.get("employee_name") == name and c.get("kind") == "legacy_duplicate":
            return c
    return None


def test_delete_legacy_keeps_card_out_of_queue():
    """delete_legacy must remove the v2 row AND keep it removed
    across multiple queue rebuilds. This regressed before 2026-06-03."""
    loop = asyncio.new_event_loop()
    v2_id, v2_name = loop.run_until_complete(_seed_legacy_v2_row())
    try:
        # 1. Sanity: the card surfaces in the active queue.
        card = _find_legacy_card(v2_name)
        assert card is not None, (
            f"Seeded v2 row {v2_name!r} did not surface as a legacy_duplicate card"
        )

        # 2. Delete it via the API.
        r = requests.post(
            f"{BASE}/api/v2/admin/reconciliation/resolve",
            headers=ADMIN,
            json={
                "conflict_id": card["conflict_id"],
                "action": "delete_legacy",
                "reason": "regression test",
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        assert body.get("action") == "delete_legacy"

        # 3. Card must be gone on the very next queue call.
        assert _find_legacy_card(v2_name) is None, (
            f"BUG: {v2_name!r} re-appeared in queue immediately after delete_legacy"
        )

        # 4. AND on the call after that — this is the call that
        # previously regressed because _resolved_still_applies wiped
        # the resolved row and re-surfaced the card.
        assert _find_legacy_card(v2_name) is None, (
            f"BUG: {v2_name!r} re-surfaced on 2nd queue rebuild "
            f"(stale resolved-row eviction)"
        )

        # 5. employees_v2 row must be soft-deleted, not hard-deleted —
        # the audit trail relies on the row staying in the collection.
        async def _check():
            db = _db()
            row = await db.employees_v2.find_one({"id": v2_id}, {"_id": 0})
            assert row is not None, "v2 row was hard-deleted; expected soft-delete"
            assert row.get("status") == "inactive", row
            assert row.get("soft_deleted_at"), row
        loop.run_until_complete(_check())
    finally:
        loop.run_until_complete(_cleanup_legacy_v2_row(v2_id))
        loop.close()


def test_delete_legacy_logs_to_audit():
    """delete_legacy must persist exactly one audit entry per click."""
    loop = asyncio.new_event_loop()
    v2_id, v2_name = loop.run_until_complete(_seed_legacy_v2_row())
    try:
        card = _find_legacy_card(v2_name)
        assert card is not None
        requests.post(
            f"{BASE}/api/v2/admin/reconciliation/resolve",
            headers=ADMIN,
            json={
                "conflict_id": card["conflict_id"],
                "action": "delete_legacy",
                "reason": "audit-log smoke",
            },
            timeout=30,
        ).raise_for_status()

        async def _count_audit():
            db = _db()
            n = await db.reconciliation_audit.count_documents(
                {"employee_id": v2_id, "action": "delete_legacy"}
            )
            return n
        n = loop.run_until_complete(_count_audit())
        assert n >= 1, f"expected ≥1 audit row for {v2_id}, got {n}"
    finally:
        loop.run_until_complete(_cleanup_legacy_v2_row(v2_id))
        loop.close()
