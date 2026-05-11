"""
Recompute qr_employees click counters from the raw qr_scans event log.

Use this any time the per-employee counters drift from reality (e.g. when
the `/r/{id}` short-url path inserts a raw scan but doesn't increment the
counter, or when a stale Reset wiped the counters without removing the
events first).

Reads MONGO_URL / DB_NAME from environment. Safe to re-run.
"""

import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "staff_score_db")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Aggregate per (employee_id, platform).
    pipeline = [
        {
            "$group": {
                "_id": {"emp": "$employee_id", "platform": "$platform"},
                "count": {"$sum": 1},
                "last": {"$max": "$scanned_at"},
            }
        }
    ]

    counts: dict[str, dict] = {}
    async for row in db.qr_scans.aggregate(pipeline):
        emp_id = row["_id"]["emp"]
        platform = (row["_id"]["platform"] or "google").lower()
        if not emp_id:
            continue
        entry = counts.setdefault(emp_id, {})
        if platform in {"google", "yelp", "tripadvisor"}:
            entry[f"{platform}_clicks"] = row["count"]
        last = row["last"]
        if last and last > entry.get("last_scan_at", ""):
            entry["last_scan_at"] = last

    print(f"Found scan data for {len(counts)} distinct employee ids.")

    # First zero everything so deleted scans don't leave stale counts.
    await db.qr_employees.update_many(
        {},
        {"$set": {"google_clicks": 0, "yelp_clicks": 0, "tripadvisor_clicks": 0}},
    )

    # Then write fresh values + total_clicks.
    updated = 0
    orphan = 0
    for emp_id, entry in counts.items():
        google = entry.get("google_clicks", 0)
        yelp = entry.get("yelp_clicks", 0)
        ta = entry.get("tripadvisor_clicks", 0)
        total = google + yelp + ta
        update = {
            "google_clicks": google,
            "yelp_clicks": yelp,
            "tripadvisor_clicks": ta,
            "total_clicks": total,
        }
        if entry.get("last_scan_at"):
            update["last_scan_at"] = entry["last_scan_at"]

        r = await db.qr_employees.update_one({"id": emp_id}, {"$set": update})
        if r.matched_count:
            updated += 1
        else:
            orphan += 1
            print(f"  WARN: scan events for id={emp_id} but no matching qr_employees row")

    # Also stamp total_clicks=0 on employees with no scans (keeps responses clean).
    await db.qr_employees.update_many(
        {"total_clicks": {"$exists": False}},
        {"$set": {"total_clicks": 0}},
    )

    print(f"Recomputed counters for {updated} qr_employees rows (orphans: {orphan}).")

    print("\nTop 10 by total_clicks after rebuild:")
    async for e in db.qr_employees.find({}, {"_id": 0, "name": 1, "total_clicks": 1, "google_clicks": 1, "yelp_clicks": 1, "tripadvisor_clicks": 1, "last_scan_at": 1}).sort("total_clicks", -1).limit(10):
        print(
            f"  {e.get('name','?'):25s} | total={e.get('total_clicks', 0)} | "
            f"g={e.get('google_clicks', 0)} y={e.get('yelp_clicks', 0)} t={e.get('tripadvisor_clicks', 0)} | "
            f"last={e.get('last_scan_at') or '—'}"
        )

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
