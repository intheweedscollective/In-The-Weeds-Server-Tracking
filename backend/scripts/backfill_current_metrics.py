"""
Backfill `employees.current_metrics` from the active snapshot for the
specified quarter/year (defaults: most-recent active snapshot).

Purpose
-------
Canonical employees carry a `current_metrics` dict (cv_score,
rt_mentions, review_tracker_bonus, total_score, …) that gets read by
the integrity gate, the admin "Most Improved" widget, and several
debug routes. After every fresh POS / CV / RT upload the snapshot is
the authoritative source — but `current_metrics` is denormalized and
gets stale. The `/api/v2/admin/integrity` `metric_drift` array surfaces
this drift.

This script syncs `current_metrics` from the snapshot's embedded rows.
Idempotent. Safe to re-run.

Usage
-----
    python scripts/backfill_current_metrics.py             # dry-run
    python scripts/backfill_current_metrics.py --apply
    python scripts/backfill_current_metrics.py --apply --year 2026 --quarter Q2
"""

import argparse
import asyncio
import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


METRIC_KEYS = (
    "cv_score",
    "nps_score",
    "cv_promoters",
    "cv_passives",
    "cv_detractors",
    "rt_mentions",
    "review_mentions",
    "review_tracker_bonus",
    "ppa",
    "lbw_percentage",
    "glassware_sales",
    "lsc_percentage",
    "total_score",
    "total_metric_bonus",
    "bonus_ppa",
    "bonus_lbw",
    "bonus_glass",
    "bonus_lsc",
    "tier_label",
    "rank",
    "guests",
    "guest_count",
    "net_sales",
)


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


async def main(apply: bool, year: Optional[int], quarter: Optional[str]):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Pick the snapshot to sync from.
    snap_query: Dict[str, Any] = {"is_current": True}
    if year:
        snap_query["year"] = year
    if quarter:
        snap_query["quarter"] = quarter.upper()
    snap = await db.snapshot_workflow.find_one(snap_query, {"_id": 0})

    if not snap:
        # Fallback: most recently completed snapshot.
        fallback_q: Dict[str, Any] = {"status": "completed"}
        if year:
            fallback_q["year"] = year
        if quarter:
            fallback_q["quarter"] = quarter.upper()
        snap = await db.snapshot_workflow.find_one(
            fallback_q, {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)],
        )

    if not snap or not snap.get("employees"):
        print("No snapshot with embedded employees found. Nothing to backfill.")
        client.close()
        return

    quarter_label = snap.get("quarter")
    year_label = snap.get("year")
    print(f"Snapshot: {snap.get('name') or snap.get('id')}  "
          f"({quarter_label} {year_label}, "
          f"is_current={snap.get('is_current')}, status={snap.get('status')})")

    # Build canonical index (id OR name OR alias → canonical row).
    canonicals = [c async for c in db.employees.find({}, {"_id": 0})]
    by_id: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for c in canonicals:
        cid = c.get("id")
        if cid:
            by_id[cid] = c
        for lid in c.get("legacy_ids") or []:
            by_id[lid] = c
        for n in [c.get("name"), c.get("display_name"),
                  c.get("report_name"), *(c.get("aliases") or [])]:
            k = _norm(n)
            if k:
                by_name.setdefault(k, c)

    updates = []   # list of (canonical_id, name, current_metrics_dict)
    unmatched = []
    for emp in snap.get("employees", []) or []:
        canon = (by_id.get(emp.get("id"))
                 or by_name.get(_norm(emp.get("name")))
                 or by_name.get(_norm(emp.get("display_name"))))
        if not canon:
            unmatched.append(emp.get("name") or emp.get("id"))
            continue
        cm = {k: emp.get(k) for k in METRIC_KEYS if k in emp and emp.get(k) is not None}
        if not cm:
            continue
        cm["quarter"] = quarter_label
        cm["year"] = year_label
        updates.append((canon["id"], canon.get("name"), cm))

    print(f"  canonical employees indexed:    {len(canonicals)}")
    print(f"  snapshot rows mapped to canonical: {len(updates)}")
    print(f"  unmatched snapshot rows:        {len(unmatched)}")
    if unmatched:
        for n in unmatched[:10]:
            print(f"    - {n}")
        if len(unmatched) > 10:
            print(f"    … +{len(unmatched) - 10} more")

    if not apply:
        # Preview a few proposed updates.
        print()
        print("Sample writes (first 5):")
        for cid, name, cm in updates[:5]:
            keys = {k: v for k, v in cm.items()
                    if k in ("cv_score", "rt_mentions", "review_tracker_bonus", "total_score")}
            print(f"  - {name}: {keys}")
        print()
        print("DRY-RUN — no writes. Re-run with --apply to commit.")
        client.close()
        return

    # Apply.
    written = 0
    for cid, name, cm in updates:
        res = await db.employees.update_one(
            {"id": cid},
            {"$set": {"current_metrics": cm}},
        )
        if res.modified_count or res.matched_count:
            written += 1
    print()
    print(f"Wrote current_metrics on {written} canonical employee(s).")
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--quarter", default=None)
    args = p.parse_args()
    asyncio.run(main(apply=args.apply, year=args.year, quarter=args.quarter))
