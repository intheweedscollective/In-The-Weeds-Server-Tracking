"""
One-shot cleanup: remove Chase Winston and Ashley Jackson from production.
- Deletes them from employees_v2
- Removes them from snapshot.employees on every active (non-deleted) snapshot
- Adds their names to deleted_names blocklist on those snapshots
- Verifies and prints final state
"""

import asyncio
import os
import re
from motor.motor_asyncio import AsyncIOMotorClient


TARGETS = ["Chase Winston", "Ashley Jackson"]


def name_pat(name: str) -> dict:
    return {"$regex": f"^{re.escape(name)}$", "$options": "i"}


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "staff_score_db")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print("=" * 70)
    print(f"DB: {db_name}")
    print(f"Targets: {TARGETS}")
    print("=" * 70)

    # ---- BEFORE state ----
    print("\n[BEFORE] employees_v2:")
    for name in TARGETS:
        async for emp in db.employees_v2.find(
            {"$or": [
                {"name": name_pat(name)},
                {"display_name": name_pat(name)},
                {"report_name": name_pat(name)},
            ]},
            {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1, "display_name": 1},
        ):
            print(f"  {emp.get('name'):20s} | id={emp.get('id'):40s} | {emp.get('quarter')} {emp.get('year')}")

    print("\n[BEFORE] snapshot_workflow rows containing targets:")
    async for snap in db.snapshot_workflow.find(
        {"status": {"$ne": "deleted"}},
        {"id": 1, "name": 1, "quarter": 1, "year": 1, "status": 1, "is_current": 1,
         "employee_count": 1, "deleted_names": 1, "employees.name": 1, "_id": 0},
    ):
        hits = [
            e.get("name") for e in snap.get("employees", [])
            if (e.get("name") or "").lower() in {t.lower() for t in TARGETS}
        ]
        if hits:
            print(
                f"  {snap.get('name'):24s} {snap.get('quarter')} {snap.get('year')} "
                f"is_current={snap.get('is_current')} status={snap.get('status')} | "
                f"hits={hits} | blocklist={snap.get('deleted_names') or []}"
            )

    # ---- DELETE from employees_v2 ----
    print("\n[ACT] Deleting from employees_v2...")
    for name in TARGETS:
        r = await db.employees_v2.delete_many({
            "$or": [
                {"name": name_pat(name)},
                {"display_name": name_pat(name)},
                {"report_name": name_pat(name)},
            ]
        })
        print(f"  {name:20s} -> {r.deleted_count} row(s) deleted")

    # ---- Update snapshots ----
    print("\n[ACT] Pulling from snapshot.employees AND adding to deleted_names...")
    for name in TARGETS:
        # Pull matching rows out of every non-deleted snapshot
        pull_res = await db.snapshot_workflow.update_many(
            {"status": {"$ne": "deleted"}},
            {"$pull": {"employees": {
                "$or": [
                    {"name": name_pat(name)},
                    {"display_name": name_pat(name)},
                    {"report_name": name_pat(name)},
                ]
            }}},
        )
        # Add to deleted_names blocklist
        block_res = await db.snapshot_workflow.update_many(
            {"status": {"$ne": "deleted"}},
            {"$addToSet": {"deleted_names": name}},
        )
        print(
            f"  {name:20s} -> pulled from {pull_res.modified_count} snapshot(s), "
            f"blocklist updated on {block_res.modified_count} snapshot(s)"
        )

    # Recompute employee_count on every snapshot
    await db.snapshot_workflow.update_many(
        {"status": {"$ne": "deleted"}},
        [{"$set": {"employee_count": {"$size": {"$ifNull": ["$employees", []]}}}}],
    )

    # ---- AFTER state ----
    print("\n" + "=" * 70)
    print("[AFTER] Verification")
    print("=" * 70)

    print("\nemployees_v2:")
    found_any = False
    for name in TARGETS:
        async for emp in db.employees_v2.find(
            {"$or": [
                {"name": name_pat(name)},
                {"display_name": name_pat(name)},
                {"report_name": name_pat(name)},
            ]},
            {"_id": 0, "id": 1, "name": 1},
        ):
            print(f"  STILL PRESENT: {emp}")
            found_any = True
    if not found_any:
        print(f"  ✓ Both targets confirmed absent from employees_v2.")

    print("\nsnapshot_workflow:")
    leftover = False
    async for snap in db.snapshot_workflow.find(
        {"status": {"$ne": "deleted"}},
        {"id": 1, "name": 1, "quarter": 1, "year": 1, "is_current": 1, "status": 1,
         "employee_count": 1, "deleted_names": 1, "employees.name": 1, "_id": 0},
    ):
        hits = [
            e.get("name") for e in snap.get("employees", [])
            if (e.get("name") or "").lower() in {t.lower() for t in TARGETS}
        ]
        if hits:
            print(f"  STILL ON SNAPSHOT: {snap.get('name')} hits={hits}")
            leftover = True
        # Show the blocklist
        bl = snap.get("deleted_names") or []
        ts_in_bl = [t for t in TARGETS if any((b or "").lower() == t.lower() for b in bl)]
        if snap.get("is_current") or len(ts_in_bl) > 0:
            print(
                f"  {snap.get('name'):24s} | is_current={snap.get('is_current')} "
                f"emp_count={snap.get('employee_count')} | "
                f"blocklist contains: {ts_in_bl}"
            )
    if not leftover:
        print("  ✓ Both targets confirmed absent from every active snapshot.employees array.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
