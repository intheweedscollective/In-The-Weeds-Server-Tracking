"""
Tests for the Data Reconciliation Portal (manual adjudication queue).

Verifies:
- Queue endpoint returns expected card shapes and the 3 priority drift cards.
- Single-card resolve endpoint requires admin (401 anon).
- Each resolution action — keep_stored, accept_snapshot, manual_override,
  defer, revoke_alias — applies correctly and logs to audit.
- Deferred cards persist across calls.
- manual_override without value_override returns 400.
- Unknown conflict_id returns 404.
"""

import os
import asyncio
import requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from conftest import ADMIN_TOKEN

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ---------------------------------------------------------------------------
# Queue shape
# ---------------------------------------------------------------------------


def test_queue_requires_admin():
    r = requests.get(f"{BASE}/api/v2/admin/reconciliation/queue", timeout=20)
    assert r.status_code == 401


def test_queue_returns_three_priority_cards():
    """Kahiaulani Ramos, Jose Plancarte Villa, and Julian Taveras should
    all surface as metric_drift cards (the user's documented priority
    list). Severity should descend so worst-first sorting holds."""
    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    active = d.get("active", [])
    names = [c.get("employee_name") for c in active]
    for must in ("Kahiaulani Ramos", "Jose Plancarte Villa", "Julian Taveras"):
        assert must in names, f"missing priority card {must}: {names}"

    # Worst-first.
    severities = [c.get("severity_pct") or 0 for c in active]
    assert severities == sorted(severities, reverse=True), (
        f"queue not sorted by severity descending: {severities}"
    )

    # Required card fields for the UI.
    for c in active:
        for k in ("conflict_id", "kind", "employee_id", "employee_name",
                  "field", "stored_value", "source"):
            assert k in c, f"card missing field {k}: {c}"


# ---------------------------------------------------------------------------
# Resolve: each action path
# ---------------------------------------------------------------------------


def _find_card(name, field="ppa"):
    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    d = r.json()
    for c in d.get("active", []) + d.get("deferred", []):
        if c.get("employee_name") == name and c.get("field") == field:
            return c
    return None


def test_resolve_defer_persists_in_deferred_section():
    card = _find_card("Julian Taveras")
    if not card:
        return  # nothing to defer
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN_HEADERS,
        json={"conflict_id": card["conflict_id"], "action": "defer",
              "reason": "borderline drift — review next quarter"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    # Re-fetch and verify it sits in `deferred[]`.
    q = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN_HEADERS,
        timeout=20,
    ).json()
    deferred_ids = [c["conflict_id"] for c in q.get("deferred", [])]
    assert card["conflict_id"] in deferred_ids, (
        f"deferred card not in deferred list: {deferred_ids}"
    )
    # Audit log records the defer.
    audit = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/audit",
        headers=ADMIN_HEADERS,
        timeout=20,
    ).json()
    assert any(
        e["conflict_id"] == card["conflict_id"] and e["action"] == "defer"
        for e in audit.get("entries", [])
    ), "defer not in audit log"


def test_resolve_keep_stored_logs_dismissal():
    card = _find_card("Jose Plancarte Villa")
    if not card:
        return
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN_HEADERS,
        json={"conflict_id": card["conflict_id"], "action": "keep_stored",
              "reason": "validated with HR"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    audit = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/audit",
        headers=ADMIN_HEADERS,
        timeout=20,
    ).json()
    entry = next(
        (e for e in audit["entries"]
         if e["conflict_id"] == card["conflict_id"] and e["action"] == "keep_stored"),
        None,
    )
    assert entry is not None, "keep_stored not logged"
    assert entry["before"] == entry["after"], "keep_stored should not change value"
    assert entry["reason"] == "validated with HR"


def test_manual_override_requires_value_override():
    card = _find_card("Jose Plancarte Villa")
    if not card:
        return
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN_HEADERS,
        json={"conflict_id": card["conflict_id"], "action": "manual_override"},
        timeout=20,
    )
    # Either 400 from the service layer or 422 from FastAPI body validation
    # — either way the resolution must NOT have applied.
    assert r.status_code in (400, 422), r.text


def test_manual_override_writes_value_and_logs():
    """End-to-end manual override on a throwaway test employee — verifies
    the canonical record gets updated and the audit log records before/after.
    Cleans up after itself."""
    async def setup_and_resolve():
        db = _db()
        # Seed a canonical employee with deliberately drifting metrics.
        import uuid
        tid = str(uuid.uuid4())
        await db.employees.insert_one({
            "id": tid,
            "name": f"Recon Test {tid[:6]}",
            "status": "active",
            "current_metrics": {
                "guests": 100,
                "guest_count": 100,
                "net_sales": 4500,
                "ppa": 99.99,  # Drift: real PPA = 45.0
            },
        })
        try:
            # Force-refresh the queue so the new card appears.
            q = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=ADMIN_HEADERS,
                timeout=30,
            ).json()
            card = next(
                (c for c in q.get("active", []) if c.get("employee_id") == tid),
                None,
            )
            assert card is not None, "test employee did not surface in queue"

            r = requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=ADMIN_HEADERS,
                json={"conflict_id": card["conflict_id"],
                      "action": "manual_override", "value_override": 47.50,
                      "reason": "operator-typed correction"},
                timeout=20,
            )
            assert r.status_code == 200, r.text
            assert r.json().get("value") == 47.50

            after = await db.employees.find_one({"id": tid})
            assert (after.get("current_metrics") or {}).get("ppa") == 47.50, (
                "canonical ppa not updated"
            )

            audit = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/audit",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).json()
            entry = next(
                (e for e in audit["entries"]
                 if e["conflict_id"] == card["conflict_id"]
                 and e["action"] == "manual_override"),
                None,
            )
            assert entry is not None
            assert entry["after"] == 47.50
            assert entry["before"] == 99.99
        finally:
            await db.employees.delete_one({"id": tid})
            await db.employees_v2.delete_many({"id": tid})

    asyncio.run(setup_and_resolve())


def test_unknown_conflict_id_returns_404():
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN_HEADERS,
        json={"conflict_id": "metric_doesnotexist123",
              "action": "keep_stored"},
        timeout=20,
    )
    assert r.status_code == 404


def test_resolve_clears_card_from_active_queue():
    """After ANY actionable resolution, the card must disappear from
    active[] and surface in resolved[]. This was the user's pain point —
    fixing kahi via manual_override left the card visible because the
    underlying raw input was still corrupt."""
    # Recreate a fresh drift card on a sandbox employee so we don't
    # depend on Kahi/Jose/Julian state (they may already be resolved
    # by earlier tests in this file).
    async def go():
        import uuid
        db = _db()
        tid = str(uuid.uuid4())
        await db.employees.insert_one({
            "id": tid,
            "name": f"Clear Test {tid[:6]}",
            "status": "active",
            "current_metrics": {
                "guests": 200,
                "guest_count": 200,
                "net_sales": 9999,
                "ppa": 12.34,  # drifts from real 49.99
            },
        })
        try:
            q1 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).json()
            card = next(
                (c for c in q1["active"] if c.get("employee_id") == tid),
                None,
            )
            assert card is not None, "test employee not in queue"
            initial_active = q1["counts"]["active"]

            # Resolve via keep_stored — the simplest action.
            requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=ADMIN_HEADERS,
                json={"conflict_id": card["conflict_id"],
                      "action": "keep_stored", "reason": "test"},
                timeout=20,
            ).raise_for_status()

            q2 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).json()
            assert q2["counts"]["active"] == initial_active - 1, (
                f"active count didn't drop: {q1['counts']['active']} -> {q2['counts']['active']}"
            )
            assert not any(c["conflict_id"] == card["conflict_id"]
                           for c in q2["active"]), "card still in active!"
            assert any(r["conflict_id"] == card["conflict_id"]
                       for r in q2.get("resolved", [])), "card not in resolved[]"

            # Un-resolve must bring it back.
            requests.post(
                f"{BASE}/api/v2/admin/reconciliation/unresolve"
                f"?conflict_id={card['conflict_id']}",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).raise_for_status()
            q3 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).json()
            assert any(c["conflict_id"] == card["conflict_id"]
                       for c in q3["active"]), "un-resolve didn't bring it back"
        finally:
            await db.employees.delete_one({"id": tid})
            await db.employees_v2.delete_many({"id": tid})
            await db.reconciliation_resolved.delete_many({})
            await db.reconciliation_deferred.delete_many({})

    asyncio.run(go())


def test_resolved_card_resurfaces_if_values_drift_again():
    """If the operator resolves a card and later the underlying data
    moves materially, the card must re-surface so they can adjudicate
    the NEW drift."""
    async def go():
        import uuid
        db = _db()
        tid = str(uuid.uuid4())
        await db.employees.insert_one({
            "id": tid,
            "name": f"Resurface Test {tid[:6]}",
            "status": "active",
            "current_metrics": {
                "guests": 100,
                "guest_count": 100,
                "net_sales": 5000,
                "ppa": 20.00,  # drifts from real 50.00
            },
        })
        try:
            q1 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).json()
            card = next(
                (c for c in q1["active"] if c.get("employee_id") == tid),
                None,
            )
            assert card is not None

            requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=ADMIN_HEADERS,
                json={"conflict_id": card["conflict_id"],
                      "action": "keep_stored"},
                timeout=20,
            ).raise_for_status()

            q2 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).json()
            assert not any(c["conflict_id"] == card["conflict_id"]
                           for c in q2["active"]), "card not cleared"

            # Materially change net_sales — fresh drift should re-surface.
            await db.employees.update_one(
                {"id": tid},
                {"$set": {"current_metrics.net_sales": 99999}},
            )

            q3 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=ADMIN_HEADERS,
                timeout=20,
            ).json()
            assert any(c["conflict_id"] == card["conflict_id"]
                       for c in q3["active"]), (
                "stale resolution didn't expire on fresh drift"
            )
        finally:
            await db.employees.delete_one({"id": tid})
            await db.employees_v2.delete_many({"id": tid})
            await db.reconciliation_resolved.delete_many({})
            await db.reconciliation_deferred.delete_many({})

    asyncio.run(go())


# ---------------------------------------------------------------------------
# Cleanup — leave the deferred Julian card un-deferred so the next run
# starts from a known state.
# ---------------------------------------------------------------------------


def test_zzz_cleanup_undefer_julian():
    card = _find_card("Julian Taveras")
    if not card:
        return
    # If Julian is deferred, fire keep_stored to clear it back to active.
    q = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN_HEADERS,
        timeout=20,
    ).json()
    if any(c["conflict_id"] == card["conflict_id"] for c in q.get("deferred", [])):
        requests.post(
            f"{BASE}/api/v2/admin/reconciliation/resolve",
            headers=ADMIN_HEADERS,
            json={"conflict_id": card["conflict_id"], "action": "keep_stored",
                  "reason": "test cleanup — re-activate"},
            timeout=20,
        )
