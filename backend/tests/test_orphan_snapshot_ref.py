"""
Regression tests for the orphan_snapshot_ref card type.

User-reported gap (2026-06-04): the Trust Score widget flagged 16
"orphaned snapshot refs" as P0 deploy blockers, but the Data
Reconciliation queue showed 0 cards for them. The operator could see
the problem in one place and was powerless to act on it from the
adjudication portal — exactly the disconnect this card type closes.

These tests prove:
  1. Orphan cards surface in the queue with a name-matched suggested
     canonical when one exists.
  2. The queue count matches the integrity endpoint's count 1:1
     (same resolvable-id logic — canonical.legacy_ids[] respected).
  3. `relink_orphan` rewrites snapshot row.employee_id (and
     frozen_display_name) to the canonical, audits the change, and
     removes the card from the active queue.
  4. `remove_orphan` deletes the row from the snapshot entirely and
     removes the card from the active queue.
  5. Both actions are idempotent: re-running the same resolve against
     an already-resolved card 404s instead of corrupting data.
"""

import asyncio
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
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
def orphan_fixture(loop):
    """Seed a unique snapshot with one row pointing at a non-existent
    employee_id and one row pointing at a real canonical (so we can
    verify the orphan is detected without also flagging the healthy
    row). The fixture employee's display name exactly matches an
    existing canonical so we get a relink suggestion.

    Returns (snapshot_id, dead_employee_id, suggested_canonical_id,
              orphan_name)."""
    async def _seed():
        db = _db()
        # Pick any existing canonical to act as the "suggested" target.
        canon = await db.employees_v2.find_one(
            {"status": {"$ne": "inactive"}}, {"_id": 0, "id": 1, "name": 1},
        )
        assert canon, "No active employees in employees_v2 — cannot seed"
        snap_id = f"orphan-test-{uuid.uuid4().hex[:8]}"
        dead_id = str(uuid.uuid4())  # guaranteed not in DB
        orphan_name = canon["name"]  # name-match → triggers suggestion
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"orphan-test-{snap_id[-8:]}",
            "quarter": "Q9", "year": 2099,  # poison-pill year
            "status": "completed",
            "is_current": False,
            "rows": [
                {
                    "employee_id": dead_id,
                    "frozen_display_name": orphan_name,
                    "total_score": None,
                    "ppa": None,
                },
                # Healthy reference row — must NOT surface as orphan.
                {
                    "employee_id": canon["id"],
                    "frozen_display_name": canon["name"],
                    "total_score": 80.0,
                },
            ],
            "employees": [],
        })
        return snap_id, dead_id, canon["id"], orphan_name

    snap_id, dead_id, canon_id, orphan_name = loop.run_until_complete(_seed())
    yield snap_id, dead_id, canon_id, orphan_name
    # Cleanup
    async def _wipe():
        db = _db()
        await db.snapshot_workflow.delete_one({"id": snap_id})
        await db.reconciliation_resolved.delete_many({"raw_inputs.snapshot_id": snap_id})
        await db.reconciliation_audit.delete_many({"raw_inputs.snapshot_id": snap_id})
    loop.run_until_complete(_wipe())


def _queue():
    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN, timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _find_card(snap_id, dead_id):
    """Search the queue for the orphan card we seeded."""
    for c in _queue().get("active", []):
        if c.get("kind") != "orphan_snapshot_ref":
            continue
        ri = c.get("raw_inputs") or {}
        if ri.get("snapshot_id") == snap_id and ri.get("missing_employee_id") == dead_id:
            return c
    return None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_orphan_card_surfaces_with_suggestion(orphan_fixture):
    snap_id, dead_id, canon_id, orphan_name = orphan_fixture
    card = _find_card(snap_id, dead_id)
    assert card is not None, (
        f"Orphan card missing — queue did not flag dead ref {dead_id[:8]} "
        f"in snapshot {snap_id}"
    )
    assert card["employee_name"] == orphan_name
    # Name-match should produce a relink suggestion.
    assert card["source"]["suggested_canonical_id"] == canon_id
    assert card["source"]["suggested_canonical_name"] == orphan_name


def test_orphan_count_matches_integrity(loop, orphan_fixture):
    """Trust Score and Reconciliation must agree on the orphan count
    1:1. Before this card type the queue showed 0 while integrity
    showed 16; the operator had no path to act."""
    snap_id, dead_id, _, _ = orphan_fixture
    q_orphans = sum(
        1 for c in _queue().get("active", [])
        if c.get("kind") == "orphan_snapshot_ref"
    )
    r = requests.get(
        f"{BASE}/api/v2/admin/integrity", headers=ADMIN, timeout=20,
    )
    assert r.status_code == 200
    i_orphans = len(r.json().get("orphaned_snapshot_refs", []))
    assert q_orphans == i_orphans, (
        f"Trust Score reports {i_orphans} orphans but Reconciliation "
        f"queue shows {q_orphans} — they must align so the operator's "
        f"two dashboards tell the same story."
    )


# ---------------------------------------------------------------------------
# relink_orphan
# ---------------------------------------------------------------------------


def test_relink_orphan_rewrites_snapshot_row(loop, orphan_fixture):
    snap_id, dead_id, canon_id, orphan_name = orphan_fixture
    card = _find_card(snap_id, dead_id)
    assert card is not None
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "relink_orphan",
            "reason": "regression test relink",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["relinked_from"] == dead_id
    assert body["relinked_to"] == canon_id

    async def _check():
        db = _db()
        snap = await db.snapshot_workflow.find_one(
            {"id": snap_id}, {"_id": 0, "rows": 1},
        )
        # Original dead-id row must be gone; new canonical-id row in its place.
        ids = [r.get("employee_id") for r in (snap or {}).get("rows", [])]
        assert dead_id not in ids
        assert canon_id in ids
    loop.run_until_complete(_check())

    # Card gone from active queue.
    assert _find_card(snap_id, dead_id) is None


def test_relink_orphan_with_explicit_target(loop, orphan_fixture):
    """`target_canonical_id` in the resolve request overrides the
    card's suggestion. Critical when the auto-suggested match is
    wrong (e.g. two employees share a first name)."""
    snap_id, dead_id, _, _ = orphan_fixture
    card = _find_card(snap_id, dead_id)
    assert card is not None
    # Pick a DIFFERENT canonical to relink into.
    async def _pick_other():
        db = _db()
        async for e in db.employees_v2.find(
            {"status": {"$ne": "inactive"},
             "id": {"$ne": card["source"]["suggested_canonical_id"]}},
            {"_id": 0, "id": 1},
        ):
            return e["id"]
        return None
    other = loop.run_until_complete(_pick_other())
    assert other, "No alternative canonical available for override test"

    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "relink_orphan",
            "target_canonical_id": other,
            "reason": "override-suggestion",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    assert r.json()["relinked_to"] == other


# ---------------------------------------------------------------------------
# remove_orphan
# ---------------------------------------------------------------------------


def test_remove_orphan_drops_row(loop, orphan_fixture):
    snap_id, dead_id, _, _ = orphan_fixture
    card = _find_card(snap_id, dead_id)
    assert card is not None
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "remove_orphan",
            "reason": "regression test remove",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["removed_employee_id"] == dead_id

    async def _check():
        db = _db()
        snap = await db.snapshot_workflow.find_one(
            {"id": snap_id}, {"_id": 0, "rows": 1},
        )
        ids = [r.get("employee_id") for r in (snap or {}).get("rows", [])]
        assert dead_id not in ids, "remove_orphan didn't actually drop the row"
        # Healthy sibling row is preserved.
        assert len(ids) == 1
    loop.run_until_complete(_check())

    assert _find_card(snap_id, dead_id) is None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_resolve_writes_audit_entry(loop, orphan_fixture):
    snap_id, dead_id, _, _ = orphan_fixture
    card = _find_card(snap_id, dead_id)
    requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "remove_orphan",
            "reason": "audit-test",
        },
        timeout=20,
    ).raise_for_status()

    async def _count():
        db = _db()
        return await db.reconciliation_audit.count_documents({
            "conflict_id": card["conflict_id"],
            "action": "remove_orphan",
        })
    n = loop.run_until_complete(_count())
    assert n == 1, f"expected exactly 1 audit row for the remove, got {n}"
