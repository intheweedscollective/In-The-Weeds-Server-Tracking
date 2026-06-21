"""
score_staged_q2.py — READ-ONLY scoring of the STAGED Q2 rebuild using
the canonical scorer + locked Q2 2026 QuarterSettings.

Imports `EmployeeV2` and `generate_hierarchy_rankings` from
`scoring_engine.py` (the live ranking path's exact code) — no formula
or weight changes. The output is the PROVISIONAL leaderboard.

LBW / glassware / LSC inputs are not in the staged POS truth, so they
arrive at the scorer as 0 — they contribute 0 to the weighted score
through the unmodified formula. This is the honest score with only
POS+CV+RT in the staged inputs.

Zero DB writes.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from scoring_engine import (  # noqa: E402
    EmployeeV2,
    QuarterSettings,
    run_full_scoring,
    generate_hierarchy_rankings,
)

STAGED_COLL = "snapshot_workflow_staging"
STAGED_NAME = "Q2_REBUILD_STAGED"


def _fnum(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # 1. Locked Q2 settings — load and ABSOLUTELY do not mutate.
    qs_doc = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    if not qs_doc:
        print("FATAL: no Q2 2026 QuarterSettings found.", file=sys.stderr)
        sys.exit(1)
    is_locked = qs_doc.get("is_locked")
    # Pydantic model drops _id and DB-only fields via `extra="ignore"`.
    settings = QuarterSettings(**{k: v for k, v in qs_doc.items() if k != "_id"})
    print(f"locked Q2 QuarterSettings loaded (is_locked={is_locked})")
    print(f"  weights : ppa={settings.weight_ppa} lbw={settings.weight_lbw} "
          f"glass={settings.weight_glass} lsc={settings.weight_lsc} "
          f"cv={settings.weight_cv}")
    print(f"  bench   : ppa={settings.benchmark_ppa} lbw={settings.benchmark_lbw} "
          f"glass={settings.benchmark_glass} lsc={settings.benchmark_lsc} "
          f"cv={settings.benchmark_cv}")
    print(f"  rt_max  : {settings.rt_max_points}  rt/mention: "
          f"{settings.rt_points_per_mention}")
    print()

    # 2. Pull the staged employees and convert to EmployeeV2.
    snap = await db[STAGED_COLL].find_one({"name": STAGED_NAME})
    if not snap:
        print(f"FATAL: no staged doc {STAGED_NAME!r}.", file=sys.stderr)
        sys.exit(1)
    print(f"staged: {len(snap.get('employees') or [])} employees from "
          f"{snap.get('id')!r}")
    print()

    employees: List[EmployeeV2] = []
    for e in (snap.get("employees") or []):
        # Map staged fields → EmployeeV2's expected inputs. Missing
        # inputs (lbw_percentage, glassware_sales, lsc_percentage)
        # default to 0 in the model — the scorer's formula then
        # contributes 0 from those components. No formula change.
        ev2 = EmployeeV2(
            id=e.get("id"),
            name=e.get("name"),
            display_name=e.get("display_name") or e.get("name"),
            job_title=e.get("job_title") or "Server",
            quarter=e.get("quarter"),
            year=e.get("year"),
            net_sales=_fnum(e.get("net_sales")),
            guests=int(_fnum(e.get("guests"))),
            ppa=_fnum(e.get("ppa")),
            # No source data for these in the rebuild — explicit 0.
            lbw_percentage=0.0,
            glassware_sales=0.0,
            lsc_percentage=0.0,
            # CV path: NPS file is aggregate-only, so promoters/passives/
            # detractors are 0 (verified above on the live snapshot, this
            # matches its real-world shape).
            nps_score=_fnum(e.get("nps_score")),
            cv_promoters=0,
            cv_passives=0,
            cv_detractors=0,
            cv_score=_fnum(e.get("cv_score")),
            # RT path
            review_mentions=int(_fnum(e.get("rt_mentions"))),
            rt_mentions=int(_fnum(e.get("rt_mentions"))),
            review_tracker_bonus=_fnum(e.get("review_tracker_bonus")),
        )
        employees.append(ev2)

    # 3. Run the canonical scoring pipeline — IDENTICAL call shape to
    #    `run_full_scoring` invoked by the live ingest / ranking path.
    #    No formula or weight modification.
    scored = run_full_scoring(employees, settings)
    rankings = generate_hierarchy_rankings(scored, settings, first_name_only=False)

    # 4. Print the leaderboard — read from the rich rankings dict
    #    PLUS the scored EmployeeV2 objects (which carry
    #    `weighted_score` directly). Component breakdown:
    #      weighted_POS = `emp.weighted_score`  (capped POS × weights, no bonuses)
    #      cv_score     = `emp.cv_score`
    #      rt_bonus     = `emp.review_tracker_bonus`
    #      metric_bonus = `emp.total_metric_bonus`
    scored_by_id = {e.id: e for e in scored}

    hdr = (
        f"{'rk':>3}  {'pos':>5}  {'name':30}  "
        f"{'TOTAL':>7}  "
        f"{'wPOS':>6}  {'ppa%':>6}  {'mbonus':>7}  "
        f"{'cv':>6}  {'rt':>6}  {'ment':>5}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rankings:
        ev = scored_by_id.get(r.get("employee_id"))
        wpos = (getattr(ev, "weighted_score", 0) or 0) if ev else 0
        ppa_pct = r.get("ppa_percentage") or r.get("score_ppa") or 0
        mb = r.get("metric_bonus") or 0
        cv = r.get("cv_score") or 0
        rt = r.get("review_tracker_bonus") or r.get("review_bonus") or 0
        mentions = r.get("review_mentions") or r.get("rt_mentions") or 0
        print(
            f"{(r.get('peer_rank') or 0):>3}  "
            f"{(r.get('position_label') or ''):>5}  "
            f"{(r.get('name') or '')[:30]:30}  "
            f"{(r.get('total_score') or 0):>7.2f}  "
            f"{wpos:>6.2f}  "
            f"{ppa_pct:>6.1f}  "
            f"{mb:>7.2f}  "
            f"{cv:>6.2f}  "
            f"{rt:>6.2f}  "
            f"{mentions:>5}"
        )

    print()
    print(f"PROVISIONAL — total_score uses the locked Q2 formula. CV is "
          f"'aggregate_only' (NPS pts only; promoters/passives/detractors=0). "
          f"LBW/glassware/LSC = 0 since not in the rebuild inputs.")


if __name__ == "__main__":
    asyncio.run(main())
