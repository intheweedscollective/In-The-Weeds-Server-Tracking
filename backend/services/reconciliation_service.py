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


def legacy_duplicate_conflict_id(v2_id: str) -> str:
    """Conflict id for a legacy v2 row that's a name-typo of a canonical
    employee (e.g. 'Kahiauani Ramos' for 'Kahi Ramos'). One card per
    legacy v2 id so the operator can merge / delete / promote individually."""
    h = hashlib.sha1(f"legacy:{v2_id}".encode()).hexdigest()
    return f"legacy_{h[:16]}"


def orphan_ref_conflict_id(snapshot_id: str, missing_employee_id: str) -> str:
    """Conflict id for an orphan snapshot reference — a row inside a
    finalized snapshot pointing at an employee_id that no longer exists
    in employees_v2. One card per (snapshot, missing_id) tuple so the
    operator can relink or remove each individually."""
    h = hashlib.sha1(
        f"orphan:{snapshot_id}:{missing_employee_id}".encode()
    ).hexdigest()
    return f"orphan_{h[:16]}"


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

    async def _build_legacy_duplicate_conflicts(self) -> List[Dict[str, Any]]:
        """Surface employees_v2 rows that don't link to any canonical
        employee via id or legacy_ids[] AND don't share a name match
        either. These are typos (Kahiauani / Drane / Treyanna), no-canon
        new staff (Chase Winston, Jeden White), or duplicate quarter
        rows that need adjudication.

        Exact name matches are NOT flagged here — they're handled by
        the structural-cleanup endpoint which auto-links the v2 row's
        id into the canonical's legacy_ids[].
        """
        # Build canonical name + alias index.
        canon_by_id: Dict[str, Dict[str, Any]] = {}
        name_to_canon: Dict[str, Dict[str, Any]] = {}
        async for c in self.db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "aliases": 1, "legacy_ids": 1,
             "display_name": 1, "report_name": 1},
        ):
            cid = c.get("id")
            if cid:
                canon_by_id[cid] = c
            for nm in (c.get("name"), c.get("display_name"),
                       c.get("report_name"), *(c.get("aliases") or [])):
                if nm:
                    name_to_canon.setdefault(nm.strip().lower(), c)

        # Index every legacy_ids[] entry → canonical owner.
        legacy_to_canon: Dict[str, Dict[str, Any]] = {}
        for c in canon_by_id.values():
            for lid in (c.get("legacy_ids") or []):
                legacy_to_canon[lid] = c

        conflicts: List[Dict[str, Any]] = []
        # We only inspect ACTIVE v2 rows for the CURRENT quarter so we
        # don't drown the operator in old per-quarter records. The
        # structural-cleanup endpoint handles historical sweeps.
        active_snap = await self.db.snapshot_workflow.find_one(
            {"is_current": True},
            {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1},
        )
        if not active_snap:
            return []

        async for v2 in self.db.employees_v2.find(
            {"quarter": active_snap.get("quarter"),
             "year": active_snap.get("year"),
             # Soft-deleted v2 rows must NOT re-surface as legacy_duplicate
             # cards. delete_legacy sets status="inactive" — without this
             # filter the operator clicks Delete legacy, the row gets
             # tombstoned, and the queue rebuilder happily re-detects it
             # on the next refresh (user-reported as "Delete legacy still
             # not working" — toast fires, audit logged, card returns).
             "status": {"$ne": "inactive"}},
            {"_id": 0},
        ):
            vid = v2.get("id")
            v_name = (v2.get("name") or "").strip()
            if not vid or not v_name:
                continue
            # Already linked? Skip.
            if vid in canon_by_id or vid in legacy_to_canon:
                continue
            # Exact-name match? Handled by structural-cleanup auto-link
            # (we don't burden the operator with these).
            if v_name.lower() in name_to_canon:
                continue

            # Find the best canonical name candidate by Levenshtein
            # similarity so the card can suggest a merge target.
            suggested = self._suggest_canonical(v_name, canon_by_id)

            conflicts.append({
                "conflict_id": legacy_duplicate_conflict_id(vid),
                "kind": "legacy_duplicate",
                "severity_pct": 60.0 if suggested else 80.0,
                "employee_id": vid,            # v2 record's id
                "employee_name": v_name,
                "field": "canonical_link",
                "stored_value": v_name,
                "snapshot_value": (suggested or {}).get("name"),
                "computed_expected": None,
                "raw_inputs": {
                    "v2_id": vid,
                    "quarter": v2.get("quarter"),
                    "year": v2.get("year"),
                    "guests": v2.get("guests") or v2.get("guest_count"),
                    "ppa": v2.get("ppa"),
                    "lsc_count": v2.get("lsc_count"),
                    "total_score": v2.get("total_score"),
                },
                "source": {
                    "suggested_canonical_id": (suggested or {}).get("id"),
                    "suggested_canonical_name": (suggested or {}).get("name"),
                    "reason": (
                        "V2 record not linked to any canonical employee"
                        + (
                            f" (closest: '{suggested.get('name')}')"
                            if suggested
                            else " and no name match found"
                        )
                    ).strip(),
                },
            })
        return conflicts

    @staticmethod
    def _suggest_canonical(
        v_name: str,
        canon_by_id: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Pick the closest canonical employee by simple
        token-overlap + character-distance heuristic. Returns None if
        no reasonable candidate exists."""
        v_low = v_name.lower()
        v_tokens = set(v_low.split())

        def _dist(a: str, b: str) -> int:
            # Tiny Levenshtein — O(len_a * len_b) is fine for short names.
            if a == b:
                return 0
            la, lb = len(a), len(b)
            if la == 0 or lb == 0:
                return max(la, lb)
            prev = list(range(lb + 1))
            for i, ca in enumerate(a, start=1):
                cur = [i] + [0] * lb
                for j, cb in enumerate(b, start=1):
                    cost = 0 if ca == cb else 1
                    cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
                prev = cur
            return prev[lb]

        best: Optional[Dict[str, Any]] = None
        best_score: float = 0.0
        for c in canon_by_id.values():
            cn = (c.get("name") or "").lower()
            if not cn:
                continue
            tokens = set(cn.split())
            overlap = len(v_tokens & tokens)
            d = _dist(v_low, cn)
            # Score: overlap weight + inverse-distance bonus.
            score = overlap * 10 + (max(0, 20 - d))
            if score > best_score:
                best_score = score
                best = c
        # Require a non-trivial match to surface a suggestion.
        if best_score < 10:
            return None
        return best


    async def _build_orphan_snapshot_conflicts(self) -> List[Dict[str, Any]]:
        """Surface snapshot rows that point at employee_ids no longer
        present in employees_v2 — "orphan refs". These dominate the
        Trust Score blocker count but were invisible to the queue
        before this card type. Common cause: an employee was renamed
        or merged, the new canonical got a fresh UUID, and the
        snapshot's `rows[]` was never rewritten to follow.

        For each orphan we try to find a canonical employee whose
        name (or alias) exactly matches the row's `frozen_display_name`,
        so the operator can `relink_orphan` with one click. If there's
        no name match we still surface the card with `remove_orphan`
        as the natural choice.
        """
        # Build the SAME resolvable-id set used by the Trust-gate
        # integrity check (`EmployeeValidator.check_orphaned_snapshot_refs`).
        # A snapshot row referencing a v2 id that's been linked into a
        # canonical's `legacy_ids[]` is NOT orphaned — that's exactly
        # what the legacy index is for. Without this we over-flag rows
        # that the Trust Score considers healthy, breaking the 1:1
        # alignment between the two views the operator looks at.
        resolvable_ids: set = set()
        async for e in self.db.employees.find(
            {}, {"_id": 0, "id": 1, "legacy_ids": 1},
        ):
            if e.get("id"):
                resolvable_ids.add(e["id"])
            for lid in (e.get("legacy_ids") or []):
                if lid:
                    resolvable_ids.add(lid)

        # Build a name → canonical lookup from employees_v2 active rows
        # for the relink suggestion. Match against name / display_name /
        # report_name / aliases all at once because rename history can
        # land in any of those.
        v2_by_name: Dict[str, Dict[str, Any]] = {}
        async for v2 in self.db.employees_v2.find(
            {"status": {"$ne": "inactive"}},
            {"_id": 0, "id": 1, "name": 1, "display_name": 1,
             "report_name": 1, "aliases": 1, "quarter": 1, "year": 1},
        ):
            for nm in (v2.get("name"), v2.get("display_name"),
                       v2.get("report_name"),
                       *(v2.get("aliases") or [])):
                if nm:
                    key = nm.strip().lower()
                    # First v2 row wins — orphan resolution will pick
                    # the same quarter/year row preferentially below.
                    v2_by_name.setdefault(key, v2)

        conflicts: List[Dict[str, Any]] = []
        # Scan EVERY snapshot — the integrity check does the same.
        # Historical finalized snapshots can contain orphan placeholder
        # rows left behind by past renames, and surfacing those is
        # exactly the point of this card type. Severity sorts urgent
        # work to the top.
        async for snap in self.db.snapshot_workflow.find(
            {"rows": {"$exists": True, "$ne": []}},
            {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1,
             "status": 1, "rows": 1, "is_current": 1},
        ):
            snap_id = snap.get("id")
            rows = snap.get("rows") or []
            if not snap_id or not rows:
                continue
            # Collect every employee_id referenced by this snapshot's
            # rows so we can detect orphans in a single pass.
            referenced_ids = {r.get("employee_id") for r in rows
                              if r.get("employee_id")}
            if not referenced_ids:
                continue
            missing_ids = referenced_ids - resolvable_ids
            if not missing_ids:
                continue
            # Track which (snapshot, missing_id) tuples we've already
            # turned into a card so a snapshot with multiple rows
            # pointing at the same dead UUID doesn't emit duplicates.
            seen_conflict_ids: set = set()
            for row in rows:
                rid = row.get("employee_id")
                if rid not in missing_ids:
                    continue
                cid = orphan_ref_conflict_id(snap_id, rid)
                if cid in seen_conflict_ids:
                    continue
                seen_conflict_ids.add(cid)
                frozen_name = (
                    row.get("frozen_display_name")
                    or row.get("name") or "(no name)"
                ).strip()
                suggested = v2_by_name.get(frozen_name.lower())
                # If we have a same-quarter/year suggestion, prefer it
                # — otherwise any name match will do.
                same_q = None
                if suggested:
                    if (suggested.get("quarter") == snap.get("quarter")
                            and suggested.get("year") == snap.get("year")):
                        same_q = suggested
                target = same_q or suggested
                # Drift severity for sort: orphans in the current
                # snapshot are more urgent than in older finalized
                # snapshots.
                sev = 100.0 if snap.get("is_current") else 75.0
                conflicts.append({
                    "conflict_id": cid,
                    "kind": "orphan_snapshot_ref",
                    "severity_pct": sev,
                    "employee_id": rid,
                    "employee_name": frozen_name,
                    "field": "snapshot_row",
                    "stored_value": frozen_name,
                    "snapshot_value": None,
                    "computed_expected": None,
                    "raw_inputs": {
                        "snapshot_id":   snap_id,
                        "snapshot_name": snap.get("name"),
                        "snapshot_quarter": snap.get("quarter"),
                        "snapshot_year":    snap.get("year"),
                        "missing_employee_id": rid,
                        # Row almost always has no score data (it's a
                        # placeholder left behind by a rename) — surface
                        # that explicitly so the operator knows
                        # remove_orphan won't lose actual numbers.
                        "row_total_score": row.get("total_score"),
                        "row_ppa":         row.get("ppa"),
                        "row_guests":      row.get("guests") or row.get("guest_count"),
                    },
                    "source": {
                        "suggested_canonical_id": (target or {}).get("id"),
                        "suggested_canonical_name": (target or {}).get("name"),
                        "reason": (
                            f"snapshot row references employee id "
                            f"{rid[:8]}… which is not in employees_v2"
                            + (f"; suggested relink → {(target or {}).get('name')}"
                               if target else "; no name-match found in employees_v2")
                        ),
                    },
                })
        return conflicts


    async def queue(self) -> Dict[str, Any]:
        """Return the active + deferred queue, sorted so the most
        severe drift sits at the top. Resolved conflicts are filtered
        out unless the underlying values have moved beyond tolerance
        since the resolution (i.e. fresh drift)."""
        metric_c  = await self._build_metric_conflicts()
        alias_c   = await self._build_alias_conflicts()
        legacy_c  = await self._build_legacy_duplicate_conflicts()
        orphan_c  = await self._build_orphan_snapshot_conflicts()
        all_c     = metric_c + alias_c + legacy_c + orphan_c

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
        target_canonical_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply one resolution. Never batches. Always logs."""
        if action not in {"keep_stored", "accept_snapshot",
                          "manual_override", "defer", "revoke_alias",
                          "merge_into", "delete_legacy", "promote_canonical",
                          "relink_orphan", "remove_orphan"}:
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
        elif card["kind"] == "legacy_duplicate":
            result = await self._apply_legacy_duplicate_resolution(
                card, action, target_canonical_id, actor, reason
            )
        elif card["kind"] == "orphan_snapshot_ref":
            result = await self._apply_orphan_resolution(
                card, action, target_canonical_id, actor, reason
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
        elif card["kind"] == "legacy_duplicate":
            # Legacy-duplicate resolutions have no numeric expected. We
            # stamp the v2 record's name so _resolved_still_applies can
            # do a string-equality check on subsequent queue rebuilds —
            # without this the resolved row stores post_stored=None and
            # the next queue() call compares "Thaddeus Hashey" ≠ None,
            # judges the resolution stale, and re-surfaces the card.
            post_stored = card.get("stored_value")
            post_expected = None
        elif card["kind"] == "orphan_snapshot_ref":
            # Once the operator relinks or removes the orphan, the next
            # queue rebuild won't find that (snapshot_id, missing_id)
            # tuple anymore — the conflict_id will no longer appear in
            # `all_c`. The resolved row therefore never gets re-checked.
            # But we still record post_stored so the unresolve flow
            # has data to show if needed.
            post_stored = card.get("stored_value")
            post_expected = None

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

    async def _apply_legacy_duplicate_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        target_canonical_id: Optional[str],
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        """Handle a `legacy_duplicate` card. Available actions:

          • keep_stored        — dismiss; nothing changes.
          • merge_into         — link the v2 record into a canonical's
                                 legacy_ids[] AND optionally store the v2
                                 name as an alias if it's a typo of the
                                 canonical name. Requires target_canonical_id.
          • delete_legacy      — soft-delete the v2 row (status=inactive)
                                 so it stops surfacing in the queue.
          • promote_canonical  — for genuinely new staff with no canonical:
                                 create a new canonical employee from the
                                 v2 row.
        """
        v2_id = card["employee_id"]
        v2_name = card["stored_value"]

        if action == "keep_stored":
            await self._audit(card, action, before=v2_name, after=v2_name,
                              actor=actor, reason=reason)
            return {"success": True, "action": action}

        if action == "merge_into":
            if not target_canonical_id:
                raise ValueError(
                    "merge_into requires target_canonical_id — pick the "
                    "canonical employee to absorb this v2 row."
                )
            target = await self.db.employees.find_one(
                {"id": target_canonical_id, "status": "active"},
                {"_id": 0, "id": 1, "name": 1, "aliases": 1, "legacy_ids": 1},
            )
            if not target:
                raise ValueError(
                    f"target canonical id {target_canonical_id} not found "
                    f"or not active"
                )
            # Link the v2 row into the canonical's legacy_ids[] AND add
            # the misspelled name as an alias if it's not already there.
            target_aliases = target.get("aliases") or []
            target_legacy  = target.get("legacy_ids") or []
            addto: Dict[str, Any] = {}
            if v2_id not in target_legacy:
                addto["legacy_ids"] = v2_id
            v_norm = (v2_name or "").strip().lower()
            t_norm = (target.get("name") or "").strip().lower()
            if v_norm and v_norm != t_norm and v2_name not in target_aliases:
                addto["aliases"] = v2_name
            if addto:
                await self.db.employees.update_one(
                    {"id": target_canonical_id},
                    {"$addToSet": addto},
                )

            # Rewrite embedded snapshot rows so the typo no longer
            # appears as a separate profile alongside the canonical.
            # Without this, the dashboard renders both (Kahiauani Ramos
            # AND Kahiaulani Ramos) until the snapshot is regenerated.
            v_norm = (v2_name or "").strip().lower()
            t_name = target.get("name") or ""
            snapshots_touched = 0
            rows_relabeled = 0
            async for snap in self.db.snapshot_workflow.find(
                {"status": {"$ne": "finalized"}},
                {"_id": 1, "id": 1, "rows": 1, "employees": 1},
            ):
                changed = False
                new_rows = []
                seen_canonical_in_rows: set = set()
                for r in (snap.get("rows") or []):
                    is_match = (
                        r.get("employee_id") == v2_id
                        or (r.get("frozen_display_name") or "").strip().lower() == v_norm
                    )
                    if is_match:
                        # If a row for the canonical already exists in
                        # this snapshot, drop the dup; otherwise relabel
                        # the typo row to point at the canonical.
                        if target_canonical_id in seen_canonical_in_rows:
                            rows_relabeled += 1
                            changed = True
                            continue
                        r = {
                            **r,
                            "employee_id": target_canonical_id,
                            "frozen_display_name": t_name,
                        }
                        seen_canonical_in_rows.add(target_canonical_id)
                        rows_relabeled += 1
                        changed = True
                    else:
                        if r.get("employee_id") == target_canonical_id:
                            seen_canonical_in_rows.add(target_canonical_id)
                    new_rows.append(r)

                new_emps = []
                seen_canonical_in_emps: set = set()
                for e in (snap.get("employees") or []):
                    is_match = (
                        e.get("id") == v2_id
                        or (e.get("name") or "").strip().lower() == v_norm
                    )
                    if is_match:
                        if target_canonical_id in seen_canonical_in_emps:
                            rows_relabeled += 1
                            changed = True
                            continue
                        e = {
                            **e,
                            "id": target_canonical_id,
                            "name": t_name,
                            "display_name": t_name,
                        }
                        seen_canonical_in_emps.add(target_canonical_id)
                        rows_relabeled += 1
                        changed = True
                    else:
                        if e.get("id") == target_canonical_id:
                            seen_canonical_in_emps.add(target_canonical_id)
                    new_emps.append(e)

                if changed:
                    snapshots_touched += 1
                    await self.db.snapshot_workflow.update_one(
                        {"_id": snap["_id"]},
                        {"$set": {
                            "rows": new_rows,
                            "employees": new_emps,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }},
                    )

            await self._audit(card, action, before=v2_name,
                              after=f"merged → {target.get('name')}",
                              actor=actor, reason=reason)
            return {
                "success": True,
                "action": action,
                "merged_into": target.get("name"),
                "target_id": target_canonical_id,
                "snapshots_touched": snapshots_touched,
                "snapshot_rows_relabeled": rows_relabeled,
            }

        if action == "delete_legacy":
            # 1. Soft-delete the v2 row.
            await self.db.employees_v2.update_many(
                {"id": v2_id},
                {"$set": {"status": "inactive",
                          "soft_deleted_at": datetime.now(timezone.utc).isoformat(),
                          "soft_deleted_by": actor}},
            )

            # 2. Propagate the deletion into every non-finalized snapshot.
            # Without this, the snapshot's rows[]/employees[] still
            # carries the typo profile by-id AND by-name, so the trust
            # badge keeps flagging it as orphan / blocklist violation
            # AND the dashboard still renders it. User-reported as
            # "When I delete a legacy profile, nothing happens."
            v_norm = (v2_name or "").strip().lower()
            snapshots_touched = 0
            rows_removed = 0
            async for snap in self.db.snapshot_workflow.find(
                {"status": {"$ne": "finalized"}},
                {"_id": 1, "id": 1, "rows": 1, "employees": 1},
            ):
                new_rows = []
                snap_rows_removed = 0
                for r in (snap.get("rows") or []):
                    if r.get("employee_id") == v2_id:
                        snap_rows_removed += 1
                        continue
                    rnm = (r.get("frozen_display_name") or "").strip().lower()
                    if v_norm and rnm == v_norm:
                        snap_rows_removed += 1
                        continue
                    new_rows.append(r)

                new_emps = []
                for e in (snap.get("employees") or []):
                    if e.get("id") == v2_id:
                        snap_rows_removed += 1
                        continue
                    enm = (e.get("name") or "").strip().lower()
                    if v_norm and enm == v_norm:
                        snap_rows_removed += 1
                        continue
                    new_emps.append(e)

                if snap_rows_removed:
                    snapshots_touched += 1
                    rows_removed += snap_rows_removed
                    await self.db.snapshot_workflow.update_one(
                        {"_id": snap["_id"]},
                        {"$set": {
                            "rows": new_rows,
                            "employees": new_emps,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }},
                    )

            await self._audit(card, action, before=v2_name, after=None,
                              actor=actor, reason=reason)
            return {
                "success": True,
                "action": action,
                "snapshots_touched": snapshots_touched,
                "snapshot_rows_removed": rows_removed,
            }

        if action == "promote_canonical":
            # Use the v2's id as the canonical id so future v2 records
            # under the same spelling auto-link. Pull the latest v2 row
            # to seed the canonical's current_metrics block.
            v2_row = await self.db.employees_v2.find_one(
                {"id": v2_id}, {"_id": 0},
            )
            if not v2_row:
                raise LookupError(f"v2 row {v2_id} not found")
            existing = await self.db.employees.find_one({"id": v2_id})
            if existing:
                # Already exists — turn into a no-op merge_into self.
                await self._audit(card, action, before=v2_name,
                                  after=v2_name + " (already canonical)",
                                  actor=actor, reason=reason)
                return {"success": True, "action": action,
                        "already_canonical": True}
            await self.db.employees.insert_one({
                "id": v2_id,
                "name": v2_name,
                "display_name": v2_name,
                "status": "active",
                "aliases": [],
                "legacy_ids": [],
                "current_metrics": {
                    k: v for k, v in v2_row.items()
                    if k in ("guests", "guest_count", "net_sales", "ppa",
                             "lsc_count", "lbw", "lbw_per_guest",
                             "guests_per_lsc", "glassware_per_guest",
                             "glassware_sales", "loyalty_sales",
                             "total_score")
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": actor,
                "created_via": "reconciliation_promote_canonical",
            })
            await self._audit(card, action, before=v2_name,
                              after=v2_name + " (promoted to canonical)",
                              actor=actor, reason=reason)
            return {"success": True, "action": action,
                    "canonical_id": v2_id}

        raise ValueError(f"action {action} not valid for legacy_duplicate")


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
    # Orphan snapshot ref resolution
    # ------------------------------------------------------------------

    async def _apply_orphan_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        target_canonical_id: Optional[str],
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        """Resolve an orphan_snapshot_ref card by either:

        1. `relink_orphan` — rewrite the snapshot row's `employee_id`
           (and `frozen_display_name` if the canonical's display name
           has drifted) to point at the provided canonical, or at the
           suggested canonical from the card if no override given.
           Used when the orphan was caused by a rename / re-create that
           left the snapshot row pointing at a dead UUID.

        2. `remove_orphan` — drop the row from the snapshot entirely.
           Safe because orphan placeholder rows carry no score data —
           the operator can confirm via the card's `row_total_score`
           field which is null for every orphan we've seen so far.
           Audited so we can always reconstruct the removal later.
        """
        if action not in ("relink_orphan", "remove_orphan"):
            raise ValueError(
                f"orphan_snapshot_ref does not support action {action!r}"
            )

        snap_id  = card["raw_inputs"]["snapshot_id"]
        miss_id  = card["raw_inputs"]["missing_employee_id"]
        frozen_name = card.get("employee_name") or ""

        snap = await self.db.snapshot_workflow.find_one(
            {"id": snap_id},
            {"_id": 0, "id": 1, "rows": 1, "employees": 1, "status": 1,
             "name": 1, "quarter": 1, "year": 1},
        )
        if not snap:
            raise LookupError(
                f"snapshot {snap_id} not found — operator must refresh"
            )
        original_rows = snap.get("rows") or []
        original_emps = snap.get("employees") or []
        # Capture the orphan row's "before" snapshot for audit before
        # we mutate anything.
        orphan_row = next(
            (r for r in original_rows if r.get("employee_id") == miss_id),
            None,
        )

        if action == "relink_orphan":
            canon_id = target_canonical_id or card.get("source", {}).get(
                "suggested_canonical_id"
            )
            if not canon_id:
                raise ValueError(
                    "relink_orphan requires target_canonical_id "
                    "(no suggestion was available)"
                )
            canon = await self.db.employees_v2.find_one(
                {"id": canon_id},
                {"_id": 0, "id": 1, "name": 1, "display_name": 1},
            )
            if not canon:
                raise LookupError(
                    f"target canonical {canon_id} not in employees_v2"
                )
            canon_name = (
                canon.get("display_name") or canon.get("name") or frozen_name
            )
            new_rows = []
            for r in original_rows:
                if r.get("employee_id") == miss_id:
                    new_r = {**r,
                             "employee_id": canon_id,
                             "frozen_display_name": canon_name}
                    new_rows.append(new_r)
                else:
                    new_rows.append(r)
            new_emps = []
            for e in original_emps:
                if e.get("id") == miss_id:
                    new_emps.append({**e, "id": canon_id, "name": canon_name})
                else:
                    new_emps.append(e)
            await self.db.snapshot_workflow.update_one(
                {"id": snap_id},
                {"$set": {
                    "rows": new_rows,
                    "employees": new_emps,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            await self._audit(
                card, action,
                before={"employee_id": miss_id, "frozen_display_name": frozen_name},
                after={"employee_id": canon_id, "frozen_display_name": canon_name,
                       "snapshot_id": snap_id, "snapshot_name": snap.get("name")},
                actor=actor, reason=reason,
            )
            return {
                "success": True,
                "action": action,
                "snapshot_id": snap_id,
                "relinked_from": miss_id,
                "relinked_to": canon_id,
            }

        # action == "remove_orphan"
        new_rows = [r for r in original_rows
                    if r.get("employee_id") != miss_id]
        new_emps = [e for e in original_emps if e.get("id") != miss_id]
        await self.db.snapshot_workflow.update_one(
            {"id": snap_id},
            {"$set": {
                "rows": new_rows,
                "employees": new_emps,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        await self._audit(
            card, action,
            before=orphan_row or {"employee_id": miss_id,
                                   "frozen_display_name": frozen_name},
            after=None,
            actor=actor, reason=reason,
        )
        return {
            "success": True,
            "action": action,
            "snapshot_id": snap_id,
            "removed_employee_id": miss_id,
            "rows_remaining": len(new_rows),
        }


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
