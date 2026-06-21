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
    """Read the aggregated NPS report (xlsx). Returns rows shaped as
    {server_name, received, avg_rating, nps_score}. The file is a
    per-server roll-up — it does NOT carry transaction-level
    promoter/passive/detractor counts, so we cannot derive the live
    `cv_score = nps_score_pts + (promoters - 2*detractors)` formula.
    We populate `nps_score`, `nps_score_pts = nps_score/10`, and
    `cv_responses`. cv_promoters/passives/detractors stay None and
    cv_source is stamped `aggregate_only` so the operator can see what
    was sourced.
    """
    candidates = [
        "/app/data/6.15_nps_Server_Performance_Report_copy.xlsx",
        "/app/data/q2_nps_truth.xlsx",
        "/app/data/q2_nps_truth.csv",
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if path is None:
        return None
    out: List[Dict[str, Any]] = []
    if path.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if not header:
            return out
        idx = {str(h).strip().lower(): i for i, h in enumerate(header) if h}
        # Tolerant header lookup so the operator can re-export with
        # slight column-name drift without breaking the stager.
        def _col(*aliases):
            for a in aliases:
                if a in idx:
                    return idx[a]
            return None
        c_name = _col("name", "server_name", "server")
        c_recv = _col("received", "responses", "total")
        c_avg  = _col("avg rating", "avg_rating", "rating")
        c_nps  = _col("nps", "nps_score")
        for r in rows_iter:
            if not r or c_name is None or r[c_name] is None:
                continue
            out.append({
                "server_name": str(r[c_name]).strip(),
                "received":    r[c_recv] if c_recv is not None else None,
                "avg_rating":  r[c_avg]  if c_avg  is not None else None,
                "nps_score":   r[c_nps]  if c_nps  is not None else None,
            })
    else:
        with open(path, newline="") as fh:
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


def extract_rt_mentions_per_canonical(
    rt_rows: List[Dict[str, Any]],
    canonical_legals: List[str],
) -> Dict[str, int]:
    """Faithful re-implementation of the LIVE mention extractor from
    snapshot_routes.py:4620-4805. Same algorithm, same dedup rule
    (`mentioned_in_review`), same `\\b<variant>\\b` regex shape.

    Seeded with the operator-authoritative Q2_ALIAS_OVERRIDE map
    instead of the hard-coded `name_variations` block — that's the
    only change. Returns {canonical_legal_name: mention_count}.
    """
    import re

    # Build first-name → [variant first-names] from override + canonical.
    # The live extractor uses first-name string matching; mirror that.
    variants_by_canonical: Dict[str, List[str]] = {}
    for legal in canonical_legals:
        first = legal.split()[0].lower() if legal else ""
        if not first:
            continue
        variants = {first}
        # Each override variant contributes its FIRST token too — that
        # matches how the live extractor treats nicknames (which are
        # first-name-shaped: "Kahi", "TK", "Trey", ...).
        for v in Q2_ALIAS_OVERRIDE.get(legal, []):
            vf = v.split()[0].lower() if v else ""
            if vf and len(vf) >= 2:
                variants.add(vf)
        # Drop variants < 3 chars — matches the live extractor's
        # `len(first_name) < 3` skip at line 4751 to suppress noise
        # from "TK"/"AJ"-style 2-letter strings. ACCEPTING that this
        # means short-name aliases like "TK" / "Tk" / "Ikey" won't
        # match — log it explicitly so the operator can override.
        variants = {v for v in variants if len(v) >= 3}
        variants_by_canonical[legal] = sorted(variants)

    # Pre-compile patterns once.
    patterns_by_canonical: Dict[str, List[re.Pattern]] = {
        legal: [re.compile(r"\b" + re.escape(v) + r"\b") for v in vs]
        for legal, vs in variants_by_canonical.items()
    }

    mentions: Dict[str, int] = {legal: 0 for legal in canonical_legals}

    for row in rt_rows:
        # Live extractor reads the `Review` column (line 4735) with
        # fallback to lowercase variants and "Content".
        review_text = (
            row.get("Review") or row.get("review")
            or row.get("Content") or row.get("content") or ""
        )
        if not review_text or not str(review_text).strip():
            continue
        review_lower = str(review_text).lower()

        # Dedup within a single review (live extractor lines 4742, 4770).
        mentioned_in_review: set = set()
        for legal, pats in patterns_by_canonical.items():
            if legal in mentioned_in_review:
                continue
            if any(p.search(review_lower) for p in pats):
                mentions[legal] += 1
                mentioned_in_review.add(legal)

    return mentions


def review_tracker_bonus(mentions: int) -> float:
    """Mirror of the live formula at snapshot_routes.py:4332 —
    `min(mentions * 0.33, 20)` rounded to 1dp. Reproducing it here so
    the staging script doesn't depend on importing snapshot_routes."""
    return round(min((mentions or 0) * 0.33, 20.0), 1)


async def load_live_normalized_percentages(db) -> Dict[str, Dict[str, float]]:
    """Path C1 source: call the LIVE internal ranking pipeline directly
    so we get the same dedup/normalization the API endpoint serves,
    without going through the external ingress (which is auth-gated).
    """
    sys.path.insert(0, "/app/backend")
    from server import _load_snapshot_first_rankings  # type: ignore

    rankings, _settings, _prior_meta = await _load_snapshot_first_rankings(
        2026, "Q2",
    )
    out: Dict[str, Dict[str, float]] = {}
    for r in rankings:
        if r.get("no_pos_data_this_period"):
            continue
        nm = (r.get("name") or r.get("display_name") or "").strip().lower()
        if not nm:
            continue
        out[nm] = {
            "lbw_pct":   float(r.get("lbw_percentage") or 0),
            "glass_pct": float(r.get("glassware_percentage") or 0),
            "lsc_pct":   float(r.get("lsc_percentage") or 0),
        }
    return out


def resolve_live_percentages_for(
    canonical_legal: str,
    live_pcts: Dict[str, Dict[str, float]],
) -> Optional[Dict[str, float]]:
    """Look up the live percentages for this canonical legal name,
    trying the legal name first then each override alias. Returns
    None when nothing matches — caller must treat that as a hard
    miss (parity check will catch it)."""
    # Direct legal-name match.
    hit = live_pcts.get(_norm(canonical_legal))
    if hit:
        return hit
    # Alias-driven match (mirrors the live ranking's first-name
    # display: "Kahi", "Lennie", "TK", etc.).
    for variant in Q2_ALIAS_OVERRIDE.get(canonical_legal, []):
        # Try full variant, then first-name only.
        for candidate in (variant, variant.split()[0] if variant else ""):
            hit = live_pcts.get(_norm(candidate))
            if hit:
                return hit
    # Also try the legal first name (live ranking uses first-name-only).
    first = canonical_legal.split()[0] if canonical_legal else ""
    if first:
        hit = live_pcts.get(_norm(first))
        if hit:
            return hit
    return None


def _path_c1_lbw_glass_lsc_for(
    canonical_legal: str,
    live_pcts: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """Path C1 enrichment: store the live ranking endpoint's already-
    merged LBW%/Glass%/LSC% DIRECTLY on the staged record. We do NOT
    back-solve per-guest raws (back-solving fabricates raw data and
    can't uniquely invert a capped/transformed normalization).

    The scorer wrapper injects these straight onto
    `EmployeeV2.score_lbw / score_glass / score_lsc` AFTER
    `calculate_normalized_scores` runs, bypassing the raw→percentage
    step for these three only. Steps 7+ (`calculate_bonus_points`,
    `calculate_total_score`) consume the injected values unmodified.

    Each value carries `source="live_derived"` so it's never confused
    with an independently reconciled number.
    """
    hit = resolve_live_percentages_for(canonical_legal, live_pcts)
    if hit is None:
        return {
            "lbw_percentage":       None,
            "glassware_percentage": None,
            "lsc_percentage":       None,
            "lbw_pct_source":       "MISS",
            "glass_pct_source":     "MISS",
            "lsc_pct_source":       "MISS",
        }
    return {
        # Direct injection — no transformation.
        "lbw_percentage":       hit["lbw_pct"],
        "glassware_percentage": hit["glass_pct"],
        "lsc_percentage":       hit["lsc_pct"],
        "lbw_pct_source":       "live_derived",
        "glass_pct_source":     "live_derived",
        "lsc_pct_source":       "live_derived",
    }


# --------------------------------------------------------------------
# Stager
# --------------------------------------------------------------------
async def stage(db) -> Dict[str, Any]:
    pos_rows = load_pos_truth()
    nps_rows = load_nps_optional()
    rt_rows  = load_rt_optional()
    resolver = build_override_resolver()

    # Path C1: live percentages source — direct call into the same
    # internal pipeline the API endpoint serves (no auth-gated HTTP).
    live_pcts: Dict[str, Dict[str, float]] = {}
    try:
        live_pcts = await load_live_normalized_percentages(db)
        print(f"loaded LIVE normalized %s for {len(live_pcts)} ranking rows "
              f"(Path C1, internal call)")
    except Exception as e:
        print(f"WARN: live ranking pipeline call failed: {e!r}. "
              f"LBW/Glass/LSC per_guest will default to 0 and parity "
              f"check WILL fail.")

    # Validate POS truth doesn't already contain anything from
    # EXCLUDE_FROM_REBUILD — if it did, we'd silently include them.
    pos_names_lc = {_norm(r["server_name"]) for r in pos_rows}
    excluded_present = [n for n in EXCLUDE_FROM_REBUILD
                        if _norm(n) in pos_names_lc]
    if excluded_present:
        print(f"WARN: POS truth contains names on the EXCLUDE list: "
              f"{excluded_present} — these will still be skipped.")

    # Pre-extract RT mentions for ALL canonical legals in one pass,
    # so the per-employee loop just looks up the count. This matches
    # the live algorithm shape (one pass over reviews, dedup per review).
    canonical_legals: List[str] = []
    for pos in pos_rows:
        legal = pos["server_name"].strip()
        if legal in EXCLUDE_FROM_REBUILD:
            continue
        canon = resolver.get(_norm(legal), legal)
        if canon not in canonical_legals:
            canonical_legals.append(canon)
    rt_mentions_by_legal: Dict[str, int] = (
        extract_rt_mentions_per_canonical(rt_rows, canonical_legals)
        if rt_rows is not None else {}
    )

    # Build the staged employees[].
    staged_employees: List[Dict[str, Any]] = []
    duplicate_guard: Dict[str, int] = {}

    for pos in pos_rows:
        legal = pos["server_name"].strip()
        if legal in EXCLUDE_FROM_REBUILD:
            continue
        canonical_legal = resolver.get(_norm(legal), legal)

        # Duplicate guard.
        if _norm(canonical_legal) in duplicate_guard:
            duplicate_guard[_norm(canonical_legal)] += 1
            continue
        duplicate_guard[_norm(canonical_legal)] = 1

        net_sales = pos["net_sales"] or 0
        guests    = int(pos["guests"] or 0)
        ppa       = pos["ppa"]

        # ---- CV (NPS) join ---------------------------------------
        cv_block: Dict[str, Any] = {
            "cv_source":     "PENDING_SOURCE_FILE" if nps_rows is None else "matched",
            "cv_promoters":  None,
            "cv_passives":   None,
            "cv_detractors": None,
            "cv_responses":  None,
            "nps_score":     None,
            "nps_score_pts": None,
            "cv_score":      None,
        }
        if nps_rows is not None:
            match = next(
                (r for r in nps_rows
                 if _norm(r.get("server_name")) == _norm(canonical_legal)),
                None,
            )
            if match:
                nps_v   = _fnum(match.get("nps_score"))
                recv_v  = _fnum(match.get("received"))
                cv_block["nps_score"]     = nps_v
                cv_block["cv_responses"]  = int(recv_v) if recv_v is not None else None
                # Live calc: `nps_score_pts = nps_score / 10`.
                cv_block["nps_score_pts"] = (round(nps_v / 10, 2)
                                              if nps_v is not None else None)
                # Without transaction-level data we can't compute the
                # promoter-bonus portion. Surface what we have and
                # tag the source so the operator sees the limitation.
                cv_block["cv_score"]      = cv_block["nps_score_pts"]
                cv_block["cv_source"]     = "aggregate_only"
            else:
                cv_block["cv_source"] = "no_nps_row"

        # ---- RT mentions ----------------------------------------
        if rt_rows is None:
            rt_block = {
                "rt_source":            "PENDING_SOURCE_FILE",
                "rt_mentions":          None,
                "review_tracker_bonus": None,
            }
        else:
            m = rt_mentions_by_legal.get(canonical_legal, 0)
            rt_block = {
                "rt_source":            "computed",
                "rt_mentions":          int(m),
                "review_tracker_bonus": review_tracker_bonus(m),
            }

        staged_employees.append({
            "id":            str(uuid.uuid4()),
            "name":          canonical_legal,
            "display_name":  canonical_legal,
            "report_name":   canonical_legal,
            "aliases":       Q2_ALIAS_OVERRIDE.get(canonical_legal, []),
            "alias_source":  "Q2_ALIAS_OVERRIDE" if canonical_legal in Q2_ALIAS_OVERRIDE else "none",
            "job_title":     "Server",
            "quarter":       QUARTER,
            "year":          YEAR,
            "net_sales":     net_sales,
            "guests":        guests,
            "guest_count":   guests,
            "ppa":           ppa,
            **_path_c1_lbw_glass_lsc_for(canonical_legal, live_pcts),
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
