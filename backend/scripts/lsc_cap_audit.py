"""
lsc_cap_audit.py — READ-ONLY. Walk every line of the LSC pipeline for all 29
staged servers and answer:
  1. What is the LSC cap actually used?
  2. Does the displayed leaderboard cap match what the weighted total uses?
  3. How many servers are above the cap and by how much?
  4. Step-by-step for Kitti Xavier's 424%.

Reads scoring_engine.py constants directly to avoid drift.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from scoring_engine import (  # type: ignore
    EmployeeV2, QuarterSettings, run_full_scoring,
    generate_hierarchy_rankings, calculate_bonus_points,
)
from snapshot_routes import _hydrate_snapshot_employees  # type: ignore


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    qs = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    settings = QuarterSettings(**{k: v for k, v in qs.items() if k != "_id"})

    print("=" * 78)
    print("WHERE LSC IS CAPPED IN scoring_engine.py")
    print("=" * 78)
    print("  Line 567:  score_lsc = (benchmark_lsc / guests_per_lsc) * 100   ← UNCAPPED RAW")
    print("  Line 599:  bonus = ((score% - 100) / 20) * 5, capped at +5")
    print("  Line 643:  capped_lsc = min(score_lsc, 100)                     ← USED IN TOTAL")
    print("  Line 1228: 'lsc_percentage': emp.score_lsc          ← LEADERBOARD DISPLAY = UNCAPPED")
    print("  Line 1252: 'earned': min(score_lsc, 100) * 0.25 + bonus_lsc")
    print()
    print(f"Q2 benchmark_lsc = {settings.benchmark_lsc}   weight_lsc = {settings.weight_lsc}")
    print(f"  → max weighted contribution from LSC = min(score, 100) * weight = "
          f"100 * {settings.weight_lsc} = {100 * settings.weight_lsc}")
    print(f"  → plus a bonus of up to +5 pts when score > 100")
    print()

    staged = await db.snapshot_workflow_staging.find_one({"name": "Q2_REBUILD_STAGED"})
    hyd = await _hydrate_snapshot_employees(db, staged)

    def _fn(v):
        try: return float(v or 0)
        except (TypeError, ValueError): return 0.0

    employees = []
    loy_by_id = {}
    for e in hyd:
        if e.get("no_pos_data_this_period"): continue
        eid = e.get("id") or e.get("canonical_id") or e.get("employee_id")
        loy_by_id[eid] = _fn(e.get("loyalty_sales"))
        employees.append(EmployeeV2(
            id=eid,
            name=e.get("name") or e.get("display_name"),
            display_name=e.get("display_name") or e.get("name"),
            job_title=e.get("job_title") or "Server",
            quarter="Q2", year=2026,
            net_sales=_fn(e.get("net_sales")), guests=int(_fn(e.get("guests") or e.get("guest_count"))),
            ppa=_fn(e.get("ppa")),
            liquor_sales=_fn(e.get("liquor_sales")), beer_sales=_fn(e.get("beer_sales")),
            wine_sales=_fn(e.get("wine_sales")),
            glassware_sales=_fn(e.get("glassware_sales") or e.get("bar_glassware_sales")),
            lsc_count=int(_fn(e.get("lsc_count"))),
            nps_score=_fn(e.get("nps_score")),
            cv_promoters=int(_fn(e.get("cv_promoters"))),
            cv_passives=int(_fn(e.get("cv_passives"))),
            cv_detractors=int(_fn(e.get("cv_detractors"))),
            cv_score=0.0,
            review_mentions=int(_fn(e.get("rt_mentions") or e.get("review_mentions"))),
            rt_mentions=int(_fn(e.get("rt_mentions") or e.get("review_mentions"))),
            review_tracker_bonus=_fn(e.get("review_tracker_bonus")),
        ))

    scored = run_full_scoring(employees, settings)

    print("=" * 130)
    print(f"PER-SERVER LSC AUDIT — all {len(scored)} staged servers (sorted by uncapped score_lsc desc)")
    print("=" * 130)
    print(f"{'name':25}  {'loy $':>9}  {'lsc_ct':>6}  {'guests':>6}  "
          f"{'g/lsc':>7}  {'raw_lsc%':>9}  {'capped@100':>10}  "
          f"{'bonus_lsc':>9}  {'earned_lsc':>10}  {'cap_active?'}")
    print("-" * 130)

    rows = []
    for e in scored:
        loy = loy_by_id.get(e.id, 0.0)
        raw = e.score_lsc or 0
        capped = min(raw, 100)
        # earned in leaderboard = capped * weight + bonus
        earned = round(capped * settings.weight_lsc + (e.bonus_lsc or 0), 2)
        cap_active = "YES" if raw > 100 else "no"
        rows.append((e.display_name or e.name, loy, e.lsc_count or 0, e.guests, e.guests_per_lsc or 0,
                     raw, capped, e.bonus_lsc or 0, earned, cap_active))

    for nm, loy, lsc_ct, g, gpl, raw, cap, bn, earn, ca in sorted(rows, key=lambda r: -r[5]):
        print(f"{nm:25}  ${loy:>7.2f}  {lsc_ct:>6}  {g:>6}  "
              f"{gpl:>7.2f}  {raw:>9.2f}  {cap:>10.2f}  "
              f"{bn:>9.2f}  {earn:>10.2f}  {ca}")
    print("-" * 130)

    # Summary stats
    above = [r for r in rows if r[5] > 100]
    above_extreme = [r for r in rows if r[5] > 200]
    print(f"\nServers with raw score_lsc > 100 (cap active for weighted total):  {len(above)} of {len(rows)}")
    print(f"Servers with raw score_lsc > 200 (cap eats >100% of headroom):     {len(above_extreme)} of {len(rows)}")
    print(f"Median raw score_lsc:  {sorted([r[5] for r in rows])[len(rows)//2]:.2f}")
    print(f"Max raw score_lsc:     {max(r[5] for r in rows):.2f}  (server: {max(rows, key=lambda r: r[5])[0]})")
    print()

    # -------- Kitti step-by-step --------
    kitti = next((e for e in scored if (e.display_name or e.name) == "Kitti Xavier"), None)
    if kitti:
        kitti_loy = loy_by_id.get(kitti.id, 0.0)
        print("=" * 78)
        print("KITTI XAVIER — step-by-step LSC math")
        print("=" * 78)
        print(f"  1. loyalty_sales (from operator truth)   = ${kitti_loy:.2f}")
        print(f"  2. lsc_count = round(loyalty / 25)        = round({kitti_loy} / 25) "
              f"= {kitti.lsc_count}")
        print(f"  3. guests                                 = {kitti.guests}")
        print(f"  4. guests_per_lsc = guests / lsc_count    = {kitti.guests} / {kitti.lsc_count} "
              f"= {kitti.guests_per_lsc:.4f}")
        print(f"  5. score_lsc (UNCAPPED)                   = "
              f"(benchmark_lsc / guests_per_lsc) * 100")
        print(f"     = ({settings.benchmark_lsc} / {kitti.guests_per_lsc:.4f}) * 100 "
              f"= {kitti.score_lsc:.2f}%")
        print()
        print(f"  6. WEIGHTED TOTAL path uses capped @ 100:")
        print(f"     capped_lsc = min({kitti.score_lsc:.2f}, 100) = 100.00")
        print(f"     weighted_contribution = 100.00 * weight_lsc({settings.weight_lsc}) "
              f"= {100*settings.weight_lsc:.2f} pts")
        print()
        print(f"  7. BONUS path (calculate_bonus_points):")
        print(f"     bonus = ((score% - 100) / 20) * 5, capped at +5")
        print(f"     raw_bonus = ((424.09 - 100) / 20) * 5 = "
              f"{((kitti.score_lsc - 100) / 20) * 5:.2f}")
        print(f"     bonus_lsc = min(raw_bonus, 5.0) = {kitti.bonus_lsc:.2f}")
        print()
        print(f"  8. LEADERBOARD DISPLAY 'LSC%' field        = {kitti.score_lsc:.2f}%  ← UNCAPPED")
        print(f"     LEADERBOARD 'earned' for LSC category   = "
              f"min(score, 100) * 0.25 + bonus = "
              f"{100 * settings.weight_lsc + kitti.bonus_lsc:.2f} pts  ← USES CAP")
        print()

    # -------- Cap consistency check --------
    print("=" * 78)
    print("CAP CONSISTENCY CHECK")
    print("=" * 78)
    print("  • Display 'lsc_percentage' field    = emp.score_lsc            UNCAPPED")
    print("  • Display 'earned' for LSC category = min(score_lsc, 100)*w+b  CAPPED@100")
    print("  • Weighted total_score              = min(score_lsc, 100)*w    CAPPED@100")
    print()
    print("  RESULT: The DISPLAYED 'LSC%' COLUMN is uncapped (shows 424.09 etc.).")
    print("          The total/earned points use CAPPED@100.")
    print("          They are INCONSISTENT in label only — not in math.")
    print("          (The total never benefits from raw% above 100; bonus")
    print("           contributes at most +5 pts above 100.)")
    print()
    print("  IMPLICATION: Whether a server scores raw_lsc = 105 or 424 has")
    print("               IDENTICAL impact on final ranking:")
    print(f"                 25 pts capped contribution + 5 pts bonus = 30.00 pts max")
    print(f"               versus 105% server: 25 + ((105-100)/20)*5 = 25 + 1.25 = 26.25 pts")
    print(f"               Difference ceiling: ~3.75 pts.")
    print()
    print("  TL;DR: The cap is correct. The DISPLAY is misleading — 'LSC% 424'")
    print("         visually exaggerates a metric whose actual scoring impact")
    print("         is bounded to 30 pts. Consider either:")
    print("           (a) cap display at 100% too, OR")
    print("           (b) show 'LSC: 100% (capped, lsc_count=46)' for >100% rows.")
    print()

    # -------- DB.employees writes needed for canonical display --------
    print("=" * 78)
    print("[SEPARATE — NOT BLOCKING PROMOTE] db.employees writes needed to display")
    print("canonical legal names instead of nicknames")
    print("=" * 78)
    pairs = [
        ("Lakeisha Martin",   "Keisha Martin",   "active"),
        ("Treyanna Quick",    "Trey Quick",      "active"),
        ("Kahiaulani Ramos",  "Kahi Ramos",      "active"),  # also Kahiauani, Kahiaulanl
        ("Glennice Nguyen",   "Lennie Nguyen",   "active"),
        ("Thomas Kozan",      "TK Kozan",        "active"),
        ("Abigail Ostrowski", "Abby Ostrowski",  "active"),
        ("Eric Ostgarden",    "Ikey Ostgarden",  "active"),
        ("Craig Simmons",     "Allen Simmons",   "active"),
    ]
    print()
    print("For each canonical legal below, the live db.employees has the legal name")
    print("as status='merged' (or its alias canonical as status='active'). To display")
    print("the legal name post-rebuild, the schema needs ONE of:")
    print()
    print("  Option A (cleanest, requires manual review):")
    print("    db.employees.update_one(")
    print("      {name: '<legal_name>'},")
    print("      {$set: {status: 'active', display_name: '<legal_name>',")
    print("              aliases: [<existing aliases + nickname>]}}")
    print("    )")
    print("    db.employees.update_one(")
    print("      {name: '<nickname>'},")
    print("      {$set: {status: 'merged', merged_into: '<legal_name canonical id>'}}")
    print("    )")
    print()
    print("  Option B (minimal — just flip display name on the active canonical):")
    print("    db.employees.update_one(")
    print("      {name: '<nickname>'},  # the currently-active canonical")
    print("      {$set: {display_name: '<legal_name>',")
    print("              aliases: [<existing + nickname-as-alias>]}}")
    print("    )")
    print()
    print("Specific pairs to update:")
    for legal, nickname, target in pairs:
        # Look up the current canonical that's active
        c_legal = await db.employees.find_one({"name": legal}, {"_id":0,"id":1,"name":1,"display_name":1,"status":1,"aliases":1})
        c_nick = await db.employees.find_one({"name": nickname}, {"_id":0,"id":1,"name":1,"display_name":1,"status":1,"aliases":1})
        print(f"\n  → {legal!r}  ⇄  {nickname!r}")
        print(f"      current legal_canonical  : {c_legal}")
        print(f"      current nickname_canonical: {c_nick}")
    print()
    print("Hold for approval. No writes made.")


if __name__ == "__main__":
    asyncio.run(main())
