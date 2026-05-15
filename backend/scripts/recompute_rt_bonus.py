"""
Recompute `review_tracker_bonus` everywhere it's stored to eliminate
the mentions-vs-bonus drift.

Per-quarter formula: review_tracker_bonus = min(mentions × coef, cap)
  where coef = quarter_settings.rt_points_per_mention (default 0.3)
        cap  = quarter_settings.rt_max_points (default 20.0)

Writes to:
  - employees_v2 (every row)
  - snapshot_workflow.employees[]   (every snapshot)
  - snapshot_workflow.rows[]        (Phase-3 thin rows; if present)
  - employees.current_metrics       (canonical, when quarter matches)

Idempotent. Safe to re-run.
"""

import asyncio
import os
from typing import Dict, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


def _bonus(mentions, coef, cap):
    try:
        return round(min((mentions or 0) * coef, cap), 2)
    except Exception:
        return 0.0


async def _load_quarter_coefs(db) -> Dict[Tuple[int, str], Tuple[float, float]]:
    """(year, quarter) → (coef, cap)"""
    out: Dict[Tuple[int, str], Tuple[float, float]] = {}
    async for s in db.quarter_settings.find({}, {"_id": 0}):
        y = s.get("year")
        q = (s.get("quarter") or "").upper()
        if not y or not q:
            continue
        coef = s.get("rt_points_per_mention", 0.3) or 0.3
        cap = s.get("rt_max_points", 20.0) or 20.0
        out[(y, q)] = (coef, cap)
    return out


async def recompute_employees_v2(db, coefs):
    updated = 0
    async for emp in db.employees_v2.find({}, {"_id": 0}):
        y = emp.get("year")
        q = (emp.get("quarter") or "").upper()
        coef, cap = coefs.get((y, q), (0.3, 20.0))
        m = emp.get("rt_mentions") or emp.get("review_mentions") or 0
        bonus = _bonus(m, coef, cap)
        stored = emp.get("review_tracker_bonus") or 0
        if abs(stored - bonus) >= 0.01:
            await db.employees_v2.update_one(
                {"id": emp["id"]},
                {"$set": {
                    "review_tracker_bonus": bonus,
                    "review_mentions": m,  # mirror for downstream readers
                }},
            )
            updated += 1
    return updated


async def recompute_snapshots(db, coefs):
    updated_rows = 0
    snapshots_touched = 0
    async for snap in db.snapshot_workflow.find({}, {"_id": 0}):
        y = snap.get("year")
        q = (snap.get("quarter") or "").upper()
        coef, cap = coefs.get((y, q), (0.3, 20.0))
        changed = False

        new_employees = []
        for e in snap.get("employees", []) or []:
            m = e.get("rt_mentions") or e.get("review_mentions") or 0
            bonus = _bonus(m, coef, cap)
            if abs((e.get("review_tracker_bonus") or 0) - bonus) >= 0.01:
                e = dict(e)
                e["review_tracker_bonus"] = bonus
                e["review_mentions"] = m
                changed = True
                updated_rows += 1
            new_employees.append(e)

        new_rows = []
        for r in snap.get("rows", []) or []:
            fm = dict(r.get("frozen_metrics") or {})
            m = fm.get("rt_mentions") or fm.get("review_mentions") or 0
            bonus = _bonus(m, coef, cap)
            if abs((fm.get("review_tracker_bonus") or 0) - bonus) >= 0.01:
                fm["review_tracker_bonus"] = bonus
                fm["review_mentions"] = m
                r = dict(r)
                r["frozen_metrics"] = fm
                changed = True
                updated_rows += 1
            new_rows.append(r)

        if changed:
            await db.snapshot_workflow.update_one(
                {"id": snap["id"]},
                {"$set": {"employees": new_employees, "rows": new_rows}},
            )
            snapshots_touched += 1
    return updated_rows, snapshots_touched


async def recompute_canonical(db, coefs):
    """Update employees.current_metrics.review_tracker_bonus when the
    canonical row's current_metrics quarter/year has a coefficient."""
    updated = 0
    async for emp in db.employees.find({}, {"_id": 0}):
        cm = emp.get("current_metrics") or {}
        y = cm.get("year")
        q = (cm.get("quarter") or "").upper()
        if not (y and q):
            continue
        coef, cap = coefs.get((y, q), (0.3, 20.0))
        m = cm.get("rt_mentions") or cm.get("review_mentions") or 0
        bonus = _bonus(m, coef, cap)
        if abs((cm.get("review_tracker_bonus") or 0) - bonus) >= 0.01:
            await db.employees.update_one(
                {"id": emp["id"]},
                {"$set": {
                    "current_metrics.review_tracker_bonus": bonus,
                    "current_metrics.review_mentions": m,
                }},
            )
            updated += 1
    return updated


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    coefs = await _load_quarter_coefs(db)
    print(f"Loaded {len(coefs)} (year, quarter) coefficient pairs.")

    v2 = await recompute_employees_v2(db, coefs)
    print(f"employees_v2 rows updated: {v2}")

    rows, snaps = await recompute_snapshots(db, coefs)
    print(f"snapshot_workflow rows updated: {rows} across {snaps} snapshot doc(s).")

    canon = await recompute_canonical(db, coefs)
    print(f"canonical employees.current_metrics updated: {canon}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
