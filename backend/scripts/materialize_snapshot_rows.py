"""
Phase 3 — Stage A migration.

For every snapshot in `snapshot_workflow`, build the thin `rows[]`
array from the legacy `employees[]` array. Uses
`EmployeeService.materialize_rows_from_employees` which:

  - resolves each embedded row to canonical via id / legacy_id / name /
    alias,
  - emits a `SnapshotEmployeeRow` with `employee_id` (FK) +
    `frozen_metrics/score/tier/rank`,
  - leaves `employees[]` intact (additive only — Stage A).

Idempotent. Safe to re-run after every snapshot mutation.

Usage:
    python scripts/materialize_snapshot_rows.py             # dry-run
    python scripts/materialize_snapshot_rows.py --apply     # commit
    python scripts/materialize_snapshot_rows.py --apply --snapshot-id <id>
"""

import argparse
import asyncio
import os
from typing import Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


async def main(apply: bool, snapshot_id: Optional[str]):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    from services.employee_service import EmployeeService
    svc = EmployeeService(db)

    query = {"id": snapshot_id} if snapshot_id else {}
    snapshots = [s async for s in db.snapshot_workflow.find(query, {"_id": 0})]
    print(f"Snapshots in scope: {len(snapshots)}")

    total_rows = 0
    total_unmatched = 0
    for snap in snapshots:
        embedded = snap.get("employees") or []
        # Dry-run: simulate the resolution without writing.
        if not apply:
            # Count unmatched up front so the dry-run is informative.
            by_id: dict = {}
            by_name: dict = {}
            async for c in db.employees.find({}, {"_id": 0}):
                cid = c.get("id")
                if cid:
                    by_id[cid] = c
                for lid in c.get("legacy_ids") or []:
                    by_id[lid] = c
                for n in [c.get("name"), c.get("display_name"),
                          c.get("report_name"), *(c.get("aliases") or [])]:
                    k = (n or "").strip().lower()
                    if k:
                        by_name.setdefault(k, c)
            matched = sum(
                1 for e in embedded
                if (by_id.get(e.get("id"))
                    or by_name.get((e.get("name") or "").strip().lower())
                    or by_name.get((e.get("display_name") or "").strip().lower()))
            )
            unmatched = len(embedded) - matched
            total_rows += matched
            total_unmatched += unmatched
            print(f"  {snap.get('quarter','?')} {snap.get('year','?')} "
                  f"(is_current={snap.get('is_current')}, "
                  f"status={snap.get('status')}, "
                  f"id={snap.get('id', '')[:8]}…): "
                  f"embedded={len(embedded)}  would-materialize={matched}  "
                  f"unmatched={unmatched}")
            continue

        count = await svc.materialize_rows_from_employees(snap)
        unmatched = len(embedded) - count
        total_rows += count
        total_unmatched += unmatched
        print(f"  {snap.get('quarter','?')} {snap.get('year','?')} "
              f"(id={snap.get('id', '')[:8]}…): "
              f"materialized {count}/{len(embedded)} rows "
              f"(unmatched={unmatched})")

    print()
    print(f"TOTAL rows materialized: {total_rows}")
    print(f"TOTAL unmatched:         {total_unmatched}")
    if not apply:
        print()
        print("DRY-RUN — no writes. Re-run with --apply to commit.")
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--snapshot-id", default=None,
                   help="Only materialize this snapshot id")
    args = p.parse_args()
    asyncio.run(main(apply=args.apply, snapshot_id=args.snapshot_id))
