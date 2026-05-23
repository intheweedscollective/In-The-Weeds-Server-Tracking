"""
One-shot maintenance script: collapse duplicate `employees_v2` rows
that have different `id`s but the same canonical employee.

Why this matters
----------------
The Q2P5W2.75 prod bug exposed that `employees_v2` still carries dupe
rows from the legacy Phase-1 migration. Example (preview):
  - id=25fc877b...  name="Lakeisha Martin"  display="Keisha Martin"  rt_mentions=0
  - id=29acf3c5...  name="Keisha Martin"    display="Keisha Martin"  rt_mentions=20

The canonical `employees` record for Keisha has the UUID 29acf3c5... and
lists "Lakeisha Martin" as an alias. So the 25fc877b row is an orphan
duplicate — same person, different id, drifted data.

This script:
  1. Loads every canonical `employees` doc and builds a name → canonical
     id map covering name + aliases + legacy_ids.
  2. Walks `employees_v2`. For each row whose `id` matches a canonical
     `legacy_id` (or whose name matches a canonical alias), it rewrites
     the row's `id` to the canonical id.
  3. After all rewrites, groups rows by (canonical_id, quarter, year)
     and collapses duplicates — keeping the row with the highest
     `total_score` (or the most non-zero metric fields when tied) and
     deleting the rest.

Run with `--apply` to commit; default is dry-run.

Usage:
  cd /app/backend && python3 -m scripts.dedupe_employees_v2 --apply
"""

import argparse
import asyncio
import os
from typing import Dict, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

# Metric fields used as a "richness" tiebreaker when collapsing dupes.
RICH_FIELDS = (
    "rt_mentions", "cv_score", "nps_score", "cv_promoters", "cv_detractors",
    "guest_count", "lsc_count", "ppa", "total_score", "review_tracker_bonus",
)


def _richness_score(doc: dict) -> int:
    """Count of non-zero metric fields. Higher = keep this row."""
    return sum(1 for f in RICH_FIELDS if (doc.get(f) or 0))


async def main(apply: bool):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    # 1. canonical lookup
    name_to_canonical_id: Dict[str, str] = {}
    legacy_id_to_canonical_id: Dict[str, str] = {}
    async for ce in db.employees.find({}, {"_id": 0, "id": 1, "name": 1, "aliases": 1, "legacy_ids": 1}):
        cid = ce.get("id")
        if not cid:
            continue
        for n in [ce.get("name")] + (ce.get("aliases") or []):
            k = (n or "").strip().lower()
            if k:
                name_to_canonical_id.setdefault(k, cid)
        for lid in ce.get("legacy_ids") or []:
            if lid:
                legacy_id_to_canonical_id.setdefault(lid, cid)

    print(f"Loaded {len(name_to_canonical_id)} name→canonical entries and {len(legacy_id_to_canonical_id)} legacy_id→canonical entries")

    # 2. Walk v2 rows, build rewrite list
    rewrites = []  # (v2_doc_id, current_id, new_canonical_id, name)
    async for v2 in db.employees_v2.find({}, {"_id": 0, "id": 1, "name": 1, "display_name": 1, "report_name": 1}):
        cur_id = v2.get("id")
        for nm in (v2.get("name"), v2.get("display_name"), v2.get("report_name")):
            k = (nm or "").strip().lower()
            cid = name_to_canonical_id.get(k) or legacy_id_to_canonical_id.get(cur_id or "")
            if cid and cid != cur_id:
                rewrites.append((cur_id, cid, nm))
                break

    print(f"Found {len(rewrites)} v2 rows whose id should be rewritten to a canonical id")

    if apply:
        for cur_id, new_cid, nm in rewrites:
            res = await db.employees_v2.update_one(
                {"id": cur_id},
                {"$set": {"id": new_cid}}
            )
            if res.modified_count:
                print(f"  rewrote {cur_id} → {new_cid}  ({nm})")

    # 3. Find duplicates per (id, quarter, year)
    grouped: Dict[Tuple[str, str, int], list] = {}
    async for v2 in db.employees_v2.find({}, {"_id": 1, "id": 1, "quarter": 1, "year": 1,
                                              "name": 1, "display_name": 1,
                                              "rt_mentions": 1, "cv_score": 1, "nps_score": 1,
                                              "cv_promoters": 1, "cv_detractors": 1,
                                              "guest_count": 1, "lsc_count": 1,
                                              "ppa": 1, "total_score": 1, "review_tracker_bonus": 1}):
        key = (v2.get("id"), (v2.get("quarter") or "").upper(), v2.get("year"))
        grouped.setdefault(key, []).append(v2)

    delete_ids = []
    for key, docs in grouped.items():
        if len(docs) <= 1:
            continue
        docs.sort(key=lambda d: (d.get("total_score") or 0, _richness_score(d)), reverse=True)
        keep = docs[0]
        for d in docs[1:]:
            delete_ids.append(d["_id"])
            print(f"  collapse {d.get('name')} {key[1]}{key[2]}: keep _id={keep['_id']} drop _id={d['_id']} (richness {_richness_score(d)})")

    print(f"\n{'DRY-RUN ' if not apply else ''}Total dupes to drop: {len(delete_ids)}")
    if apply and delete_ids:
        res = await db.employees_v2.delete_many({"_id": {"$in": delete_ids}})
        print(f"Deleted {res.deleted_count} dupe v2 rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
