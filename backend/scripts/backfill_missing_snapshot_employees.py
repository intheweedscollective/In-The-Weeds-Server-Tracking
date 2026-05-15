"""
Backfill: copy employees that exist in employees_v2 for Q2 2026 but are
missing from the active snapshot.employees array back into the snapshot.

Caused by: manual "Add Employee" calls made before today's code change that
auto-pushes new employees into the current snapshot.
"""

import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ.get("DB_NAME", "staff_score_db")]

    snap = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": "Q2", "year": 2026}
    )
    if not snap:
        print("No current Q2 2026 snapshot found")
        return

    snap_id = snap["_id"]
    snap_emp_keys = {((e.get("name") or "").lower(), e.get("id")) for e in snap.get("employees", [])}
    snap_names = {k[0] for k in snap_emp_keys}
    snap_ids = {k[1] for k in snap_emp_keys if k[1]}

    to_add = []
    async for e in db.employees_v2.find({"quarter": "Q2", "year": 2026}, {"_id": 0}):
        name = (e.get("name") or "").lower()
        eid = e.get("id")
        if not name:
            continue
        # Already present?
        if name in snap_names or (eid and eid in snap_ids):
            continue
        # Defensive defaults so slide / ranking pages don't break.
        e.setdefault("display_name", e.get("name"))
        e.setdefault("report_name", e.get("name"))
        e.setdefault("cv_promoters", 0)
        e.setdefault("cv_passives", 0)
        e.setdefault("cv_detractors", 0)
        e.setdefault("cv_score", 0)
        e.setdefault("nps_score", 0)
        e.setdefault("rt_mentions", 0)
        e.setdefault("review_tracker_bonus", 0)
        e.setdefault("total_metric_bonus", 0)
        e.setdefault("dar_penalty", 0)
        to_add.append(e)

    print(f"To add to snapshot: {len(to_add)}")
    for e in to_add:
        print(f"  {e.get('name')} (id={e.get('id')}, ppa={e.get('ppa')}, guests={e.get('guest_count')})")

    if not to_add:
        print("Nothing to do.")
        return

    await db.snapshot_workflow.update_one(
        {"_id": snap_id},
        {
            "$push": {"employees": {"$each": to_add}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
        },
    )
    await db.snapshot_workflow.update_one(
        {"_id": snap_id},
        [{"$set": {"employee_count": {"$size": {"$ifNull": ["$employees", []]}}}}],
    )

    after = await db.snapshot_workflow.find_one({"_id": snap_id}, {"employee_count": 1, "_id": 0})
    print(f"Snapshot now has {after.get('employee_count')} employees.")
    c.close()


if __name__ == "__main__":
    asyncio.run(main())
