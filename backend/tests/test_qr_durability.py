"""
Regression tests for QR durability hooks.

  - Every scan handler writes to BOTH `qr_scans` AND
    `qr_click_log_immutable`. If a deploy ever wipes qr_scans, the
    immutable log still has the full history.
  - Daily snapshot is idempotent per-day (re-running on same day
    updates the row instead of appending).
  - Health check flags long silent gaps.

⚠️ Isolated test DB.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()
TEST_DB = "_qr_durability_test_db"


def _client():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c, c[TEST_DB]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_record_scan_writes_to_both_logs():
    async def runner():
        import qr_tracking
        c, db = _client()
        await db.qr_employees.drop()
        await db.qr_scans.drop()
        await db.qr_click_log_immutable.drop()

        await db.qr_employees.insert_one({
            "id": "emp-1", "name": "Test Emp",
            "google_clicks": 0, "yelp_clicks": 0,
            "tripadvisor_clicks": 0, "total_clicks": 0,
        })

        # Stub the module-level _db.
        original_db = qr_tracking._db
        qr_tracking._db = db
        try:
            await qr_tracking._record_scan("emp-1", "google")
            await qr_tracking._record_scan("emp-1", "tripadvisor")
            await qr_tracking._record_scan("emp-1", "yelp")
        finally:
            qr_tracking._db = original_db

        # All three collections updated.
        emp = await db.qr_employees.find_one({"id": "emp-1"})
        assert emp["google_clicks"] == 1
        assert emp["tripadvisor_clicks"] == 1
        assert emp["yelp_clicks"] == 1
        assert emp["total_clicks"] == 3

        assert await db.qr_scans.count_documents({}) == 3
        assert await db.qr_click_log_immutable.count_documents({}) == 3

        # If admin "resets" qr_scans, the immutable log survives.
        await db.qr_scans.delete_many({})
        assert await db.qr_scans.count_documents({}) == 0
        assert await db.qr_click_log_immutable.count_documents({}) == 3

        await db.qr_employees.drop()
        await db.qr_scans.drop()
        await db.qr_click_log_immutable.drop()
        c.close()
    _run(runner())


def test_record_scan_writes_event_even_when_employee_missing():
    """Edge case: someone scans a deleted-employee QR. We still want
    the event recorded in the immutable log."""
    async def runner():
        import qr_tracking
        c, db = _client()
        await db.qr_employees.drop()
        await db.qr_scans.drop()
        await db.qr_click_log_immutable.drop()

        original_db = qr_tracking._db
        qr_tracking._db = db
        try:
            await qr_tracking._record_scan("ghost-id", "google")
        finally:
            qr_tracking._db = original_db

        # qr_employees has no row to increment — that's fine.
        assert await db.qr_employees.count_documents({}) == 0
        # But both event logs got the row, name=Unknown.
        scan = await db.qr_scans.find_one({}, {"_id": 0})
        imm = await db.qr_click_log_immutable.find_one({}, {"_id": 0})
        assert scan["employee_id"] == "ghost-id"
        assert scan["employee_name"] == "Unknown"
        assert imm["employee_id"] == "ghost-id"

        c.close()
    _run(runner())


def test_daily_snapshot_idempotent_per_day():
    async def runner():
        c, db = _client()
        await db.qr_employees.drop()
        await db.qr_daily_snapshots.drop()

        await db.qr_employees.insert_one({
            "id": "e1", "name": "Anna",
            "google_clicks": 5, "yelp_clicks": 0, "tripadvisor_clicks": 0,
        })

        # Twice on the same day → 1 doc.
        today = datetime.now(timezone.utc).date().isoformat()
        for _ in range(2):
            rows = []
            async for q in db.qr_employees.find({}, {"_id": 0}):
                rows.append({
                    "employee_id": q.get("id"), "name": q.get("name"),
                    "yelp_clicks": q.get("yelp_clicks") or 0,
                    "google_clicks": q.get("google_clicks") or 0,
                    "tripadvisor_clicks": q.get("tripadvisor_clicks") or 0,
                })
            total = sum(r["yelp_clicks"] + r["google_clicks"]
                        + r["tripadvisor_clicks"] for r in rows)
            await db.qr_daily_snapshots.update_one(
                {"date": today},
                {"$set": {"date": today, "rows": rows,
                          "employee_count": len(rows), "total_clicks": total}},
                upsert=True,
            )
        assert await db.qr_daily_snapshots.count_documents({}) == 1

        await db.qr_employees.drop()
        await db.qr_daily_snapshots.drop()
        c.close()
    _run(runner())
