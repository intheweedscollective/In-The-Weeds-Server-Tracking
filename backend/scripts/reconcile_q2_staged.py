"""
reconcile_q2_staged.py — READ-ONLY reconciliation of /app/data/q2_pos_truth.csv
against the STAGED rebuild (`snapshot_workflow_staging`).

Same shape and rules as `reconcile_q2.py`, but reads the staged
collection instead of `snapshot_workflow`. Zero DB writes.
"""

import asyncio
import csv
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

CSV_PATH      = "/app/data/q2_pos_truth.csv"
STAGED_COLL   = "snapshot_workflow_staging"
STAGED_NAME   = "Q2_REBUILD_STAGED"
DELTA_EPS     = 0.01


def _norm(s): return (s or "").strip().lower()


def _fnum(v):
    if v is None or v == "":
        return None
    try: return float(v)
    except (TypeError, ValueError): return None


def _delta(a, t):
    if a is None or t is None: return None
    return a - t


def _fmt(v, w=10, d=2):
    if v is None: return f"{'MISSING':>{w}}"
    return f"{v:>{w}.{d}f}"


def _fmt_delta(v, w=9):
    if v is None: return f"{'n/a':>{w}}"
    if abs(v) < DELTA_EPS: return f"{0.0:>+{w}.2f}"
    return f"{v:>+{w}.2f}"


def index_rows(snap):
    all_rows, by_id, by_name = [], {}, {}
    def _push(r):
        idx = len(all_rows); r["_row_idx"] = idx; all_rows.append(r)
        if r.get("employee_id"):
            by_id.setdefault(r["employee_id"], []).append(idx)
        nk = _norm(r.get("name"))
        if nk: by_name.setdefault(nk, []).append(idx)
    for r in (snap.get("rows") or []):
        fm = r.get("frozen_metrics") or {}
        _push({
            "_source":     "rows[]",
            "employee_id": r.get("employee_id"),
            "name":        r.get("frozen_display_name") or fm.get("name"),
            "net_sales":   fm.get("net_sales"),
            "guests":      fm.get("guests") if fm.get("guests") is not None else fm.get("guest_count"),
            "ppa":         fm.get("ppa"),
            "total_score": r.get("frozen_score") or fm.get("total_score"),
        })
    for e in (snap.get("employees") or []):
        if e.get("id") and e.get("id") in by_id: continue
        _push({
            "_source":     "employees[]",
            "employee_id": e.get("id"),
            "name":        e.get("display_name") or e.get("name"),
            "net_sales":   e.get("net_sales"),
            "guests":      e.get("guests") if e.get("guests") is not None else e.get("guest_count"),
            "ppa":         e.get("ppa"),
            "total_score": e.get("total_score"),
        })
    return all_rows, by_id, by_name


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    snap = await db[STAGED_COLL].find_one({"name": STAGED_NAME})
    if not snap:
        print(f"FATAL: no doc named {STAGED_NAME!r} in {STAGED_COLL}", file=sys.stderr)
        sys.exit(1)
    print(f"using STAGED snapshot: id={snap.get('id')!r} status={snap.get('status')!r} "
          f"rows={len(snap.get('rows') or [])} employees={len(snap.get('employees') or [])}")

    truth = []
    with open(CSV_PATH, newline="") as fh:
        for row in csv.DictReader(fh):
            truth.append({
                "server_name": row["server_name"],
                "net_sales":   _fnum(row["net_sales"]),
                "guests":      _fnum(row["guests"]),
                "ppa":         _fnum(row["ppa"]),
            })
    print(f"loaded {len(truth)} CSV rows from {CSV_PATH}")

    all_rows, by_id, by_name = index_rows(snap)
    print(f"flat staged rows indexed: {len(all_rows)}")
    print()

    hdr = (f"{'#':>2}  {'server (csv)':30}  {'match':10}  {'app_name':30}  "
           f"{'net_sales':>11} {'Δ':>10}  {'guests':>7} {'Δ':>7}  "
           f"{'ppa':>7} {'Δ':>7}  {'internal_ppa_gap':>18}")
    print(hdr); print("-" * len(hdr))

    matched_idx, unmatched, delta_rows = set(), [], []
    matched_count = 0

    for i, t in enumerate(truth, 1):
        nk = _norm(t["server_name"])
        idxs = by_name.get(nk, [])
        if not idxs:
            unmatched.append(t["server_name"])
            print(f"{i:>2}  {t['server_name']:30}  {'UNMATCHED':10}  {'—':30}  "
                  f"{'—':>11} {'—':>10}  {'—':>7} {'—':>7}  {'—':>7} {'—':>7}  {'—':>18}")
            continue
        # Stage guarantees one row per legal name → idxs is len 1
        if len(idxs) > 1:
            print(f"!! WARNING: {t['server_name']!r} resolves to {len(idxs)} staged rows — duplicate guard breached")
        row = all_rows[idxs[0]]
        matched_count += 1
        matched_idx.add(idxs[0])

        app_ns, app_g, app_ppa = _fnum(row.get("net_sales")), _fnum(row.get("guests")), _fnum(row.get("ppa"))
        d_ns  = _delta(app_ns,  t["net_sales"])
        d_g   = _delta(app_g,   t["guests"])
        d_ppa = _delta(app_ppa, t["ppa"])
        gap = app_ppa - (app_ns/app_g) if app_ns is not None and app_g not in (None, 0) and app_ppa is not None else None
        if any(d is not None and abs(d) >= DELTA_EPS for d in (d_ns, d_g, d_ppa)):
            delta_rows.append(t["server_name"])
        print(f"{i:>2}  {t['server_name']:30}  {'name':10}  {(row.get('name') or '')[:30]:30}  "
              f"{_fmt(app_ns, 11)} {_fmt_delta(d_ns, 10)}  "
              f"{_fmt(app_g, 7, 0)} {_fmt_delta(d_g, 7)}  "
              f"{_fmt(app_ppa, 7)} {_fmt_delta(d_ppa, 7)}  "
              f"{_fmt(gap, 18, 4)}")

    uncovered = [r for i, r in enumerate(all_rows) if i not in matched_idx]
    print()
    print("=" * 80)
    print("COVERAGE SUMMARY (staged)")
    print("=" * 80)
    print(f"CSV rows                                  : {len(truth)}")
    print(f"Staged rows (rows[] + employees mirror)   : {len(all_rows)}")
    print(f"CSV rows matched                          : {matched_count} / {len(truth)}")
    print(f"CSV rows UNMATCHED                        : {len(unmatched)}")
    for n in unmatched: print(f"    UNMATCHED CSV : {n!r}")
    print(f"Staged rows NOT covered by any CSV row    : {len(uncovered)}")
    for r in uncovered:
        print(f"    UNCOVERED STAGED: name={r.get('name')!r} net={r.get('net_sales')} guests={r.get('guests')} ppa={r.get('ppa')}")
    print()
    print(f"Servers with ANY nonzero delta on net_sales/guests/ppa (eps={DELTA_EPS}): {len(delta_rows)}")
    for n in delta_rows: print(f"    DELTA  : {n!r}")
    print()
    print("Notes:")
    print("  • READ-ONLY: zero writes. Live `snapshot_workflow` untouched.")
    print("  • CV (NPS) and RT not reconciled here — source files PENDING delivery.")


if __name__ == "__main__":
    asyncio.run(main())
