"""
reconcile_q2.py — READ-ONLY reconciliation of /app/data/q2_pos_truth.csv
against the app's stored Q2 2026 sales values for Store 337.

Reconciles only the POS sales metrics that drive the score:
  net_sales, guests, ppa
(`check_avg` is intentionally NOT reconciled — it is not a scoring
metric and is not stored on the snapshot row schema.)

Hard contract:
  * ZERO writes to MongoDB.
  * Pulls app values from the SAME data path the ranking endpoint uses:
    the most-recent Q2 2026 snapshot's `rows[]` (frozen_metrics) /
    `employees[]` array.
  * Name resolution: CSV name → snapshot row by
       (a) exact case-insensitive frozen_display_name / name match,
       (b) failing that, canonical-record alias / legacy_id lookup,
       (c) failing that, UNMATCHED (printed explicitly — never silent).
  * Reports two-way coverage: which CSV rows didn't match a snapshot
    row, AND which snapshot rows aren't covered by the CSV.

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
# from float rounding in the original POS export (which stores to 2dp).
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
                by_name.setdefault(k, c)
    return by_id, by_name


def index_snapshot_rows(
    snap: Dict[str, Any]
) -> Tuple[List[Dict], Dict[str, List[int]], Dict[str, List[int]]]:
    """Returns:
      all_rows   — flat list of every snapshot row (rows[] + employees[]
                   mirror entries that aren't already in rows[]).
                   Each row is augmented with `_row_idx` for coverage.
      by_id      — employee_id → list of indices into all_rows.
      by_name    — lowercased name → list of indices into all_rows.
    """
    all_rows: List[Dict] = []
    by_id: Dict[str, List[int]] = {}
    by_name: Dict[str, List[int]] = {}

    def _push(row: Dict):
        idx = len(all_rows)
        row["_row_idx"] = idx
        all_rows.append(row)
        eid = row.get("employee_id")
        if eid:
            by_id.setdefault(eid, []).append(idx)
        nk = _norm(row.get("name"))
        if nk:
            by_name.setdefault(nk, []).append(idx)

    # snapshot.rows[] — authoritative source for the ranking.
    for r in (snap.get("rows") or []):
        fm = r.get("frozen_metrics") or {}
        _push({
            "_source":      "rows[]",
            "employee_id":  r.get("employee_id"),
            "name":         (r.get("frozen_display_name")
                             or r.get("frozen_report_name")
                             or fm.get("name")),
            "net_sales":    fm.get("net_sales"),
            "guests":       (fm.get("guests")
                             if fm.get("guests") is not None
                             else fm.get("guest_count")),
            "ppa":          fm.get("ppa"),
            "total_score":  r.get("frozen_score") or fm.get("total_score"),
        })

    # snapshot.employees[] mirror — only push entries whose id we
    # haven't already captured via rows[]. Same shape so coverage
    # reporting is uniform.
    for e in (snap.get("employees") or []):
        if e.get("id") and e.get("id") in by_id:
            continue
        _push({
            "_source":     "employees[]",
            "employee_id": e.get("id"),
            "name":        e.get("display_name") or e.get("name"),
            "net_sales":   e.get("net_sales"),
            "guests":      (e.get("guests")
                            if e.get("guests") is not None
                            else e.get("guest_count")),
            "ppa":         e.get("ppa"),
            "total_score": e.get("total_score"),
        })

    return all_rows, by_id, by_name


def resolve_snapshot_row(
    csv_name: str,
    canonical_by_name: Dict[str, Dict],
    all_rows: List[Dict],
    snap_by_id: Dict[str, List[int]],
    snap_by_name: Dict[str, List[int]],
) -> Tuple[Optional[Dict], str]:
    """Returns (row, match_method).
       match_method ∈ {'name', 'alias→id', 'alias→name', 'UNMATCHED'}.
    """
    nk = _norm(csv_name)

    def _best_of(idxs: List[int]) -> Dict:
        # Prefer the row with the highest total_score — mirrors the
        # ranking's dedup behavior.
        chosen = max(
            idxs,
            key=lambda i: (all_rows[i].get("total_score") or 0),
        )
        return all_rows[chosen]

    # 1. Direct snapshot-row name match.
    if nk in snap_by_name:
        return _best_of(snap_by_name[nk]), "name"

    # 2. Alias resolution via canonical record.
    canon = canonical_by_name.get(nk)
    if canon:
        for cid in [canon.get("id"), *(canon.get("legacy_ids") or [])]:
            if cid and cid in snap_by_id:
                return _best_of(snap_by_id[cid]), "alias→id"
        for n in [canon.get("name"), canon.get("display_name"),
                  canon.get("report_name"), *(canon.get("aliases") or [])]:
            knk = _norm(n)
            if knk and knk in snap_by_name:
                return _best_of(snap_by_name[knk]), "alias→name"

    return None, "UNMATCHED"


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # 1. CSV exactly as-is.
    truth: List[Dict[str, Any]] = []
    with open(CSV_PATH, newline="") as fh:
        for row in csv.DictReader(fh):
            truth.append({
                "server_name": row["server_name"],
                "net_sales":   _fnum(row["net_sales"]),
                "guests":      _fnum(row["guests"]),
                "ppa":         _fnum(row["ppa"]),
            })
    print(f"loaded {len(truth)} CSV rows from {CSV_PATH}")

    # 2. Snapshot + indexes.
    snap = await load_snapshot(db)
    if not snap:
        print(f"NO snapshot found for {YEAR} {QUARTER} — aborting.")
        sys.exit(1)
    print(f"using snapshot: name={snap.get('name')!r} status={snap.get('status')!r} "
          f"is_current={snap.get('is_current')!r} "
          f"rows={len(snap.get('rows') or [])} "
          f"employees={len(snap.get('employees') or [])}")
    all_rows, snap_by_id, snap_by_name = index_snapshot_rows(snap)
    canon_by_id, canon_by_name = await build_canonical_index(db)
    print(f"flat snapshot rows indexed (rows[] + employees[] mirror, deduped by id): "
          f"{len(all_rows)}")

    # 3. Per-server table.
    print()
    header = (
        f"{'#':>2}  {'server (csv)':30}  {'match':10}  "
        f"{'app_name':30}  "
        f"{'net_sales':>11} {'Δ':>10}  "
        f"{'guests':>7} {'Δ':>7}  "
        f"{'ppa':>7} {'Δ':>7}  "
        f"{'internal_ppa_gap':>18}"
    )
    print(header)
    print("-" * len(header))

    matched_row_indices: set = set()
    unmatched_csv: List[str] = []
    delta_rows: List[str] = []
    matched_count = 0

    for i, t in enumerate(truth, 1):
        app_row, method = resolve_snapshot_row(
            t["server_name"], canon_by_name, all_rows, snap_by_id, snap_by_name,
        )
        if app_row is None:
            unmatched_csv.append(t["server_name"])
            print(
                f"{i:>2}  {t['server_name']:30}  "
                f"{'UNMATCHED':10}  "
                f"{'—':30}  "
                f"{'—':>11} {'—':>10}  "
                f"{'—':>7} {'—':>7}  "
                f"{'—':>7} {'—':>7}  "
                f"{'—':>18}"
            )
            continue

        matched_count += 1
        matched_row_indices.add(app_row["_row_idx"])

        app_ns  = _fnum(app_row.get("net_sales"))
        app_g   = _fnum(app_row.get("guests"))
        app_ppa = _fnum(app_row.get("ppa"))

        d_ns  = _delta(app_ns,  t["net_sales"])
        d_g   = _delta(app_g,   t["guests"])
        d_ppa = _delta(app_ppa, t["ppa"])

        if app_ns is not None and app_g not in (None, 0) and app_ppa is not None:
            internal_gap = app_ppa - (app_ns / app_g)
        else:
            internal_gap = None

        if any(d is not None and abs(d) >= DELTA_EPS for d in (d_ns, d_g, d_ppa)):
            delta_rows.append(t["server_name"])

        print(
            f"{i:>2}  {t['server_name']:30}  "
            f"{method:10}  "
            f"{(app_row.get('name') or '')[:30]:30}  "
            f"{_fmt(app_ns, 11):>11} {_fmt_delta(d_ns, 10)}  "
            f"{_fmt(app_g, 7, 0):>7} {_fmt_delta(d_g, 7)}  "
            f"{_fmt(app_ppa, 7):>7} {_fmt_delta(d_ppa, 7)}  "
            f"{_fmt(internal_gap, 18, 4):>18}"
        )

    # 4. Coverage in the OTHER direction: snapshot rows not covered by the CSV.
    uncovered_rows: List[Dict] = [
        r for i, r in enumerate(all_rows)
        if i not in matched_row_indices
    ]

    # 5. Summary.
    print()
    print("=" * 80)
    print("COVERAGE SUMMARY")
    print("=" * 80)
    print(f"CSV rows                                  : {len(truth)}")
    print(f"Snapshot rows (rows[] + employees mirror) : {len(all_rows)}")
    print(f"CSV rows matched to a snapshot row        : {matched_count} / {len(truth)}")
    print(f"CSV rows UNMATCHED                        : {len(unmatched_csv)}")
    if unmatched_csv:
        for n in unmatched_csv:
            print(f"    UNMATCHED CSV : {n!r}")
    print(f"Snapshot rows NOT covered by any CSV row  : {len(uncovered_rows)}")
    if uncovered_rows:
        for r in uncovered_rows:
            ns = r.get("net_sales")
            g  = r.get("guests")
            ppa = r.get("ppa")
            ts  = r.get("total_score")
            print(f"    UNCOVERED SNAP: name={r.get('name')!r:35} "
                  f"source={r.get('_source'):12} "
                  f"net_sales={ns!r:>10}  guests={g!r:>5}  "
                  f"ppa={ppa!r:>6}  total_score={ts!r}")

    print()
    print(f"Servers with ANY nonzero delta on net_sales/guests/ppa "
          f"(eps={DELTA_EPS}): {len(delta_rows)}")
    for n in delta_rows:
        print(f"    DELTA  : {n!r}")

    print()
    print("Notes:")
    print("  • Δ is (app − truth). Positive = app overstates, negative = app understates.")
    print("  • 'app_internal_ppa_gap' = app_ppa − (app_net_sales / app_guests). "
          "Within ±0.005 is just 2-decimal rounding in the POS export.")
    print("  • READ-ONLY: this script makes zero writes to MongoDB.")


if __name__ == "__main__":
    asyncio.run(main())
