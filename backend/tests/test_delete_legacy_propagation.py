"""
Test for the 2026-06-02 delete_legacy propagation fix.

Bug: delete_legacy only soft-deleted the employees_v2 row. The same
employee continued to live inside snapshot_workflow.rows[] and
snapshot_workflow.employees[] arrays, so:
  - the trust badge still flagged blocklist violations and orphan refs
  - the dashboard still rendered the typo profile
  - user reported: "When I delete a legacy profile, nothing happens.
    The error persists after deleting"

Fix: delete_legacy now also prunes the v2_id and matching name from
every non-finalized snapshot's rows[] and employees[] arrays.
Finalized snapshots remain immutable.
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


def test_delete_legacy_prunes_embedded_snapshot_rows():
    """End-to-end: seed a fake legacy v2 row + embed it in a
    non-finalized snapshot, then run delete_legacy and verify the
    snapshot's rows[] and employees[] no longer contain it."""
    async def go():
        db = _db()
        vid = str(uuid.uuid4())
        nm = f"PruneTest-{vid[:6]}"
        # Seed a current-quarter v2 row so the card surfaces.
        curr = await db.snapshot_workflow.find_one({"is_current": True})
        if not curr:
            return
        q, y = curr.get("quarter"), curr.get("year")
        await db.employees_v2.insert_one({
            "id": vid, "name": nm, "quarter": q, "year": y,
            "status": "active", "guests": 1, "ppa": 1.0,
        })
        # Seed a probe snapshot that embeds the row (by id) AND a row
        # whose frozen_display_name matches the name (no id, by-name path).
        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"PruneTestSnap-{snap_id[:6]}",
            "status": "in_progress",
            "rows": [
                {"employee_id": vid, "frozen_display_name": nm},
                {"employee_id": "other-id", "frozen_display_name": nm},
            ],
            "employees": [
                {"id": vid, "name": nm},
                {"id": "different-id", "name": nm},
            ],
        })
        try:
            q1 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=H, timeout=30,
            ).json()
            card = next(
                (c for c in q1["active"] if c.get("employee_id") == vid),
                None,
            )
            assert card is not None, "v2 row didn't surface"

            r = requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=H, timeout=20,
                json={"conflict_id": card["conflict_id"],
                      "action": "delete_legacy",
                      "reason": "test propagation"},
            )
            assert r.status_code == 200, r.text
            payload = r.json()
            assert payload["snapshots_touched"] >= 1
            assert payload["snapshot_rows_removed"] >= 4  # 2 rows + 2 emps

            # Snapshot must no longer contain the v2_id NOR the name.
            after = await db.snapshot_workflow.find_one({"id": snap_id})
            for r in (after.get("rows") or []):
                assert r.get("employee_id") != vid, "v2_id still in rows[]"
                assert (r.get("frozen_display_name") or "").lower() != nm.lower(), \
                    "name still in rows[]"
            for e in (after.get("employees") or []):
                assert e.get("id") != vid, "v2_id still in employees[]"
                assert (e.get("name") or "").lower() != nm.lower(), \
                    "name still in employees[]"

            # v2 row is soft-deleted.
            v2 = await db.employees_v2.find_one({"id": vid})
            assert v2.get("status") == "inactive"
        finally:
            await db.snapshot_workflow.delete_one({"id": snap_id})
            await db.employees_v2.delete_one({"id": vid})
            await db.reconciliation_resolved.delete_many({"employee_id": vid})

    asyncio.run(go())


def test_delete_legacy_does_not_touch_finalized_snapshots():
    """Finalized snapshots are immutable historical record. Even if
    they embed the deleted v2 row, delete_legacy must NOT modify
    them."""
    async def go():
        db = _db()
        vid = str(uuid.uuid4())
        nm = f"FinalImmuTest-{vid[:6]}"
        curr = await db.snapshot_workflow.find_one({"is_current": True})
        if not curr:
            return
        q, y = curr.get("quarter"), curr.get("year")
        await db.employees_v2.insert_one({
            "id": vid, "name": nm, "quarter": q, "year": y,
            "status": "active",
        })
        snap_id = str(uuid.uuid4())
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"FinalSnap-{snap_id[:6]}",
            "status": "finalized",
            "rows": [{"employee_id": vid, "frozen_display_name": nm}],
            "employees": [{"id": vid, "name": nm}],
        })
        try:
            q1 = requests.get(
                f"{BASE}/api/v2/admin/reconciliation/queue",
                headers=H, timeout=30,
            ).json()
            card = next(
                (c for c in q1["active"] if c.get("employee_id") == vid),
                None,
            )
            if not card:
                return
            requests.post(
                f"{BASE}/api/v2/admin/reconciliation/resolve",
                headers=H, timeout=20,
                json={"conflict_id": card["conflict_id"],
                      "action": "delete_legacy"},
            )
            after = await db.snapshot_workflow.find_one({"id": snap_id})
            assert len(after.get("rows") or []) == 1, \
                "finalized snapshot's rows[] was mutated"
            assert len(after.get("employees") or []) == 1, \
                "finalized snapshot's employees[] was mutated"
        finally:
            await db.snapshot_workflow.delete_one({"id": snap_id})
            await db.employees_v2.delete_one({"id": vid})
            await db.reconciliation_resolved.delete_many({"employee_id": vid})

    asyncio.run(go())
