"""
Test for the 2026-06-02 clicks-by-day backfill fix.

Bug: /qr/clicks-by-day only emitted rows for employees who had ≥1 scan
in the window, so the dashboard daily-clicks leaderboard silently
dropped active employees with 0 clicks. User reported "29 employees but
only 17 show." After the fix, every active+tracked employee surfaces,
with zero-click rows sorted to the bottom.
"""

import os
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import asyncio

load_dotenv("/app/backend/.env")
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def test_clicks_by_day_includes_zero_click_employees():
    """Every currently-tracked active employee must surface as a row,
    even with total=0. Zero-click rows sort to the bottom."""
    async def count_active_tracked():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        qr_tracked = {
            (q.get("name") or "").strip().lower()
            async for q in db.qr_employees.find({}, {"_id": 0, "name": 1})
        }
        active_tracked = 0
        async for e in db.employees.find(
            {"status": "active"},
            {"_id": 0, "name": 1, "aliases": 1},
        ):
            nm = (e.get("name") or "").strip().lower()
            if not nm:
                continue
            # Skip test placeholders
            if "test" in nm.split() or nm.startswith("demo "):
                continue
            if nm in qr_tracked or any(
                (a or "").strip().lower() in qr_tracked
                for a in (e.get("aliases") or [])
            ):
                active_tracked += 1
        return active_tracked

    expected = asyncio.run(count_active_tracked())
    r = requests.get(f"{BASE}/api/qr/clicks-by-day?days=30", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    rows = r.json().get("rows", [])
    # Allow a small drift because there can be ghost scans whose
    # employee_name doesn't match any current canonical — they won't
    # have a backfill counterpart. But the count must be at LEAST
    # equal to the active+tracked roster (this is the regression).
    assert len(rows) >= expected, (
        f"expected ≥ {expected} rows (active+tracked employees), got {len(rows)}"
    )

    # The last row should be a zero-click employee (assuming any
    # exist) — i.e. the response is sorted total-desc.
    totals = [r.get("total", 0) for r in rows]
    assert totals == sorted(totals, reverse=True), (
        f"rows not sorted total-desc: {totals[:5]} ... {totals[-5:]}"
    )


def test_clicks_by_day_zero_rows_have_correct_shape():
    """Backfilled zero rows must have the same shape as scan-driven
    rows so the frontend table renders them uniformly."""
    r = requests.get(f"{BASE}/api/qr/clicks-by-day?days=30", headers=H, timeout=20)
    rows = r.json().get("rows", [])
    days = r.json().get("days", [])

    for row in rows:
        if row.get("total", 0) > 0:
            continue
        # This is a backfilled zero row.
        assert row.get("name")
        assert row.get("active") is True
        by_day = row.get("by_day") or []
        assert len(by_day) == len(days), (
            f"by_day length mismatch on {row.get('name')}: {len(by_day)} vs {len(days)}"
        )
        assert sum(by_day) == 0
        totals = row.get("totals") or {}
        assert totals.get("yelp", 0) == 0
        assert totals.get("google", 0) == 0
        assert totals.get("tripadvisor", 0) == 0
