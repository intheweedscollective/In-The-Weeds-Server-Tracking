"""
stage_q2_rebuild.py — STAGED, NON-DESTRUCTIVE rebuild of the Q2 2026
canonical employee set.

Writes to a NEW collection `snapshot_workflow_staging` only. Does NOT
touch `snapshot_workflow`, `employees`, `employees_v2`, or any other
live collection. The live snapshot stays exactly as it is until the
operator explicitly promotes the staged result.

Inputs:
  POS = /app/data/q2_pos_truth.csv             (authoritative)
  NPS = /app/data/q2_nps_truth.csv             (CV source — PENDING delivery)
  RT  = /app/data/export-2026-06-15.csv        (RT source — PENDING delivery)

Alias override (hard-coded, supersedes DB-stored aliases for THIS rebuild):
  Kahiaulani Ramos  ← Kahiaulanl Ramos, Kahiauani Ramos, Kahi Ramos, Kahi
  Glennice Nguyen   ← Glennlce Nguyen, Lennie Nguyen, Lennie
  Thomas Kozan      ← TK Kozan, TK
  Lakeisha Martin   ← Keisha Martin, Keisha
  Abigail Ostrowski ← Abby Ostrowski, Abby
  Treyanna Quick    ← Trey Quick, Trey
  Eric Ostgarden    ← Ikey Ostgarden, Ikey
  Craig Simmons     ← Allen Simmons, Allen

Excluded entirely (terminated or test fixture):
  Matthew Spath, Lindsey Gonzales, Drift Test 32f9f1

Run:  python /app/backend/scripts/stage_q2_rebuild.py
"""

import asyncio
import csv
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

# ---- Locked source-file paths --------------------------------------
POS_CSV  = "/app/data/q2_pos_truth.csv"
NPS_CSV  = "/app/data/q2_nps_truth.csv"
RT_CSV   = "/app/data/export-2026-06-15.csv"

STAGING_COLL = "snapshot_workflow_staging"
STAGED_NAME  = "Q2_REBUILD_STAGED"
YEAR = 2026
QUARTER = "Q2"

# ---- Alias override (operator-authoritative for Q2 rebuild) --------
# Format: legal_name -> [variants treated as the same person]
Q2_ALIAS_OVERRIDE: Dict[str, List[str]] = {
    "Kahiaulani Ramos":  ["Kahiaulanl Ramos", "Kahiauani Ramos", "Kahi Ramos", "Kahi"],
    "Glennice Nguyen":   ["Glennlce Nguyen",  "Lennie Nguyen",   "Lennie"],
    "Thomas Kozan":      ["TK Kozan",         "TK"],
    "Lakeisha Martin":   ["Keisha Martin",    "Keisha"],
    "Abigail Ostrowski": ["Abby Ostrowski",   "Abby"],
    "Treyanna Quick":    ["Trey Quick",       "Trey"],
    "Eric Ostgarden":    ["Ikey Ostgarden",   "Ikey"],
    "Craig Simmons":     ["Allen Simmons",    "Allen"],
}

EXCLUDE_FROM_REBUILD = {"Matthew Spath", "Lindsey Gonzales", "Drift Test 32f9f1"}


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _fnum(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_override_resolver() -> Dict[str, str]:
    """Lowercase variant → canonical legal name.

    Bidirectional: every variant AND every legal name resolves to
    itself (so a CSV row already using the legal name still passes
    through cleanly).
    """
    resolver: Dict[str, str] = {}
    for legal, variants in Q2_ALIAS_OVERRIDE.items():
        resolver[_norm(legal)] = legal
        for v in variants:
            resolver[_norm(v)] = legal
    return resolver


# --------------------------------------------------------------------
# Source-file readers
# --------------------------------------------------------------------
def load_pos_truth() -> List[Dict[str, Any]]:
    if not os.path.exists(POS_CSV):
        print(f"FATAL: POS truth file not found at {POS_CSV}", file=sys.stderr)
        sys.exit(1)
    out: List[Dict[str, Any]] = []
    with open(POS_CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append({
                "server_name": (row.get("server_name") or "").strip(),
                "net_sales":   _fnum(row.get("net_sales")),
                "guests":      _fnum(row.get("guests")),
                "ppa":         _fnum(row.get("ppa")),
            })
    return out


def load_nps_optional() -> Optional[List[Dict[str, Any]]]:
    """Returns None when the NPS source file isn't yet on disk.
    Caller flags those rows as PENDING_SOURCE_FILE rather than
    inventing zeros.
    """
    if not os.path.exists(NPS_CSV):
        return None
    out: List[Dict[str, Any]] = []
    with open(NPS_CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append({k: row.get(k) for k in row.keys()})
    return out


def load_rt_optional() -> Optional[List[Dict[str, Any]]]:
    if not os.path.exists(RT_CSV):
        return None
    out: List[Dict[str, Any]] = []
    with open(RT_CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append({k: row.get(k) for k in row.keys()})
    return out


# --------------------------------------------------------------------
# Stager
# --------------------------------------------------------------------
async def stage(db) -> Dict[str, Any]:
    pos_rows = load_pos_truth()
    nps_rows = load_nps_optional()
    rt_rows  = load_rt_optional()
    resolver = build_override_resolver()

    # Validate POS truth doesn't already contain anything from
    # EXCLUDE_FROM_REBUILD — if it did, we'd silently include them.
    pos_names_lc = {_norm(r["server_name"]) for r in pos_rows}
    excluded_present = [n for n in EXCLUDE_FROM_REBUILD
                        if _norm(n) in pos_names_lc]
    if excluded_present:
        print(f"WARN: POS truth contains names on the EXCLUDE list: "
              f"{excluded_present} — these will still be skipped.")

    # Build the staged employees[].
    staged_employees: List[Dict[str, Any]] = []
    duplicate_guard: Dict[str, int] = {}

    for pos in pos_rows:
        legal = pos["server_name"].strip()
        if legal in EXCLUDE_FROM_REBUILD:
            continue
        # Canonicalize via the override map; if the CSV name isn't in
        # the map at all, the legal name from the CSV IS the legal name.
        canonical_legal = resolver.get(_norm(legal), legal)

        # Duplicate guard: enforce ONE row per canonical legal name.
        if _norm(canonical_legal) in duplicate_guard:
            duplicate_guard[_norm(canonical_legal)] += 1
            continue
        duplicate_guard[_norm(canonical_legal)] = 1

        # POS metrics — straight from the truth CSV.
        net_sales = pos["net_sales"] or 0
        guests    = int(pos["guests"] or 0)
        ppa       = pos["ppa"]

        # CV (NPS) join — exact legal-name match in the NPS report.
        cv_block: Dict[str, Any] = {
            "cv_source": "PENDING_SOURCE_FILE" if nps_rows is None else "matched",
            "cv_promoters": None,
            "cv_passives": None,
            "cv_detractors": None,
            "nps_score": None,
        }
        if nps_rows is not None:
            match = next(
                (r for r in nps_rows
                 if _norm(r.get("server_name") or r.get("name")) == _norm(canonical_legal)),
                None,
            )
            if match:
                cv_block["cv_promoters"]  = _fnum(match.get("promoters"))
                cv_block["cv_passives"]   = _fnum(match.get("passives"))
                cv_block["cv_detractors"] = _fnum(match.get("detractors"))
                cv_block["nps_score"]     = _fnum(match.get("nps_score")
                                                   or match.get("nps"))
            else:
                cv_block["cv_source"] = "no_nps_row"

        # RT mentions — the live app reads a pre-counted `mentions`
        # field per row from the parsed RT file (snapshot_routes.py
        # ~line 4330). It does NOT extract counts from raw review
        # text. So once the RT CSV is delivered, we'll:
        #   1. confirm whether the file has a `mentions` column
        #      already (pre-counted) — if yes, sum across rows whose
        #      `server_name` (canonicalized via the override map)
        #      equals this employee, and
        #   2. if the file is raw review text instead, halt and ask
        #      the operator which column to count against, rather
        #      than inventing an extractor.
        rt_block: Dict[str, Any] = {
            "rt_source": "PENDING_SOURCE_FILE" if rt_rows is None else "computed",
            "rt_mentions": None,
        }
        if rt_rows is not None:
            # Detect schema: pre-counted vs raw-text.
            first = rt_rows[0] if rt_rows else {}
            has_mentions_col = any(
                k.lower() in ("mentions", "mention_count", "count")
                for k in first.keys()
            )
            if has_mentions_col:
                # Sum mentions across rows that map to this canonical.
                mention_key = next(
                    k for k in first.keys()
                    if k.lower() in ("mentions", "mention_count", "count")
                )
                name_key = next(
                    (k for k in first.keys()
                     if k.lower() in ("name", "server_name", "server", "employee")),
                    None,
                )
                if name_key is None:
                    rt_block["rt_source"] = "rt_csv_missing_name_column"
                else:
                    total = 0
                    for r in rt_rows:
                        rn = _norm(r.get(name_key))
                        if resolver.get(rn, r.get(name_key) or "") == canonical_legal:
                            v = _fnum(r.get(mention_key))
                            if v is not None:
                                total += v
                    rt_block["rt_mentions"] = int(total)
            else:
                rt_block["rt_source"] = "rt_csv_is_raw_text_HALT"

        staged_employees.append({
            "id":            str(uuid.uuid4()),
            "name":          canonical_legal,
            "display_name":  canonical_legal,
            "report_name":   canonical_legal,
            "aliases":       Q2_ALIAS_OVERRIDE.get(canonical_legal, []),
            "alias_source":  "Q2_ALIAS_OVERRIDE" if canonical_legal in Q2_ALIAS_OVERRIDE else "none",
            "job_title":     "Server",  # snapshot-first; live record stays untouched
            "quarter":       QUARTER,
            "year":          YEAR,
            "net_sales":     net_sales,
            "guests":        guests,
            "guest_count":   guests,
            "ppa":           ppa,
            **cv_block,
            **rt_block,
        })

    # Write to staging collection only.
    now = datetime.now(timezone.utc).isoformat()
    staged_doc = {
        "id":              f"staged-{QUARTER}-{YEAR}-{uuid.uuid4().hex[:8]}",
        "name":            STAGED_NAME,
        "year":            YEAR,
        "quarter":         QUARTER,
        "status":          "staged",
        "is_current":      False,
        "is_staging":      True,
        "created_at":      now,
        "source_files": {
            "pos": POS_CSV,
            "nps": NPS_CSV if nps_rows is not None else f"PENDING:{NPS_CSV}",
            "rt":  RT_CSV  if rt_rows  is not None else f"PENDING:{RT_CSV}",
        },
        "alias_override":  Q2_ALIAS_OVERRIDE,
        "excluded":        sorted(EXCLUDE_FROM_REBUILD),
        "employees":       staged_employees,
        # Compatibility shim for the reconciliation script — it walks
        # both rows[] and employees[].
        "rows": [
            {
                "employee_id":           e["id"],
                "frozen_display_name":   e["name"],
                "frozen_report_name":    e["report_name"],
                "frozen_score":          None,
                "frozen_metrics":        {
                    "net_sales": e["net_sales"],
                    "guests":    e["guests"],
                    "ppa":       e["ppa"],
                },
            }
            for e in staged_employees
        ],
    }

    # NON-DESTRUCTIVE WRITE: drop any prior staging doc of this name,
    # then insert the new one. The live `snapshot_workflow` collection
    # is never touched by this script.
    await db[STAGING_COLL].delete_many({"name": STAGED_NAME})
    await db[STAGING_COLL].insert_one(dict(staged_doc))

    return {
        "staged_doc_id":    staged_doc["id"],
        "n_employees":      len(staged_employees),
        "n_duplicates_collapsed": sum(v - 1 for v in duplicate_guard.values()),
        "nps_status":       "loaded" if nps_rows is not None else "PENDING",
        "rt_status":        "loaded" if rt_rows  is not None else "PENDING",
    }


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # ---- BEFORE counts (live snapshot, untouched) ------------------
    live = await db.snapshot_workflow.find_one(
        {"year": YEAR, "quarter": QUARTER},
        sort=[("effective_date", -1), ("completed_at", -1), ("updated_at", -1)],
    )
    print("=" * 80)
    print("BEFORE — live snapshot (untouched)")
    print("=" * 80)
    if live:
        print(f"  collection : snapshot_workflow")
        print(f"  name       : {live.get('name')!r}")
        print(f"  status     : {live.get('status')!r}")
        print(f"  is_current : {live.get('is_current')!r}")
        print(f"  rows       : {len(live.get('rows') or [])}")
        print(f"  employees  : {len(live.get('employees') or [])}")
    else:
        print("  (no live Q2 snapshot found)")

    # ---- STAGE ------------------------------------------------------
    result = await stage(db)

    # ---- AFTER counts (staging collection only) --------------------
    staged = await db[STAGING_COLL].find_one({"id": result["staged_doc_id"]})
    print()
    print("=" * 80)
    print("AFTER — staged rebuild (new collection, live snapshot UNCHANGED)")
    print("=" * 80)
    print(f"  collection : {STAGING_COLL}")
    print(f"  id         : {staged['id']}")
    print(f"  name       : {staged['name']!r}")
    print(f"  status     : {staged['status']!r}  (NOT promoted)")
    print(f"  rows       : {len(staged.get('rows') or [])}")
    print(f"  employees  : {len(staged.get('employees') or [])}")
    print(f"  duplicates collapsed via override : {result['n_duplicates_collapsed']}")
    print(f"  NPS source : {result['nps_status']}")
    print(f"  RT  source : {result['rt_status']}")

    # Re-verify the live snapshot is still exactly as it was.
    live_after = await db.snapshot_workflow.find_one(
        {"year": YEAR, "quarter": QUARTER},
        sort=[("effective_date", -1), ("completed_at", -1), ("updated_at", -1)],
    )
    print()
    print("LIVE-SNAPSHOT INTEGRITY CHECK")
    print(f"  before rows / after rows  : "
          f"{len((live or {}).get('rows') or [])} / "
          f"{len((live_after or {}).get('rows') or [])}")
    print(f"  before emps / after emps  : "
          f"{len((live or {}).get('employees') or [])} / "
          f"{len((live_after or {}).get('employees') or [])}")
    print(f"  same _id?                 : "
          f"{(live or {}).get('_id') == (live_after or {}).get('_id')}")


if __name__ == "__main__":
    asyncio.run(main())
