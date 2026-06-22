"""
diff_staged_vs_live_split_servers.py — READ-ONLY.

For every alias-SPLIT server in the applied-20 set (canonical legal whose
alias set matches >1 live snapshot row in Q2P6W2), print side-by-side:

  STAGED  vs  CURRENT LIVE (as the live board displays right now):
    LBW%, Glass%, LSC%, final score, tier
  + per-metric Δ
  + TIER CHANGE flag
  + final-score Δ (total movement, not just per-metric)

No writes. No promotion. Pure report.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from scripts.stage_q2_rebuild import Q2_ALIAS_OVERRIDE  # type: ignore


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


async def _hydrate_and_score(db, snap_doc) -> List[Dict[str, Any]]:
    """Run live hydrator + scorer on a snapshot doc and return the ranked
    rows that `generate_hierarchy_rankings` produces (same shape the
    leaderboard displays).
    """
    from snapshot_routes import _hydrate_snapshot_employees  # type: ignore
    from scoring_engine import (  # type: ignore
        EmployeeV2, QuarterSettings, run_full_scoring,
        generate_hierarchy_rankings,
    )

    qs_doc = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    settings = QuarterSettings(**{k: v for k, v in qs_doc.items() if k != "_id"})

    hyd = await _hydrate_snapshot_employees(db, snap_doc)

    def _fn(v: Any) -> float:
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    employees: List[EmployeeV2] = []
    for e in hyd:
        if e.get("no_pos_data_this_period"):
            continue
        employees.append(EmployeeV2(
            id=e.get("id") or e.get("canonical_id") or e.get("employee_id"),
            name=e.get("name") or e.get("display_name"),
            display_name=e.get("display_name") or e.get("name"),
            job_title=e.get("job_title") or "Server",
            quarter="Q2", year=2026,
            net_sales=_fn(e.get("net_sales")),
            guests=int(_fn(e.get("guests") or e.get("guest_count"))),
            ppa=_fn(e.get("ppa")),
            liquor_sales=_fn(e.get("liquor_sales")),
            beer_sales=_fn(e.get("beer_sales")),
            wine_sales=_fn(e.get("wine_sales")),
            glassware_sales=_fn(
                e.get("glassware_sales") or e.get("bar_glassware_sales")
            ),
            lsc_count=int(_fn(e.get("lsc_count"))),
            nps_score=_fn(e.get("nps_score")),
            cv_promoters=int(_fn(e.get("cv_promoters"))),
            cv_passives=int(_fn(e.get("cv_passives"))),
            cv_detractors=int(_fn(e.get("cv_detractors"))),
            cv_score=0.0,
            review_mentions=int(_fn(e.get("rt_mentions"))),
            rt_mentions=int(_fn(e.get("rt_mentions"))),
            review_tracker_bonus=_fn(e.get("review_tracker_bonus")),
        ))

    scored = run_full_scoring(employees, settings)
    return generate_hierarchy_rankings(scored, settings, first_name_only=False)


def _row_for(rk: List[Dict[str, Any]], legal: str) -> Optional[Dict[str, Any]]:
    """Find a ranked row by legal name OR any Q2_ALIAS_OVERRIDE alias,
    matching against both `name` and `display_name` fields."""
    candidates = {_norm(legal)} | {_norm(a) for a in Q2_ALIAS_OVERRIDE.get(legal, [])}
    for r in rk:
        if _norm(r.get("name")) in candidates or _norm(r.get("display_name")) in candidates:
            return r
    return None


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    live = await db.snapshot_workflow.find_one({"name": "Q2P6W2"})
    staged = await db.snapshot_workflow_staging.find_one({"name": "Q2_REBUILD_STAGED"})
    if not live or not staged:
        print("FATAL: live or staged doc missing."); sys.exit(1)

    # 1. Identify alias-SPLIT canonicals in the applied-20 set.
    #    A canonical is "alias-split" if its alias set (legal + variants)
    #    matches more than one live snapshot row.
    live_rows = live.get("rows") or []
    live_names_lc = [_norm(r.get("frozen_display_name")) for r in live_rows]

    staged_emps = staged.get("employees") or []
    applied_legals = [e.get("name") for e in staged_emps if e.get("name")]

    split_servers: List[Tuple[str, List[str]]] = []
    for legal in applied_legals:
        aliases = {_norm(legal)} | {_norm(a) for a in Q2_ALIAS_OVERRIDE.get(legal, [])}
        matched = [r.get("frozen_display_name") for r in live_rows
                   if _norm(r.get("frozen_display_name")) in aliases]
        if len(matched) > 1:
            split_servers.append((legal, matched))

    print("=" * 84)
    print("ALIAS-SPLIT SERVERS in applied-20 (canonical legal -> live alias rows)")
    print("=" * 84)
    for legal, matched in split_servers:
        print(f"  {legal:22}  ({len(matched)} live rows: {matched})")
    if not split_servers:
        print("  (none)")
        return
    print()

    # 2. Hydrate + score BOTH snapshots through the live pipeline.
    print("Hydrating + scoring LIVE snapshot...")
    live_rk = await _hydrate_and_score(db, live)
    print("Hydrating + scoring STAGED snapshot...")
    staged_rk = await _hydrate_and_score(db, staged)
    print()

    # 3. Build the comparison table.
    print("=" * 116)
    print("STAGED vs CURRENT LIVE — alias-split servers")
    print("=" * 116)
    header = (
        f"{'canonical legal':22}  {'metric':12}  "
        f"{'STAGED':>9}  {'LIVE':>9}  {'Δ':>8}    "
        f"{'STAGED label':>22}  {'LIVE label':>22}"
    )
    print(header)
    print("-" * len(header))

    for legal, _matched in split_servers:
        s = _row_for(staged_rk, legal)
        l = _row_for(live_rk,   legal)
        if not s or not l:
            print(f"  {legal:22}  -> staged_found={bool(s)} live_found={bool(l)} "
                  f"(row missing in one or both — skipping detail)")
            continue
        s_label = s.get("display_name") or s.get("name") or "?"
        l_label = l.get("display_name") or l.get("name") or "?"

        def _g(r: Dict[str, Any], k: str) -> float:
            v = r.get(k)
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0.0

        for label, field in [
            ("LBW%",   "lbw_percentage"),
            ("Glass%", "glassware_percentage"),
            ("LSC%",   "lsc_percentage"),
        ]:
            sp, lp = _g(s, field), _g(l, field)
            print(f"{legal:22}  {label:12}  {sp:>9.2f}  {lp:>9.2f}  {sp - lp:>+8.2f}    "
                  f"{s_label:>22}  {l_label:>22}")

        # Final-score + tier movement
        s_score = _g(s, "final_score") or _g(s, "total_score")
        l_score = _g(l, "final_score") or _g(l, "total_score")
        s_tier = s.get("tier_label") or s.get("performance_tier") or "?"
        l_tier = l.get("tier_label") or l.get("performance_tier") or "?"
        tier_change = "YES" if s_tier != l_tier else "no"
        print(f"{legal:22}  {'FINAL':12}  {s_score:>9.2f}  {l_score:>9.2f}  "
              f"{s_score - l_score:>+8.2f}    "
              f"{'tier=' + str(s_tier):>22}  {'tier=' + str(l_tier):>22}   "
              f"tier_change={tier_change}")
        print("-" * len(header))

    print()
    print("READ-ONLY REPORT. Nothing was modified.")


if __name__ == "__main__":
    asyncio.run(main())
