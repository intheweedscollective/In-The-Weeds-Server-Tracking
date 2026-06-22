"""
archive_daniel_mayorga.py — single targeted change.

Field used:  db.employees.status   (existing schema field)
Prior value: 'active'   (1 of 28 active canonicals; 6 already 'terminated')
New value:   'terminated'
Also set:    terminated_at = now (was None)
             archived_reason note for audit trail

NO deletion. current_metrics preserved for historical reference.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # ------------------------------------------------------------------
    # 0. Pre-state
    # ------------------------------------------------------------------
    before = await db.employees.find_one({"name": "Daniel Mayorga"})
    if not before:
        print("FATAL: db.employees has no 'Daniel Mayorga' canonical."); sys.exit(1)
    print("BEFORE:")
    print(f"   id              = {before.get('id')!r}")
    print(f"   name            = {before.get('name')!r}")
    print(f"   display_name    = {before.get('display_name')!r}")
    print(f"   STATUS FIELD    = 'status'   (existing schema field; "
          f"valid values seen in DB: active/merged/terminated/deleted)")
    print(f"   prior status    = {before.get('status')!r}")
    print(f"   terminated_at   = {before.get('terminated_at')!r}")
    print(f"   current_metrics = preserved (Q1 2026: net=${before.get('current_metrics',{}).get('net_sales')}, "
          f"final={before.get('current_metrics',{}).get('total_score')})")
    print()

    # ------------------------------------------------------------------
    # 1. Update — single, targeted.
    # ------------------------------------------------------------------
    now_iso = datetime.now(timezone.utc).isoformat()
    res = await db.employees.update_one(
        {"_id": before["_id"]},
        {"$set": {
            "status": "terminated",
            "terminated_at": now_iso,
            "archived_reason": "Former employee — no Q2 POS data; archived to suppress phantom row.",
            "updated_at": now_iso,
        }},
    )
    print(f"db.employees.update_one matched={res.matched_count} modified={res.modified_count}")
    after = await db.employees.find_one({"_id": before["_id"]})
    print()
    print("AFTER:")
    print(f"   status        = {after.get('status')!r}")
    print(f"   terminated_at = {after.get('terminated_at')!r}")
    print(f"   archived_reason = {after.get('archived_reason')!r}")
    print(f"   current_metrics PRESERVED: {bool(after.get('current_metrics'))}")
    print(f"   aliases       = {after.get('aliases')}  (unchanged)")
    print()

    # ------------------------------------------------------------------
    # 2. Re-hydrate live Q2P6W2 and verify Daniel is gone.
    # ------------------------------------------------------------------
    from snapshot_routes import _hydrate_snapshot_employees  # type: ignore
    from scoring_engine import (  # type: ignore
        EmployeeV2, QuarterSettings, run_full_scoring, generate_hierarchy_rankings,
    )

    qs = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    settings = QuarterSettings(**{k: v for k, v in qs.items() if k != "_id"})

    live = await db.snapshot_workflow.find_one({"name": "Q2P6W2"})
    hyd = await _hydrate_snapshot_employees(db, live)

    daniel_in_hyd = [e for e in hyd if (e.get("name") or e.get("display_name") or "").lower() == "daniel mayorga"]
    phantoms = [e for e in hyd if e.get("no_pos_data_this_period")]
    print(f"Hydrator returned {len(hyd)} rows.")
    print(f"   Daniel Mayorga in hydrated set? {len(daniel_in_hyd)} occurrence(s) "
          f"-> {'✓ removed' if not daniel_in_hyd else '❌ still present'}")
    print(f"   no_pos_data_this_period phantoms: {len(phantoms)} -> "
          f"{[e.get('display_name') or e.get('name') for e in phantoms]}")
    print()

    if daniel_in_hyd:
        print("❌ FAIL — Daniel still appears in hydrated rankings.")
        sys.exit(2)

    # ------------------------------------------------------------------
    # 3. Re-confirm scored set still 29, no other roster changes.
    # ------------------------------------------------------------------
    def _fn(v):
        try: return float(v or 0)
        except (TypeError, ValueError): return 0.0

    emps = []
    for e in hyd:
        if e.get("no_pos_data_this_period"): continue
        emps.append(EmployeeV2(
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
    scored = run_full_scoring(emps, settings)
    rk = generate_hierarchy_rankings(scored, settings, first_name_only=False)
    print(f"Scored set size: {len(scored)}   (must be 29)")
    if len(scored) != 29:
        print(f"❌ FAIL — scored set != 29."); sys.exit(3)
    print(f"✓ Scored set is 29.")
    print()

    # Verify the expected 29 are present, no others
    expected = {
        "Bruce Diesel Rabago", "Arianna Pena", "Jeden White", "Cory West",
        "Kahiaulani Ramos", "Rachael Escobar", "Adriana Bracamontes",
        "Jose Plancarte Villa", "Thomas Kozan", "Dylan Franklin",
        "Robert Mckinnon", "Polly Blocker", "Abigail Ostrowski",
        "Glennice Nguyen", "Ethan Dever", "Tarek Araman", "Kelsey Corkum",
        "Eddie Garcia", "Craig Simmons", "Eric Ostgarden",
        "Starwars Mckinnon-Herrera", "Caitlin Carden", "Jamie Rousseau",
        "Lexi Crandall", "Diane Peterson", "Treyanna Quick",
        "Julian Taveras", "Lakeisha Martin", "Kitti Xavier",
    }
    got = {(r.get("name") or "").strip() for r in rk}
    missing = expected - got
    extra = got - expected
    print(f"   missing from scored set: {sorted(missing) if missing else '(none)'}")
    print(f"   unexpected in scored:    {sorted(extra) if extra else '(none)'}")
    if missing or extra:
        print(f"❌ FAIL — roster drift detected."); sys.exit(4)
    print(f"✓ Roster identical to expected 29 — no other changes.")
    print()

    print("=" * 78)
    print("✓ DONE. Single change applied. Report and stop.")
    print("=" * 78)
    print(f"   db.employees.Daniel_Mayorga: status active → terminated")
    print(f"   current_metrics preserved (Q1 2026 historical record intact)")
    print(f"   hydrator phantom rows now: {len(phantoms)}")
    print(f"   scored set still: {len(scored)}")
    print(f"   roster drift: none")
    print()


if __name__ == "__main__":
    asyncio.run(main())
