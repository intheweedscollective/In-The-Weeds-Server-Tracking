"""
Smoke test for QR ghost-ID healing flow.

Verifies:
  1. A scan against a UUID NOT in qr_employees:
       - lands in qr_click_log_immutable with employee_name='Unknown' and
         counter_applied=False.
       - does NOT increment any qr_employees counter.
  2. After /admin/heal-ghost-ids POST with the mapping:
       - the alias is persisted in qr_employee_id_aliases.
       - past immutable events for the ghost get re-attributed
         (employee_name updated, counter_applied=True).
       - the canonical employee's counter increments by the scan count.
  3. Re-running heal is idempotent (no double-count).
  4. A subsequent scan with the SAME ghost UUID now resolves via the
     alias and increments the canonical counter on the fly.
"""

import asyncio
import os
import uuid

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

# Load .env so MONGO_URL/DB_NAME work when running this file directly.
from dotenv import load_dotenv  # type: ignore
load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
API = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()


async def main() -> None:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    api = httpx.AsyncClient(base_url=API.rstrip("/"), follow_redirects=False, timeout=20.0)

    ghost_id = str(uuid.uuid4())
    # Pick a real employee from qr_employees as the heal target.
    target = await db.qr_employees.find_one({}, {"_id": 0, "id": 1, "name": 1})
    assert target, "Need at least one qr_employees record"
    canonical_id = target["id"]
    canonical_name = target["name"]

    # Seed a test admin session and authenticate via Bearer header.
    admin_email = (os.environ.get("ALLOWED_ADMIN_EMAILS") or "owner@intheweedscollective.com").split(",")[0].strip()
    test_token = f"test-ghost-heal-{uuid.uuid4()}"
    test_user_id = f"test-admin-{uuid.uuid4()}"
    from datetime import datetime, timezone, timedelta
    await db.users.insert_one({
        "user_id": test_user_id,
        "email": admin_email,
        "name": "Test Admin",
    })
    await db.user_sessions.insert_one({
        "session_token": test_token,
        "user_id": test_user_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })
    api.headers["Authorization"] = f"Bearer {test_token}"

    before = await db.qr_employees.find_one({"id": canonical_id}, {"_id": 0})
    before_total = (before or {}).get("total_clicks") or 0
    print(f"Target: {canonical_name} ({canonical_id}), starting total_clicks={before_total}")

    # 1. Three scans against the ghost UUID.
    for _ in range(3):
        r = await api.get(f"/api/qr/go/{ghost_id}")
        assert r.status_code == 302, f"Expected 302, got {r.status_code}"

    # Counter should still be unchanged.
    mid = await db.qr_employees.find_one({"id": canonical_id}, {"_id": 0})
    assert (mid or {}).get("total_clicks", 0) == before_total, "Counter incremented for ghost — should be NO-OP"
    imm_count = await db.qr_click_log_immutable.count_documents(
        {"employee_id": ghost_id, "counter_applied": False}
    )
    assert imm_count == 3, f"Expected 3 unresolved immutable events, got {imm_count}"
    print(f"OK: 3 ghost scans logged, counter still {before_total}")

    # 2. Heal.
    res = await api.post(
        "/api/qr/admin/heal-ghost-ids",
        json={"mappings": [{"printed_id": ghost_id, "canonical_id": canonical_id}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["events_reattributed"] == 3, body
    assert body["employees_updated"] == 1, body
    print(f"OK: heal -> {body}")

    # Counter should have jumped by 3.
    after = await db.qr_employees.find_one({"id": canonical_id}, {"_id": 0})
    after_total = (after or {}).get("total_clicks") or 0
    assert after_total == before_total + 3, f"Expected total_clicks={before_total + 3}, got {after_total}"
    print(f"OK: counter back-filled to {after_total}")

    # Alias persisted.
    alias = await db.qr_employee_id_aliases.find_one({"printed_id": ghost_id}, {"_id": 0})
    assert alias and alias["canonical_id"] == canonical_id, alias
    print("OK: alias row persisted")

    # 3. Re-run heal — must NOT double count.
    res = await api.post(
        "/api/qr/admin/heal-ghost-ids",
        json={"mappings": [{"printed_id": ghost_id, "canonical_id": canonical_id}]},
    )
    assert res.status_code == 200, res.text
    body2 = res.json()
    assert body2["events_reattributed"] == 0, f"Idempotency broken: {body2}"
    again = await db.qr_employees.find_one({"id": canonical_id}, {"_id": 0})
    assert (again or {}).get("total_clicks", 0) == after_total, "Counter changed on idempotent re-run"
    print("OK: heal is idempotent (events_reattributed=0 on re-run)")

    # 4. Next scan with the same ghost UUID now resolves via alias.
    r = await api.get(f"/api/qr/go/{ghost_id}")
    assert r.status_code == 302
    fresh = await db.qr_employees.find_one({"id": canonical_id}, {"_id": 0})
    assert (fresh or {}).get("total_clicks", 0) == after_total + 1, "Live alias resolution failed"
    print("OK: live scan via alias incremented canonical counter")

    # Cleanup test artifacts so we don't leave preview noise.
    await db.qr_click_log_immutable.delete_many({"employee_id": ghost_id})
    await db.qr_scans.delete_many({"employee_id": ghost_id})
    await db.qr_employee_id_aliases.delete_many({"printed_id": ghost_id})
    # Reverse the increments we caused.
    await db.qr_employees.update_one(
        {"id": canonical_id},
        {"$inc": {"google_clicks": -4, "total_clicks": -4}},
    )
    print("\nAll ghost-heal tests passed ✓")

    # Clean up the test session.
    await db.user_sessions.delete_one({"session_token": test_token})
    await db.users.delete_one({"user_id": test_user_id})

    await api.aclose()
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
