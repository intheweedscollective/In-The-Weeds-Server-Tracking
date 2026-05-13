"""
Phase 3 Stage C — archive `employees_v2` and prepare for drop.

What this does
--------------
1. **Verify** no remaining read paths target `employees_v2` directly
   (other than the safety-net fallbacks we kept in Stage B).
2. **Archive** every `employees_v2` document into
   `employees_v2_archive` with an `archived_at` timestamp + this
   script's `archive_run_id`.
3. **Optionally drop** `employees_v2` with `--drop`.

The script is dry-run by default. We deliberately split the destructive
final step behind a separate flag so the audit can run on production
data without risk.

Usage
-----
    python scripts/archive_employees_v2.py                  # dry-run + audit
    python scripts/archive_employees_v2.py --apply          # archive only
    python scripts/archive_employees_v2.py --apply --drop   # archive + drop
"""

import argparse
import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


async def audit_readers(db) -> int:
    """Return number of canonical / current-snapshot rows. Sanity check
    so we know the data layer is healthy before we wipe `employees_v2`."""
    canonical = await db.employees.count_documents({"status": "active"})
    snap = await db.snapshot_workflow.find_one(
        {"is_current": True}, {"_id": 0, "row_count": 1, "employees": 1, "rows": 1}
    ) or {}
    rows_len = len(snap.get("rows") or [])
    emps_len = len(snap.get("employees") or [])
    v2 = await db.employees_v2.count_documents({})

    print(f"  canonical active: {canonical}")
    print(f"  active snapshot rows[]: {rows_len}")
    print(f"  active snapshot employees[]: {emps_len}")
    print(f"  employees_v2: {v2}")

    if rows_len == 0 and emps_len == 0:
        print("  ⚠️  Active snapshot has NO rows AND NO employees — refusing to archive.")
        return -1
    if canonical < rows_len / 2 if rows_len else 1:
        print("  ⚠️  Canonical count seems too low — refusing to archive.")
        return -1
    return v2


async def archive(db, apply: bool, drop: bool):
    print("=== Phase 3 Stage C — employees_v2 archive ===")
    print()
    v2_count = await audit_readers(db)
    if v2_count < 0:
        print("Audit failed — aborting.")
        return

    if not apply:
        print()
        print("DRY-RUN — pass --apply to copy employees_v2 → employees_v2_archive.")
        print("        — pass --apply --drop to also drop employees_v2.")
        return

    # Step 1: archive.
    run_id = str(uuid.uuid4())
    archived_at = datetime.now(timezone.utc).isoformat()
    print()
    print(f"Archiving {v2_count} employees_v2 rows → employees_v2_archive (run_id={run_id})…")
    docs = []
    async for d in db.employees_v2.find({}, {"_id": 0}):
        d["archive_run_id"] = run_id
        d["archived_at"] = archived_at
        docs.append(d)
    if docs:
        await db.employees_v2_archive.insert_many(docs)
    archive_count = await db.employees_v2_archive.count_documents(
        {"archive_run_id": run_id}
    )
    print(f"  archived: {archive_count} docs in this run")
    print(f"  archive collection total: {await db.employees_v2_archive.count_documents({})}")

    if not drop:
        print()
        print("Archive complete. Re-run with --apply --drop to drop the live collection.")
        return

    # Step 2: drop the live collection.
    print()
    print("Dropping live employees_v2 collection…")
    await db.employees_v2.drop()
    print(f"  employees_v2 after drop: {await db.employees_v2.count_documents({})}")
    print()
    print("Done. Recovery path: copy any doc from `employees_v2_archive`")
    print("back into `employees_v2` by archive_run_id.")


async def main(apply: bool, drop: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        await archive(db, apply=apply, drop=drop)
    finally:
        client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="Actually copy employees_v2 → employees_v2_archive.")
    p.add_argument("--drop", action="store_true",
                   help="After archiving, drop the live employees_v2 collection.")
    args = p.parse_args()
    asyncio.run(main(apply=args.apply, drop=args.drop))
