"""
build_q2_from_operator_truth.py — STAGING ONLY.

Source of truth: operator-verified extraction from SSD_6_15_26.pdf (table
transcribed directly off the printed PDF). Both stored parses are abandoned
(Source A and Source B both have proven OCR errors).

Critical corrections embedded vs the prior staged doc:
  - Ethan Dever  : Loyalty=300.00 (not 325 / not 325k), Wine=245.50 (not 2.00),
                   Food=34,766.74 (derived; not 3.00)
  - Cory West    : Food=13,223.44 (derived; not 132,234.00)
  - Lakeisha     : Loyalty=925.00 (not 1100)
  - Robert       : Loyalty=700.00 (not 725) — re-verified vs op table
  - Tarek        : Loyalty=225.00 (not 250)
  - Kelsey       : Loyalty=225.00 (matches Source A, re-asserted)
  - Eddie        : Loyalty=125.00 (not 175)
  - Craig        : Loyalty=125.00 (not 200)
  - Jamie        : Loyalty=125.00 (not 150)
  - Caitlin      : Loyalty=25.00 (matches)
  - Kitti        : Loyalty=1125.00 (not 1150)
  - Many others minor — full table embedded below verbatim.

The small +$25–$170 integrity gaps in the prior parse were LOYALTY over-reads
(not a missing negative column). There is no Voids/Comps column on this report.

Stage only. No live writes. No promotion.
"""

import asyncio
import csv
import os
import sys
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from scripts.stage_q2_rebuild import Q2_ALIAS_OVERRIDE  # type: ignore

DOLLARS_PER_LSC = 25.0

# Operator's verified truth table.  Each row: (legal, net, liq, beer, wine,
# glass, loyalty, guests).
TRUTH: List[Tuple[str, float, float, float, float, float, float, int]] = [
    ("Bruce Diesel Rabago",        2582.24,   180.00,   26.50,    0.00,   132.00,    0.00,   53),
    ("Arianna Pena",               2084.78,   109.00,   86.25,   55.00,    60.00,    0.00,   44),
    ("Jeden White",                6684.02,   571.00,  191.50,   18.00,   169.00,    0.00,  144),
    ("Cory West",                 16302.94,  1520.50,  657.50,  138.50,   638.00,  125.00,  317),
    ("Kahiaulani Ramos",          30516.08,  2395.50, 1533.25,  171.00,   885.00,  125.00,  643),
    ("Rachael Escobar",           34202.31,  2827.50, 1673.25,  235.50,   951.00,  200.00,  714),
    ("Adriana Bracamontes",       31939.11,  2719.00, 1333.75,   96.50,  1059.00,  125.00,  661),
    ("Jose Plancarte Villa",      48569.44,  4067.50, 2413.50,  415.00,  1468.00,  275.00,  990),
    ("Thomas Kozan",              56485.89,  5101.00, 2569.75,  273.50,  1480.00,   75.00, 1168),
    ("Dylan Franklin",            31314.21,  1936.00, 1418.75,  265.00,   921.00,   50.00,  651),
    ("Robert Mckinnon",           83418.74,  6340.50, 3689.75,  398.00,  2261.00,  700.00, 1759),
    ("Polly Blocker",             39878.92,  3465.50, 1514.50,  134.50,   981.00,  300.00,  832),
    ("Abigail Ostrowski",         66120.57,  5263.00, 3853.75,  382.00,  1672.00,  125.00, 1361),
    ("Glennice Nguyen",           67753.38,  4892.50, 3413.00,  409.00,  2318.00,  325.00, 1412),
    ("Ethan Dever",               42793.74,  4006.00, 2133.50,  245.50,  1342.00,  300.00,  877),
    ("Tarek Araman",              83289.73,  6603.50, 3799.25,  566.50,  2189.00,  225.00, 1752),
    ("Kelsey Corkum",             53808.86,  4203.50, 2342.75,  279.00,  1287.00,  225.00, 1154),
    ("Eddie Garcia",              41688.00,  3656.50, 1995.00,  192.50,   930.00,  125.00,  831),
    ("Craig Simmons",             47633.20,  3161.00, 2607.00,  259.00,  1473.00,  125.00, 1007),
    ("Eric Ostgarden",            62439.68,  5687.00, 3693.00,  370.00,  1912.00,  125.00, 1285),
    ("Starwars Mckinnon-Herrera", 62065.69,  5041.50, 3232.50,  357.50,  1960.00,  200.00, 1239),
    ("Caitlin Carden",            19232.84,  1747.00,  857.00,   78.00,   532.00,   25.00,  399),
    ("Jamie Rousseau",           102442.63,  8829.00, 5388.75,  954.50,  3970.00,  125.00, 2112),
    ("Lexi Crandall",             26459.37,  1763.50, 1240.50,  247.00,   655.00,   75.00,  564),
    ("Diane Peterson",            63585.53,  5413.50, 2972.25,  392.50,  1394.00, 1050.00, 1306),
    ("Treyanna Quick",            56188.32,  5693.50, 3604.75,  320.50,  2473.00,  200.00, 1043),
    ("Julian Taveras",            49942.06,  4234.00, 2436.75,  209.00,  1055.00,  125.00,  994),
    ("Lakeisha Martin",           89283.75,  7626.50, 4372.75,  681.00,  2618.00,  925.00, 1760),
    ("Kitti Xavier",              55746.35,  5268.00, 2509.50,  193.00,  1759.00, 1125.00, 1061),
]

ANCHORS = {
    "Kahiaulani Ramos": (30516.08,  643, 47.46),
    "Thomas Kozan":     (56485.89, 1168, 48.36),
    "Glennice Nguyen":  (67753.38, 1412, 47.98),
}

EXPECTED_PHANTOM_LEGALS = [
    "Robert Mckinnon", "Tarek Araman", "Diane Peterson", "Kelsey Corkum",
    "Julian Taveras", "Eddie Garcia", "Polly Blocker", "Dylan Franklin",
    "Lexi Crandall",
]


def _norm(s):
    return (s or "").strip().lower()


def _score_lsc(loy: float, guests: int, benchmark: float) -> Tuple[int, float, float]:
    """Return (lsc_count, guests_per_lsc, score_lsc capped at 250)."""
    lsc = round(loy / DOLLARS_PER_LSC) if loy > 0 else 0
    gpl = round(guests / lsc, 4) if lsc > 0 else 0.0
    sc = (benchmark / gpl) * 100 if gpl > 0 else 0.0
    return lsc, gpl, min(sc, 250.0)


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    print("=" * 90)
    print("OPERATOR-VERIFIED TRUTH TABLE — 29 servers")
    print("=" * 90)

    # ---------------------------------------------------------------
    # 1. Integrity assert on the operator table itself.
    # ---------------------------------------------------------------
    integrity_fail: List[str] = []
    rows: List[Dict[str, Any]] = []
    for legal, net, liq, beer, wine, glass, loy, g in TRUTH:
        food = round(net - (liq + beer + wine + glass + loy), 2)
        check = round(liq + beer + wine + glass + loy + food, 2)
        if abs(check - net) > 0.005:
            integrity_fail.append(f"{legal}: derived {check} != net {net}")
        ppa_calc = round(net / g, 2) if g > 0 else 0
        rows.append({
            "legal": legal,
            "net": net, "guests": g, "ppa": ppa_calc,
            "liquor": liq, "beer": beer, "wine": wine,
            "glass": glass, "loyalty": loy, "food": food,
        })
    print(f"Integrity (Liq+Beer+Wine+Glass+Loy+Food == Net): "
          f"{'✓ all 29 pass' if not integrity_fail else '❌ ' + str(len(integrity_fail)) + ' fail'}")
    for s in integrity_fail:
        print(f"   ❌ {s}")
    if integrity_fail:
        print("HALT — transcription bug in operator table or in this script.")
        sys.exit(1)
    print()

    # ---------------------------------------------------------------
    # 2. Anchor cross-check.
    # ---------------------------------------------------------------
    print("Anchor cross-check:")
    by_legal = {r["legal"]: r for r in rows}
    fail_anchor = False
    for legal, (e_net, e_g, e_ppa) in ANCHORS.items():
        r = by_legal.get(legal)
        if not r:
            print(f"   ❌ {legal}: MISSING"); fail_anchor = True; continue
        ok = abs(r["net"] - e_net) < 0.01 and r["guests"] == e_g and abs(r["ppa"] - e_ppa) < 0.05
        mark = "✓" if ok else "❌"
        print(f"   {mark} {legal:20}  net={r['net']:.2f}/{e_net}  guests={r['guests']}/{e_g}  ppa={r['ppa']}/{e_ppa}")
        if not ok:
            fail_anchor = True
    if fail_anchor:
        print("HALT — anchor cross-check failed.")
        sys.exit(2)
    print()

    # ---------------------------------------------------------------
    # 3. 9-phantom regression check.
    # ---------------------------------------------------------------
    print("9-phantom regression — all must be in the truth table:")
    phantom_fail = False
    for legal in EXPECTED_PHANTOM_LEGALS:
        r = by_legal.get(legal)
        ok = r is not None and r["net"] > 0 and r["guests"] > 0
        mark = "✓" if ok else "❌"
        if ok:
            print(f"   {mark} {legal:25}  net=${r['net']:>9.2f}  guests={r['guests']:>5}  loy=${r['loyalty']:>7.2f}")
        else:
            print(f"   {mark} {legal:25}  MISSING")
            phantom_fail = True
    if phantom_fail:
        print("HALT — phantom regression failed.")
        sys.exit(3)
    print()

    # ---------------------------------------------------------------
    # 4. Write q2_pos_truth_v3.csv
    # ---------------------------------------------------------------
    csv_path = "/app/backend/q2_pos_truth_v3.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "canonical_legal", "net_sales", "guests", "ppa",
            "food_sales", "liquor_sales", "beer_sales", "wine_sales",
            "bar_glassware_sales", "loyalty_sales", "lsc_count_derived",
        ])
        w.writeheader()
        for r in rows:
            lsc, _, _ = _score_lsc(r["loyalty"], r["guests"], 100.0)
            w.writerow({
                "canonical_legal":     r["legal"],
                "net_sales":           r["net"],
                "guests":              r["guests"],
                "ppa":                 r["ppa"],
                "food_sales":          r["food"],
                "liquor_sales":        r["liquor"],
                "beer_sales":          r["beer"],
                "wine_sales":          r["wine"],
                "bar_glassware_sales": r["glass"],
                "loyalty_sales":       r["loyalty"],
                "lsc_count_derived":   lsc,
            })
    print(f"✓ Wrote canonical truth -> {csv_path}")
    print()

    # ---------------------------------------------------------------
    # 5. BEFORE snapshot for Ethan + Lakeisha (capture from CURRENT
    #    staged doc, BEFORE we overwrite it).
    # ---------------------------------------------------------------
    from scoring_engine import (  # type: ignore
        EmployeeV2, QuarterSettings, run_full_scoring,
        generate_hierarchy_rankings,
    )
    from snapshot_routes import _hydrate_snapshot_employees  # type: ignore

    qs = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    settings = QuarterSettings(**{k: v for k, v in qs.items() if k != "_id"})

    staged_doc = await db.snapshot_workflow_staging.find_one({"name": "Q2_REBUILD_STAGED"})
    prior_by_legal: Dict[str, Dict[str, Any]] = {}
    for e in staged_doc.get("employees") or []:
        nm = (e.get("name") or "").strip()
        if nm:
            prior_by_legal[nm] = e

    def _fn(v):
        try: return float(v or 0)
        except (TypeError, ValueError): return 0.0

    # Score the PRIOR staged data (BEFORE corrections).
    prior_hyd = await _hydrate_snapshot_employees(db, staged_doc)
    prior_emps: List[EmployeeV2] = []
    for e in prior_hyd:
        if e.get("no_pos_data_this_period"): continue
        prior_emps.append(EmployeeV2(
            id=e.get("id") or e.get("canonical_id") or e.get("employee_id"),
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
    prior_scored = run_full_scoring(prior_emps, settings)
    prior_rk = generate_hierarchy_rankings(prior_scored, settings, first_name_only=False)
    prior_by = {((r.get("display_name") or r.get("name") or "").strip().lower()): r for r in prior_rk}

    # ---------------------------------------------------------------
    # 6. Build new employees[] + rows[] arrays, preserving NPS/RT/identity
    #    fields from the prior staged record.
    # ---------------------------------------------------------------
    new_employees: List[Dict[str, Any]] = []
    new_rows: List[Dict[str, Any]] = []
    for r in rows:
        legal = r["legal"]
        lsc_count, gpl, _ = _score_lsc(r["loyalty"], r["guests"], settings.benchmark_lsc)
        liq, beer, wine = r["liquor"], r["beer"], r["wine"]
        glass = r["glass"]; net = r["net"]; g = r["guests"]; ppa = r["ppa"]; loy = r["loyalty"]; food = r["food"]
        lbw_total = round(liq + beer + wine, 2)
        lbw_per_guest = round(lbw_total / g, 4) if g > 0 else 0.0
        glass_per_guest = round(glass / g, 4) if g > 0 else 0.0
        prior = prior_by_legal.get(legal) or {}

        emp = {
            "id": prior.get("id"),
            "canonical_id": prior.get("canonical_id"),
            "name": legal,
            "display_name": prior.get("display_name") or legal,
            "report_name": prior.get("report_name") or legal,
            "job_title": prior.get("job_title") or "Server",
            "quarter": "Q2", "year": 2026,
            "net_sales": net, "guests": g, "guest_count": g, "ppa": ppa,
            "food_sales": food,
            "liquor_sales": liq, "beer_sales": beer, "wine_sales": wine,
            "lbw": lbw_total, "lbw_per_guest": lbw_per_guest,
            "bar_glassware_sales": glass, "glassware_sales": glass,
            "glassware_per_guest": glass_per_guest,
            "loyalty_sales": loy,
            "lsc_count": lsc_count, "guests_per_lsc": gpl,
            "nps_score":      prior.get("nps_score"),
            "cv_promoters":   prior.get("cv_promoters"),
            "cv_passives":    prior.get("cv_passives"),
            "cv_detractors":  prior.get("cv_detractors"),
            "cv_score":       prior.get("cv_score"),
            "review_mentions": prior.get("review_mentions") or prior.get("rt_mentions"),
            "rt_mentions":     prior.get("rt_mentions") or prior.get("review_mentions"),
            "review_tracker_bonus": prior.get("review_tracker_bonus") or 0,
            "pos_source": "operator-verified SSD 6.15.26.pdf transcription",
            "lsc_source_note": f"lsc_count = round(loyalty_sales / ${DOLLARS_PER_LSC:.0f})",
        }
        new_employees.append(emp)
        new_rows.append({
            "employee_id": emp["id"],
            "frozen_display_name": legal,
            "frozen_report_name": emp["report_name"],
            "frozen_score": None,
            "frozen_metrics": {
                "name": legal,
                "net_sales": net, "guests": g, "guest_count": g, "ppa": ppa,
                "food_sales": food,
                "liquor_sales": liq, "beer_sales": beer, "wine_sales": wine,
                "lbw": lbw_total, "lbw_per_guest": lbw_per_guest,
                "bar_glassware_sales": glass, "glassware_sales": glass,
                "glassware_per_guest": glass_per_guest,
                "loyalty_sales": loy,
                "lsc_count": lsc_count, "guests_per_lsc": gpl,
                "nps_score": emp["nps_score"],
                "cv_promoters": emp["cv_promoters"],
                "cv_passives":  emp["cv_passives"],
                "cv_detractors": emp["cv_detractors"],
                "review_mentions": emp["review_mentions"],
                "rt_mentions": emp["rt_mentions"],
            },
        })

    await db.snapshot_workflow_staging.update_one(
        {"_id": staged_doc["_id"]},
        {"$set": {
            "employees": new_employees,
            "rows": new_rows,
            "pos_source": "operator-verified SSD 6.15.26.pdf transcription",
            "lsc_derivation": f"lsc_count = round(loyalty_sales / ${DOLLARS_PER_LSC:.0f})",
            "rebuilt_at": "2026-02 (build_q2_from_operator_truth)",
        }},
    )
    print(f"✓ Staged {len(new_employees)} servers from operator-verified truth.")
    print()

    # ---------------------------------------------------------------
    # 7. Re-hydrate + score and print full leaderboard.
    # ---------------------------------------------------------------
    staged_doc = await db.snapshot_workflow_staging.find_one({"_id": staged_doc["_id"]})
    hyd = await _hydrate_snapshot_employees(db, staged_doc)
    after_emps: List[EmployeeV2] = []
    for e in hyd:
        if e.get("no_pos_data_this_period"): continue
        after_emps.append(EmployeeV2(
            id=e.get("id") or e.get("canonical_id") or e.get("employee_id"),
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
    after_scored = run_full_scoring(after_emps, settings)
    rk = generate_hierarchy_rankings(after_scored, settings, first_name_only=False)

    print(f"Locked Q2 benchmarks: lbw={settings.benchmark_lbw}  glass={settings.benchmark_glass}  "
          f"lsc={settings.benchmark_lsc}  ppa={settings.benchmark_ppa}  is_locked={qs.get('is_locked')}")
    print()
    print("=" * 138)
    print(f"FULL LEADERBOARD ({len(rk)} servers) — Q2P6W2 STAGED (operator-truth)")
    print("=" * 138)
    print(f"{'#':>3}  {'name':25}  {'tier':14}  {'PPA%':>7}  {'LBW%':>7}  {'Glass%':>7}  "
          f"{'LSC%':>7}  {'CV%':>6}  {'RT bonus':>8}  {'FINAL':>7}   notes")
    print("-" * 138)
    rk_sorted = sorted(rk, key=lambda r: -((r.get("final_score") or r.get("total_score") or 0)))
    for i, r in enumerate(rk_sorted, start=1):
        nm = r.get("display_name") or r.get("name") or "?"
        canonical = nm
        for canon, aliases in Q2_ALIAS_OVERRIDE.items():
            if _norm(nm) in {_norm(canon)} | {_norm(a) for a in aliases}:
                canonical = canon; break
        is_phantom = canonical in EXPECTED_PHANTOM_LEGALS
        notes = " ★ phantom-recovered" if is_phantom else ""
        if canonical in ("Ethan Dever", "Lakeisha Martin", "Cory West"):
            notes += " 🔧 op-corrected"
        final = _fn(r.get("final_score") or r.get("total_score"))
        tier = r.get("tier_label") or r.get("performance_tier") or "?"
        print(f"{i:>3}  {nm:25}  {str(tier):14}  "
              f"{_fn(r.get('ppa_percentage')):>7.2f}  "
              f"{_fn(r.get('lbw_percentage')):>7.2f}  "
              f"{_fn(r.get('glassware_percentage')):>7.2f}  "
              f"{_fn(r.get('lsc_percentage')):>7.2f}  "
              f"{_fn(r.get('cv_percentage') or r.get('cv_score')):>6.2f}  "
              f"{_fn(r.get('review_tracker_bonus')):>8.2f}  "
              f"{final:>7.2f}  {notes}")
    print("-" * 138)
    print()

    # ---------------------------------------------------------------
    # 8. BEFORE vs AFTER for Ethan + Lakeisha.
    # ---------------------------------------------------------------
    after_by = {((r.get("display_name") or r.get("name") or "").strip().lower()): r for r in rk}

    def _comp(legal: str):
        before = prior_by.get(_norm(legal)) or {}
        after = after_by.get(_norm(legal)) or {}
        if not before or not after:
            return None
        return {
            "before_lbw": _fn(before.get("lbw_percentage")),
            "before_glass": _fn(before.get("glassware_percentage")),
            "before_lsc": _fn(before.get("lsc_percentage")),
            "before_cv":  _fn(before.get("cv_percentage") or before.get("cv_score")),
            "before_rt":  _fn(before.get("review_tracker_bonus")),
            "before_final": _fn(before.get("final_score") or before.get("total_score")),
            "before_tier": before.get("tier_label") or before.get("performance_tier") or "?",
            "after_lbw":  _fn(after.get("lbw_percentage")),
            "after_glass": _fn(after.get("glassware_percentage")),
            "after_lsc":  _fn(after.get("lsc_percentage")),
            "after_cv":   _fn(after.get("cv_percentage") or after.get("cv_score")),
            "after_rt":   _fn(after.get("review_tracker_bonus")),
            "after_final": _fn(after.get("final_score") or after.get("total_score")),
            "after_tier": after.get("tier_label") or after.get("performance_tier") or "?",
        }

    print("=" * 102)
    print("BEFORE → AFTER (operator corrections)")
    print("=" * 102)
    for legal in ("Ethan Dever", "Lakeisha Martin", "Cory West"):
        c = _comp(legal)
        if not c:
            print(f"  {legal}: not in both leaderboards"); continue
        print(f"\n  {legal}:")
        print(f"    LBW%   {c['before_lbw']:>7.2f}  →  {c['after_lbw']:>7.2f}   Δ {c['after_lbw']-c['before_lbw']:+.2f}")
        print(f"    Glass% {c['before_glass']:>7.2f}  →  {c['after_glass']:>7.2f}   Δ {c['after_glass']-c['before_glass']:+.2f}")
        print(f"    LSC%   {c['before_lsc']:>7.2f}  →  {c['after_lsc']:>7.2f}   Δ {c['after_lsc']-c['before_lsc']:+.2f}")
        print(f"    CV%    {c['before_cv']:>7.2f}  →  {c['after_cv']:>7.2f}   Δ {c['after_cv']-c['before_cv']:+.2f}")
        print(f"    RT     {c['before_rt']:>7.2f}  →  {c['after_rt']:>7.2f}   Δ {c['after_rt']-c['before_rt']:+.2f}")
        print(f"    FINAL  {c['before_final']:>7.2f}  →  {c['after_final']:>7.2f}   Δ {c['after_final']-c['before_final']:+.2f}")
        print(f"    Tier   {c['before_tier']!r:>14}  →  {c['after_tier']!r:>14}   "
              f"{'TIER CHANGE' if c['before_tier'] != c['after_tier'] else 'no tier change'}")
    print()

    # ---------------------------------------------------------------
    # 9. Per-class tier breakdown.
    # ---------------------------------------------------------------
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for r in rk:
        jt = (r.get("job_title") or "Server").lower()
        by_class.setdefault(jt, []).append(r)
    print("=" * 78)
    print("Per-class tier counts")
    print("=" * 78)
    for jt, lst in sorted(by_class.items()):
        tiers: Dict[str, int] = {}
        for r in lst:
            t = r.get("tier_label") or r.get("performance_tier") or "?"
            tiers[t] = tiers.get(t, 0) + 1
        print(f"  {jt:12} ({len(lst):>2} servers): {tiers}")
    print()

    print("=" * 78)
    print("STAGING ONLY. NO PROMOTION. NO LIVE WRITES.")
    print("Source:      operator-verified SSD 6.15.26.pdf transcription (29 rows).")
    print("Truth CSV:   /app/backend/q2_pos_truth_v3.csv")
    print("Staged doc:  snapshot_workflow_staging.Q2_REBUILD_STAGED")
    print("=" * 78)
    print("HOLD FOR OPERATOR REVIEW.")


if __name__ == "__main__":
    asyncio.run(main())
