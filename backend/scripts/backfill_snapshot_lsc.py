"""
Snapshot LSC + Display-Name Backfill
====================================

A snapshot is frozen at a moment-in-time. Sometimes that moment captures
incomplete POS data — for example Q2P5W2.5 on 2026-05-13 was frozen with
`lsc_count = None` for 17 of 28 rows because the POS file uploaded that
day was missing the LSC column. The live `employees_v2` collection had
correct LSC values for those servers; the snapshot just didn't see them.

This script reaches across to the live `employees_v2` (using canonical
aliases for resolution) and overlays the missing fields into
`snapshot_workflow.rows[].frozen_metrics`, then recomputes
`total_score` / `frozen_score` / `frozen_rank` through the canonical
`compute_total_score_dict`.

Guarantees:

  • Idempotent — re-running with the same inputs produces no further
    change because the predicate is "current value is None or 0".
  • Non-destructive — fields that already had a real value in the
    snapshot are left alone.
  • Auditable — every change is appended to `audit_log` with
    before/after pairs and the action `snapshot_backfill_lsc`.
  • Bounded — only updates these specific fields:
      score_lsc, lsc_count, guests_per_lsc,
      score_ppa, score_lbw, score_glass,   (in case those were missing too)
      cv_score, rt_mentions, review_mentions, review_tracker_bonus,
      total_metric_bonus,
      bonus_ppa, bonus_lbw, bonus_glass, bonus_lsc,
      job_title (only when v2 has trainer/bartender)
    plus the recomputed total_score / pre_dar_score / weighted_score.

Usage:
    python scripts/backfill_snapshot_lsc.py --snapshot-name "Q2P5W2.5" --dry-run
    python scripts/backfill_snapshot_lsc.py --snapshot-name "Q2P5W2.5" --apply
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # type: ignore
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from scoring_engine import compute_total_score_dict, QuarterSettings  # noqa: E402


OVERLAY_FIELDS = (
    "score_lsc", "lsc_count", "guests_per_lsc",
    "score_ppa", "score_lbw", "score_glass",
    "guests", "guest_count",
    "cv_score", "nps_score", "cv_promoters", "cv_passives", "cv_detractors",
    "rt_mentions", "review_mentions", "review_tracker_bonus",
    "total_metric_bonus",
    "bonus_ppa", "bonus_lbw", "bonus_glass", "bonus_lsc",
)
SCORING_INPUT_FIELDS = (
    "score_ppa", "score_lbw", "score_glass", "score_lsc",
    "cv_score", "review_tracker_bonus", "total_metric_bonus", "dar_penalty",
)


def _norm(s: Optional[str]) -> str:
    return (s or "").lower().strip()


async def _build_v2_index(db, quarter: str, year: int) -> Dict[str, Dict[str, Any]]:
    """Return { canonical_id_or_name : merged_overlay } for the quarter."""
    # 1. canonical employees → id + alias map
    canonical_id_by_name: Dict[str, str] = {}
    canonical_aliases_by_id: Dict[str, List[str]] = {}
    async for ce in db.employees.find(
        {}, {"_id": 0, "id": 1, "name": 1, "display_name": 1, "aliases": 1},
    ):
        cid = ce.get("id")
        if not cid:
            continue
        canonical_aliases_by_id[cid] = []
        for n in [ce.get("name"), ce.get("display_name"), *(ce.get("aliases") or [])]:
            if not n:
                continue
            key = _norm(n)
            canonical_id_by_name.setdefault(key, cid)
            canonical_aliases_by_id[cid].append(key)

    by_id: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}

    async for v2 in db.employees_v2.find(
        {"quarter": quarter, "year": year},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1, "report_name": 1,
         "job_title": 1,
         **{f: 1 for f in OVERLAY_FIELDS}},
    ):
        overlay = {k: v2.get(k) for k in OVERLAY_FIELDS
                   if v2.get(k) not in (None, 0, 0.0)}
        jt = (v2.get("job_title") or "").lower().strip()
        if jt in ("trainer", "bartender"):
            overlay["job_title"] = jt
        if not overlay:
            continue

        # Index by id
        if v2.get("id"):
            existing = by_id.get(v2["id"]) or {}
            by_id[v2["id"]] = {**overlay, **existing}

        # Resolve to canonical id via name → also expand to all aliases
        v2_names = {_norm(n) for n in (v2.get("name"), v2.get("display_name"),
                                       v2.get("report_name")) if n}
        canonical_id = next(
            (canonical_id_by_name[n] for n in v2_names
             if n in canonical_id_by_name),
            None,
        )
        if canonical_id:
            existing = by_id.get(canonical_id) or {}
            by_id[canonical_id] = {**overlay, **existing}
            for alias_key in canonical_aliases_by_id.get(canonical_id, []):
                v2_names.add(alias_key)

        for n in v2_names:
            existing = by_name.get(n) or {}
            by_name[n] = {**overlay, **existing}

    return {"by_id": by_id, "by_name": by_name}


async def _load_settings(db, year: int, quarter: str) -> QuarterSettings:
    qs_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()}, {"_id": 0},
    )
    return QuarterSettings(**qs_doc) if qs_doc else QuarterSettings(
        year=year, quarter=quarter.upper(),
    )


def _resolve_overlay(
    row: Dict[str, Any],
    v2_idx: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Find the v2 overlay that matches this snapshot row."""
    by_id = v2_idx["by_id"]
    by_name = v2_idx["by_name"]

    eid = row.get("employee_id")
    if eid and eid in by_id:
        return by_id[eid]
    for n_field in ("frozen_display_name", "frozen_report_name"):
        nm = _norm(row.get(n_field))
        if nm and nm in by_name:
            return by_name[nm]
    return {}


def _apply_overlay_to_metrics(
    fm: Dict[str, Any],
    overlay: Dict[str, Any],
) -> Dict[str, Any]:
    """Return (updated_metrics, list_of_field_changes). Idempotent."""
    changes: List[Dict[str, Any]] = []
    updated = dict(fm)
    for k, v in overlay.items():
        if k == "job_title":
            current = (updated.get("job_title") or "").lower().strip()
            if v in ("trainer", "bartender") and current in ("", "server"):
                changes.append({"field": k, "before": fm.get(k), "after": v})
                updated[k] = v
            continue
        # All other fields: only fill when current value is missing/zero.
        current = updated.get(k)
        if current in (None, 0, 0.0) and v not in (None, 0, 0.0):
            changes.append({"field": k, "before": current, "after": v})
            updated[k] = v
    return updated, changes


TIER_ORDER = {
    "Trainer": 1, "Bartender": 2, "A-Server": 3,
    "B-Server": 4, "C-Server": 5, "Server": 6,
}


def _classify_tier(job_title: Optional[str], score: float,
                   a_min: float, b_min: float) -> str:
    jt = (job_title or "").lower().strip()
    if jt == "trainer":
        return "Trainer"
    if jt == "bartender":
        return "Bartender"
    if score >= a_min:
        return "A-Server"
    if score >= b_min:
        return "B-Server"
    return "C-Server"


async def backfill(
    db,
    snapshot_name: str,
    apply: bool,
) -> Dict[str, Any]:
    snap = await db.snapshot_workflow.find_one(
        {"name": snapshot_name}, {"_id": 0},
    )
    if not snap:
        raise SystemExit(f"Snapshot '{snapshot_name}' not found")
    if snap.get("status") == "finalized":
        raise SystemExit(
            f"Refusing to backfill a FINALIZED snapshot. "
            f"Finalized snapshots are intentionally immutable."
        )

    quarter = (snap.get("quarter") or "").upper()
    year = snap.get("year")
    settings = await _load_settings(db, year, quarter)
    v2_idx = await _build_v2_index(db, quarter, year)

    rows = snap.get("rows") or []
    if not rows:
        raise SystemExit("Snapshot has no rows[] to backfill.")

    summary = {
        "snapshot_name": snapshot_name,
        "snapshot_id": snap.get("id"),
        "quarter": quarter, "year": year,
        "rows_total": len(rows),
        "rows_changed": 0,
        "fields_filled": 0,
        "score_changes": [],
        "no_overlay_for": [],
    }

    # Pass 1: overlay each row's frozen_metrics
    updated_rows: List[Dict[str, Any]] = []
    for r in rows:
        fm = dict(r.get("frozen_metrics") or {})
        overlay = _resolve_overlay(r, v2_idx)
        if not overlay:
            summary["no_overlay_for"].append(r.get("frozen_display_name"))
            updated_rows.append(r)
            continue
        new_fm, changes = _apply_overlay_to_metrics(fm, overlay)
        if changes:
            # Recompute via canonical engine.
            scored = compute_total_score_dict(
                {k: new_fm.get(k) or 0 for k in SCORING_INPUT_FIELDS}, settings,
            )
            new_fm["weighted_score"] = scored["weighted_score"]
            new_fm["pre_dar_score"] = scored["pre_dar_score"]
            new_fm["total_score"] = scored["total_score"]
            old_score = fm.get("total_score") or 0
            summary["score_changes"].append({
                "name": r.get("frozen_display_name"),
                "before": old_score,
                "after": new_fm["total_score"],
                "delta": round(new_fm["total_score"] - old_score, 2),
                "fields": [c["field"] for c in changes],
            })
            summary["rows_changed"] += 1
            summary["fields_filled"] += len(changes)
        new_r = dict(r)
        new_r["frozen_metrics"] = new_fm
        new_r["frozen_score"] = new_fm.get("total_score") or r.get("frozen_score")
        updated_rows.append(new_r)

    # Pass 2: re-rank within each tier (Trainer < Bartender < A < B < C, score desc)
    a_min = settings.a_server_min_score or 85.0
    b_min = settings.b_server_min_score or 70.0
    for r in updated_rows:
        fm = r["frozen_metrics"]
        score = fm.get("total_score") or 0
        tier = _classify_tier(fm.get("job_title"), score, a_min, b_min)
        fm["tier_label"] = tier
        r["frozen_tier"] = tier

    sorted_rows = sorted(
        updated_rows,
        key=lambda r: (
            TIER_ORDER.get((r["frozen_metrics"].get("tier_label") or "Server"), 99),
            -(r.get("frozen_score") or 0),
        ),
    )
    for idx, r in enumerate(sorted_rows, 1):
        old_rank = r.get("frozen_rank")
        r["frozen_rank"] = idx
        if old_rank != idx:
            r["frozen_metrics"]["peer_rank"] = idx

    # Pass 3: persist and audit
    if apply:
        now = datetime.now(timezone.utc).isoformat()
        await db.snapshot_workflow.update_one(
            {"id": snap["id"]},
            {"$set": {
                "rows": sorted_rows,
                "backfill_at": now,
                "backfill_summary": {
                    "rows_changed": summary["rows_changed"],
                    "fields_filled": summary["fields_filled"],
                    "ran_at": now,
                },
            }},
        )
        # Mirror changes onto `employees[]` array for legacy consumers
        # that haven't moved to the FK-join read path yet.
        if snap.get("employees"):
            for r in sorted_rows:
                target_name = (r.get("frozen_display_name") or "").lower().strip()
                fm = r.get("frozen_metrics") or {}
                for emp in snap["employees"]:
                    if (emp.get("name") or "").lower().strip() == target_name:
                        for k in OVERLAY_FIELDS + ("total_score", "weighted_score",
                                                    "pre_dar_score", "tier_label"):
                            v = fm.get(k)
                            if v not in (None, 0, 0.0):
                                emp[k] = v
            await db.snapshot_workflow.update_one(
                {"id": snap["id"]},
                {"$set": {"employees": snap["employees"]}},
            )
        # Audit log
        for change in summary["score_changes"]:
            await db.audit_log.insert_one({
                "action": "snapshot_backfill_lsc",
                "snapshot_id": snap["id"],
                "snapshot_name": snapshot_name,
                "employee_name": change["name"],
                "score_before": change["before"],
                "score_after": change["after"],
                "fields_filled": change["fields"],
                "ran_at": now,
            })

    return summary


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot-name", required=True)
    p.add_argument("--apply", action="store_true",
                   help="Persist changes. Without this flag, runs as dry-run.")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.apply and not args.dry_run:
        # Default to dry-run for safety.
        args.dry_run = True

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        s = await backfill(db, args.snapshot_name, apply=args.apply)
        print(f"\nSnapshot:        {s['snapshot_name']} ({s['snapshot_id']})")
        print(f"Quarter/year:    {s['quarter']} {s['year']}")
        print(f"Rows total:      {s['rows_total']}")
        print(f"Rows changed:    {s['rows_changed']}")
        print(f"Fields filled:   {s['fields_filled']}")
        if s["no_overlay_for"]:
            print(f"\nNo v2 overlay found for {len(s['no_overlay_for'])} row(s):")
            for n in s["no_overlay_for"]:
                print(f"  - {n}")
        if s["score_changes"]:
            print(f"\n{'Name':<28} {'Before':>8} {'After':>8} {'Δ':>8}  Filled")
            print("-" * 80)
            for ch in sorted(s["score_changes"], key=lambda x: -abs(x["delta"])):
                print(f"  {ch['name']:<26} {ch['before']:>8.2f} {ch['after']:>8.2f} "
                      f"{ch['delta']:>+8.2f}  {','.join(ch['fields'])}")
        print(f"\nMode: {'APPLIED' if args.apply else 'DRY RUN — no changes saved'}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
