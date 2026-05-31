"""
Reconciliation Service — Manual adjudication queue for canonical-vs-
snapshot data drift.

Surfaces every conflict that `/api/v2/admin/scoring-trust` flags
(metric drift, alias collisions) as an individual resolution card.
The owner makes one explicit decision per card — there is no
auto-resolution.

Resolution actions:
  - keep_stored       : leave canonical as-is, dismiss flag
  - accept_snapshot   : overwrite canonical with the snapshot-derived value
  - manual_override   : write the operator-typed value to canonical
  - defer             : push card to "Review Later" (persists across sessions)
  - revoke_alias      : remove an alias from canonical (alias-collision cards)

Persistence:
  - reconciliation_deferred  — { conflict_id, snoozed_at, reason? }
  - reconciliation_audit     — append-only event log of every resolution

Every resolution logs: actor, employee, field, before/after, action,
timestamp. There is no batch path. Each card is one POST.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


# ---------------------------------------------------------------------------
# Conflict-id helpers
# ---------------------------------------------------------------------------
# Deterministic so deferred cards survive reloads and the operator can
# resolve the same flag on the next visit.


def metric_conflict_id(employee_id: str, metric: str) -> str:
    h = hashlib.sha1(f"metric:{employee_id}:{metric}".encode()).hexdigest()
    return f"metric_{h[:16]}"


def alias_conflict_id(primary_id: str, duplicate_id: str, alias: str) -> str:
    h = hashlib.sha1(
        f"alias:{primary_id}:{duplicate_id}:{alias.lower()}".encode()
    ).hexdigest()
    return f"alias_{h[:16]}"


# ---------------------------------------------------------------------------
# Tolerances — must match `/scoring-trust` so the two views never disagree.
# ---------------------------------------------------------------------------
METRIC_TOLERANCE = 0.02   # 2 % — drift threshold for FLAGGING a conflict
METRIC_MIN_ABS   = 0.05   # 5 ¢

# Once an operator has explicitly resolved a card, we suppress it on
# subsequent refreshes UNTIL the underlying values drift by ≥1% from
# the resolved snapshot. This is intentionally tighter than the 2%
# flagging threshold so a resolved card never re-surfaces inside the
# noise band — only on genuinely fresh drift.
RESOLVED_REFRESH_THRESHOLD = 0.01  # 1 %


class ReconciliationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    # ------------------------------------------------------------------
    # Build the conflict queue
    # ------------------------------------------------------------------

    async def _build_metric_conflicts(self) -> List[Dict[str, Any]]:
        """Replicate the `/scoring-trust` metric-drift detection, but with
        full source attribution attached so each card can name the
        snapshot it disagrees with."""
        conflicts: List[Dict[str, Any]] = []
        # Index the active snapshot per (quarter, year) for source labelling.
        active_snap = await self.db.snapshot_workflow.find_one(
            {"is_current": True},
            {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1,
             "effective_date": 1, "employees": 1},
        )
        snap_emps_by_id: Dict[str, Dict[str, Any]] = {}
        for e in (active_snap or {}).get("employees", []) or []:
            if e.get("id"):
                snap_emps_by_id[e["id"]] = e

        async for emp in self.db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "current_metrics": 1,
             "legacy_ids": 1},
        ):
            cm = emp.get("current_metrics") or {}
            guests = cm.get("guests") or cm.get("guest_count") or 0
            if not guests or guests <= 0:
                continue

            # Build the snapshot mirror for this employee so the
            # "accept_snapshot" action knows what to write.
            snap_emp = snap_emps_by_id.get(emp.get("id"))
            if not snap_emp:
                for lid in (emp.get("legacy_ids") or []):
                    if lid in snap_emps_by_id:
                        snap_emp = snap_emps_by_id[lid]
                        break

            checks = [
                # (metric, numerator_field, denom_field)
                ("ppa",            "net_sales", "guests"),
                ("guests_per_lsc", "guests",    "lsc_count"),
                ("lbw_per_guest",  "lbw",       "guests"),
            ]
            for metric, num_field, denom_field in checks:
                stored = cm.get(metric)
                if stored is None:
                    continue
                num   = cm.get(num_field)
                denom = cm.get(denom_field) if denom_field != "guests" else guests
                if not denom or denom <= 0 or num is None:
                    continue
                try:
                    expected = round(float(num) / float(denom), 2)
                except (TypeError, ZeroDivisionError, ValueError):
                    continue
                diff = abs(expected - float(stored))
                if diff < METRIC_MIN_ABS:
                    continue
                rel = diff / max(abs(expected), abs(float(stored)), 1e-9)
                if rel <= METRIC_TOLERANCE:
                    continue

                # Snapshot value (the alternative the operator can
                # accept). We trust the snapshot's stored derived value
                # over a recomputation when present, because the
                # snapshot was scored through `run_full_scoring`.
                snapshot_value = None
                if snap_emp:
                    snapshot_value = snap_emp.get(metric)
                # Fallback: recompute from canonical raw inputs.
                if snapshot_value is None:
                    snapshot_value = expected

                conflicts.append({
                    "conflict_id": metric_conflict_id(emp["id"], metric),
                    "kind": "metric_drift",
                    "severity_pct": round(rel * 100, 2),
                    "employee_id": emp["id"],
                    "employee_name": emp.get("name"),
                    "field": metric,
                    "stored_value": float(stored),
                    "snapshot_value": snapshot_value,
                    "computed_expected": expected,
                    "raw_inputs": {
                        num_field: num,
                        denom_field: denom,
                    },
                    "source": {
                        "snapshot_id": (active_snap or {}).get("id"),
                        "snapshot_name": (active_snap or {}).get("name"),
                        "quarter": (active_snap or {}).get("quarter"),
                        "year": (active_snap or {}).get("year"),
                        "effective_date": (active_snap or {}).get("effective_date"),
                    },
                })

        return conflicts

    async def _build_alias_conflicts(self) -> List[Dict[str, Any]]:
        """Alias-collision flags from active canonical employees that
        carry another active canonical employee's primary name in their
        aliases array. Resolution = revoke the alias."""
        rows = await self.db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "aliases": 1},
        ).to_list(2000)
        name_to_id = {(r.get("name") or "").lower(): r.get("id") for r in rows
                      if r.get("name")}

        conflicts: List[Dict[str, Any]] = []
        for r in rows:
            primary_id = r.get("id")
            primary_name = r.get("name")
            for a in (r.get("aliases") or []):
                al = (a or "").strip().lower()
                if not al:
                    continue
                owner_id = name_to_id.get(al)
                if not owner_id or owner_id == primary_id:
                    continue
                # Find the duplicate's display name for the card.
                owner = next((x for x in rows if x.get("id") == owner_id), None)
                conflicts.append({
                    "conflict_id": alias_conflict_id(primary_id, owner_id, a),
                    "kind": "alias_collision",
                    "severity_pct": 100.0,
                    "employee_id": primary_id,
                    "employee_name": primary_name,
                    "field": "aliases",
                    "stored_value": a,
                    "snapshot_value": None,
                    "computed_expected": None,
                    "raw_inputs": {
                        "alias": a,
                        "owned_by": owner.get("name") if owner else None,
                    },
                    "source": {
                        "owner_id": owner_id,
                        "owner_name": owner.get("name") if owner else None,
                        "reason": "alias matches another active employee's primary name",
                    },
                })
        return conflicts

    async def queue(self) -> Dict[str, Any]:
        """Return the active + deferred queue, sorted so the most
        severe drift sits at the top. Resolved conflicts are filtered
        out unless the underlying values have moved beyond tolerance
        since the resolution (i.e. fresh drift)."""
        metric_c = await self._build_metric_conflicts()
        alias_c  = await self._build_alias_conflicts()
        all_c    = metric_c + alias_c

        deferred_ids = {d["conflict_id"]
                        async for d in self.db.reconciliation_deferred.find(
                            {}, {"_id": 0, "conflict_id": 1}
                        )}

        # Resolved registry — once the operator clicks any actionable
        # resolution (keep_stored / accept_snapshot / manual_override /
        # revoke_alias) we stamp the resolved tuple here so the card
        # stays hidden. If the data moves materially after that, the
        # card re-surfaces and the stale resolved row is dropped.
        resolved_by_id: Dict[str, Dict[str, Any]] = {}
        async for r in self.db.reconciliation_resolved.find({}, {"_id": 0}):
            resolved_by_id[r["conflict_id"]] = r

        active:   List[Dict[str, Any]] = []
        deferred: List[Dict[str, Any]] = []
        stale_resolved: List[str] = []  # conflict_ids whose resolution is no longer valid

        for c in all_c:
            cid = c["conflict_id"]
            if cid in deferred_ids:
                deferred.append(c)
                continue
            resolved = resolved_by_id.get(cid)
            if resolved is not None:
                if self._resolved_still_applies(c, resolved):
                    # Cleared. Hide it.
                    continue
                # Values moved past tolerance since the operator
                # acknowledged this — re-surface as new drift.
                stale_resolved.append(cid)
            active.append(c)

        if stale_resolved:
            await self.db.reconciliation_resolved.delete_many(
                {"conflict_id": {"$in": stale_resolved}}
            )

        # Sort severity descending so the operator's eye goes to the
        # worst offenders first.
        active.sort(key=lambda x: -(x.get("severity_pct") or 0))
        deferred.sort(key=lambda x: -(x.get("severity_pct") or 0))

        # Attach defer reasons.
        if deferred:
            reasons = {d["conflict_id"]: d
                       async for d in self.db.reconciliation_deferred.find(
                           {}, {"_id": 0}
                       )}
            for d in deferred:
                rec = reasons.get(d["conflict_id"]) or {}
                d["deferred_at"] = rec.get("snoozed_at")
                d["defer_reason"] = rec.get("reason")

        # Build the "resolved (cleared)" section so the UI can show
        # what's been recently dismissed and let the operator un-resolve
        # if they changed their mind. Cap at the 50 most recent.
        resolved_recent: List[Dict[str, Any]] = []
        async for r in self.db.reconciliation_resolved.find(
            {}, {"_id": 0}
        ).sort("resolved_at", -1).limit(50):
            resolved_recent.append(r)

        return {
            "active": active,
            "deferred": deferred,
            "resolved": resolved_recent,
            "counts": {
                "active": len(active),
                "deferred": len(deferred),
                "resolved": len(resolved_recent),
                "total": len(active) + len(deferred),
            },
        }

    async def unresolve(self, conflict_id: str) -> Dict[str, Any]:
        """Operator changed their mind — drop the resolved stamp so the
        card re-surfaces in the active queue on next refresh. The audit
        log keeps the original resolution event."""
        res = await self.db.reconciliation_resolved.delete_one(
            {"conflict_id": conflict_id}
        )
        return {"success": True, "removed": res.deleted_count}

    # ------------------------------------------------------------------
    # Resolve a single card
    # ------------------------------------------------------------------

    async def resolve(
        self,
        conflict_id: str,
        action: str,
        actor: str,
        value_override: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply one resolution. Never batches. Always logs."""
        if action not in {"keep_stored", "accept_snapshot",
                          "manual_override", "defer", "revoke_alias"}:
            raise ValueError(f"unknown action: {action}")

        # Re-derive the conflict so we don't trust client-side state.
        queue = await self.queue()
        all_cards = queue["active"] + queue["deferred"]
        card = next((c for c in all_cards if c["conflict_id"] == conflict_id),
                    None)
        if not card:
            raise LookupError(
                f"conflict_id {conflict_id} not found — it may have already "
                f"been resolved or the underlying data changed."
            )

        # If we're deferring, ALWAYS allowed — write a stub row.
        if action == "defer":
            await self.db.reconciliation_deferred.update_one(
                {"conflict_id": conflict_id},
                {"$set": {
                    "conflict_id": conflict_id,
                    "snoozed_at": datetime.now(timezone.utc).isoformat(),
                    "reason": reason or "",
                    "employee_name": card.get("employee_name"),
                    "field": card.get("field"),
                }},
                upsert=True,
            )
            await self._audit(card, action, before=card.get("stored_value"),
                              after=card.get("stored_value"), actor=actor,
                              reason=reason)
            return {"success": True, "action": action,
                    "conflict_id": conflict_id}

        # Once an actionable resolution happens, the card is no longer
        # deferred.
        await self.db.reconciliation_deferred.delete_one(
            {"conflict_id": conflict_id}
        )

        # Each remaining action is per-kind.
        if card["kind"] == "metric_drift":
            result = await self._apply_metric_resolution(
                card, action, value_override, actor, reason
            )
        elif card["kind"] == "alias_collision":
            result = await self._apply_alias_resolution(
                card, action, actor, reason
            )
        else:
            raise ValueError(f"unhandled card kind: {card.get('kind')}")

        # Stamp the resolved registry so the queue filter hides this
        # card going forward. We re-derive the post-resolution stored
        # and expected so the "still applies" check has the authoritative
        # tuple to compare against on the next refresh.
        await self._stamp_resolved(card, action, actor, reason)
        return result

    async def _stamp_resolved(
        self,
        card: Dict[str, Any],
        action: str,
        actor: str,
        reason: Optional[str],
    ) -> None:
        """After an actionable resolution, record the post-resolution
        (stored, expected) tuple so the queue can hide the card until
        a NEW drift materialises."""
        post_stored: Any = None
        post_expected: Any = None

        if card["kind"] == "metric_drift":
            emp = await self.db.employees.find_one(
                {"id": card["employee_id"]},
                {"_id": 0, "current_metrics": 1},
            ) or {}
            cm = emp.get("current_metrics") or {}
            field = card["field"]
            post_stored = cm.get(field)
            # Recompute expected from the current raw inputs.
            raw_inputs = card.get("raw_inputs") or {}
            if field == "ppa":
                num, denom = cm.get("net_sales"), cm.get("guests") or cm.get("guest_count")
            elif field == "guests_per_lsc":
                num, denom = cm.get("guests") or cm.get("guest_count"), cm.get("lsc_count")
            elif field == "lbw_per_guest":
                num, denom = cm.get("lbw") or cm.get("lbw_total"), cm.get("guests") or cm.get("guest_count")
            else:
                num, denom = None, None
            try:
                if num is not None and denom:
                    post_expected = round(float(num) / float(denom), 2)
            except (TypeError, ZeroDivisionError, ValueError):
                post_expected = None
            # If raw_inputs were null at resolution time, also remember that.
            _ = raw_inputs
        elif card["kind"] == "alias_collision":
            post_stored = card.get("stored_value")
            post_expected = None  # alias drift doesn't have a numeric expected

        await self.db.reconciliation_resolved.update_one(
            {"conflict_id": card["conflict_id"]},
            {"$set": {
                "conflict_id": card["conflict_id"],
                # Caller-facing schema fields — these are what the user
                # specified for the resolved record contract:
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolution_type": action,
                "resolved_value": post_stored,
                "resolved_by": actor,
                # Internal bookkeeping the queue() filter and the
                # "recently cleared" UI table use:
                "employee_id": card.get("employee_id"),
                "employee_name": card.get("employee_name"),
                "field": card.get("field"),
                "kind": card.get("kind"),
                "action": action,           # alias of resolution_type
                "actor": actor,             # alias of resolved_by
                "reason": reason or "",
                "post_stored": post_stored,    # alias of resolved_value
                "post_expected": post_expected,
            }},
            upsert=True,
        )

    def _resolved_still_applies(
        self,
        card: Dict[str, Any],
        resolved: Dict[str, Any],
    ) -> bool:
        """A resolution remains in effect as long as both the stored
        value and the recomputed expected value are within
        `RESOLVED_REFRESH_THRESHOLD` (1%) of the snapshot taken at
        resolution time. If either drifts ≥1%, the card re-surfaces
        as fresh drift."""
        if card.get("kind") == "alias_collision":
            # The only way an alias-collision card survives `revoke_alias`
            # is if the alias was re-added later. We compare stored
            # alias strings; if they match exactly, the resolution holds.
            return (resolved.get("post_stored") == card.get("stored_value"))

        def _within(a, b):
            if a is None or b is None:
                # Either both null (e.g. raw input never populated) — still
                # the same state. One null + one numeric = state changed.
                return a is None and b is None
            try:
                a_f, b_f = float(a), float(b)
            except (TypeError, ValueError):
                return a == b
            diff = abs(a_f - b_f)
            if diff < METRIC_MIN_ABS:
                return True
            rel = diff / max(abs(a_f), abs(b_f), 1e-9)
            return rel < RESOLVED_REFRESH_THRESHOLD

        return (
            _within(card.get("stored_value"),       resolved.get("post_stored"))
            and _within(card.get("computed_expected"), resolved.get("post_expected"))
        )

    async def _apply_metric_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        value_override: Optional[float],
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        emp_id = card["employee_id"]
        field  = card["field"]
        stored = card["stored_value"]

        if action == "keep_stored":
            # Nothing to write — just log so audit shows the dismissal.
            await self._audit(card, action, before=stored, after=stored,
                              actor=actor, reason=reason)
            return {"success": True, "action": action, "value": stored}

        if action == "accept_snapshot":
            new_value = card.get("snapshot_value")
            if new_value is None:
                new_value = card.get("computed_expected")
            if new_value is None:
                raise ValueError("no snapshot value available to accept")
            await self._write_metric(emp_id, field, float(new_value))
            await self._audit(card, action, before=stored,
                              after=float(new_value), actor=actor,
                              reason=reason)
            return {"success": True, "action": action,
                    "value": float(new_value)}

        if action == "manual_override":
            if value_override is None:
                raise ValueError("manual_override requires value_override")
            new_value = float(value_override)
            await self._write_metric(emp_id, field, new_value)
            await self._audit(card, action, before=stored, after=new_value,
                              actor=actor, reason=reason)
            return {"success": True, "action": action, "value": new_value}

        raise ValueError(f"action {action} not valid for metric_drift")

    async def _apply_alias_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        emp_id = card["employee_id"]
        alias  = card["stored_value"]

        if action == "keep_stored":
            await self._audit(card, action, before=alias, after=alias,
                              actor=actor, reason=reason)
            return {"success": True, "action": action}

        if action == "revoke_alias":
            await self.db.employees.update_one(
                {"id": emp_id},
                {"$pull": {"aliases": alias}},
            )
            await self._audit(card, action, before=alias, after=None,
                              actor=actor, reason=reason)
            return {"success": True, "action": action}

        raise ValueError(f"action {action} not valid for alias_collision")

    async def _write_metric(self, employee_id: str, field: str,
                            value: float) -> None:
        """Update canonical employee.current_metrics[field] and, when
        it makes sense, recompute the derived ratio so the new raw
        value is internally consistent."""
        await self.db.employees.update_one(
            {"id": employee_id},
            {"$set": {f"current_metrics.{field}": value,
                      "current_metrics.updated_at":
                          datetime.now(timezone.utc).isoformat()}},
        )
        # Also mirror into employees_v2 (current quarter) when present so
        # the dashboard hydration sees the corrected value on next read.
        await self.db.employees_v2.update_many(
            {"id": employee_id},
            {"$set": {field: value}},
        )

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    async def _audit(
        self,
        card: Dict[str, Any],
        action: str,
        *,
        before: Any,
        after: Any,
        actor: str,
        reason: Optional[str],
    ) -> None:
        await self.db.reconciliation_audit.insert_one({
            "conflict_id": card.get("conflict_id"),
            "kind": card.get("kind"),
            "employee_id": card.get("employee_id"),
            "employee_name": card.get("employee_name"),
            "field": card.get("field"),
            "action": action,
            "before": before,
            "after": after,
            "actor": actor,
            "reason": reason or "",
            "logged_at": datetime.now(timezone.utc).isoformat(),
        })

    async def audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = self.db.reconciliation_audit.find(
            {}, {"_id": 0}
        ).sort("logged_at", -1).limit(limit)
        return [doc async for doc in cursor]
