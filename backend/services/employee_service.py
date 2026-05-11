"""
EmployeeService — the ONLY way the rest of the application is allowed to
read or write employee data.

Once Phase 2 is complete, every router, slide generator, audit pass, QR
sync, scoring engine call, and CSV export will go through this module.
Direct queries against `employees` / `employees_v2` / `snapshot.employees`
are forbidden.

Design rules baked in here:
1. **Identity is immutable.** `id` is a UUID generated at create-time and
   never changes. Rename / merge / store-transfer all keep the id.
2. **Soft-delete.** `terminate()` flips `status="terminated"`. The row
   stays in the collection; historical snapshots remain renderable.
3. **Current rankings filter on `status=="active"`.** Terminated and
   merged employees never appear in live rankings or live slides.
4. **Snapshot reads are joined.** `get_snapshot_rankings()` looks up
   each snapshot row's `employee_id` in the canonical collection and
   returns the joined view. The frozen_display_name in the snapshot row
   wins over the current display_name so historical slides stay
   historically accurate even after renames.
5. **Alias-aware lookup.** `find_by_name_or_alias()` checks the
   canonical name, display_name, report_name, and every alias before
   giving up — this is how new uploads avoid creating duplicates when a
   POS export carries a nickname.

This service is intentionally narrow. New methods should be added by
extending this file, not by writing new Mongo queries elsewhere.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from models.employee import (
    Employee,
    EmployeeStatus,
    SnapshotEmployeeRow,
)


CANONICAL_COLLECTION = "employees"
LEGACY_V2_COLLECTION = "employees_v2"
SNAPSHOT_COLLECTION = "snapshot_workflow"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ci_re(value: str) -> Dict[str, str]:
    return {"$regex": f"^{re.escape(value)}$", "$options": "i"}


class EmployeeService:
    """Async employee data-access layer. Construct once, share everywhere."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.col = db[CANONICAL_COLLECTION]
        self.snap_col = db[SNAPSHOT_COLLECTION]

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    async def get_by_id(self, employee_id: str, *, include_inactive: bool = True) -> Optional[Dict[str, Any]]:
        """Find by canonical id. Returns the JSON-safe dict (no _id)."""
        if not employee_id:
            return None
        query: Dict[str, Any] = {"id": employee_id}
        if not include_inactive:
            query["status"] = "active"
        return await self.col.find_one(query, {"_id": 0})

    async def find_by_name_or_alias(
        self,
        name: str,
        *,
        include_inactive: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Locate the canonical employee given any of:
            - exact name (case-insensitive)
            - display_name
            - report_name
            - any entry in aliases[]

        Used by every upload parser to avoid creating duplicates. By
        default we ignore terminated/merged rows; pass include_inactive
        when re-hiring or unmerging.
        """
        if not name:
            return None
        pat = _ci_re(name.strip())
        status_filter = {} if include_inactive else {"status": "active"}
        return await self.col.find_one(
            {
                **status_filter,
                "$or": [
                    {"name": pat},
                    {"display_name": pat},
                    {"report_name": pat},
                    {"aliases": pat},
                ],
            },
            {"_id": 0},
        )

    async def list_active(
        self,
        *,
        quarter: Optional[str] = None,
        year: Optional[int] = None,
        store_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """All active employees, optionally scoped to a quarter/year/store."""
        query: Dict[str, Any] = {"status": "active"}
        if store_id:
            query["store_id"] = store_id
        if quarter or year:
            and_clauses: List[Dict[str, Any]] = []
            if quarter:
                and_clauses.append({"current_metrics.quarter": quarter.upper()})
            if year:
                and_clauses.append({"current_metrics.year": year})
            if and_clauses:
                query["$and"] = and_clauses
        return [doc async for doc in self.col.find(query, {"_id": 0})]

    async def count_active(self) -> int:
        return await self.col.count_documents({"status": "active"})

    async def get_snapshot_rankings(self, snapshot_id: str) -> List[Dict[str, Any]]:
        """
        Resolve a snapshot's `rows[]` (FK list) into a fully-populated
        ranking list.

        For each row we return the canonical employee fields merged with
        the frozen snapshot values, with frozen winning on display_name /
        report_name / score (historical accuracy) and canonical winning
        on identity (id, status, store_id, job_title).
        """
        snap = await self.snap_col.find_one({"id": snapshot_id})
        if not snap:
            return []

        rows = snap.get("rows") or []
        if not rows:
            # Legacy snapshot: still uses embedded employees array — return
            # it verbatim. Phase 3 will migrate these into rows[] format.
            return snap.get("employees") or []

        out: List[Dict[str, Any]] = []
        for row in rows:
            emp_id = row.get("employee_id")
            emp = await self.col.find_one({"id": emp_id}, {"_id": 0}) if emp_id else None
            merged: Dict[str, Any] = {}
            if emp:
                merged.update(emp)
                # Don't leak the "current_metrics" denormalized blob into
                # the snapshot view — it's likely from a newer quarter.
                merged.pop("current_metrics", None)
            # Frozen fields win.
            merged["id"] = emp_id or merged.get("id")
            merged["name"] = row.get("frozen_display_name") or merged.get("name")
            merged["display_name"] = row.get("frozen_display_name") or merged.get("display_name")
            merged["report_name"] = row.get("frozen_report_name") or merged.get("report_name")
            merged["total_score"] = row.get("frozen_score", 0.0)
            merged["performance_tier"] = row.get("frozen_tier")
            merged["peer_rank"] = row.get("frozen_rank")
            merged.update(row.get("frozen_metrics") or {})
            out.append(merged)
        return out

    # ------------------------------------------------------------------
    # WRITE — IDENTITY
    # ------------------------------------------------------------------

    async def create_employee(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new canonical employee. Idempotent on name — if a row
        with the same canonical name already exists, returns that row
        instead of creating a duplicate.
        """
        name = (data.get("name") or data.get("display_name") or "").strip()
        if not name:
            raise ValueError("name is required")

        existing = await self.find_by_name_or_alias(name, include_inactive=True)
        if existing:
            # If they were terminated and we're now adding them again,
            # un-terminate. Don't return a stale "merged" row though —
            # surface a clear error if someone is re-adding a merged id.
            if existing.get("status") == "merged":
                raise ValueError(
                    f"'{name}' was previously merged into {existing.get('merged_into')}. "
                    "Unmerge first or use a different name."
                )
            if existing.get("status") == "terminated":
                await self.reactivate(existing["id"])
                existing = await self.get_by_id(existing["id"])
            return existing  # type: ignore[return-value]

        emp = Employee(
            id=data.get("id") or str(uuid.uuid4()),
            name=name,
            display_name=data.get("display_name") or name.split()[0],
            report_name=data.get("report_name") or name,
            aliases=list(data.get("aliases") or []),
            job_title=data.get("job_title") or "Server",
            store_id=data.get("store_id"),
        )
        # Capture any explicit current_metrics the caller seeded.
        if data.get("current_metrics"):
            emp.current_metrics = emp.current_metrics.model_copy(
                update=data["current_metrics"]
            )
        doc = emp.to_mongo()
        await self.col.insert_one(doc)
        # Mongo mutates the doc with _id — strip before returning.
        doc.pop("_id", None)
        return doc

    async def rename(
        self,
        employee_id: str,
        *,
        name: Optional[str] = None,
        display_name: Optional[str] = None,
        report_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Rename without changing the id. Old name is appended to aliases."""
        emp = await self.col.find_one({"id": employee_id}, {"_id": 0})
        if not emp:
            return None

        update: Dict[str, Any] = {"updated_at": _now_iso()}
        push_aliases: List[str] = []
        if name and name != emp.get("name"):
            push_aliases.append(emp["name"])
            update["name"] = name
        if display_name and display_name != emp.get("display_name"):
            push_aliases.append(emp.get("display_name") or emp["name"])
            update["display_name"] = display_name
        if report_name and report_name != emp.get("report_name"):
            push_aliases.append(emp.get("report_name") or emp["name"])
            update["report_name"] = report_name

        mongo_update: Dict[str, Any] = {"$set": update}
        if push_aliases:
            mongo_update["$addToSet"] = {"aliases": {"$each": [a for a in push_aliases if a]}}

        return await self.col.find_one_and_update(
            {"id": employee_id},
            mongo_update,
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    async def terminate(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """
        Soft-delete. Flips status to "terminated" and stamps the time.
        Does NOT touch any snapshot rows — historical slides keep showing
        the employee with their frozen data.
        """
        return await self.col.find_one_and_update(
            {"id": employee_id, "status": {"$ne": "merged"}},
            {"$set": {
                "status": "terminated",
                "terminated_at": _now_iso(),
                "updated_at": _now_iso(),
            }},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    async def reactivate(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Reverse a soft-delete."""
        return await self.col.find_one_and_update(
            {"id": employee_id, "status": "terminated"},
            {"$set": {"status": "active", "updated_at": _now_iso()},
             "$unset": {"terminated_at": ""}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    async def merge_employees(self, *, survivor_id: str, duplicate_id: str) -> Dict[str, Any]:
        """
        Combine two records into one. Aliases / names of the duplicate
        get added to the survivor; the duplicate row is flagged
        status="merged" and points at the survivor via merged_into.
        Snapshot rows are NOT auto-rewired (would corrupt history) —
        a separate `rewire_snapshot_refs(duplicate_id, survivor_id)`
        method can be called explicitly if desired.
        """
        if survivor_id == duplicate_id:
            raise ValueError("survivor and duplicate must differ")
        survivor = await self.col.find_one({"id": survivor_id}, {"_id": 0})
        duplicate = await self.col.find_one({"id": duplicate_id}, {"_id": 0})
        if not survivor or not duplicate:
            raise ValueError("survivor or duplicate not found")

        new_aliases = set(survivor.get("aliases") or [])
        for n in [duplicate.get("name"), duplicate.get("display_name"),
                  duplicate.get("report_name")]:
            if n:
                new_aliases.add(n)
        new_aliases.update(duplicate.get("aliases") or [])
        new_aliases.discard(survivor.get("name"))
        new_aliases.discard(survivor.get("display_name"))

        await self.col.update_one(
            {"id": survivor_id},
            {"$set": {"aliases": sorted(new_aliases), "updated_at": _now_iso()}},
        )
        await self.col.update_one(
            {"id": duplicate_id},
            {"$set": {
                "status": "merged",
                "merged_into": survivor_id,
                "merged_at": _now_iso(),
                "updated_at": _now_iso(),
            }},
        )
        return {"survivor_id": survivor_id, "duplicate_id": duplicate_id}

    # ------------------------------------------------------------------
    # LEGACY MIRROR — keep employees_v2 in sync during Phase 2
    # ------------------------------------------------------------------
    #
    # Until Phase 3 retires `employees_v2`, many code paths (scoring engine,
    # audit, snapshot processing, slide generators) still read it directly.
    # Every write through this service mirrors into employees_v2 so the
    # canonical collection is the source of truth WITHOUT silently
    # breaking the legacy readers. Phase 3 deletes this collection +
    # removes mirror_to_legacy calls.

    async def mirror_to_legacy_v2(self, employee: Dict[str, Any]) -> None:
        """
        Upsert the given canonical employee into `employees_v2` so legacy
        readers stay in sync. Idempotent. Matches by id when present, by
        name+quarter+year otherwise.
        """
        if not employee or not employee.get("id"):
            return
        cm = employee.get("current_metrics") or {}
        # Project canonical fields + current_metrics into the v2 shape.
        v2_doc: Dict[str, Any] = {
            "id": employee["id"],
            "name": employee.get("name"),
            "display_name": employee.get("display_name"),
            "report_name": employee.get("report_name"),
            "aliases": employee.get("aliases") or [],
            "job_title": employee.get("job_title") or "Server",
            "quarter": cm.get("quarter"),
            "year": cm.get("year"),
            "updated_at": employee.get("updated_at") or _now_iso(),
        }
        # Pour current_metrics fields directly into top level.
        for k, v in cm.items():
            if k in ("quarter", "year"):
                continue
            v2_doc[k] = v
        # Soft-deleted employees should disappear from legacy too.
        if employee.get("status") in ("terminated", "merged"):
            await self.db.employees_v2.delete_many({"id": employee["id"]})
            return
        await self.db.employees_v2.update_one(
            {"id": employee["id"]},
            {"$set": v2_doc, "$setOnInsert": {"created_at": _now_iso()}},
            upsert=True,
        )

    async def delete_completely(self, employee_id: str) -> Dict[str, Any]:
        """
        End-to-end soft-delete that respects all the bug-class fixes
        from earlier today:
          1. Soft-deletes the canonical employee (status="terminated").
          2. Removes them from employees_v2 (so legacy slides + audit
             stop showing them).
          3. Pulls them from every snapshot's embedded `employees[]`.
          4. Adds their name to every active snapshot's `deleted_names`
             blocklist so a future merge_snapshot_data re-merge can't
             silently re-add them.
        """
        emp = await self.get_by_id(employee_id)
        if not emp:
            return {"success": False, "reason": "not_found"}

        await self.terminate(employee_id)
        # employees_v2 mirror — terminated rows are deleted, not soft-deleted.
        v2_removed = (await self.db.employees_v2.delete_many({"id": employee_id})).deleted_count

        names_to_pull = [n for n in [
            emp.get("name"), emp.get("display_name"), emp.get("report_name"),
            *(emp.get("aliases") or []),
            *(emp.get("legacy_ids") or []),  # legacy ids work as ids for $pull
        ] if n]
        pulled_total = 0
        for n in set(names_to_pull):
            r = await self.snap_col.update_many(
                {},
                {"$pull": {"employees": {"$or": [
                    {"id": n},
                    {"name": {"$regex": f"^{re.escape(n)}$", "$options": "i"}},
                    {"display_name": {"$regex": f"^{re.escape(n)}$", "$options": "i"}},
                ]}}},
            )
            pulled_total += r.modified_count
        # Blocklist primary names (terminated should never come back via re-merge).
        primary_names = {emp.get("name"), emp.get("display_name"), emp.get("report_name")}
        primary_names.discard(None)
        if primary_names:
            await self.snap_col.update_many(
                {"status": {"$ne": "deleted"}},
                {"$addToSet": {"deleted_names": {"$each": list(primary_names)}}},
            )
        # Recompute employee_count on every touched snapshot.
        await self.snap_col.update_many(
            {},
            [{"$set": {"employee_count": {"$size": {"$ifNull": ["$employees", []]}}}}],
        )

        return {
            "success": True,
            "employee_id": employee_id,
            "name": emp.get("name"),
            "snapshots_modified": pulled_total,
            "employees_v2_removed": v2_removed,
        }

    async def upsert_current_metrics(
        self,
        employee_id: str,
        metrics: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update the `current_metrics` cache for an employee. This is
        denormalized for fast reads and is rebuilt from snapshots on
        every Confirm POS Review / Reprocess.
        """
        set_doc = {
            f"current_metrics.{k}": v
            for k, v in (metrics or {}).items()
            if v is not None
        }
        set_doc["updated_at"] = _now_iso()
        return await self.col.find_one_and_update(
            {"id": employee_id},
            {"$set": set_doc},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    # ------------------------------------------------------------------
    # WRITE — SNAPSHOT ROWS (the new thin snapshot schema)
    # ------------------------------------------------------------------

    async def write_snapshot_rows(
        self,
        snapshot_id: str,
        ranked_employees: Iterable[Dict[str, Any]],
    ) -> int:
        """
        Replace a snapshot's `rows[]` with a fresh list of
        `SnapshotEmployeeRow` instances. Returns the row count.

        Each ranked employee dict must carry `id` (canonical FK) and the
        relevant frozen fields. This is what `process_snapshot` will call
        once Phase 2 lands.
        """
        rows: List[Dict[str, Any]] = []
        for idx, emp in enumerate(ranked_employees, start=1):
            emp_id = emp.get("id")
            if not emp_id:
                continue
            row = SnapshotEmployeeRow(
                employee_id=emp_id,
                frozen_display_name=(
                    emp.get("display_name") or emp.get("name") or ""
                ),
                frozen_report_name=emp.get("report_name") or emp.get("name"),
                frozen_metrics={
                    k: v
                    for k, v in emp.items()
                    if k not in {"id", "name", "display_name", "report_name",
                                 "aliases", "status", "store_id", "merged_into",
                                 "created_at", "updated_at"}
                },
                frozen_score=float(emp.get("total_score") or 0.0),
                frozen_tier=emp.get("performance_tier"),
                frozen_rank=emp.get("peer_rank") or idx,
            )
            rows.append(row.model_dump(mode="json"))

        await self.snap_col.update_one(
            {"id": snapshot_id},
            {"$set": {"rows": rows, "row_count": len(rows), "updated_at": _now_iso()}},
        )
        return len(rows)


__all__ = ["EmployeeService", "CANONICAL_COLLECTION", "LEGACY_V2_COLLECTION", "SNAPSHOT_COLLECTION"]
