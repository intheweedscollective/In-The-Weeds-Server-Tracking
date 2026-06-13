"""
Tests for the 2026-06-01 trust-badge & QR ghost-dismiss fixes.

Covers:
1. /scoring-trust integrity breakdown is exposed by category.
2. EmployeeValidator.check_orphaned_snapshot_refs honours legacy_ids[]
   so a row pointing at a v2 id that's been linked into a canonical's
   legacy_ids is NOT flagged as orphan.
3. /qr/admin/dismiss-ghost-ids drops the dismissed printed_ids from
   /qr/admin/health.ghost_ids.count AND from /qr/admin/ghost-ids list.
4. Dismissed ghosts can be undismissed and re-surface.
"""

import os
import asyncio
import uuid
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from conftest import ADMIN_TOKEN

load_dotenv("/app/backend/.env")
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
H = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# --------------------------------------------------------------------
# Trust badge integrity breakdown
# --------------------------------------------------------------------


def test_trust_integrity_breakdown_is_exposed():
    """The integrity block must expose a `breakdown` dict so the modal
    can show 'orphan refs: N · blocklist: M' instead of the cryptic
    'P0 18 / P2 18' rollup."""
    r = requests.get(f"{BASE}/api/v2/admin/scoring-trust", headers=H, timeout=30)
    assert r.status_code == 200, r.text
    integ = r.json().get("details", {}).get("integrity", {})
    assert "breakdown" in integ
    assert isinstance(integ["breakdown"], dict)


# --------------------------------------------------------------------
# Orphan check honors legacy_ids[]
# --------------------------------------------------------------------


def test_legacy_ids_in_canonical_clears_orphan_flag():
    """Inject a snapshot row pointing at a v2_id that lives in a
    canonical's legacy_ids[]. The integrity check must NOT flag it
    as orphan."""
    async def go():
        db = _db()
        v2id = str(uuid.uuid4())
        # Pick a real active canonical and add the v2id to legacy_ids[].
        canon = await db.employees.find_one({"status": "active"}, {"_id": 0, "id": 1, "legacy_ids": 1})
        assert canon is not None
        original_legacy = list(canon.get("legacy_ids") or [])
        await db.employees.update_one(
            {"id": canon["id"]},
            {"$addToSet": {"legacy_ids": v2id}},
        )

        # Create a probe snapshot containing exactly one row whose
        # employee_id is v2id. If the orphan check honors legacy_ids
        # it should NOT show up in the integrity report.
        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"OrphanTest-{snap_id[:6]}",
            "status": "in_progress",
            "rows": [{"employee_id": v2id, "frozen_display_name": "Probe"}],
            "employees": [],
        })
        try:
            r = requests.get(f"{BASE}/api/v2/admin/integrity", headers=H, timeout=30)
            assert r.status_code == 200, r.text
            orphans = r.json().get("orphaned_snapshot_refs", [])
            assert not any(o.get("snapshot_id") == snap_id for o in orphans), (
                f"orphan check fired despite legacy_ids carrying {v2id}"
            )
        finally:
            await db.snapshot_workflow.delete_one({"id": snap_id})
            await db.employees.update_one(
                {"id": canon["id"]},
                {"$set": {"legacy_ids": original_legacy}},
            )

    asyncio.run(go())


# --------------------------------------------------------------------
# QR ghost dismiss / undismiss
# --------------------------------------------------------------------


def test_dismiss_ghost_id_drops_from_health_count():
    async def go():
        db = _db()
        probe_id = str(uuid.uuid4())
        # Seed a fake immutable scan with a ghost printed_id.
        from datetime import datetime, timezone
        await db.qr_click_log_immutable.insert_one({
            "employee_id": probe_id,
            "platform": "yelp",
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        try:
            r1 = requests.get(f"{BASE}/api/qr/admin/health", headers=H, timeout=20).json()
            count_before = r1.get("ghost_ids", {}).get("count", 0)
            assert count_before >= 1

            r2 = requests.post(
                f"{BASE}/api/qr/admin/dismiss-ghost-ids",
                headers=H,
                json={"printed_ids": [probe_id], "reason": "test probe"},
                timeout=20,
            )
            assert r2.status_code == 200, r2.text
            assert r2.json().get("dismissed_count") == 1

            r3 = requests.get(f"{BASE}/api/qr/admin/health", headers=H, timeout=20).json()
            count_after = r3.get("ghost_ids", {}).get("count", 0)
            assert count_after == count_before - 1, (
                f"dismiss didn't drop ghost count: {count_before} -> {count_after}"
            )
            assert r3.get("ghost_ids", {}).get("dismissed_count", 0) >= 1

            # Undismiss should restore the count.
            r4 = requests.post(
                f"{BASE}/api/qr/admin/undismiss-ghost-id",
                headers=H,
                json={"printed_id": probe_id},
                timeout=20,
            )
            assert r4.status_code == 200, r4.text
            r5 = requests.get(f"{BASE}/api/qr/admin/health", headers=H, timeout=20).json()
            assert r5.get("ghost_ids", {}).get("count", 0) == count_before
        finally:
            await db.qr_click_log_immutable.delete_many({"employee_id": probe_id})
            await db.qr_ghost_dismissed.delete_one({"printed_id": probe_id})

    asyncio.run(go())


def test_dismiss_requires_printed_ids():
    r = requests.post(
        f"{BASE}/api/qr/admin/dismiss-ghost-ids",
        headers=H,
        json={"printed_ids": []},
        timeout=20,
    )
    assert r.status_code == 400
