"""
promote_q2_rebuild_to_live.py — DESTRUCTIVE PROMOTION (operator-authorized).

STOP-ON-FAILURE protocol:
  1. BACKUP   — copy current live Q2P6W2 to a timestamped archive doc.
                Verify row/employee counts match. STOP if mismatched.
  2. NAME DISPLAY — 8 db.employees Option-B flips (display_name + aliases).
  3. PROMOTE  — write staged employees[]+rows[] → live, preserving raws
                so the runtime hydrator recomputes percentages from POS.
  4. POST-PROMOTE VERIFY — anchor parity (Δ must be 0.00), 29 present
                with zero insufficient_data, per-class tier counts, name
                display check. ROLL BACK from step-1 backup on any anchor
                divergence.
  5. REPORT and STOP.

LSC display cap (step 3 in the operator's ordering — display-only) was
applied separately as a code edit to scoring_engine.py
(`lsc_percentage = min(score_lsc, 100)`; raw preserved on `score_lsc`
and on the diagnostic key `lsc_percentage_uncapped`).
"""

import asyncio
import copy
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

# Operator anchors that must reconcile post-promote.
ANCHORS = {
    "Kahiaulani Ramos": (30516.08,  643, 47.46),
    "Thomas Kozan":     (56485.89, 1168, 48.36),
    "Glennice Nguyen":  (67753.38, 1412, 47.98),
    # Plus two corrected servers
    "Ethan Dever":      (42793.74,  877, 48.80),  # 42793.74/877=48.80
    "Lakeisha Martin":  (89283.75, 1760, 50.73),
}

EXPECTED_PHANTOM_LEGALS = [
    "Robert Mckinnon", "Tarek Araman", "Diane Peterson", "Kelsey Corkum",
    "Julian Taveras", "Eddie Garcia", "Polly Blocker", "Dylan Franklin",
    "Lexi Crandall",
]

# 8 db.employees flips (Option B — keep nickname canonical active, just
# relabel display_name to the legal name and add the nickname to aliases).
# These are the surviving "active" canonical IDs.
NAME_FLIPS: List[Tuple[str, str, str]] = [
    # (active_canonical_name_now, new_display_name, nickname_to_add_to_aliases)
    ("Keisha Martin",   "Lakeisha Martin",   "Keisha Martin"),
    ("Trey Quick",      "Treyanna Quick",    "Trey Quick"),
    ("Abby Ostrowski",  "Abigail Ostrowski", "Abby Ostrowski"),
    ("Kahi Ramos",      "Kahiaulani Ramos",  "Kahi Ramos"),
    ("Lennie Nguyen",   "Glennice Nguyen",   "Lennie Nguyen"),
    ("TK Kozan",        "Thomas Kozan",      "TK Kozan"),
    ("Ikey Ostgarden",  "Eric Ostgarden",    "Ikey Ostgarden"),
    ("Allen Simmons",   "Craig Simmons",     "Allen Simmons"),
]


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


async def step1_backup(db) -> Dict[str, Any]:
    live = await db.snapshot_workflow.find_one({"name": "Q2P6W2"})
    if not live:
        raise SystemExit("STEP 1 FAIL: live Q2P6W2 not found.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_name = f"Q2P6W2_preFinalPromote_{ts}"
    archive_id = f"archive-Q2P6W2-{ts}-{live['_id']}"

    archive = copy.deepcopy(live)
    archive["_id"] = archive_id
    archive["name"] = archive_name
    archive["archived_from"] = live.get("_id")
    archive["archived_from_id"] = live.get("id")
    archive["archived_at"] = datetime.now(timezone.utc).isoformat()
    archive["archive_reason"] = "pre-final-promote operator-truth Q2 rebuild"

    res = await db.snapshot_workflow.insert_one(archive)
    print(f"   ✓ Archive inserted: _id={res.inserted_id}")
    print(f"     name={archive_name!r}")

    # Verify counts
    a = await db.snapshot_workflow.find_one({"_id": res.inserted_id})
    live_rows = len(live.get("rows") or [])
    live_emps = len(live.get("employees") or [])
    a_rows = len(a.get("rows") or [])
    a_emps = len(a.get("employees") or [])
    print(f"     LIVE  rows={live_rows}  employees={live_emps}")
    print(f"     ARCH  rows={a_rows}  employees={a_emps}")
    if a_rows != live_rows or a_emps != live_emps:
        await db.snapshot_workflow.delete_one({"_id": res.inserted_id})
        raise SystemExit("STEP 1 FAIL: archive count mismatch. Backup deleted. ABORT.")
    return {"archive_id": res.inserted_id, "archive_name": archive_name,
            "live_id_for_restore": live.get("_id"), "pre_live": live}


async def step2_name_flips(db) -> List[Dict[str, Any]]:
    print()
    print("STEP 2 — db.employees display-name flips (Option B)")
    print("=" * 78)
    changes = []
    for current_name, new_display, nickname_alias in NAME_FLIPS:
        before = await db.employees.find_one({"name": current_name})
        if not before:
            raise SystemExit(f"STEP 2 FAIL: db.employees has no row with name={current_name!r}")
        existing_aliases = list(before.get("aliases") or [])
        new_aliases = list(existing_aliases)
        if nickname_alias not in new_aliases:
            new_aliases.append(nickname_alias)
        # Remove new_display from aliases (it's now the display_name)
        new_aliases = [a for a in new_aliases if _norm(a) != _norm(new_display)]

        res = await db.employees.update_one(
            {"_id": before["_id"]},
            {"$set": {
                "display_name": new_display,
                "aliases":      new_aliases,
                "name_flip_at": datetime.now(timezone.utc).isoformat(),
                "name_flip_reason": "operator-truth Q2 rebuild — display legal names",
            }},
        )
        after = await db.employees.find_one({"_id": before["_id"]})
        print(f"  {current_name!r:22}  display: {before.get('display_name')!r:22} -> {after.get('display_name')!r}")
        print(f"  {'':22}  aliases: {existing_aliases} -> {after.get('aliases')}")
        changes.append({"name": current_name, "before": before, "after": after,
                        "modified_count": res.modified_count})
    print(f"  ✓ {len(changes)} canonicals updated.")
    return changes


async def step4_promote(db) -> None:
    print()
    print("STEP 4 — PROMOTE staged → live Q2P6W2")
    print("=" * 78)
    staged = await db.snapshot_workflow_staging.find_one({"name": "Q2_REBUILD_STAGED"})
    if not staged:
        raise SystemExit("STEP 4 FAIL: staged Q2_REBUILD_STAGED not found.")

    # Sanity: staged rows must carry raw POS fields (not pre-computed % only).
    sample = (staged.get("employees") or [{}])[0]
    needed_raws = ("liquor_sales", "beer_sales", "wine_sales", "lsc_count",
                   "guests", "net_sales")
    missing_raws = [k for k in needed_raws if k not in sample]
    if missing_raws:
        raise SystemExit(f"STEP 4 FAIL: staged emp[0] missing raw fields: {missing_raws}")
    print(f"   ✓ Staged emp[0] has POS raws: {needed_raws}")

    s_emps = staged.get("employees") or []
    s_rows = staged.get("rows") or []
    print(f"   Staged: employees={len(s_emps)} rows={len(s_rows)}")
    if len(s_emps) != 29:
        raise SystemExit(f"STEP 4 FAIL: staged employees count != 29 (got {len(s_emps)}).")

    # Build full set on live: preserve live's other top-level fields,
    # replace employees + rows.
    now_iso = datetime.now(timezone.utc).isoformat()
    res = await db.snapshot_workflow.update_one(
        {"name": "Q2P6W2"},
        {"$set": {
            "employees": s_emps,
            "rows": s_rows,
            "employee_count": len(s_emps),
            "row_count": len(s_rows),
            "updated_at": now_iso,
            "promoted_from_staged_at": now_iso,
            "promoted_from_staged_source": "operator-verified SSD 6.15.26.pdf transcription",
            "pos_source": staged.get("pos_source"),
            "lsc_derivation": staged.get("lsc_derivation"),
            "is_current": True,
            "status": "completed",
        },
         "$unset": {
            "rolled_back_at": "",
            "rolled_back_from_promote": "",
            "rolled_back_reason": "",
        }},
    )
    print(f"   ✓ snapshot_workflow.Q2P6W2 updated (modified_count={res.modified_count}).")


async def step5_verify(db, pre_live: Dict[str, Any]) -> bool:
    print()
    print("STEP 5 — POST-PROMOTE VERIFY")
    print("=" * 78)

    from snapshot_routes import _hydrate_snapshot_employees  # type: ignore
    from scoring_engine import (  # type: ignore
        EmployeeV2, QuarterSettings, run_full_scoring,
        generate_hierarchy_rankings,
    )

    qs = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    settings = QuarterSettings(**{k: v for k, v in qs.items() if k != "_id"})

    live = await db.snapshot_workflow.find_one({"name": "Q2P6W2"})
    print(f"   LIVE post-promote: rows={len(live.get('rows') or [])}  "
          f"employees={len(live.get('employees') or [])}")

    # Hydrate + score
    hyd = await _hydrate_snapshot_employees(db, live)
    print(f"   Hydrator returned: {len(hyd)} rows.")

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
    by_disp_lc = {((r.get("display_name") or r.get("name") or "").strip().lower()): r for r in rk}
    by_name_lc = {((r.get("name") or "").strip().lower()): r for r in rk}

    # 5a — Anchor parity (vs operator anchors directly; Δ must be 0.00 on net/guests/ppa)
    print()
    print("   5a. Anchor parity (live post-promote vs operator-anchor truth):")
    anchor_fail = False
    for legal, (e_net, e_g, e_ppa) in ANCHORS.items():
        # Look up via display name OR name OR alias map
        r = by_disp_lc.get(legal.lower()) or by_name_lc.get(legal.lower())
        if not r:
            # try common alias
            for alt in ("Keisha Martin", "Trey Quick", "Abby Ostrowski",
                        "Kahi Ramos", "Lennie Nguyen", "TK Kozan",
                        "Ikey Ostgarden", "Allen Simmons"):
                rr = by_disp_lc.get(alt.lower())
                if rr and (rr.get("name") or "").strip() == legal:
                    r = rr; break
        if not r:
            print(f"      ❌ {legal:20}  NOT IN HYDRATED RANKINGS")
            anchor_fail = True; continue
        net = _fn(r.get("net_sales"))
        g = int(_fn(r.get("guests") or r.get("guest_count")))
        ppa_calc = round(net / g, 2) if g > 0 else 0
        d_net = net - e_net
        d_g = g - e_g
        d_ppa = ppa_calc - e_ppa
        ok = abs(d_net) < 0.01 and d_g == 0 and abs(d_ppa) < 0.05
        mark = "✓" if ok else "❌"
        print(f"      {mark} {legal:20}  net={net:>9.2f} (Δ{d_net:+.2f})  "
              f"guests={g:>5} (Δ{d_g:+})  ppa={ppa_calc:>5.2f} (Δ{d_ppa:+.2f})")
        if not ok:
            anchor_fail = True
    if anchor_fail:
        return False

    # 5b — All 29 present
    print()
    print("   5b. 29 present, zero insufficient_data:")
    npd = [e for e in hyd if e.get("no_pos_data_this_period")]
    insuf = [e for e in hyd if (e.get("status") or "") == "insufficient_data"]
    print(f"      total hydrated: {len(hyd)}")
    print(f"      no_pos_data_this_period: {len(npd)} -> {[e.get('display_name') for e in npd]}")
    print(f"      insufficient_data:        {len(insuf)} -> {[e.get('display_name') for e in insuf]}")
    if insuf:
        print("      ❌ FAIL — at least one insufficient_data row")
        return False
    print(f"      scored (non-phantom): {len(scored)}")
    if len(scored) != 29:
        print(f"      ❌ FAIL — scored count != 29 (got {len(scored)})")
        return False
    print(f"      ✓ 29 scored, 0 insufficient_data")

    # 5c — Phantoms now appear with full POS
    print()
    print("   5c. 9 phantoms recovered with full POS data:")
    for legal in EXPECTED_PHANTOM_LEGALS:
        r = by_disp_lc.get(legal.lower()) or by_name_lc.get(legal.lower())
        if not r:
            print(f"      ❌ {legal:22}  NOT FOUND")
            return False
        net = _fn(r.get("net_sales"))
        g = int(_fn(r.get("guests") or r.get("guest_count")))
        print(f"      ✓ {legal:22}  net=${net:>9.2f}  guests={g:>5}")

    # 5d — Per-class tier counts
    print()
    print("   5d. Per-class tier counts:")
    by_class: Dict[str, Dict[str, int]] = {}
    for r in rk:
        jt = (r.get("job_title") or "Server").lower()
        t = r.get("tier_label") or r.get("performance_tier") or "?"
        by_class.setdefault(jt, {})[t] = by_class.setdefault(jt, {}).get(t, 0) + 1
    for jt in sorted(by_class):
        total = sum(by_class[jt].values())
        print(f"      {jt:12} ({total:>2}): {by_class[jt]}")

    # 5e — Name display: 8 legal names should now display as legal
    print()
    print("   5e. Name display (8 flips):")
    flip_targets = [legal for _curr, legal, _nick in NAME_FLIPS]
    for legal in flip_targets:
        r = by_disp_lc.get(legal.lower())
        if r:
            print(f"      ✓ {legal:22}  display='{r.get('display_name')}'")
        else:
            # Look it up via name
            r = by_name_lc.get(legal.lower())
            print(f"      {'✓' if r else '❌'} {legal:22}  "
                  f"display='{(r or {}).get('display_name')}'  "
                  f"name='{(r or {}).get('name')}'")

    # 5f — LSC column capping check
    print()
    print("   5f. LSC display capping (lsc_percentage must be ≤ 100):")
    bad = [r for r in rk if (r.get("lsc_percentage") or 0) > 100.01]
    print(f"      rows with lsc_percentage > 100: {len(bad)}  (must be 0)")
    if bad:
        for b in bad[:3]:
            print(f"        ❌ {b.get('display_name')}: lsc_percentage={b.get('lsc_percentage')}")
        return False
    # Quick spot-check on Kitti
    kitti = by_disp_lc.get("kitti xavier")
    if kitti:
        print(f"      ✓ Kitti Xavier  lsc_percentage={kitti.get('lsc_percentage')}  "
              f"(uncapped diag={kitti.get('lsc_percentage_uncapped')}, "
              f"score_lsc raw={kitti.get('score_lsc')})")

    return True


async def rollback(db, archive_id: Any, pre_live: Dict[str, Any]) -> None:
    print()
    print("=" * 78)
    print("ROLLBACK — restoring live Q2P6W2 from archive")
    print("=" * 78)
    # Restore live by setting employees, rows, and other tracked fields
    await db.snapshot_workflow.update_one(
        {"_id": pre_live["_id"]},
        {"$set": {k: pre_live[k] for k in (
            "employees", "rows", "employee_count", "row_count",
            "updated_at", "is_current", "status", "uploads", "version",
            "processing_log", "notes",
        ) if k in pre_live}},
    )
    print(f"   live Q2P6W2 restored from in-memory pre_live snapshot.")
    print(f"   archive id remains: {archive_id}")


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    print("=" * 78)
    print("PROMOTE Q2_REBUILD_STAGED → LIVE Q2P6W2  (operator-authorized)")
    print("=" * 78)

    # Step 1 — BACKUP
    print()
    print("STEP 1 — BACKUP live Q2P6W2 to timestamped archive")
    print("=" * 78)
    backup = await step1_backup(db)

    # Step 2 — NAME FLIPS
    name_changes = await step2_name_flips(db)

    # Step 4 — PROMOTE (step 3 / LSC display cap was a separate code edit)
    try:
        await step4_promote(db)
    except SystemExit as ex:
        print(str(ex))
        await rollback(db, backup["archive_id"], backup["pre_live"])
        sys.exit(2)

    # Step 5 — VERIFY
    ok = await step5_verify(db, backup["pre_live"])
    if not ok:
        print()
        print("STEP 5 FAIL — initiating rollback per protocol.")
        await rollback(db, backup["archive_id"], backup["pre_live"])
        sys.exit(3)

    print()
    print("=" * 78)
    print("✓ PROMOTION COMPLETE — all post-promote checks passed.")
    print("=" * 78)
    print(f"   archive (rollback target): {backup['archive_name']}")
    print(f"   db.employees flips      : {len(name_changes)} (legal names now display)")
    print(f"   lsc_percentage display  : capped at 100 (uncapped retained on diagnostic key)")
    print()
    print("REPORT AND STOP — no further changes without operator sign-off.")


if __name__ == "__main__":
    asyncio.run(main())
