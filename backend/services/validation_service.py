"""
Integrity validation for the canonical employee data layer.

Run via `python scripts/run_validation_suite.py` or programmatically by
calling `await EmployeeValidator(db).run_all()`. Returns a structured
report — no destructive writes.

Checks
------
1. duplicate_canonical_ids   - any `employees.id` appearing more than once
2. duplicate_active_names    - two active employees with the same canonical
                               name (often the symptom of an unmerged duplicate)
3. orphaned_snapshot_refs    - snapshot.rows[].employee_id pointing at an id
                               that doesn't exist in `employees`
4. legacy_only_employees     - rows present in `employees_v2` but missing from
                               canonical `employees` (migration incomplete)
5. snapshot_only_employees   - employees embedded in `snapshot.employees[]`
                               but missing from canonical `employees`
6. employees_missing_id      - canonical rows with empty/null id
7. inactive_in_current_snap  - current snapshot embeds a terminated employee
                               (slide would still render them)
8. blocklist_violations      - employees on a snapshot's deleted_names but
                               still embedded in that snapshot's employees[]
                               array (the "ghosts come back" bug class)
9. metric_drift              - same employee has different cv_score / rt_mentions
                               between canonical and the embedded snapshot row
                               (signals stale `employees_v2` cache)

This suite is used as the deployment gate: if any P0 check fails, refuse
to flip the read path to canonical until the migration script is rerun.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


def _ci(value: str) -> str:
    return (value or "").strip().lower()


class EmployeeValidator:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def run_all(self) -> Dict[str, Any]:
        results = {
            "duplicate_canonical_ids": await self.check_duplicate_canonical_ids(),
            "duplicate_active_names": await self.check_duplicate_active_names(),
            "orphaned_snapshot_refs": await self.check_orphaned_snapshot_refs(),
            "legacy_only_employees": await self.check_legacy_only_employees(),
            "snapshot_only_employees": await self.check_snapshot_only_employees(),
            "employees_missing_id": await self.check_employees_missing_id(),
            "inactive_in_current_snap": await self.check_inactive_in_current_snapshot(),
            "blocklist_violations": await self.check_blocklist_violations(),
            "metric_drift": await self.check_metric_drift(),
        }
        # Roll-up: count total issues + classify severity for the deploy gate.
        p0_issues = sum(
            len(results[k]) for k in
            ("duplicate_canonical_ids", "orphaned_snapshot_refs",
             "employees_missing_id", "blocklist_violations")
        )
        p1_issues = sum(
            len(results[k]) for k in
            ("duplicate_active_names", "inactive_in_current_snap",
             "metric_drift")
        )
        p2_issues = sum(
            len(results[k]) for k in
            ("legacy_only_employees", "snapshot_only_employees")
        )
        results["summary"] = {
            "p0_issues": p0_issues,
            "p1_issues": p1_issues,
            "p2_issues": p2_issues,
            "deploy_gate": "PASS" if p0_issues == 0 else "FAIL",
        }
        return results

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    async def check_duplicate_canonical_ids(self) -> List[Dict[str, Any]]:
        ids: Counter[str] = Counter()
        async for e in self.db.employees.find({}, {"_id": 0, "id": 1, "name": 1}):
            eid = e.get("id")
            if eid:
                ids[eid] += 1
        return [
            {"id": eid, "count": count}
            for eid, count in ids.items()
            if count > 1
        ]

    async def check_duplicate_active_names(self) -> List[Dict[str, Any]]:
        by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        async for e in self.db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "display_name": 1},
        ):
            key = _ci(e.get("name") or "")
            if not key:
                continue
            by_name[key].append({"id": e.get("id"), "name": e.get("name")})
        return [
            {"name": name, "rows": rows}
            for name, rows in by_name.items()
            if len(rows) > 1
        ]

    async def check_orphaned_snapshot_refs(self) -> List[Dict[str, Any]]:
        canonical_ids = set()
        async for e in self.db.employees.find({}, {"_id": 0, "id": 1}):
            if e.get("id"):
                canonical_ids.add(e["id"])

        orphans: List[Dict[str, Any]] = []
        async for snap in self.db.snapshot_workflow.find(
            {"rows": {"$exists": True, "$ne": []}},
            {"id": 1, "name": 1, "rows.employee_id": 1, "_id": 0},
        ):
            for row in snap.get("rows", []):
                ref = row.get("employee_id")
                if ref and ref not in canonical_ids:
                    orphans.append({
                        "snapshot_id": snap.get("id"),
                        "snapshot_name": snap.get("name"),
                        "missing_employee_id": ref,
                    })
        return orphans

    async def check_legacy_only_employees(self) -> List[Dict[str, Any]]:
        canonical_ids = set()
        canonical_names = set()
        async for e in self.db.employees.find({}, {"_id": 0, "id": 1, "name": 1, "aliases": 1}):
            if e.get("id"):
                canonical_ids.add(e["id"])
            if e.get("name"):
                canonical_names.add(_ci(e["name"]))
            for a in e.get("aliases") or []:
                canonical_names.add(_ci(a))

        out: List[Dict[str, Any]] = []
        async for e in self.db.employees_v2.find({}, {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1}):
            eid = e.get("id")
            name = _ci(e.get("name") or "")
            if eid and eid in canonical_ids:
                continue
            if name and name in canonical_names:
                continue
            out.append({
                "v2_id": eid,
                "name": e.get("name"),
                "quarter": e.get("quarter"),
                "year": e.get("year"),
            })
        return out

    async def check_snapshot_only_employees(self) -> List[Dict[str, Any]]:
        canonical_ids = set()
        canonical_names = set()
        async for e in self.db.employees.find({}, {"_id": 0, "id": 1, "name": 1, "aliases": 1}):
            if e.get("id"):
                canonical_ids.add(e["id"])
            if e.get("name"):
                canonical_names.add(_ci(e["name"]))
            for a in e.get("aliases") or []:
                canonical_names.add(_ci(a))

        out: List[Dict[str, Any]] = []
        async for snap in self.db.snapshot_workflow.find(
            {"status": {"$ne": "deleted"}},
            {"id": 1, "name": 1, "quarter": 1, "year": 1,
             "employees.id": 1, "employees.name": 1, "_id": 0},
        ):
            for emp in snap.get("employees", []) or []:
                eid = emp.get("id")
                name = _ci(emp.get("name") or "")
                if eid and eid in canonical_ids:
                    continue
                if name and name in canonical_names:
                    continue
                out.append({
                    "snapshot_id": snap.get("id"),
                    "snapshot_name": snap.get("name"),
                    "embedded_id": eid,
                    "embedded_name": emp.get("name"),
                })
        return out

    async def check_employees_missing_id(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        async for e in self.db.employees.find(
            {"$or": [{"id": {"$exists": False}}, {"id": None}, {"id": ""}]},
            {"_id": 1, "name": 1},
        ):
            out.append({"mongo_id": str(e.get("_id")), "name": e.get("name")})
        return out

    async def check_inactive_in_current_snapshot(self) -> List[Dict[str, Any]]:
        inactive_ids = set()
        async for e in self.db.employees.find(
            {"status": {"$in": ["terminated", "merged"]}},
            {"_id": 0, "id": 1, "name": 1, "status": 1},
        ):
            if e.get("id"):
                inactive_ids.add(e["id"])

        out: List[Dict[str, Any]] = []
        async for snap in self.db.snapshot_workflow.find(
            {"is_current": True},
            {"id": 1, "name": 1, "employees.id": 1, "employees.name": 1,
             "rows.employee_id": 1, "rows.frozen_display_name": 1, "_id": 0},
        ):
            # Check both legacy embedded employees AND new rows[]
            for emp in snap.get("employees", []) or []:
                if emp.get("id") and emp["id"] in inactive_ids:
                    out.append({
                        "snapshot_id": snap.get("id"),
                        "snapshot_name": snap.get("name"),
                        "shape": "legacy_embedded",
                        "employee_id": emp.get("id"),
                        "name": emp.get("name"),
                    })
            for row in snap.get("rows", []) or []:
                if row.get("employee_id") and row["employee_id"] in inactive_ids:
                    out.append({
                        "snapshot_id": snap.get("id"),
                        "snapshot_name": snap.get("name"),
                        "shape": "rows",
                        "employee_id": row.get("employee_id"),
                        "name": row.get("frozen_display_name"),
                    })
        return out

    async def check_blocklist_violations(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        async for snap in self.db.snapshot_workflow.find(
            {"deleted_names": {"$exists": True, "$ne": []}},
            {"id": 1, "name": 1, "deleted_names": 1,
             "employees.name": 1, "rows.frozen_display_name": 1, "_id": 0},
        ):
            blocked = {_ci(n) for n in (snap.get("deleted_names") or []) if n}
            if not blocked:
                continue
            hits = set()
            for emp in snap.get("employees", []) or []:
                if _ci(emp.get("name") or "") in blocked:
                    hits.add(emp.get("name"))
            for row in snap.get("rows", []) or []:
                if _ci(row.get("frozen_display_name") or "") in blocked:
                    hits.add(row.get("frozen_display_name"))
            if hits:
                out.append({
                    "snapshot_id": snap.get("id"),
                    "snapshot_name": snap.get("name"),
                    "blocked_but_still_present": sorted(hits),
                })
        return out

    async def check_metric_drift(self) -> List[Dict[str, Any]]:
        """
        Compares cv_score / rt_mentions on each canonical employee's
        `current_metrics` against the embedded value in the current
        snapshot. Surfaces stale denormalized caches.
        """
        out: List[Dict[str, Any]] = []
        async for snap in self.db.snapshot_workflow.find(
            {"is_current": True},
            {"id": 1, "name": 1, "quarter": 1, "year": 1,
             "employees": 1, "rows": 1, "_id": 0},
        ):
            # Build a quick lookup of snapshot values keyed by id OR name
            snap_lookup: Dict[str, Dict[str, Any]] = {}
            for emp in snap.get("employees", []) or []:
                key = emp.get("id") or _ci(emp.get("name") or "")
                if key:
                    snap_lookup[key] = emp
            for row in snap.get("rows", []) or []:
                key = row.get("employee_id") or _ci(row.get("frozen_display_name") or "")
                if key:
                    snap_lookup[key] = {
                        **(row.get("frozen_metrics") or {}),
                        "id": row.get("employee_id"),
                        "name": row.get("frozen_display_name"),
                    }

            async for emp in self.db.employees.find(
                {"status": "active"},
                {"_id": 0, "id": 1, "name": 1, "current_metrics": 1},
            ):
                key = emp.get("id") or _ci(emp.get("name") or "")
                snap_emp = snap_lookup.get(key)
                if not snap_emp:
                    continue
                cm = emp.get("current_metrics") or {}
                for field in ("cv_score", "rt_mentions", "review_tracker_bonus", "total_score"):
                    sv = snap_emp.get(field)
                    cv = cm.get(field)
                    if sv is None or cv is None:
                        continue
                    try:
                        if abs(float(sv) - float(cv)) > 0.05:
                            out.append({
                                "employee_id": emp.get("id"),
                                "name": emp.get("name"),
                                "field": field,
                                "canonical": cv,
                                "snapshot": sv,
                            })
                    except (TypeError, ValueError):
                        pass
        return out


__all__ = ["EmployeeValidator"]
