"""
Regression test for the "edit reverts" bug on the Employees / Data
Uploads page.

The bug:
  • User edits a metric in the Employees / Data Uploads UI.
  • Frontend calls `PUT /api/v2/employees/{id}` with the new value.
  • Backend updates `employees_v2`, fires the success toast.
  • Frontend re-fetches `/api/v2/snapshot-workflow/current-rankings`.
  • That endpoint reads from `snapshot.rows[].frozen_metrics` first.
  • The PUT NEVER wrote there → the response is the old/frozen value.
  • UI snaps back to the original.

Root cause:
  • The PUT only synced `snapshot.employees[]` (legacy embedded array),
    not `snapshot.rows[].frozen_metrics` (the FK-join's source).
  • The original sync code filtered by `quarter`/`year` from the v2
    record, which can be stale (legacy v2 docs carry the quarter they
    were FIRST seeded with, not the current snapshot's quarter).

Fix: also sync into `snapshot.rows[].frozen_metrics`, AND drop the
quarter/year filter — just match by employee_id / name.

This test enforces the contract end-to-end.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # type: ignore
load_dotenv("/app/backend/.env")

API = open("/app/frontend/.env").read().split(
    "REACT_APP_BACKEND_URL="
)[1].split("\n")[0].strip()


def test_edit_does_not_revert_on_refetch():
    """End-to-end smoke: PUT a unique value, refetch, assert no revert."""
    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]

        # Seed an isolated employee + snapshot row so this test never
        # touches a real preview employee. The "stale v2 quarter" detail
        # is what made the original bug invisible to a casual test —
        # so we reproduce it exactly: v2 quarter "Q1" but the snapshot
        # is "Q2".
        eid = "test-revert-" + uuid.uuid4().hex[:8]
        snap_id = "test-snap-" + uuid.uuid4().hex[:8]
        admin_email = (os.environ.get("ALLOWED_ADMIN_EMAILS")
                       or "owner@intheweedscollective.com").split(",")[0].strip()
        now_iso = datetime.now(timezone.utc).isoformat()

        await db.employees.insert_one({
            "id": eid, "name": "RevertTest User",
            "display_name": "RevertTest User", "status": "active",
        })
        await db.employees_v2.insert_one({
            "id": eid, "name": "RevertTest User",
            "report_name": "RevertTest User",
            "quarter": "Q1",  # <-- stale quarter — the original bug condition
            "year": 2026,
            "net_sales": 1000.0,
            "ppa": 10.0, "lbw_per_guest": 5.0, "glassware_per_guest": 1.0,
            "lsc_count": 4, "guests": 100, "guests_per_lsc": 25,
            "score_ppa": 70, "score_lbw": 70, "score_glass": 70, "score_lsc": 70,
            "total_score": 70,
        })
        await db.snapshot_workflow.insert_one({
            "id": snap_id, "name": "REVERT-TEST",
            "quarter": "Q2", "year": 2026,
            "is_current": False, "status": "completed",
            "rows": [{
                "employee_id": eid,
                "frozen_display_name": "RevertTest User",
                "frozen_report_name": "RevertTest User",
                "frozen_metrics": {
                    "name": "RevertTest User",
                    "quarter": "Q2", "year": 2026,
                    "net_sales": 1000.0, "ppa": 10.0,
                    "score_ppa": 70, "score_lbw": 70,
                    "score_glass": 70, "score_lsc": 70,
                    "total_score": 70,
                },
                "frozen_score": 70,
            }],
            "employees": [{
                "id": eid, "name": "RevertTest User",
                "net_sales": 1000.0, "ppa": 10.0,
                "total_score": 70,
            }],
            "created_at": now_iso,
        })

        test_token = f"t-{uuid.uuid4()}"
        test_user_id = f"u-{uuid.uuid4()}"
        await db.users.insert_one({
            "user_id": test_user_id, "email": admin_email, "name": "T",
        })
        await db.user_sessions.insert_one({
            "session_token": test_token, "user_id": test_user_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        api = httpx.AsyncClient(
            base_url=API, follow_redirects=False, timeout=30.0,
            headers={"Authorization": f"Bearer {test_token}"},
        )

        try:
            # PUT a deliberately weird value.
            new_val = 12345.67
            r = await api.put(f"/api/v2/employees/{eid}",
                              json={"net_sales": new_val})
            assert r.status_code == 200, r.text

            # Re-read the snapshot row directly — the new value MUST be
            # in `rows[].frozen_metrics.net_sales`. If it isn't, the
            # refetch will appear to revert.
            row_q = await db.snapshot_workflow.aggregate([
                {"$match": {"id": snap_id}},
                {"$project": {"r": {"$filter": {"input": "$rows", "as": "r",
                                "cond": {"$eq": ["$$r.employee_id", eid]}}}}},
            ]).to_list(1)
            fm = row_q[0]["r"][0]["frozen_metrics"]
            assert abs((fm.get("net_sales") or 0) - new_val) < 0.01, (
                f"rows[].frozen_metrics.net_sales was not synced. "
                f"Expected {new_val}, got {fm.get('net_sales')}. "
                f"This is the original revert bug."
            )

            # Also confirm the legacy `employees[]` array got synced
            # (the UI / older read paths still consume that).
            snap_doc = await db.snapshot_workflow.find_one(
                {"id": snap_id}, {"_id": 0, "employees": 1},
            )
            legacy = next((e for e in snap_doc["employees"]
                           if e["id"] == eid), None)
            assert legacy is not None
            assert abs((legacy.get("net_sales") or 0) - new_val) < 0.01

            # And the v2 record itself.
            v2 = await db.employees_v2.find_one(
                {"id": eid}, {"_id": 0, "net_sales": 1},
            )
            assert abs((v2.get("net_sales") or 0) - new_val) < 0.01
        finally:
            await db.employees.delete_one({"id": eid})
            await db.employees_v2.delete_one({"id": eid})
            await db.snapshot_workflow.delete_one({"id": snap_id})
            await db.user_sessions.delete_one({"session_token": test_token})
            await db.users.delete_one({"user_id": test_user_id})
            await api.aclose()
            client.close()

    asyncio.run(run())


if __name__ == "__main__":
    test_edit_does_not_revert_on_refetch()
    print("OK edit-revert regression")
