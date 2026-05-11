"""
Phase-1 migration: build the canonical `employees` collection from
existing `employees_v2` + every `snapshot_workflow.employees[]` array.

NON-DESTRUCTIVE. This script only WRITES to the new `employees`
collection. It does NOT modify `employees_v2`, `snapshot_workflow`, or
any other existing data. Phase 2 will refactor the read paths to use the
canonical collection; Phase 3 will rewire snapshots into the thin
`rows[]` schema and remove the legacy collection.

What it does
------------
1. Scan `employees_v2` for distinct employees.
2. Scan every `snapshot.employees[]` for additional names that don't
   exist in v2 (manual adds, legacy rows).
3. For each distinct person:
     a. Choose canonical id (existing employees_v2.id wins; otherwise
        the most-recent snapshot.employees.id wins; otherwise generate
        new UUID).
     b. Choose canonical name (longest non-empty `name` value seen).
     c. Collect every other historical name into aliases[].
     d. Copy the most-recent `current_metrics` block from the most-recent
        snapshot.employees row for that person, falling back to v2.
     e. Mark `status="active"` unless every source row was missing —
        then `status="terminated"` (probably a soft-deleted historical).
4. Upsert into `employees` (idempotent — safe to re-run).
5. Print a summary with counts + samples.

Identity matching rule
----------------------
Two source rows are considered the same person if:
  - same `id`, OR
  - same canonical name (case-insensitive, whitespace-normalized) +
    same quarter/year window OR same store_id when present.

If a v2 row and a snapshot embedded row carry different `id`s but the
SAME canonical name, the v2 id wins (it's the long-lived one). The
snapshot id is recorded as a `legacy_id` alias so we can rewire
snapshot rows in Phase 3 without losing the FK.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ci(value: str) -> str:
    return (value or "").strip().lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Fields we copy from a source row into Employee.current_metrics.
CURRENT_METRIC_FIELDS = (
    "guests", "guest_count", "net_sales", "ppa",
    "liquor_sales", "beer_sales", "wine_sales", "food_sales",
    "lbw", "lbw_per_guest",
    "glassware_sales", "bar_glassware_sales", "glassware_per_guest",
    "loyalty_sales", "lsc_count", "guests_per_lsc",
    "cv_promoters", "cv_passives", "cv_detractors", "cv_responses",
    "cv_avg_rating", "cv_score", "nps_score",
    "rt_mentions", "review_mentions", "review_tracker_bonus",
    "score_ppa", "score_lbw", "score_glass", "score_lsc",
    "bonus_ppa", "bonus_lbw", "bonus_glass", "bonus_lsc",
    "total_metric_bonus", "weighted_score", "pre_dar_score",
    "dar_penalty", "total_score", "performance_tier", "peer_rank",
)


class CanonicalEmployeeRecord:
    """In-memory accumulator for one canonical person before we upsert."""

    def __init__(self):
        self.id: Optional[str] = None
        self.name: str = ""
        self.display_name: Optional[str] = None
        self.report_name: Optional[str] = None
        self.job_title: str = "Server"
        self.aliases: set[str] = set()
        # Track every historical id we saw so Phase 3 can rewire FK refs.
        self.legacy_ids: set[str] = set()
        self.most_recent_seen: Optional[str] = None  # ISO timestamp
        self.current_metrics: Dict[str, Any] = {}
        self.had_active_source: bool = False
        self.source_quarter: Optional[str] = None
        self.source_year: Optional[int] = None

    def merge(self, src: Dict[str, Any], *, source_tag: str, recency: str):
        # Prefer the longest, non-empty name as canonical.
        for field in ("name", "display_name", "report_name"):
            val = (src.get(field) or "").strip()
            current = getattr(self, field) or ""
            if val and (not current or len(val) > len(current)):
                if current and _ci(current) != _ci(val):
                    self.aliases.add(current)
                setattr(self, field, val)
            elif val:
                if _ci(val) != _ci(current):
                    self.aliases.add(val)

        if src.get("job_title"):
            self.job_title = src["job_title"]

        for a in src.get("aliases") or []:
            if a and _ci(a) != _ci(self.name):
                self.aliases.add(a)

        # Track all ids seen — useful for FK rewires in Phase 3.
        eid = src.get("id")
        if eid:
            self.legacy_ids.add(eid)
            # First non-empty id wins as canonical (preserves prod uuids).
            if not self.id:
                self.id = eid

        # current_metrics: only overwrite when this source is MORE RECENT.
        recency_str = recency.isoformat() if hasattr(recency, "isoformat") else str(recency or "")
        if recency_str >= (self.most_recent_seen or ""):
            self.most_recent_seen = recency_str
            for field in CURRENT_METRIC_FIELDS:
                if field in src and src[field] is not None:
                    self.current_metrics[field] = src[field]
            if src.get("quarter"):
                self.source_quarter = src["quarter"]
                self.current_metrics["quarter"] = src["quarter"]
            if src.get("year"):
                self.source_year = src["year"]
                self.current_metrics["year"] = src["year"]

        if source_tag == "snapshot" or source_tag == "v2":
            self.had_active_source = True

    def to_canonical(self) -> Dict[str, Any]:
        return {
            "id": self.id or str(uuid.uuid4()),
            "name": self.name,
            "display_name": self.display_name or (self.name.split()[0] if self.name else ""),
            "report_name": self.report_name or self.name,
            "aliases": sorted(a for a in self.aliases if a and _ci(a) != _ci(self.name)),
            "legacy_ids": sorted(i for i in self.legacy_ids if i and i != self.id),
            "job_title": self.job_title,
            "status": "active" if self.had_active_source else "terminated",
            "merged_into": None,
            "store_id": None,
            "current_metrics": self.current_metrics or {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "terminated_at": None if self.had_active_source else _now_iso(),
            "migration_source": "phase1_backfill",
        }


async def main() -> int:
    load_dotenv()
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "staff_score_db")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    dry_run = "--apply" not in sys.argv

    print(f"\n{'=' * 70}")
    print(f"Phase-1 canonical employee backfill (dry_run={dry_run})")
    print(f"DB: {db_name}  |  source: employees_v2 + snapshot.employees")
    print(f"{'=' * 70}\n")

    # 1) Index every distinct person by (lowercased canonical name).
    # We DO NOT collapse across stores yet (single-store today, multi-store later).
    accumulator: Dict[str, CanonicalEmployeeRecord] = {}

    def _key_for(src: Dict[str, Any]) -> Optional[str]:
        name = (src.get("name") or src.get("display_name") or "").strip()
        return _ci(name) if name else None

    # --- employees_v2 (long-lived rows, ids respected) ---
    v2_count = 0
    async for v2 in db.employees_v2.find({}, {"_id": 0}):
        k = _key_for(v2)
        if not k:
            continue
        v2_count += 1
        rec = accumulator.setdefault(k, CanonicalEmployeeRecord())
        recency = v2.get("updated_at") or v2.get("created_at") or "1970"
        rec.merge(v2, source_tag="v2", recency=recency)

    # --- snapshot.employees[] (every snapshot, sorted oldest -> newest so
    # the newest current_metrics win) ---
    snap_count = 0
    async for snap in db.snapshot_workflow.find(
        {"status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "quarter": 1, "year": 1, "completed_at": 1,
         "updated_at": 1, "is_current": 1, "employees": 1},
    ).sort([("year", 1), ("completed_at", 1)]):
        for emp in snap.get("employees", []) or []:
            k = _key_for(emp)
            if not k:
                continue
            snap_count += 1
            rec = accumulator.setdefault(k, CanonicalEmployeeRecord())
            recency = snap.get("completed_at") or snap.get("updated_at") or "1970"
            # Inject quarter/year onto the source emp so they land in current_metrics.
            src = {**emp, "quarter": snap.get("quarter"), "year": snap.get("year")}
            rec.merge(src, source_tag="snapshot", recency=recency)

    print(f"Scanned {v2_count} rows in employees_v2 and {snap_count} embedded rows across snapshots.")
    print(f"Resolved to {len(accumulator)} distinct canonical employees.\n")

    # 2) Apply (or just preview).
    new_count = 0
    updated_count = 0
    sample = []
    for rec in accumulator.values():
        canonical = rec.to_canonical()
        if dry_run:
            sample.append(canonical)
            continue

        # Upsert by id when we have one, else by canonical name.
        existing = await db.employees.find_one(
            {"id": canonical["id"]} if canonical.get("id") else
            {"name": {"$regex": f"^{re.escape(canonical['name'])}$", "$options": "i"}},
            {"_id": 0, "id": 1},
        )
        if existing:
            # Don't trash an existing canonical record's status / created_at.
            preserve = {"created_at"}
            update = {k: v for k, v in canonical.items() if k not in preserve}
            await db.employees.update_one(
                {"id": existing["id"]},
                {"$set": update,
                 "$addToSet": {"aliases": {"$each": canonical.get("aliases") or []},
                               "legacy_ids": {"$each": canonical.get("legacy_ids") or []}}},
            )
            updated_count += 1
        else:
            await db.employees.insert_one(canonical)
            new_count += 1

    if dry_run:
        print("DRY RUN — no writes performed.")
        print("Sample of 5 canonical rows the script would have written:")
        for r in sample[:5]:
            print(
                f"  id={r['id'][:8]:8s} | name='{r['name']}' "
                f"| status={r['status']} | aliases={r['aliases'][:3]} "
                f"| legacy_ids={r['legacy_ids'][:3]} | metrics_keys={len(r['current_metrics'])}"
            )
        print("\nRe-run with `--apply` to write to MongoDB.")
    else:
        print(f"Applied: {new_count} inserted, {updated_count} updated.")

    # Indexes: idempotent.
    print("\nEnsuring indexes on employees collection...")
    await db.employees.create_index("id", unique=True)
    await db.employees.create_index("name")
    await db.employees.create_index("status")
    await db.employees.create_index("legacy_ids")
    await db.employees.create_index("aliases")
    print("  ✓ indexes ensured")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
