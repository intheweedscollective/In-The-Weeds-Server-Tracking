"""
One-shot maintenance script: collapse `employees_v2` duplicates that
share the same (name_normalized, quarter, year) tuple.

`name_normalized` is defined as `name.strip().upper()` — this is the
exact uniqueness contract the new upsert pattern + compound unique
index will enforce going forward.

For each (name_normalized, quarter, year) bucket with >1 rows:
  1. Pick a winner = highest `total_score`, tiebreak on most non-zero
     metric fields, then earliest `created_at`.
  2. For every non-zero field on a loser that is null/0/missing on the
     winner, copy it into the winner.
  3. Rewrite every `snapshot_workflow.rows[]` and `.employees[]` entry
     that references a loser's `id` so it points at the winner's id +
     name. Snapshot integrity (frozen rows) is preserved — finalized
     snapshots are explicitly skipped per system guarantees.
  4. Delete losers from `employees_v2`.

Also backfills `name_normalized` on every row (including singletons)
so the unique index can be created safely after this script runs.

Usage:
  Dry-run (default — prints plan, writes nothing):
    cd /app/backend && python3 -m scripts.dedupe_by_name_quarter_year

  Apply:
    cd /app/backend && python3 -m scripts.dedupe_by_name_quarter_year --apply
"""

import argparse
import asyncio
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

# Fields treated as "non-zero" for the merge step. If a winner has 0
# or None in any of these and a loser has a non-zero value, the loser's
# value is copied onto the winner.
MERGEABLE_FIELDS = (
    "guest_count", "guests", "net_sales", "food_sales", "liquor_sales",
    "beer_sales", "wine_sales", "lbw_total", "lbw", "bar_glassware_sales",
    "glassware_sales", "loyalty_sales", "lsc_count", "ppa", "lbw_per_guest",
    "glassware_per_guest", "guests_per_lsc", "rt_mentions",
    "review_tracker_bonus", "cv_score", "cv_promoters", "cv_detractors",
    "nps_score", "total_score", "pre_dar_score", "peer_rank",
    "display_name", "report_name", "job_title", "tier_label",
)

# These fields are arrays we want to UNION across the duplicates rather
# than overwrite. Aliases especially are critical — typo-name spellings
# from losers should survive as aliases on the winner so future POS
# uploads under those spellings still route to the canonical row.
UNION_FIELDS = ("aliases", "legacy_ids")


def _normalize(name: Optional[str]) -> str:
    return (name or "").strip().upper()


def _richness(doc: Dict[str, Any]) -> int:
    return sum(1 for f in MERGEABLE_FIELDS if doc.get(f))


def _pick_winner(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Highest total_score → most non-zero fields → earliest created_at."""
    def key(d):
        return (
            -(d.get("total_score") or 0),     # higher score first
            -_richness(d),                    # richer doc next
            (d.get("created_at") or ""),      # older row last
        )
    return sorted(rows, key=key)[0]


def _merged_payload(winner: Dict[str, Any],
                    losers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the $set payload that copies non-zero loser fields onto
    the winner, and union-merges aliases/legacy_ids."""
    payload: Dict[str, Any] = {}
    for f in MERGEABLE_FIELDS:
        w_val = winner.get(f)
        if w_val:
            continue  # winner already has it — never overwrite
        for L in losers:
            l_val = L.get(f)
            if l_val:
                payload[f] = l_val
                break
    # Union arrays.
    for f in UNION_FIELDS:
        bag = list(winner.get(f) or [])
        seen = {(x.lower() if isinstance(x, str) else x) for x in bag}
        for L in losers:
            # Also collect the loser's display/report name + the raw
            # `name` field into the alias bag so the typo spelling
            # survives and re-routes future uploads to the winner.
            extras = []
            if f == "aliases":
                for k in ("name", "display_name", "report_name"):
                    v = L.get(k)
                    if v and v.strip() and v != winner.get("name"):
                        extras.append(v.strip())
                extras.extend(list(L.get("aliases") or []))
            else:
                extras = list(L.get(f) or [])
            for x in extras:
                key = x.lower() if isinstance(x, str) else x
                if key not in seen:
                    bag.append(x)
                    seen.add(key)
        if bag != (winner.get(f) or []):
            payload[f] = bag
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


async def _rewrite_snapshot_refs(db, loser_ids: List[str],
                                 winner_id: str, winner_name: str,
                                 apply: bool) -> Tuple[int, int]:
    """For every NON-finalized snapshot, rewrite embedded rows[] /
    employees[] entries that reference any of `loser_ids` so they
    point at the winner. Finalized snapshots are immutable historical
    record and are skipped.

    Returns (snapshots_touched, rows_rewritten)."""
    snapshots_touched = 0
    rows_rewritten = 0
    async for snap in db.snapshot_workflow.find(
        {"status": {"$ne": "finalized"}},
        {"_id": 1, "rows": 1, "employees": 1},
    ):
        changed = False
        new_rows = []
        for r in (snap.get("rows") or []):
            if r.get("employee_id") in loser_ids:
                r = {**r, "employee_id": winner_id,
                     "frozen_display_name": winner_name}
                changed = True
                rows_rewritten += 1
            new_rows.append(r)
        new_emps = []
        for e in (snap.get("employees") or []):
            if e.get("id") in loser_ids:
                e = {**e, "id": winner_id, "name": winner_name}
                changed = True
            new_emps.append(e)
        if changed:
            snapshots_touched += 1
            if apply:
                await db.snapshot_workflow.update_one(
                    {"_id": snap["_id"]},
                    {"$set": {
                        "rows": new_rows,
                        "employees": new_emps,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
    return snapshots_touched, rows_rewritten


async def run(apply: bool) -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # ----- Stage 1: backfill name_normalized everywhere -----
    print("\n=== Stage 1: backfill name_normalized ===")
    missing = 0
    async for row in db.employees_v2.find(
        {"name_normalized": {"$exists": False}},
        {"_id": 1, "name": 1},
    ):
        missing += 1
        if apply:
            await db.employees_v2.update_one(
                {"_id": row["_id"]},
                {"$set": {"name_normalized": _normalize(row.get("name"))}},
            )
    print(f"  rows missing name_normalized: {missing}")
    if apply:
        # Also normalize rows where name_normalized exists but is stale
        # (e.g. someone renamed the row but didn't update the
        # normalized form yet).
        rebuilt = 0
        async for row in db.employees_v2.find(
            {}, {"_id": 1, "name": 1, "name_normalized": 1},
        ):
            expected = _normalize(row.get("name"))
            if row.get("name_normalized") != expected:
                rebuilt += 1
                await db.employees_v2.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"name_normalized": expected}},
                )
        print(f"  rows with stale name_normalized rebuilt: {rebuilt}")

    # ----- Stage 2: group by (name_normalized, quarter, year) -----
    print("\n=== Stage 2: detect duplicate buckets ===")
    buckets: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = defaultdict(list)
    async for r in db.employees_v2.find({}, {"_id": 0}):
        key = (_normalize(r.get("name")), r.get("quarter"), r.get("year"))
        if not key[0] or not key[1] or not key[2]:
            continue  # skip rows missing name/quarter/year — they can't
                      # safely participate in the unique index
        buckets[key].append(r)

    dupes = {k: v for k, v in buckets.items() if len(v) > 1}
    print(f"  unique buckets: {len(buckets)}")
    print(f"  buckets with duplicates: {len(dupes)}")

    if not dupes:
        print("\nNo duplicates to collapse. ✅")
        return

    # ----- Stage 3: collapse each duplicate bucket -----
    print("\n=== Stage 3: collapse duplicates ===")
    total_losers = 0
    total_snap_touch = 0
    total_snap_rows = 0
    for (nn, q, y), rows in sorted(dupes.items()):
        winner = _pick_winner(rows)
        losers = [r for r in rows if r["id"] != winner["id"]]
        total_losers += len(losers)
        payload = _merged_payload(winner, losers)
        loser_ids = [L["id"] for L in losers]

        print(f"  [{nn}] {q}/{y}: {len(rows)} rows → keep id={winner['id'][:8]}"
              f"  (score={winner.get('total_score')!r:>5})  drop {len(losers)}")
        for L in losers:
            print(f"     - drop id={L['id'][:8]}  score={L.get('total_score')!r:>5}"
                  f"  rich={_richness(L)}")
        if payload:
            print(f"     merge $set fields: {sorted(payload.keys())}")

        snap_touch, snap_rows = await _rewrite_snapshot_refs(
            db, loser_ids, winner["id"], winner.get("name", ""), apply,
        )
        total_snap_touch += snap_touch
        total_snap_rows += snap_rows
        if snap_touch:
            print(f"     snapshots updated: {snap_touch} (rows rewritten: {snap_rows})")

        if apply:
            if payload:
                await db.employees_v2.update_one(
                    {"id": winner["id"]}, {"$set": payload}
                )
            await db.employees_v2.delete_many({"id": {"$in": loser_ids}})

    # ----- Summary -----
    print("\n=== Summary ===")
    print(f"  duplicate buckets collapsed: {len(dupes)}")
    print(f"  loser rows deleted:          {total_losers}")
    print(f"  non-finalized snapshots touched: {total_snap_touch}")
    print(f"  snapshot rows rewritten:     {total_snap_rows}")
    if not apply:
        print("\n(DRY RUN — re-run with --apply to commit.)")
    else:
        print("\nDONE. You can now create the unique index:")
        print('  await db.employees_v2.create_index('
              '[("name_normalized", 1), ("quarter", 1), ("year", 1)], '
              'unique=True)')


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="Commit changes (default is dry-run).")
    args = p.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
