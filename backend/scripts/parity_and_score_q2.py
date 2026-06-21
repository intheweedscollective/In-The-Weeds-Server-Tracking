"""
parity_and_score_q2.py — Mandatory parity check + leaderboard rescore
for the STAGED Q2 rebuild, using DIRECT INJECTION of live percentages
into the scorer's normalized-metric attributes (no raw back-solving).

Pipeline (mirrors run_full_scoring step-for-step, with one surgical
override AFTER step 6 and BEFORE step 7):
  1. calculate_lbw_total          — sum L/B/W raws on the model (we
                                     don't have them; safe no-op)
  2. calculate_derived_metrics    — computes per-guest ratios
  3. calculate_customer_voice_score — sets cv_score from NPS/promoters
  4. calculate_review_tracker_bonus — sets review_tracker_bonus
  5. calculate_combined_cv_rt     — diagnostic only
  6. calculate_normalized_scores  — writes score_ppa from ppa, would
                                     write 0 for score_lbw/glass/lsc
                                     since raws=0
  >>> INJECT: emp.score_lbw   = staged.lbw_percentage        (live_derived)
              emp.score_glass = staged.glassware_percentage  (live_derived)
              emp.score_lsc   = staged.lsc_percentage        (live_derived)
  7. calculate_bonus_points       — reads score_* (gets the injected
                                     percentages for LBW/Glass/LSC)
  8. calculate_dar_penalty
  9. calculate_total_score        — weights everything using locked Q2
  10. calculate_rankings
  11. calculate_performance_tiers

Read-only. Zero writes.
"""

import asyncio
import os
import sys
from typing import List

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from scoring_engine import (  # noqa: E402
    EmployeeV2, QuarterSettings, generate_hierarchy_rankings,
    calculate_lbw_total, calculate_derived_metrics,
    calculate_customer_voice_score, calculate_review_tracker_bonus,
    calculate_combined_cv_rt, calculate_normalized_scores,
    calculate_bonus_points, calculate_dar_penalty,
    calculate_total_score, calculate_rankings,
    calculate_performance_tiers,
)

LIVE_ANCHOR = {
    "Lakeisha Martin":  {"lbw_pct": 90.0,  "glass_pct": 110.4, "lsc_pct": 250.0},
    "Treyanna Quick":   {"lbw_pct": 115.2, "glass_pct": 175.6, "lsc_pct": 76.7},
    "Ethan Dever":      {"lbw_pct": 91.8,  "glass_pct": 113.3, "lsc_pct": 136.8},
}
PARITY_TOL = 0.5


def _fnum(v):
    if v is None or v == "": return 0.0
    try: return float(v)
    except (TypeError, ValueError): return 0.0


def score_with_direct_injection(
    staged_emps, settings: QuarterSettings,
) -> tuple:
    """Returns (scored_employees, rankings_dict_list)."""
    employees: List[EmployeeV2] = []
    inject_pcts: dict = {}
    for e in staged_emps:
        ev2 = EmployeeV2(
            id=e.get("id"), name=e.get("name"),
            display_name=e.get("display_name") or e.get("name"),
            job_title=e.get("job_title") or "Server",
            quarter=e.get("quarter"), year=e.get("year"),
            net_sales=_fnum(e.get("net_sales")),
            guests=int(_fnum(e.get("guests"))),
            ppa=_fnum(e.get("ppa")),
            # Raws stay 0 — we do NOT back-solve.
            lbw_per_guest=0.0,
            glassware_per_guest=0.0,
            guests_per_lsc=0.0,
            nps_score=_fnum(e.get("nps_score")),
            cv_promoters=0, cv_passives=0, cv_detractors=0,
            cv_score=_fnum(e.get("cv_score")),
            review_mentions=int(_fnum(e.get("rt_mentions"))),
            rt_mentions=int(_fnum(e.get("rt_mentions"))),
            review_tracker_bonus=_fnum(e.get("review_tracker_bonus")),
        )
        employees.append(ev2)
        inject_pcts[ev2.id] = {
            "lbw":   e.get("lbw_percentage"),
            "glass": e.get("glassware_percentage"),
            "lsc":   e.get("lsc_percentage"),
        }

    # Steps 1–5
    for emp in employees: calculate_lbw_total(emp)
    for emp in employees: calculate_derived_metrics(emp)
    for emp in employees: calculate_customer_voice_score(emp)
    for emp in employees: calculate_review_tracker_bonus(emp, settings)
    for emp in employees: calculate_combined_cv_rt(emp)
    # Step 6 — writes score_ppa from ppa; will set lbw/glass/lsc to 0
    # because raws are 0. That's fine, the next block overrides them.
    for emp in employees: calculate_normalized_scores(emp, settings)
    # >>> SURGICAL INJECTION — bypass raw→% for LBW/Glass/LSC only.
    for emp in employees:
        pcts = inject_pcts.get(emp.id) or {}
        if pcts.get("lbw")   is not None: emp.score_lbw   = float(pcts["lbw"])
        if pcts.get("glass") is not None: emp.score_glass = float(pcts["glass"])
        if pcts.get("lsc")   is not None: emp.score_lsc   = float(pcts["lsc"])
    # Steps 7–11
    for emp in employees: calculate_bonus_points(emp, settings)
    for emp in employees: calculate_dar_penalty(emp)
    for emp in employees: calculate_total_score(emp, settings)
    employees = calculate_rankings(employees)
    employees = calculate_performance_tiers(employees)
    for emp in employees:
        emp.quarter = settings.quarter
        emp.year = settings.year
        emp.quarter_settings_id = settings.id

    rankings = generate_hierarchy_rankings(employees, settings, first_name_only=False)
    return employees, rankings


def score_baseline_zero_metrics(staged_emps, settings: QuarterSettings) -> list:
    """PPA-only baseline (LBW/Glass/LSC forced to 0) for the tier-shift
    diff. Same shape as `score_with_direct_injection`, but the injection
    block is a no-op."""
    employees: List[EmployeeV2] = []
    for e in staged_emps:
        employees.append(EmployeeV2(
            id=e.get("id"), name=e.get("name"),
            display_name=e.get("display_name") or e.get("name"),
            job_title=e.get("job_title") or "Server",
            quarter=e.get("quarter"), year=e.get("year"),
            net_sales=_fnum(e.get("net_sales")),
            guests=int(_fnum(e.get("guests"))),
            ppa=_fnum(e.get("ppa")),
            lbw_per_guest=0.0, glassware_per_guest=0.0, guests_per_lsc=0.0,
            nps_score=_fnum(e.get("nps_score")),
            cv_promoters=0, cv_passives=0, cv_detractors=0,
            cv_score=_fnum(e.get("cv_score")),
            review_mentions=int(_fnum(e.get("rt_mentions"))),
            rt_mentions=int(_fnum(e.get("rt_mentions"))),
            review_tracker_bonus=_fnum(e.get("review_tracker_bonus")),
        ))
    for emp in employees: calculate_lbw_total(emp)
    for emp in employees: calculate_derived_metrics(emp)
    for emp in employees: calculate_customer_voice_score(emp)
    for emp in employees: calculate_review_tracker_bonus(emp, settings)
    for emp in employees: calculate_combined_cv_rt(emp)
    for emp in employees: calculate_normalized_scores(emp, settings)
    for emp in employees: calculate_bonus_points(emp, settings)
    for emp in employees: calculate_dar_penalty(emp)
    for emp in employees: calculate_total_score(emp, settings)
    employees = calculate_rankings(employees)
    employees = calculate_performance_tiers(employees)
    return generate_hierarchy_rankings(employees, settings, first_name_only=False)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    snap = await db.snapshot_workflow_staging.find_one({"name": "Q2_REBUILD_STAGED"})
    staged_emps = snap.get("employees") or []
    print(f"staged: {len(staged_emps)} employees from {snap.get('id')!r}")

    qs_doc = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    settings = QuarterSettings(**{k: v for k, v in qs_doc.items() if k != "_id"})
    print(f"settings is_locked={qs_doc.get('is_locked')!r}")
    print()

    # ---- PARITY CHECK against LIVE_ANCHOR --------------------------
    print("=" * 78)
    print("PARITY CHECK  (staged direct-injection vs live anchor, ±0.5)")
    print("=" * 78)
    by_name = {e["name"]: e for e in staged_emps}
    parity_fail = False
    print(f"{'name':22}  {'metric':10}  {'staged':>7}  {'live':>7}  {'Δ':>6}  {'src':14}  result")
    for legal, anchor in LIVE_ANCHOR.items():
        emp = by_name.get(legal)
        if not emp:
            print(f"  ❌ {legal!r} not in staged set"); parity_fail = True; continue
        for key, label, staged_field, src_field in [
            ("lbw_pct",   "LBW%",    "lbw_percentage",      "lbw_pct_source"),
            ("glass_pct", "Glass%",  "glassware_percentage","glass_pct_source"),
            ("lsc_pct",   "LSC%",    "lsc_percentage",      "lsc_pct_source"),
        ]:
            staged_pct = emp.get(staged_field)
            live_pct = anchor[key]
            src = emp.get(src_field) or "?"
            if staged_pct is None:
                print(f"{legal:22}  {label:10}  {'MISS':>7}  {live_pct:>7.2f}  "
                      f"{'n/a':>6}  {src:14}  ❌ FAIL"); parity_fail = True; continue
            d = staged_pct - live_pct
            ok = abs(d) <= PARITY_TOL
            mark = "✓" if ok else "❌ FAIL"
            print(f"{legal:22}  {label:10}  {staged_pct:>7.2f}  {live_pct:>7.2f}  "
                  f"{d:>+6.2f}  {src:14}  {mark}")
            if not ok: parity_fail = True

    if parity_fail:
        print("\nPARITY FAIL — stopping per protocol.")
        sys.exit(2)
    print(f"\n✓ All 9 parity checks passed within ±{PARITY_TOL}.\n")

    # ---- LEADERBOARD ---------------------------------------------
    print("=" * 78)
    print("FULL LEADERBOARD  (direct-injection scoring on staged set)")
    print("=" * 78)
    scored, rankings = score_with_direct_injection(staged_emps, settings)
    scored_by_id = {e.id: e for e in scored}
    hdr = (
        f"{'rk':>3}  {'pos':>5}  {'name':28}  "
        f"{'TOTAL':>7}  {'wPOS':>6}  "
        f"{'ppa%':>5}  {'lbw%':>5}  {'glass%':>6}  {'lsc%':>6}  "
        f"{'cv':>5}  {'rt':>5}  {'mb':>5}"
    )
    print(hdr); print("-" * len(hdr))
    new_tiers = {}
    for r in rankings:
        ev = scored_by_id.get(r.get("employee_id"))
        wpos = (getattr(ev, "weighted_score", 0) or 0) if ev else 0
        mb = (getattr(ev, "total_metric_bonus", 0) or 0) if ev else 0
        nm = (r.get("name") or "")
        new_tiers[nm] = (r.get("position_label") or "")[:1]
        print(
            f"{(r.get('peer_rank') or 0):>3}  "
            f"{(r.get('position_label') or ''):>5}  "
            f"{nm[:28]:28}  "
            f"{(r.get('total_score') or 0):>7.2f}  "
            f"{wpos:>6.2f}  "
            f"{(r.get('ppa_percentage') or 0):>5.1f}  "
            f"{(r.get('lbw_percentage') or 0):>5.1f}  "
            f"{(r.get('glassware_percentage') or 0):>6.1f}  "
            f"{(r.get('lsc_percentage') or 0):>6.1f}  "
            f"{(r.get('cv_score') or 0):>5.2f}  "
            f"{(r.get('review_tracker_bonus') or 0):>5.2f}  "
            f"{mb:>5.2f}"
        )

    # ---- TIER-SHIFT DIFF vs PPA-only baseline --------------------
    print()
    print("=" * 78)
    print("TIER-SHIFT DIFF — direct-injection vs PPA-only baseline")
    print("=" * 78)
    base_rankings = score_baseline_zero_metrics(staged_emps, settings)
    base_tiers = {r.get("name"): (r.get("position_label") or "")[:1]
                  for r in base_rankings}
    shifts = []
    for nm, new_t in new_tiers.items():
        old_t = base_tiers.get(nm, "?")
        if new_t != old_t:
            shifts.append((nm, old_t, new_t))
    print(f"servers shifted tier: {len(shifts)} / {len(new_tiers)}")
    for nm, old_t, new_t in shifts:
        print(f"  {nm:28}  {old_t!r}  →  {new_t!r}")

    print()
    print("PATH TAKEN     : C1 (direct injection of live-derived percentages; "
          "NO raw back-solving)")
    print(f"PARITY CHECK   : passed (9/9 within ±{PARITY_TOL})")
    print(f"TIER SHIFTS    : {len(shifts)} / {len(new_tiers)}")
    print("PROMOTION      : NOT executed. Held for operator sign-off.")


if __name__ == "__main__":
    asyncio.run(main())
