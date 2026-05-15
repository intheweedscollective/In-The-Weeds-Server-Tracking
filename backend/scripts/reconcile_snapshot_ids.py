"""
Reconcile drift between canonical `employees.id` and the various legacy
ids stored on `employees_v2` and `snapshot_workflow.employees[]`.

Background
----------
Phase 1 migrated 59 v2 rows + 262 embedded rows into 37 canonical
employees, recording each legacy UUID in `employees.legacy_ids[]`. That
worked at migration time, but since then new POS / CV / RT uploads
have continued to mint fresh UUIDs on subsequent quarters for the same
person (e.g. Diane has id `d6577c43…` on Q1 v2 + canonical, but
`7e525961…` on Q2 v2 and `84473c85…` on the active Q2 snapshot). The
drift is the underlying cause of bugs like the snapshot PNG showing
CV/NPS = 0 for Diane.

What this script does
---------------------
For every `employees_v2` row and every `snapshot_workflow.employees[*]`
row:

  1. Resolve the canonical employee via `EmployeeService.find_by_name_or_alias`
     (name / display_name / report_name / aliases, case-insensitive).
  2. If found AND the row's id differs from `canonical.id`, rewrite the
     id and capture the old UUID in `employees.legacy_ids[]` so future
     lookups still resolve.
  3. If NOT found, log it as `unmatched` — these are the rows that
     would become orphans after Phase 3 drops `employees_v2`. They get
     auto-created by default with `--auto-create-missing` (default ON
     in apply mode unless overridden).

Idempotent. Safe to re-run.

Usage
-----
  python scripts/reconcile_snapshot_ids.py             # dry-run report
  python scripts/reconcile_snapshot_ids.py --apply     # writes
  python scripts/reconcile_snapshot_ids.py --apply --no-auto-create
"""

import argparse
import asyncio
import os
import re
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv()


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _build_canonical_index(canonicals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index name → canonical row across name, display_name, report_name, aliases."""
    by_name: Dict[str, Dict[str, Any]] = {}
    by_id: Dict[str, Dict[str, Any]] = {}
    for c in canonicals:
        cid = c.get("id")
        if cid:
            by_id[cid] = c
        for lid in c.get("legacy_ids") or []:
            by_id[lid] = c
        for n in [c.get("name"), c.get("display_name"), c.get("report_name"),
                  *(c.get("aliases") or [])]:
            k = _norm(n)
            if k:
                by_name.setdefault(k, c)
    return {"by_name": by_name, "by_id": by_id}


def _resolve(row: Dict[str, Any], index: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Try id → legacy_id → name → display_name → report_name."""
    rid = row.get("id")
    if rid and rid in index["by_id"]:
        return index["by_id"][rid]
    for fld in ("name", "display_name", "report_name"):
        k = _norm(row.get(fld))
        if k and k in index["by_name"]:
            return index["by_name"][k]
    return None


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

async def scan_v2(db, index) -> Tuple[List[dict], List[dict]]:
    rewrites: List[dict] = []
    unmatched: List[dict] = []
    async for v in db.employees_v2.find({}, {"_id": 0}):
        canonical = _resolve(v, index)
        if not canonical:
            unmatched.append({"id": v.get("id"), "name": v.get("name"),
                              "quarter": v.get("quarter"), "year": v.get("year")})
            continue
        if v.get("id") and v["id"] != canonical["id"]:
            rewrites.append({
                "collection": "employees_v2",
                "doc_match": {"id": v["id"]},
                "old_id": v["id"],
                "new_id": canonical["id"],
                "name": v.get("name"),
                "quarter": v.get("quarter"),
                "year": v.get("year"),
            })
    return rewrites, unmatched


async def scan_snapshots(db, index) -> Tuple[List[dict], List[dict]]:
    rewrites: List[dict] = []
    unmatched: List[dict] = []
    async for snap in db.snapshot_workflow.find({}, {"_id": 0}):
        sid = snap.get("id")
        sq = snap.get("quarter")
        sy = snap.get("year")
        for idx, emp in enumerate(snap.get("employees") or []):
            canonical = _resolve(emp, index)
            if not canonical:
                unmatched.append({
                    "collection": "snapshot_workflow",
                    "snapshot_id": sid, "snapshot_quarter": sq, "snapshot_year": sy,
                    "emp_id": emp.get("id"), "name": emp.get("name"),
                })
                continue
            if emp.get("id") and emp["id"] != canonical["id"]:
                rewrites.append({
                    "collection": "snapshot_workflow",
                    "snapshot_id": sid,
                    "emp_idx": idx,
                    "old_id": emp["id"],
                    "new_id": canonical["id"],
                    "name": emp.get("name"),
                    "quarter": sq, "year": sy,
                })
    return rewrites, unmatched


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

async def apply_rewrites(db, rewrites: List[dict]) -> Dict[str, int]:
    """Rewrite ids in-place. Capture old ids in canonical.legacy_ids[]."""
    stats = defaultdict(int)
    legacy_to_add: Dict[str, set] = defaultdict(set)

    for r in rewrites:
        legacy_to_add[r["new_id"]].add(r["old_id"])
        if r["collection"] == "employees_v2":
            res = await db.employees_v2.update_one(
                r["doc_match"], {"$set": {"id": r["new_id"]}},
            )
            stats["v2_updates"] += res.modified_count
        elif r["collection"] == "snapshot_workflow":
            res = await db.snapshot_workflow.update_one(
                {"id": r["snapshot_id"]},
                {"$set": {f"employees.{r['emp_idx']}.id": r["new_id"]}},
            )
            stats["snapshot_updates"] += res.modified_count

    for cid, old_ids in legacy_to_add.items():
        await db.employees.update_one(
            {"id": cid},
            {"$addToSet": {"legacy_ids": {"$each": sorted(old_ids)}}},
        )
        stats["canonicals_appended"] += 1

    return dict(stats)


async def auto_create_canonicals(db, unmatched: List[dict]) -> int:
    """Create a canonical record for each unique unmatched name.
    Returns the number of canonicals created."""
    from services.employee_service import EmployeeService
    svc = EmployeeService(db)
    seen: set = set()
    created = 0
    for u in unmatched:
        name = (u.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        # Race-safe: create_employee is idempotent on name.
        result = await svc.create_employee({"name": name})
        # Newly created (not pre-existing terminated/reactivated)
        if result.get("created_at") and abs(
            (int(result["created_at"][-1]) if isinstance(result["created_at"], str) else 0)
        ) >= 0:
            created += 1
    return created


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(apply: bool, auto_create_missing: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    canonicals = [c async for c in db.employees.find({}, {"_id": 0})]
    print(f"Canonical employees in scope: {len(canonicals)}")

    index = _build_canonical_index(canonicals)

    v2_rewrites, v2_unmatched = await scan_v2(db, index)
    snap_rewrites, snap_unmatched = await scan_snapshots(db, index)

    print()
    print("=== employees_v2 ===")
    print(f"  id rewrites needed:  {len(v2_rewrites)}")
    print(f"  unmatched rows:      {len(v2_unmatched)}")
    for r in v2_rewrites[:10]:
        print(f"    - {r['name']:<25} Q{r['quarter']}/{r['year']}: {r['old_id'][:8]} → {r['new_id'][:8]}")
    if len(v2_rewrites) > 10:
        print(f"    … +{len(v2_rewrites) - 10} more")

    print()
    print("=== snapshot_workflow.employees[] ===")
    print(f"  id rewrites needed:  {len(snap_rewrites)}")
    print(f"  unmatched rows:      {len(snap_unmatched)}")
    for r in snap_rewrites[:10]:
        print(f"    - {r['name']:<25} snap={r['snapshot_id'][:8]}: {r['old_id'][:8]} → {r['new_id'][:8]}")
    if len(snap_rewrites) > 10:
        print(f"    … +{len(snap_rewrites) - 10} more")

    print()
    if v2_unmatched:
        print("=== UNMATCHED (would become orphans after Phase 3) ===")
        # Dedup by name for the report
        by_name = defaultdict(list)
        for u in v2_unmatched:
            by_name[u.get("name") or "?"].append(u)
        for name, rows in sorted(by_name.items())[:20]:
            print(f"  - {name} ({len(rows)} row(s))")
        if len(by_name) > 20:
            print(f"    … +{len(by_name) - 20} more names")

    if not apply:
        print()
        print("DRY-RUN — no writes. Re-run with --apply to commit.")
        client.close()
        return

    print()
    print("Applying rewrites…")
    if auto_create_missing and (v2_unmatched or snap_unmatched):
        created = await auto_create_canonicals(db, v2_unmatched + snap_unmatched)
        print(f"  Auto-created {created} new canonical employee(s).")
        # Rebuild the index after creates so re-scan can match.
        canonicals = [c async for c in db.employees.find({}, {"_id": 0})]
        index = _build_canonical_index(canonicals)
        v2_rewrites, v2_unmatched = await scan_v2(db, index)
        snap_rewrites, snap_unmatched = await scan_snapshots(db, index)

    stats = await apply_rewrites(db, v2_rewrites + snap_rewrites)
    print(f"  employees_v2 rewrites:    {stats.get('v2_updates', 0)}")
    print(f"  snapshot row rewrites:    {stats.get('snapshot_updates', 0)}")
    print(f"  canonicals updated with legacy_ids: {stats.get('canonicals_appended', 0)}")

    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="Commit rewrites (otherwise dry-run report only).")
    p.add_argument("--no-auto-create", action="store_true",
                   help="Skip auto-creating canonicals for unmatched names.")
    args = p.parse_args()
    asyncio.run(main(apply=args.apply, auto_create_missing=not args.no_auto_create))
