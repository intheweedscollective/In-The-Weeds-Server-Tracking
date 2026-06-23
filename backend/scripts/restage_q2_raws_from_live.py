"""
restage_q2_raws_from_live.py — STAGING-ONLY.

Copies the AUTHORITATIVE raw POS fields from each canonical's authoritative
live snapshot row into the staged rows so the hydrator/scorer can recompute
LBW/Glass/LSC normally — no back-solving, no fabrication, no formula change.

Authoritative row = the live snapshot row whose net_sales matches the
canonical's POS truth value EXACTLY (for split servers that's the typo'd row,
verified in the earlier merge validation). For non-split servers it's the only
row carrying that legal name OR any alias mapped via Q2_ALIAS_OVERRIDE.

Zero writes to `snapshot_workflow` (live). Only updates
`snapshot_workflow_staging.Q2_REBUILD_STAGED`.

Then runs the live `_hydrate_snapshot_employees` + scorer on the staged doc
and prints the parity check for:
  - Clean anchors: Lakeisha Martin, Treyanna Quick, Ethan Dever
  - Split/truth-override servers: Kahiaulani Ramos, Glennice Nguyen
"""

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from scripts.stage_q2_rebuild import Q2_ALIAS_OVERRIDE  # type: ignore


# --------------------------------------------------------------------
# Parity anchors — what the staged hydrator+scorer must reproduce.
#
# For CLEAN anchors (Lakeisha / Treyanna / Ethan): the single authoritative
# live row IS what live displays today, so staged % == live-displayed %.
#
# For SPLIT / TRUTH-OVERRIDE anchors (Kahiaulani / Glennice): the live
# display is a *mongrel* — the active canonical (Kahi Ramos / Lennie
# Nguyen) survived dedup but its displayed % is a mix of fields pulled
# from MULTIPLE alias rows by the hydrator overlay. So "live displayed"
# is not a valid correctness target here. The correctness target is
# the standalone-scored % computed from the AUTHORITATIVE typo'd row's
# raws + the official Q2 benchmarks:
#   score_lbw   = lbw_per_guest    / benchmark_lbw   * 100
#   score_glass = glass_per_guest  / benchmark_glass * 100
#   score_lsc   = benchmark_lsc / guests_per_lsc * 100   (inverse)
# Q2 benchmarks (validated against db.quarter_settings): lbw=8.0,
# glass=1.35, lsc=100.0
#
# Authoritative typo'd row raws (verified above on Q2P6W2 live):
#   Kahiaulanl Ramos: lbw_per_g=6.38  glass_per_g=1.38  guests_per_lsc=128.60
#   Glennlce Nguyen:  lbw_per_g=6.17  glass_per_g=1.64  guests_per_lsc=108.62
# Standalone scoring of those raws:
#   Kahiaulani: lbw=79.75  glass=102.22  lsc=77.76
#   Glennice:   lbw=77.12  glass=121.48  lsc=92.06
# --------------------------------------------------------------------
LIVE_ANCHOR: Dict[str, Dict[str, Any]] = {
    "Lakeisha Martin": {
        "lbw": 90.00, "glass": 110.37, "lsc": 250.00,
        "anchor_kind": "clean", "src_row": "Lakeisha Martin",
    },
    "Treyanna Quick": {
        "lbw": 115.25, "glass": 175.56, "lsc": 76.70,
        "anchor_kind": "clean", "src_row": "Treyanna Quick",
    },
    "Ethan Dever": {
        "lbw": 91.75, "glass": 113.33, "lsc": 136.84,
        "anchor_kind": "clean", "src_row": "Ethan Dever",
    },
    "Kahiaulani Ramos": {
        "lbw": 79.75, "glass": 102.22, "lsc": 77.76,
        "anchor_kind": "split", "src_row": "Kahiaulanl Ramos",
    },
    "Glennice Nguyen": {
        "lbw": 77.12, "glass": 121.48, "lsc": 92.06,
        "anchor_kind": "split", "src_row": "Glennlce Nguyen",
    },
}

# Negative-control: what staged % WOULD have produced if raws had been
# pulled from a duplicate alias row instead of the authoritative one.
# Used as proof-by-contrast that the script picked the right row.
DUP_ROW_SCORES: Dict[str, Dict[str, Tuple[str, float, float, float]]] = {
    # canonical -> dup_row_name -> (lbw, glass, lsc)
    "Kahiaulani Ramos": {
        "Kahi Ramos":       (83.00,  97.04, 36.17),
        "Kahiauani Ramos":  (101.12, 104.44, 84.39),
        "Kahiaulani Ramos (non-typo)": (83.00, 97.04, 90.42),
    },
    "Glennice Nguyen": {
        "Lennie Nguyen":     (78.25, 119.26, 97.52),
        "Glennice Nguyen (non-typo)": (78.25, 119.26, 97.52),
    },
}

TOL = 0.5  # ±0.5 percentage point tolerance — anything bigger is a real diff.

# --------------------------------------------------------------------
# FRESH-SESSION CONSTRAINT: GUARDED PHANTOM SKIP
# Expected phantom servers (legal canonicals present in staged Q2 rebuild
# but with NO authoritative live snapshot row). Matched by first name.
# If a staged employee falls through that is NOT in this set -> HALT.
# If the final skipped count != 9 -> HALT.
# --------------------------------------------------------------------
EXPECTED_PHANTOM_FIRST_NAMES: Set[str] = {
    "Tarek", "Diane", "Kelsey", "Robert", "Eddie",
    "Julian", "Polly", "Dylan", "Lexi",
}

# --------------------------------------------------------------------
# RAW FIELDS the hydrator/scorer consumes for LBW/Glass/LSC.
#
# Scorer pipeline (scoring_engine.run_full_scoring -> calculate_lbw_total
# -> calculate_derived_metrics -> calculate_normalized_scores):
#   lbw           = liquor_sales + beer_sales + wine_sales
#   lbw_per_guest = lbw / guests
#   glassware_per_guest = glassware_sales / guests
#   guests_per_lsc      = guests / lsc_count
#   score_lbw   = (lbw_per_guest / benchmark_lbw) * 100
#   score_glass = (glassware_per_guest / benchmark_glass) * 100
#   score_lsc   = (benchmark_lsc / guests_per_lsc) * 100   (inverse)
#
# So the MINIMAL raw source fields needed are:
#   liquor_sales, beer_sales, wine_sales       (LBW source)
#   glassware_sales / bar_glassware_sales      (Glass source)
#   lsc_count / loyalty_sales                  (LSC source)
#   plus guests (already on the staged row)
#
# We also copy the pre-derived per-guest ratios for traceability/debug,
# but the scorer will overwrite them from the raw sources above.
# --------------------------------------------------------------------
RAW_FIELDS: Tuple[str, ...] = (
    "liquor_sales", "beer_sales", "wine_sales",
    "lbw", "lbw_per_guest",
    "bar_glassware_sales", "glassware_sales", "glassware_per_guest",
    "lsc_count", "loyalty_sales", "guests_per_lsc",
)


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _first_name(legal: str) -> str:
    return (legal or "").strip().split()[0] if legal and legal.strip() else ""


def _find_authoritative_row(
    canonical_legal: str,
    truth_net_sales: float,
    live_rows: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return the live row whose frozen_display_name matches the canonical
    OR any Q2_ALIAS_OVERRIDE alias, AND whose net_sales equals the staged
    POS truth net_sales (within $0.01). For non-split servers a single
    name-match row is accepted as authoritative.

    Never sums alias rows. Never fabricates. Never back-solves.
    """
    candidates_names = {_norm(canonical_legal)} | {
        _norm(v) for v in Q2_ALIAS_OVERRIDE.get(canonical_legal, [])
    }

    # First pass: name-match AND net_sales-match.
    for r in live_rows:
        nm = _norm(r.get("frozen_display_name"))
        if nm not in candidates_names:
            continue
        fm = r.get("frozen_metrics") or {}
        try:
            ns = float(fm.get("net_sales") or 0)
        except (TypeError, ValueError):
            ns = 0.0
        if abs(ns - truth_net_sales) <= 0.01:
            return r, "exact_match"

    # Second pass: single name-match row with no net_sales hit -> accept.
    matches = [r for r in live_rows
               if _norm(r.get("frozen_display_name")) in candidates_names]
    if len(matches) == 1:
        return matches[0], "single_row"
    if len(matches) > 1:
        return None, f"AMBIGUOUS_{len(matches)}_ROWS_NO_TRUTH_MATCH"
    return None, "NO_NAME_MATCH"


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    live = await db.snapshot_workflow.find_one({"name": "Q2P6W2"})
    staged = await db.snapshot_workflow_staging.find_one({"name": "Q2_REBUILD_STAGED"})
    if not live or not staged:
        print("FATAL: live or staged doc missing.", file=sys.stderr)
        sys.exit(1)
    live_rows = live.get("rows") or []
    staged_emps = list(staged.get("employees") or [])
    staged_rows = list(staged.get("rows") or [])
    print(f"live rows: {len(live_rows)}   staged employees: {len(staged_emps)}   staged rows: {len(staged_rows)}")
    print(f"RAW field set (hydrator/scorer consumed): {RAW_FIELDS}")
    print(f"EXPECTED_PHANTOM_FIRST_NAMES: {sorted(EXPECTED_PHANTOM_FIRST_NAMES)}")
    print()

    # --------------------------------------------------------------
    # Phase A — for each staged employee, find authoritative live row
    # and copy raws. Guarded skip for the 9 expected phantoms ONLY.
    # --------------------------------------------------------------
    applied: List[str] = []
    skipped_phantoms: List[str] = []
    by_legal: Dict[str, Dict[str, Any]] = {}

    for e in staged_emps:
        legal = e.get("name") or ""
        truth_ns = float(e.get("net_sales") or 0)
        auth, method = _find_authoritative_row(legal, truth_ns, live_rows)

        if auth is None:
            fn = _first_name(legal)
            if fn in EXPECTED_PHANTOM_FIRST_NAMES:
                skipped_phantoms.append(legal)
                continue
            # Unexpected miss — HALT, do not silently fall through.
            print()
            print("=" * 70)
            print("HALT — UNEXPECTED NO-MATCH SERVER")
            print("=" * 70)
            print(f"  staged_name   = {legal!r}")
            print(f"  staged_net_$  = {truth_ns}")
            print(f"  reason        = {method}")
            print(f"  first_name    = {fn!r}  (not in EXPECTED_PHANTOM_FIRST_NAMES)")
            print()
            print("This server is not on the expected 9-phantom list. Either an "
                  "alias is missing from Q2_ALIAS_OVERRIDE, or a real server "
                  "silently fell through an identity mismatch. Investigate "
                  "before re-running.")
            sys.exit(2)

        # Found authoritative row -> capture raws for use on both
        # employees[] and rows[].
        fm = auth.get("frozen_metrics") or {}
        raws = {k: fm.get(k) for k in RAW_FIELDS}
        by_legal[legal] = {
            "raws": raws,
            "auth_live_name": auth.get("frozen_display_name"),
            "method": method,
        }
        applied.append(legal)

    # --------------------------------------------------------------
    # Phase B — assertions on counts AND set identity.
    # --------------------------------------------------------------
    skipped_first_names = {_first_name(n) for n in skipped_phantoms}

    print(f"applied_count       = {len(applied):>3}   (expected 20)")
    print(f"skipped_phantoms    = {len(skipped_phantoms):>3}   (expected 9)")
    print(f"  -> {sorted(skipped_phantoms)}")
    print(f"  -> first names: {sorted(skipped_first_names)}")
    print(f"total_staged        = {len(staged_emps):>3}")
    print()

    if len(skipped_phantoms) != 9:
        print("HALT — skipped count != 9.", file=sys.stderr)
        sys.exit(3)

    if skipped_first_names != EXPECTED_PHANTOM_FIRST_NAMES:
        missing = EXPECTED_PHANTOM_FIRST_NAMES - skipped_first_names
        extra = skipped_first_names - EXPECTED_PHANTOM_FIRST_NAMES
        print("HALT — skipped phantom set != EXPECTED_PHANTOM_FIRST_NAMES.")
        print(f"  missing from skipped (expected, not seen): {sorted(missing)}")
        print(f"  unexpected in skipped (seen, not expected): {sorted(extra)}")
        sys.exit(4)

    print("✓ Set-equality A: skipped == EXPECTED_PHANTOM_FIRST_NAMES")

    if len(applied) != 20:
        print(f"HALT — applied_count != 20 (got {len(applied)}).", file=sys.stderr)
        sys.exit(5)

    # --------------------------------------------------------------
    # Phase C — write raws into BOTH employees[] AND rows[] for the
    # 20 applied servers. The hydrator falls back to snapshot["employees"]
    # when the staging doc's id is not present in snapshot_workflow, so
    # employees[] is the path that actually feeds the scorer here. We
    # update rows[] too for downstream consistency / future promote.
    # --------------------------------------------------------------
    new_employees: List[Dict[str, Any]] = []
    for e in staged_emps:
        legal = e.get("name") or ""
        if legal in by_legal:
            raws = by_legal[legal]["raws"]
            # Merge raws onto the staged employee dict. Do NOT clobber
            # truth-override fields (net_sales, guests, ppa) that came
            # from POS truth — only fill the raw POS fields the scorer
            # needs to recompute per-guest ratios.
            merged = dict(e)
            for k, v in raws.items():
                merged[k] = v
            # The scorer reads `glassware_sales` from EmployeeV2; copy
            # bar_glassware_sales into glassware_sales when only the
            # bar_ variant was on the live row.
            if not merged.get("glassware_sales") and merged.get("bar_glassware_sales") is not None:
                merged["glassware_sales"] = merged["bar_glassware_sales"]
            new_employees.append(merged)
        else:
            # Phantom -> leave the row untouched. It'll be tagged
            # status="insufficient_data" in the separate authorized
            # promotion step.
            new_employees.append(e)

    new_rows: List[Dict[str, Any]] = []
    for e in new_employees:
        legal = e.get("name") or ""
        raws = (by_legal.get(legal) or {}).get("raws") or {}
        # Rebuild the thin row with frozen_metrics carrying truth + raws.
        new_rows.append({
            "employee_id": e.get("id"),
            "frozen_display_name": legal,
            "frozen_report_name": e.get("report_name") or legal,
            "frozen_score": None,
            "frozen_metrics": {
                "name": legal,
                # Truth-override (PPA-driving):
                "net_sales":   e.get("net_sales"),
                "guests":      e.get("guests"),
                "guest_count": e.get("guests"),
                "ppa":         e.get("ppa"),
                # CV/RT (already on staged emp):
                "nps_score":      e.get("nps_score"),
                "cv_promoters":   e.get("cv_promoters"),
                "cv_passives":    e.get("cv_passives"),
                "cv_detractors":  e.get("cv_detractors"),
                "review_mentions": e.get("rt_mentions"),
                "rt_mentions":     e.get("rt_mentions"),
                # AUTHORITATIVE raws copied from live (NO summing, NO fabrication):
                **raws,
                # Glassware fallback
                "glassware_sales": e.get("glassware_sales") or raws.get("glassware_sales") or raws.get("bar_glassware_sales"),
            },
        })

    await db.snapshot_workflow_staging.update_one(
        {"_id": staged["_id"]},
        {"$set": {
            "employees": new_employees,
            "rows": new_rows,
            "raws_copied_at": "2026-02 (restage_q2_raws_from_live)",
        }},
    )
    print(f"✓ staged employees[] + rows[] rebuilt with authoritative raws "
          f"for the 20 applied servers; 9 phantoms preserved untouched.")
    print()

    # Sanity dump — the 5 parity anchors' copied raws + match method.
    print("Copied-raws sanity (5 parity anchors):")
    for legal in LIVE_ANCHOR:
        info = by_legal.get(legal)
        if not info:
            print(f"  {legal:22}  (NOT IN APPLIED — likely a name-mismatch)")
            continue
        raws = info["raws"]
        print(f"  {legal:22}  method={info['method']:<12}  "
              f"src_row={info['auth_live_name']!r}")
        print(f"      liquor={raws.get('liquor_sales')!r:>10}  beer={raws.get('beer_sales')!r:>10}  "
              f"wine={raws.get('wine_sales')!r:>10}  glass={raws.get('bar_glassware_sales') or raws.get('glassware_sales')!r:>10}  "
              f"lsc_count={raws.get('lsc_count')!r:>6}  lbw_per_g={raws.get('lbw_per_guest')!r}  "
              f"glass_per_g={raws.get('glassware_per_guest')!r}  guests_per_lsc={raws.get('guests_per_lsc')!r}")
    print()

    # --------------------------------------------------------------
    # Phase D — run live hydrator + scorer on the STAGED doc, parity.
    # --------------------------------------------------------------
    staged = await db.snapshot_workflow_staging.find_one({"_id": staged["_id"]})

    from snapshot_routes import _hydrate_snapshot_employees  # type: ignore
    from scoring_engine import (  # type: ignore
        EmployeeV2, QuarterSettings, run_full_scoring, generate_hierarchy_rankings,
    )
    qs_doc = await db.quarter_settings.find_one({"year": 2026, "quarter": "Q2"})
    if not qs_doc:
        print("FATAL: QuarterSettings Q2 2026 missing.", file=sys.stderr); sys.exit(6)
    settings = QuarterSettings(**{k: v for k, v in qs_doc.items() if k != "_id"})

    hyd = await _hydrate_snapshot_employees(db, staged)
    print(f"hydrator returned {len(hyd)} rows from the staged doc.")

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
            # Source raws — calculate_lbw_total/calculate_derived_metrics
            # will recompute lbw, lbw_per_guest, glassware_per_guest,
            # guests_per_lsc from these.
            liquor_sales=_fn(e.get("liquor_sales")),
            beer_sales=_fn(e.get("beer_sales")),
            wine_sales=_fn(e.get("wine_sales")),
            glassware_sales=_fn(
                e.get("glassware_sales") or e.get("bar_glassware_sales")
            ),
            lsc_count=int(_fn(e.get("lsc_count"))),
            # CV/RT
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
    rk = generate_hierarchy_rankings(scored, settings, first_name_only=False)

    # Index parity output by both name and display_name to be robust to
    # whatever the hydrator's dedup chose as the surviving label.
    by_name: Dict[str, Dict[str, Any]] = {}
    for r in rk:
        for k in (r.get("name"), r.get("display_name")):
            if k:
                by_name[k.strip().lower()] = r

    # Lookup helper that also tries aliases (so "Lakeisha Martin" resolves
    # to "Keisha Martin" if the hydrator's display overlay flipped it,
    # and vice versa).
    def _row_for(legal: str) -> Optional[Dict[str, Any]]:
        r = by_name.get(legal.lower())
        if r:
            return r
        for alias in Q2_ALIAS_OVERRIDE.get(legal, []):
            r = by_name.get(alias.lower())
            if r:
                return r
        # Also try reverse: the canonical legal might map back to a
        # canonical whose primary name is different (e.g. "Lakeisha Martin"
        # -> "Keisha Martin"). We already index by alias above.
        return None

    print()
    print("=" * 78)
    print("HYDRATOR PARITY CHECK (staged-rebuilt-with-raws)")
    print("  CLEAN anchors: target = live-displayed % (already correct in live).")
    print("  SPLIT anchors: target = standalone-scoring of the AUTHORITATIVE")
    print("    typo'd row's raws + Q2 benchmarks (live-displayed is a mongrel")
    print("    overlay of multiple alias rows and is not a valid target).")
    print("=" * 78)
    print(f"{'name':22}  {'kind':5}  {'metric':8}  {'staged%':>8}  {'target%':>8}  {'Δ':>7}  result")
    print("-" * 78)
    pf = False
    for legal, anchor in LIVE_ANCHOR.items():
        r = _row_for(legal)
        if not r:
            print(f"  {legal:22} -> not in scored rankings (likely filtered "
                  f"by canonical status='merged'). HALT-worthy.")
            pf = True
            continue
        kind = anchor.get("anchor_kind", "?")
        for k, label, field in [
            ("lbw",   "LBW%",   "lbw_percentage"),
            ("glass", "Glass%", "glassware_percentage"),
            ("lsc",   "LSC%",   "lsc_percentage"),
        ]:
            staged_pct = r.get(field) or 0
            tgt_pct = anchor[k]
            d = staged_pct - tgt_pct
            ok = abs(d) <= TOL
            mark = "✓" if ok else "❌ FAIL"
            print(f"{legal:22}  {kind:5}  {label:8}  {staged_pct:>8.2f}  {tgt_pct:>8.2f}  "
                  f"{d:>+7.2f}  {mark}")
            if not ok:
                pf = True
    print("-" * 78)
    print()
    # Negative-control / contrast: for split anchors, show what the staged
    # % WOULD have been if raws had been pulled from a duplicate alias row.
    # The staged % should NOT match any of these.
    print("Negative-control (proof-by-contrast that raws came from the AUTHORITATIVE row,")
    print("not a duplicate alias row). Staged % above should NOT match any of these:")
    for legal, dups in DUP_ROW_SCORES.items():
        r = _row_for(legal)
        if not r:
            continue
        staged_lbw = r.get("lbw_percentage") or 0
        staged_gl = r.get("glassware_percentage") or 0
        staged_ls = r.get("lsc_percentage") or 0
        print(f"  {legal}:")
        print(f"    staged                          = ({staged_lbw:6.2f}, {staged_gl:6.2f}, {staged_ls:6.2f})")
        for dup_name, (lbw, gl, ls) in dups.items():
            matches_any = (
                abs(staged_lbw - lbw) <= TOL
                and abs(staged_gl - gl) <= TOL
                and abs(staged_ls - ls) <= TOL
            )
            badge = "❌ MATCH (raws from wrong row!)" if matches_any else "✓ does not match"
            print(f"    if-from {dup_name!r:34}  = ({lbw:6.2f}, {gl:6.2f}, {ls:6.2f})  {badge}")
            if matches_any:
                pf = True
    print()
    print("Note: Thomas Kozan has a known upstream guest-count inconsistency; a "
          "small PPA-side wobble there is expected, not a script bug.")
    print()

    if pf:
        print("PARITY FAIL — one or more cells outside ±%.1f. STOP per protocol; "
              "do NOT promote." % TOL)
        sys.exit(7)

    print(f"✓ Hydrator parity PASSED — all parity cells within ±{TOL} pp.")
    print()
    print("STAGING-ONLY RUN COMPLETE. Re-promote is a SEPARATE authorized step:")
    print("  backup -> segregate 9 phantoms as status='insufficient_data' -> "
          "atomic update -> post-verify.")
    print()
    print(f"Set-equality reminder: skipped raw set ({len(skipped_phantoms)}) "
          f"MUST equal the segregated insufficient_data set in the promote step. "
          f"Verify before promoting: {sorted(skipped_phantoms)}")


if __name__ == "__main__":
    asyncio.run(main())
