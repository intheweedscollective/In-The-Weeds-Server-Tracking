"""
Regression tests for the `canonical_metrics_drift` reconciliation
card type.

User-reported gap (Message 759): the canonical mirror
`employees.current_metrics` was drifting from `employees_v2` (the
source of truth) for the active quarter. The drift produced wrong
dashboard numbers and corrupt trend percentages on slides, but the
Reconciliation portal had no card type to surface it.

These tests prove:
  1. A canonical row whose scoring metrics differ from its v2 row
     (active quarter) surfaces as a `canonical_metrics_drift` card
     with the drifted fields enumerated in raw_inputs.
  2. `guests` uses the absolute threshold (METRICS_DRIFT_GUEST_ABS=10),
     not the 2% relative threshold — small guest deltas don't flag.
  3. `sync_canonical_from_v2` $sets only the scoring fields and leaves
     CV / NPS / RT untouched.
  4. `keep_canonical_drift` does not write metrics — it just silences
     the card by stamping the canonical hash, and resurfaces only
     when the canonical hash changes.
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
def drift_fixture(loop):
    """Seed one canonical employee + a matching v2 row for the ACTIVE
    quarter whose scoring fields disagree by ≥2% so the drift card
    surfaces. CV / NPS / RT are populated only on the canonical so
    we can assert sync_canonical_from_v2 doesn't touch them.

    Yields (canonical_id, v2_id, active_quarter, active_year)."""
    async def _seed():
        db = _db()
        snap = await db.snapshot_workflow.find_one(
            {"is_current": True},
            {"_id": 0, "quarter": 1, "year": 1},
        )
        assert snap, "no active snapshot — cannot seed drift fixture"
        q, y = snap["quarter"], snap["year"]
        cid = f"drift-test-{uuid.uuid4().hex[:8]}"
        # Canonical has drifted scoring metrics PLUS CV/NPS/RT that
        # must stay intact after sync.
        await db.employees.insert_one({
            "id": cid,
            "name": f"Drift Test {cid[-6:]}",
            "status": "active",
            "aliases": [],
            "legacy_ids": [],
            "current_metrics": {
                "guests": 1000,          # v2 says 1500 → 50% over guest abs
                "total_score": 80.0,     # v2 says 90.0
                "ppa": 26.0,             # v2 says 28.0
                "lbw": 4000.0,           # v2 says 5000.0
                "glassware_sales": 800,  # v2 says 1100
                "lsc_count": 50,         # v2 says 70
                # Non-scoring keys that must stay untouched.
                "cv": 4.7,
                "nps": 88,
                "rt": 0.92,
            },
        })
        await db.employees_v2.insert_one({
            "id": cid,
            "name": f"Drift Test {cid[-6:]}",
            "name_normalized": f"drift test {cid[-6:]}",
            "quarter": q,
            "year": y,
            "status": "active",
            "guests": 1500,
            "total_score": 90.0,
            "ppa": 28.0,
            "lbw": 5000.0,
            "glassware_sales": 1100,
            "lsc_count": 70,
        })
        return cid, q, y

    cid, q, y = loop.run_until_complete(_seed())
    yield cid, q, y

    async def _wipe():
        db = _db()
        await db.employees.delete_one({"id": cid})
        await db.employees_v2.delete_many({"id": cid})
        await db.reconciliation_resolved.delete_many({"employee_id": cid})
        await db.reconciliation_audit.delete_many({"employee_id": cid})
        await db.reconciliation_deferred.delete_many({})
    loop.run_until_complete(_wipe())


def _queue():
    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN, timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _find_drift_card(cid):
    for c in _queue().get("active", []):
        if (c.get("kind") == "canonical_metrics_drift"
                and c.get("employee_id") == cid):
            return c
    return None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_drift_card_surfaces_with_field_breakdown(drift_fixture):
    cid, q, y = drift_fixture
    card = _find_drift_card(cid)
    assert card is not None, "canonical_metrics_drift card missing from queue"
    drifted = {d["field"] for d in card["raw_inputs"]["drifted_fields"]}
    # All six scoring fields drifted in the fixture.
    assert {"guests", "total_score", "ppa", "lbw",
            "glassware_sales", "lsc_count"}.issubset(drifted)
    assert card["raw_inputs"]["quarter"] == q
    assert card["raw_inputs"]["year"] == y
    # Card carries the canonical hash so silence can be hashed.
    assert card["raw_inputs"]["canonical_hash"]


def test_drift_card_respects_guest_abs_threshold(loop):
    """A canonical that differs from v2 by <10 guests must NOT flag
    even though all other relative checks would pass."""
    db = _db()
    cid = f"drift-guest-{uuid.uuid4().hex[:8]}"

    async def _seed():
        snap = await db.snapshot_workflow.find_one(
            {"is_current": True},
            {"_id": 0, "quarter": 1, "year": 1},
        )
        q, y = snap["quarter"], snap["year"]
        await db.employees.insert_one({
            "id": cid,
            "name": f"Tiny Drift {cid[-6:]}",
            "status": "active",
            "current_metrics": {
                "guests": 1000,
                # Other fields identical so only `guests` could flag.
                "total_score": 90.0,
                "ppa": 28.0,
                "lbw": 5000.0,
                "glassware_sales": 1100,
                "lsc_count": 70,
            },
        })
        await db.employees_v2.insert_one({
            "id": cid, "name": f"Tiny Drift {cid[-6:]}",
            "name_normalized": f"tiny drift {cid[-6:]}",
            "quarter": q, "year": y, "status": "active",
            "guests": 1005,         # diff = 5 → below 10 threshold
            "total_score": 90.0, "ppa": 28.0, "lbw": 5000.0,
            "glassware_sales": 1100, "lsc_count": 70,
        })
    loop.run_until_complete(_seed())
    try:
        card = _find_drift_card(cid)
        assert card is None, (
            "drift card surfaced despite guest diff <10 — abs threshold "
            "not being enforced"
        )
    finally:
        async def _wipe():
            await db.employees.delete_one({"id": cid})
            await db.employees_v2.delete_many({"id": cid})
        loop.run_until_complete(_wipe())


# ---------------------------------------------------------------------------
# sync_canonical_from_v2
# ---------------------------------------------------------------------------


def test_sync_overwrites_only_scoring_fields(loop, drift_fixture):
    cid, _, _ = drift_fixture
    card = _find_drift_card(cid)
    assert card

    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "sync_canonical_from_v2",
            "reason": "regression test sync",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert set(body["fields_synced"]) == {
        "guests", "total_score", "ppa", "lbw",
        "glassware_sales", "lsc_count",
    }

    async def _check():
        db = _db()
        emp = await db.employees.find_one({"id": cid}, {"_id": 0, "current_metrics": 1})
        cm = emp["current_metrics"]
        # Scoring fields now match v2.
        assert cm["guests"] == 1500
        assert cm["total_score"] == 90.0
        assert cm["ppa"] == 28.0
        assert cm["lbw"] == 5000.0
        assert cm["glassware_sales"] == 1100
        assert cm["lsc_count"] == 70
        # CV / NPS / RT untouched.
        assert cm["cv"] == 4.7
        assert cm["nps"] == 88
        assert cm["rt"] == 0.92
    loop.run_until_complete(_check())

    # Card gone from queue.
    assert _find_drift_card(cid) is None


# ---------------------------------------------------------------------------
# keep_canonical_drift
# ---------------------------------------------------------------------------


def test_keep_canonical_drift_silences_card(loop, drift_fixture):
    cid, _, _ = drift_fixture
    card = _find_drift_card(cid)
    assert card
    canonical_hash = card["raw_inputs"]["canonical_hash"]

    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={
            "conflict_id": card["conflict_id"],
            "action": "keep_canonical_drift",
            "reason": "silence-test",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    assert r.json()["silenced_until_canonical_changes"] is True

    # Canonical metrics must NOT have changed.
    async def _check_no_write():
        db = _db()
        emp = await db.employees.find_one({"id": cid}, {"_id": 0, "current_metrics": 1})
        cm = emp["current_metrics"]
        assert cm["guests"] == 1000
        assert cm["total_score"] == 80.0
        assert cm["ppa"] == 26.0
    loop.run_until_complete(_check_no_write())

    # Card hidden from queue.
    assert _find_drift_card(cid) is None

    # Resolved registry has the canonical hash stamped.
    async def _check_stamp():
        db = _db()
        rec = await db.reconciliation_resolved.find_one(
            {"conflict_id": card["conflict_id"]}, {"_id": 0},
        )
        assert rec
        assert rec["post_stored"] == canonical_hash
    loop.run_until_complete(_check_stamp())


def test_keep_canonical_drift_resurfaces_on_canonical_change(loop, drift_fixture):
    """If the canonical side changes after a silence, the card must
    re-surface so the operator sees the new drift state."""
    cid, _, _ = drift_fixture
    card = _find_drift_card(cid)
    assert card

    requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "keep_canonical_drift", "reason": "silence"},
        timeout=20,
    ).raise_for_status()
    assert _find_drift_card(cid) is None

    # Mutate canonical scoring → hash changes → card must re-surface.
    async def _mutate():
        db = _db()
        await db.employees.update_one(
            {"id": cid},
            {"$set": {"current_metrics.ppa": 25.5}},  # was 26.0
        )
    loop.run_until_complete(_mutate())

    card2 = _find_drift_card(cid)
    assert card2 is not None, (
        "card did not re-surface after canonical mutated — silence "
        "hash check is broken"
    )
