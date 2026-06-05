"""
Regression tests for the `alias_cross_assignment` reconciliation
card type.

User-reported scenario: an alias like "Kahi" (legitimately the
nickname for Kahiaulani) is accidentally added to another canonical
employee's aliases[] too. POS uploads under that spelling then route
non-deterministically. The portal must surface this and let the
operator revoke the alias from the wrong owner one canonical at a
time — without losing it from the legitimate owner.
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
TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"
ADMIN = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


@pytest.fixture
def cross_alias_fixture(loop):
    """Seed two canonical employees both carrying the same alias
    'Kahi'. The "legitimate" owner is the Kahiaulani record; the
    "wrong" owner is a fake employee that mistakenly absorbed the
    alias. Yields (good_id, bad_id, shared_alias)."""
    alias = f"Kahi-{uuid.uuid4().hex[:6]}"   # unique per run to avoid
                                             # collisions with seeded data
    good_id = f"cross-good-{uuid.uuid4().hex[:8]}"
    bad_id  = f"cross-bad-{uuid.uuid4().hex[:8]}"

    async def _seed():
        db = _db()
        await db.employees.insert_many([
            {
                "id": good_id,
                "name": f"Kahiaulani Ramos {good_id[-6:]}",
                "status": "active",
                "aliases": [alias],
                "legacy_ids": [],
            },
            {
                "id": bad_id,
                "name": f"Wrong Owner {bad_id[-6:]}",
                "status": "active",
                "aliases": [alias],
                "legacy_ids": [],
            },
        ])
    loop.run_until_complete(_seed())
    yield good_id, bad_id, alias

    async def _wipe():
        db = _db()
        await db.employees.delete_many({"id": {"$in": [good_id, bad_id]}})
        await db.reconciliation_resolved.delete_many(
            {"raw_inputs.alias_normalised": alias.lower()}
        )
        await db.reconciliation_audit.delete_many(
            {"employee_id": {"$in": [good_id, bad_id]}}
        )
    loop.run_until_complete(_wipe())


def _queue():
    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN, timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _find_cross_card(alias):
    norm = alias.strip().lower()
    for c in _queue().get("active", []):
        if c.get("kind") != "alias_cross_assignment":
            continue
        if (c.get("raw_inputs") or {}).get("alias_normalised") == norm:
            return c
    return None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_cross_card_surfaces_with_both_claimants(cross_alias_fixture):
    good_id, bad_id, alias = cross_alias_fixture
    card = _find_cross_card(alias)
    assert card is not None, (
        f"alias_cross_assignment card missing for '{alias}' — queue "
        f"is not detecting the cross-claim"
    )
    claimant_ids = {c["canonical_id"]
                    for c in card["raw_inputs"]["claimants"]}
    assert good_id in claimant_ids
    assert bad_id in claimant_ids
    assert card["stored_value"] == alias
    assert card["raw_inputs"]["claim_hash"]


# ---------------------------------------------------------------------------
# revoke_alias_from
# ---------------------------------------------------------------------------


def test_revoke_alias_from_wrong_owner_only(loop, cross_alias_fixture):
    """Strip the alias from the wrong canonical; the legitimate
    owner keeps it. After resolution the queue no longer flags the
    cross-assignment because only one claimant remains."""
    good_id, bad_id, alias = cross_alias_fixture
    card = _find_cross_card(alias)
    assert card

    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "revoke_alias_from",
            "target_canonical_id": bad_id,
            "reason": "Kahi belongs to Kahiaulani only",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["revoked_from_id"] == bad_id

    async def _check():
        db = _db()
        good = await db.employees.find_one({"id": good_id}, {"_id": 0, "aliases": 1})
        bad  = await db.employees.find_one({"id": bad_id},  {"_id": 0, "aliases": 1})
        # Legitimate owner still has it; wrong owner does not.
        assert alias in (good.get("aliases") or [])
        assert alias not in (bad.get("aliases") or [])
    loop.run_until_complete(_check())

    # Card is gone — only one claimant left.
    assert _find_cross_card(alias) is None


def test_revoke_requires_target(loop, cross_alias_fixture):
    _, _, alias = cross_alias_fixture
    card = _find_cross_card(alias)
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "revoke_alias_from"},
        timeout=20,
    )
    assert r.status_code == 400
    assert "target_canonical_id" in r.text


def test_revoke_rejects_non_claimant_target(loop, cross_alias_fixture):
    """The target must be one of the listed claimants — passing some
    other canonical id must 400 rather than silently mutate."""
    _, _, alias = cross_alias_fixture
    card = _find_cross_card(alias)
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "revoke_alias_from",
            "target_canonical_id": "not-in-claimant-set",
        },
        timeout=20,
    )
    assert r.status_code == 400
    assert "claimant" in r.text.lower()


# ---------------------------------------------------------------------------
# keep_stored silence + claimant-hash resurface
# ---------------------------------------------------------------------------


def test_keep_stored_silences_until_new_claimant(loop, cross_alias_fixture):
    good_id, bad_id, alias = cross_alias_fixture
    card = _find_cross_card(alias)
    assert card

    # Silence.
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "keep_stored",
              "reason": "operator says all claimants are valid"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    assert _find_cross_card(alias) is None

    # Add a third claimant → claim_hash changes → card re-surfaces.
    new_id = f"cross-extra-{uuid.uuid4().hex[:8]}"
    async def _add():
        db = _db()
        await db.employees.insert_one({
            "id": new_id,
            "name": f"Late Joiner {new_id[-6:]}",
            "status": "active",
            "aliases": [alias],
            "legacy_ids": [],
        })
    loop.run_until_complete(_add())
    try:
        resurfaced = _find_cross_card(alias)
        assert resurfaced is not None, (
            "card did not re-surface after a new canonical claimed "
            "the alias — claim-hash check is broken"
        )
        ids = {c["canonical_id"] for c in resurfaced["raw_inputs"]["claimants"]}
        assert new_id in ids
    finally:
        async def _wipe():
            await _db().employees.delete_one({"id": new_id})
        loop.run_until_complete(_wipe())
