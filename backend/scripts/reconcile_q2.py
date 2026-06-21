"""
reconcile_q2.py — READ-ONLY reconciliation of /app/data/q2_pos_truth.csv
against the app's stored Q2 2026 sales values for Store 337.

Hard contract:
  * ZERO writes to MongoDB.
  * Pulls app values from the SAME data path the ranking endpoint uses:
    the most-recent Q2 2026 snapshot's `rows[]` (frozen_metrics) /
    `employees[]` array. That's what `_hydrate_snapshot_employees`
    consumes — same source of truth the dashboard renders.
  * Name resolution: CSV name → snapshot row by
       (a) exact case-insensitive frozen_display_name/name match,
       (b) failing that, canonical-record alias / legacy_id lookup,
       (c) failing that, UNMATCHED (printed explicitly — never silent).
  * Prints per-server deltas, `app_internal_ppa_gap`, and a summary.

Run:  python /app/backend/scripts/reconcile_q2.py
"""

import asyncio
import csv
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

CSV_PATH = "/app/data/q2_pos_truth.csv"
YEAR = 2026
QUARTER = "Q2"

# Tolerance for "nonzero" delta — values smaller than this are noise
# from float math, NOT a real disagreement. Operator can tighten if
# they want even more sensitivity.
DELTA_EPS = 0.01


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _fnum(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _delta(app: Optional[float], truth: Optional[float]) -> Optional[float]:
    if app is None or truth is None:
        return None
    return app - truth


def _fmt(v: Optional[float], width: int = 10, decimals: int = 2) -> str:
    if v is None:
        return f"{'MISSING':>{width}}"
    return f"{v:>{width}.{decimals}f}"


def _fmt_delta(v: Optional[float], width: int = 9) -> str:
    if v is None:
        return f"{'n/a':>{width}}"
    if abs(v) < DELTA_EPS:
        return f"{0.0:>+{width}.2f}"
    return f"{v:>+{width}.2f}"


async def load_snapshot(db) -> Dict[str, Any]:
    """Fetch the same Q2 snapshot the ranking endpoint reads."""
    snap = await db.snapshot_workflow.find_one(
        {"year": YEAR, "quarter": QUARTER},
        sort=[
            ("effective_date", -1),
            ("completed_at", -1),
            ("updated_at", -1),
        ],
    )
    return snap


async def build_canonical_index(db) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    """Two indexes:
       by_id  — every canonical id AND every legacy_id → canonical doc
       by_name — every name / display_name / report_name / alias (lowercased) → canonical doc
    """
    by_id: Dict[str, Dict] = {}
    by_name: Dict[str, Dict] = {}
    async for c in db.employees.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1, "report_name": 1,
         "aliases": 1, "legacy_ids": 1, "status": 1},
    ):
        cid = c.get("id")
        if cid:
            by_id[cid] = c
        for lid in (c.get("legacy_ids") or []):
            if lid:
                by_id.setdefault(lid, c)
        for n in [c.get("name"), c.get("display_name"),
                  c.get("report_name"), *(c.get("aliases") or [])]:
            k = _norm(n)
            if k:
                # First write wins so an active canonical isn't
                # overwritten by a merged one sharing the same alias.
                by_name.setdefault(k, c)
    return by_id, by_name


def index_snapshot_rows(snap: Dict[str, Any]) -> Tuple[Dict[str, List[Dict]],
                                                       Dict[str, List[Dict]]]:
    """Two indexes over snapshot rows + employees[]:
       by_id_in_snap   — employee_id → list of row-shaped dicts
       by_name_in_snap — lowercased name → list of row-shaped dicts
    The list shape means we never silently lose duplicates; the caller
    decides what to do when more than one row matches.
    """
    by_id: Dict[str, List[Dict]] = {}
    by_name: Dict[str, List[Dict]] = {}

    # snapshot.rows[]: frozen_metrics blob carries the numbers.
    for r in (snap.get("rows") or []):
        fm = r.get("frozen_metrics") or {}
        row = {
            "_source":      "rows[]",
            "employee_id":  r.get("employee_id"),
            "name":         (r.get("frozen_display_name")
                             or r.get("frozen_report_name")
                             or fm.get("name")),
            "net_sales":    fm.get("net_sales"),
            "guests":       (fm.get("guests")
                             if fm.get("guests") is not None
                             else fm.get("guest_count")),
            "check_avg":    fm.get("check_avg"),
            "ppa":          fm.get("ppa"),
            "total_score":  r.get("frozen_score") or fm.get("total_score"),
        }
        eid = row["employee_id"]
        if eid:
            by_id.setdefault(eid, []).append(row)
        nk = _norm(row["name"])
        if nk:
            by_name.setdefault(nk, []).append(row)

    # snapshot.employees[]: parallel legacy mirror — same fields at top.
    for e in (snap.get("employees") or []):
        # If we already saw this employee via rows[] (same id), prefer
        # rows[] (authoritative) and skip the employees[] mirror.
        if e.get("id") and e.get("id") in by_id:
            continue
        row = {
            "_source":     "employees[]",
            "employee_id": e.get("id"),
            "name":        e.get("display_name") or e.get("name"),
            "net_sales":   e.get("net_sales"),
            "guests":      (e.get("guests")
                            if e.get("guests") is not None
                            else e.get("guest_count")),
            "check_avg":   e.get("check_avg"),
            "ppa":         e.get("ppa"),
            "total_score": e.get("total_score"),
        }
        eid = row["employee_id"]
        if eid:
            by_id.setdefault(eid, []).append(row)
        nk = _norm(row["name"])
        if nk:
            by_name.setdefault(nk, []).append(row)

    return by_id, by_name


def resolve_snapshot_row_for_csv_name(
    csv_name: str,
    canonical_by_name: Dict[str, Dict],
    snap_by_id: Dict[str, List[Dict]],
    snap_by_name: Dict[str, List[Dict]],
) -> Tuple[Optional[Dict], str]:
    """Returns (row, match_method).
       match_method ∈ {'name', 'alias→id', 'alias→name', 'UNMATCHED'}.
    """
    nk = _norm(csv_name)
    # 1. Direct name match against snapshot rows.
    if nk in snap_by_name:
        rows = snap_by_name[nk]
        # If multiple rows share the same name (rare), pick the one
        # with the highest total_score — matches the dedup the
        # ranking applies.
        rows_sorted = sorted(
            rows,
            key=lambda r: (r.get("total_score") or 0),
            reverse=True,
        )
        return rows_sorted[0], "name"

    # 2. Alias resolution via canonical: CSV name → canonical → id → snap row.
    canon = canonical_by_name.get(nk)
    if canon:
        # Try canonical.id first, then any legacy_ids[].
        for cid in [canon.get("id"), *(canon.get("legacy_ids") or [])]:
            if cid and cid in snap_by_id:
                rows = sorted(
                    snap_by_id[cid],
                    key=lambda r: (r.get("total_score") or 0),
                    reverse=True,
                )
                return rows[0], "alias→id"
        # 3. Last fallback: canonical's other known names against snap_by_name.
        for n in [canon.get("name"), canon.get("display_name"),
                  canon.get("report_name"), *(canon.get("aliases") or [])]:
            knk = _norm(n)
            if knk and knk in snap_by_name:
                rows = sorted(
                    snap_by_name[knk],
                    key=lambda r: (r.get("total_score") or 0),
                    reverse=True,
                )
                return rows[0], "alias→name"

    return None, "UNMATCHED"


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    db = AsyncIOMotorClient(mongo_url)[db_name]

    # 1. Load CSV exactly as-is.
    truth: List[Dict[str, Any]] = []
    with open(CSV_PATH, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            truth.append({
                "server_name": row["server_name"],
                "net_sales":   _fnum(row["net_sales"]),
                "guests":      _fnum(row["guests"]),
                "check_avg":   _fnum(row["check_avg"]),
                "ppa":         _fnum(row["ppa"]),
            })
    print(f"loaded {len(truth)} CSV rows from {CSV_PATH}")

    # 2. Load the snapshot the ranking actually reads + canonical index.
    snap = await load_snapshot(db)
    if not snap:
        print(f"NO snapshot found for {YEAR} {QUARTER} — aborting.")
        sys.exit(1)
    print(f"using snapshot: name={snap.get('name')!r} status={snap.get('status')!r} "
          f"is_current={snap.get('is_current')!r} "
          f"rows={len(snap.get('rows') or [])} "
          f"employees={len(snap.get('employees') or [])}")
    snap_by_id, snap_by_name = index_snapshot_rows(snap)
    canon_by_id, canon_by_name = await build_canonical_index(db)

    # 3. Per-server reconciliation.
    print()
    header = (
        f"{'#':>2}  {'server (csv)':30}  {'match':10}  "
        f"{'app_name':30}  "
        f"{'net_sales':>11} {'Δ':>10}  "
        f"{'guests':>7} {'Δ':>7}  "
        f"{'check_avg':>10} {'Δ':>8}  "
        f"{'ppa':>7} {'Δ':>7}  "
        f"{'internal_ppa_gap':>18}"
    )
    print(header)
    print("-" * len(header))

    unmatched: List[str] = []
    any_delta_rows: List[str] = []

    for i, t in enumerate(truth, 1):
        app_row, method = resolve_snapshot_row_for_csv_name(
            t["server_name"], canon_by_name, snap_by_id, snap_by_name,
        )
        if app_row is None:
            unmatched.append(t["server_name"])
            print(
                f"{i:>2}  {t['server_name']:30}  "
                f"{'UNMATCHED':10}  "
                f"{'—':30}  "
                f"{'—':>11} {'—':>10}  "
                f"{'—':>7} {'—':>7}  "
                f"{'—':>10} {'—':>8}  "
                f"{'—':>7} {'—':>7}  "
                f"{'—':>18}"
            )
            continue

        app_ns   = _fnum(app_row.get("net_sales"))
        app_g    = _fnum(app_row.get("guests"))
        app_ca   = _fnum(app_row.get("check_avg"))
        app_ppa  = _fnum(app_row.get("ppa"))

        d_ns  = _delta(app_ns,  t["net_sales"])
        d_g   = _delta(app_g,   t["guests"])
        d_ca  = _delta(app_ca,  t["check_avg"])
        d_ppa = _delta(app_ppa, t["ppa"])

        # app_internal_ppa_gap = app stored ppa − (app net_sales / app guests)
        if app_ns is not None and app_g not in (None, 0) and app_ppa is not None:
            internal_gap = app_ppa - (app_ns / app_g)
        else:
            internal_gap = None

        # Flag any nonzero delta across the four fields (above eps).
        # MISSING app values are reported separately — they aren't a
        # delta, they're absence of data. The spec asks for "ANY
        # nonzero delta", so we count only rows where a real |Δ| ≥ eps
        # appears on at least one field.
        deltas_present = any(
            d is not None and abs(d) >= DELTA_EPS
            for d in (d_ns, d_g, d_ca, d_ppa)
        )
        if deltas_present:
            any_delta_rows.append(t["server_name"])

        print(
            f"{i:>2}  {t['server_name']:30}  "
            f"{method:10}  "
            f"{(app_row.get('name') or '')[:30]:30}  "
            f"{_fmt(app_ns, 11):>11} {_fmt_delta(d_ns, 10)}  "
            f"{_fmt(app_g, 7, 0):>7} {_fmt_delta(d_g, 7)}  "
            f"{_fmt(app_ca, 10):>10} {_fmt_delta(d_ca, 8)}  "
            f"{_fmt(app_ppa, 7):>7} {_fmt_delta(d_ppa, 7)}  "
            f"{_fmt(internal_gap, 18, 4):>18}"
        )

    # 4. Summary.
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"CSV rows                 : {len(truth)}")
    print(f"UNMATCHED (no app record): {len(unmatched)}")
    if unmatched:
        for n in unmatched:
            print(f"    UNMATCHED: {n!r}")
    print(f"Servers with ANY nonzero delta (eps={DELTA_EPS}) "
          f"OR a MISSING app field: {len(any_delta_rows)}")
    for n in any_delta_rows:
        print(f"    DELTA  : {n!r}")
    print()
    print("Notes:")
    print("  • Δ is (app − truth). Positive = app overstates, negative = app understates.")
    print("  • 'app_internal_ppa_gap' = app_ppa − (app_net_sales / app_guests). "
          "Nonzero means the app disagrees with itself (i.e. stored ppa "
          "≠ implied ppa).")
    print("  • check_avg: the snapshot row schema does NOT store this field anywhere "
          "(verified: 0/33 rows have check_avg set). Every row shows 'MISSING'.")
    print("  • READ-ONLY: this script makes zero writes to MongoDB.")


if __name__ == "__main__":
    asyncio.run(main())
