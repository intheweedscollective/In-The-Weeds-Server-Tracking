"""
Tests for:
1. /api/v2/admin/structural-cleanup — phased dry-run / apply
2. Reconciliation portal's `legacy_duplicate` card type:
   - queue surfaces non-linked v2 records
   - merge_into action wires legacy_ids[] + aliases[]
   - delete_legacy soft-deletes the v2 row
   - promote_canonical creates a canonical record
"""

import os
import uuid
import asyncio
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ---------------------------------------------------------------------------
# Structural cleanup
# ---------------------------------------------------------------------------


def test_structural_cleanup_requires_admin():
    r = requests.post(f"{BASE}/api/v2/admin/structural-cleanup", timeout=20)
    assert r.status_code == 401


def test_structural_cleanup_dry_run_returns_plan():
    """Dry-run must return a plan but not write."""
    r = requests.post(
        f"{BASE}/api/v2/admin/structural-cleanup",
        headers=H, timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("dry_run") is True
    s = d.get("summary", {})
    for k in ("auto_link_count", "orphan_snapshots", "orphan_total",
              "blocklist_snapshots", "blocklist_total"):
        assert k in s


def test_structural_cleanup_orphan_prune_default_off():
    """Default scope MUST NOT prune orphans (typo v2 records would look
    like orphans). Operator opts in with ?orphan_prune=true."""
    r = requests.post(
        f"{BASE}/api/v2/admin/structural-cleanup",
        headers=H, timeout=30,
    )
    d = r.json()
    assert d["summary"]["orphan_total"] == 0
    assert d["orphan_prune"] == []


# ---------------------------------------------------------------------------
# Legacy duplicate cards
# ---------------------------------------------------------------------------


def test_legacy_duplicate_cards_appear_in_queue():
    """Inject a v2-only row with no canonical match and verify the
    portal surfaces it as a legacy_duplicate card."""
    async def go():
        db = _db()
        vid = str(uuid.uuid4())
        nm = f"LegacyDupTest-{vid[:6]}"

        # Pull current snapshot's quarter/year
        snap = await db.snapshot_workflow.find_one({"is_current": True})
        if not snap:
            return
        q, y = snap.get("quarter"), snap.get("year")

        await db.employees_v2.insert_one({
            "id": vid, "name": nm, "quarter": q, "year": y,
            "guests": 100, "ppa": 50.0, "lsc_count": 5,
        })
        try:
            r = requests.get(f"{BASE}/api/v2/admin/reconciliation/queue",
                             headers=H, timeout=30).json()
            card = next(
                (c for c in r.get("active", [])
                 if c.get("employee_id") == vid),
                None,
            )
            assert card is not None, "v2-only row not surfaced as card"
            assert card["kind"] == "legacy_duplicate"
            assert card["employee_name"] == nm
            assert card["raw_inputs"]["guests"] == 100
        finally:
            await db.employees_v2.delete_one({"id": vid})

    asyncio.run(go())


def test_merge_into_requires_target_canonical_id():
    async def go():
        db = _db()
        vid = str(uuid.uuid4())
        nm = f"MergeReq-{vid[:6]}"
        snap = await db.snapshot_workflow.find_one({"is_current": True})
        if not snap:
            return
        await db.employees_v2.insert_one({
            "id": vid, "name": nm, "quarter": snap.get("quarter"),
            "year": snap.get("year"), "guests": 1, "ppa": 1.0,
        })
        try:
            q = requests.get(f"{BASE}/api/v2/admin/reconciliation/queue",
                             headers=H, timeout=30).json()
            card = next((c for c in q["active"] if c["employee_id"] == vid), None)
            assert card is not None
            r = requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=H, timeout=20,
                json={"conflict_id": card["conflict_id"], "action": "merge_into"},
            )
            assert r.status_code == 400
            assert "target_canonical_id" in r.text
        finally:
            await db.employees_v2.delete_one({"id": vid})
            await db.reconciliation_resolved.delete_many({"employee_id": vid})

    asyncio.run(go())


def test_merge_into_links_legacy_ids_and_alias():
    """End-to-end merge: typo v2 row → canonical employee. Verifies the
    legacy_ids[] gets the v2 id AND the misspelled name lands in aliases."""
    async def go():
        db = _db()
        # Pick a real active canonical as merge target.
        target = await db.employees.find_one({"status": "active"},
                                              {"_id": 0, "id": 1, "name": 1,
                                               "aliases": 1, "legacy_ids": 1})
        if not target:
            return
        vid = str(uuid.uuid4())
        typo_name = f"{target['name'][:3]}xZyTypo-{vid[:6]}"

        snap = await db.snapshot_workflow.find_one({"is_current": True})
        if not snap:
            return

        await db.employees_v2.insert_one({
            "id": vid, "name": typo_name, "quarter": snap.get("quarter"),
            "year": snap.get("year"), "guests": 100, "ppa": 50.0,
        })
        # Make sure target doesn't already carry the alias/legacy id.
        await db.employees.update_one(
            {"id": target["id"]},
            {"$pull": {"aliases": typo_name, "legacy_ids": vid}},
        )
        try:
            q = requests.get(f"{BASE}/api/v2/admin/reconciliation/queue",
                             headers=H, timeout=30).json()
            card = next((c for c in q["active"]
                         if c["employee_id"] == vid), None)
            assert card is not None

            r = requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=H, timeout=20,
                json={"conflict_id": card["conflict_id"],
                      "action": "merge_into",
                      "target_canonical_id": target["id"],
                      "reason": "test merge"},
            )
            assert r.status_code == 200, r.text
            res = r.json()
            assert res["merged_into"] == target["name"]

            after = await db.employees.find_one({"id": target["id"]})
            assert vid in (after.get("legacy_ids") or [])
            assert typo_name in (after.get("aliases") or [])
        finally:
            await db.employees.update_one(
                {"id": target["id"]},
                {"$pull": {"aliases": typo_name, "legacy_ids": vid}},
            )
            await db.employees_v2.delete_one({"id": vid})
            await db.reconciliation_resolved.delete_many({"employee_id": vid})

    asyncio.run(go())


def test_delete_legacy_soft_deletes_v2_row():
    async def go():
        db = _db()
        vid = str(uuid.uuid4())
        nm = f"DeleteLegacy-{vid[:6]}"
        snap = await db.snapshot_workflow.find_one({"is_current": True})
        if not snap:
            return
        await db.employees_v2.insert_one({
            "id": vid, "name": nm, "quarter": snap.get("quarter"),
            "year": snap.get("year"), "status": "active", "guests": 1,
        })
        try:
            q = requests.get(f"{BASE}/api/v2/admin/reconciliation/queue",
                             headers=H, timeout=30).json()
            card = next((c for c in q["active"]
                         if c["employee_id"] == vid), None)
            assert card is not None

            r = requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=H, timeout=20,
                json={"conflict_id": card["conflict_id"],
                      "action": "delete_legacy"},
            )
            assert r.status_code == 200, r.text

            after = await db.employees_v2.find_one({"id": vid})
            assert after.get("status") == "inactive"
            assert after.get("soft_deleted_at")
        finally:
            await db.employees_v2.delete_one({"id": vid})
            await db.reconciliation_resolved.delete_many({"employee_id": vid})

    asyncio.run(go())


def test_promote_canonical_creates_employee_row():
    async def go():
        db = _db()
        vid = str(uuid.uuid4())
        nm = f"PromoteTest-{vid[:6]}"
        snap = await db.snapshot_workflow.find_one({"is_current": True})
        if not snap:
            return
        await db.employees_v2.insert_one({
            "id": vid, "name": nm, "quarter": snap.get("quarter"),
            "year": snap.get("year"), "guests": 50, "ppa": 42.0,
        })
        try:
            q = requests.get(f"{BASE}/api/v2/admin/reconciliation/queue",
                             headers=H, timeout=30).json()
            card = next((c for c in q["active"]
                         if c["employee_id"] == vid), None)
            assert card is not None

            r = requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=H, timeout=20,
                json={"conflict_id": card["conflict_id"],
                      "action": "promote_canonical",
                      "reason": "new staff, not a typo"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["canonical_id"] == vid

            canonical = await db.employees.find_one({"id": vid})
            assert canonical is not None
            assert canonical["name"] == nm
            assert canonical["status"] == "active"
        finally:
            await db.employees.delete_one({"id": vid})
            await db.employees_v2.delete_one({"id": vid})
            await db.reconciliation_resolved.delete_many({"employee_id": vid})

    asyncio.run(go())
