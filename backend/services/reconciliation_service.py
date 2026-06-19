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


def canonical_metrics_drift_conflict_id(employee_id: str,
                                        quarter: str,
                                        year: int) -> str:
    """Conflict id for canonical-vs-v2 scoring metric drift for a single
    employee in the active quarter. Deterministic so silenced cards
    stay silenced across reloads and the SHA1 hash check can decide
    when to resurface."""
    h = hashlib.sha1(
        f"canon_drift:{employee_id}:{quarter}:{year}".encode()
    ).hexdigest()
    return f"canon_drift_{h[:16]}"


def alias_cross_assignment_conflict_id(alias: str) -> str:
    """Conflict id for an alias claimed by ≥2 canonical employees. One
    card per alias string (normalised, lower-cased) so the operator
    sees every claimant at once and revokes from the wrong owner(s)."""
    h = hashlib.sha1(
        f"alias_cross:{(alias or '').strip().lower()}".encode()
    ).hexdigest()
    return f"alias_cross_{h[:16]}"


def duplicate_snapshot_rows_conflict_id(snapshot_id: str,
                                        employee_id: str) -> str:
    """Conflict id for a snapshot whose `rows[]` array contains the
    same `employee_id` multiple times. One card per
    (snapshot, employee) tuple — distinct from `orphan_snapshot_ref`
    which is the unmatched-FK case."""
    h = hashlib.sha1(
        f"dup_rows:{snapshot_id}:{employee_id}".encode()
    ).hexdigest()
    return f"dup_rows_{h[:16]}"


def canonical_name_collision_conflict_id(name_norm: str) -> str:
    """Conflict id for ≥2 active canonical employees sharing the same
    (lower-cased, stripped) name. Distinct from `alias_cross_assignment`
    — there both canonicals carry the SAME alias; here they have the
    same canonical name itself."""
    h = hashlib.sha1(
        f"canon_name_dup:{(name_norm or '').strip().lower()}".encode()
    ).hexdigest()
    return f"canon_name_dup_{h[:16]}"


# ---------------------------------------------------------------------------
# Tolerances — must match `/scoring-trust` so the two views never disagree.
# ---------------------------------------------------------------------------
METRIC_TOLERANCE = 0.02   # 2 % — drift threshold for FLAGGING a conflict
METRIC_MIN_ABS   = 0.05   # 5 ¢

# Guest-count drift is integer-noisy at low counts (rounding inside POS
# exports, lost half-shifts) so we flag only when the absolute gap
# crosses this threshold. Per agreed rules.
METRICS_DRIFT_GUEST_ABS = 10

# Scoring-metric fields the canonical "mirrors" from employees_v2 and
# that `sync_canonical_from_v2` is allowed to overwrite. CV / NPS / RT
# are deliberately excluded — they enter the canonical from separate
# pipelines and must not be touched by a drift sync.
CANONICAL_SCORING_FIELDS = (
    "guests",
    "total_score",
    "ppa",
    "lbw",
    "glassware_sales",
    "lsc_count",
)

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
            # Credible-candidate filter. Pure Levenshtein on two short
            # multi-token names is too noisy — "lindsey gonzales" vs
            # "lennie nguyen" lands at distance ~10 by accident and the
            # old `score = overlap*10 + max(0, 20-d)` formula would clear
            # the threshold purely on that bonus, producing a totally
            # bogus merge suggestion. Require either:
            #   - at least one shared full token (last name typically),
            #     which is how real typos look ("kahiauani ramos" shares
            #     "ramos" with "kahiaulani ramos"), OR
            #   - a tight whole-string Levenshtein (≤ 4) which catches
            #     genuine misspellings of a single-token name (e.g.
            #     "treyana" → "treyanna").
            if overlap == 0 and d > 4:
                continue
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
                # Snapshot rows in the current schema bury the score
                # inside `frozen_metrics`/`frozen_score`. Older rows
                # used the flat `total_score` field. Read BOTH so the
                # card honestly reflects whether the row carries data
                # — historically we only read `total_score` and the
                # UI mis-labeled real rows as "safe to remove".
                row_score = (
                    row.get("frozen_score")
                    or row.get("total_score")
                    or (row.get("frozen_metrics") or {}).get("total_score")
                    or (row.get("frozen_metrics") or {}).get("pre_dar_score")
                )
                row_ppa_val = (
                    row.get("ppa")
                    or (row.get("frozen_metrics") or {}).get("ppa")
                )
                row_guests_val = (
                    row.get("guests") or row.get("guest_count")
                    or (row.get("frozen_metrics") or {}).get("guests")
                    or (row.get("frozen_metrics") or {}).get("guest_count")
                )
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
                        # Honestly surface what the row actually
                        # contains. The auto-resolver uses the same
                        # source-of-truth (`frozen_score`) so the UI
                        # claim matches what the sweeper sees.
                        "row_total_score": row_score,
                        "row_ppa":         row_ppa_val,
                        "row_guests":      row_guests_val,
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


    @staticmethod
    def _canonical_metrics_hash(
        canonical_metrics: Optional[Dict[str, Any]],
    ) -> str:
        """SHA1 of the subset of canonical scoring metrics that the
        `canonical_metrics_drift` card watches. Used by
        `keep_canonical_drift` to silence the card until the canonical
        side changes again — re-surfacing only on genuinely new drift,
        not on the same numbers the operator just acknowledged."""
        cm = canonical_metrics or {}
        # Normalise to floats (or None) and a stable key order so
        # re-running on identical data yields the same digest.
        normalised: List[str] = []
        for f in CANONICAL_SCORING_FIELDS:
            v = cm.get(f)
            # Treat `guests`/`guest_count` as the same logical input.
            if f == "guests" and v is None:
                v = cm.get("guest_count")
            if v is None:
                normalised.append(f"{f}=∅")
            else:
                try:
                    normalised.append(f"{f}={float(v):.6f}")
                except (TypeError, ValueError):
                    normalised.append(f"{f}={v!r}")
        payload = "|".join(normalised)
        return hashlib.sha1(payload.encode()).hexdigest()

    async def _build_canonical_metrics_drift_conflicts(
        self,
    ) -> List[Dict[str, Any]]:
        """Surface employees whose canonical `current_metrics` differs
        from their `employees_v2` row for the ACTIVE quarter. This is
        the structural drift the user was hitting (canonical mirror
        falling out of step with the source of truth → wrong dashboard
        numbers, wrong slide trends).

        Detection rules (agreed with user, Message 759):
          * Only the active quarter — derived from
            `snapshot_workflow.find_one({"is_current": True})`.
          * Six scoring fields compared (CANONICAL_SCORING_FIELDS).
          * `guests`: flag when |canonical − v2| ≥ METRICS_DRIFT_GUEST_ABS.
          * All other fields: flag when relative drift > METRIC_TOLERANCE
            AND absolute drift ≥ METRIC_MIN_ABS.
          * One card per employee aggregating every drifted field, so
            the operator decides once: sync everything from v2, or
            silence the whole picture.

        Resolutions:
          * sync_canonical_from_v2 — field-level $set ONLY on scoring
            fields (CV / NPS / RT untouched).
          * keep_canonical_drift — store canonical SHA1 hash so the
            card stays hidden until the canonical changes.
          * defer — standard.
        """
        active_snap = await self.db.snapshot_workflow.find_one(
            {"is_current": True},
            {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1},
        )
        if not active_snap:
            return []
        q, y = active_snap.get("quarter"), active_snap.get("year")
        if not q or y is None:
            return []

        # Index every v2 row for the active quarter by id AND by legacy
        # id-mirror so we can resolve aliases the same way the snapshot
        # hydrator does.
        v2_by_id: Dict[str, Dict[str, Any]] = {}
        async for v2 in self.db.employees_v2.find(
            {"quarter": q, "year": y, "status": {"$ne": "inactive"}},
            {"_id": 0},
        ):
            if v2.get("id"):
                v2_by_id[v2["id"]] = v2

        conflicts: List[Dict[str, Any]] = []
        async for emp in self.db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "current_metrics": 1,
             "legacy_ids": 1},
        ):
            emp_id = emp.get("id")
            if not emp_id:
                continue
            # Locate the v2 row for this canonical: prefer same id,
            # fall back to any legacy_ids[] entry.
            v2 = v2_by_id.get(emp_id)
            if not v2:
                for lid in (emp.get("legacy_ids") or []):
                    if lid in v2_by_id:
                        v2 = v2_by_id[lid]
                        break
            if not v2:
                # No v2 row for this canonical in the active quarter →
                # nothing to drift against. The legacy_duplicate /
                # orphan_snapshot cards cover the other direction.
                continue

            cm = emp.get("current_metrics") or {}
            drifted: List[Dict[str, Any]] = []
            max_rel: float = 0.0

            for field in CANONICAL_SCORING_FIELDS:
                c_val = cm.get(field)
                # `guests` lives under `guest_count` in older canonical
                # records — accept either as the canonical value so
                # we don't false-flag pure legacy bookkeeping.
                if field == "guests" and c_val is None:
                    c_val = cm.get("guest_count")
                v_val = v2.get(field)
                if field == "guests" and v_val is None:
                    v_val = v2.get("guest_count")
                # If both are absent, nothing to compare. If only one
                # is absent the other side is missing data and is a
                # genuine drift the operator wants to see.
                if c_val is None and v_val is None:
                    continue
                if c_val is None or v_val is None:
                    drifted.append({
                        "field": field,
                        "canonical": c_val,
                        "v2": v_val,
                        "abs_diff": None,
                        "rel_pct": 100.0,
                        "reason": "one side null",
                    })
                    max_rel = max(max_rel, 100.0)
                    continue
                try:
                    cf, vf = float(c_val), float(v_val)
                except (TypeError, ValueError):
                    continue
                diff = abs(cf - vf)
                # Guests: absolute threshold rules.
                if field == "guests":
                    if diff < METRICS_DRIFT_GUEST_ABS:
                        continue
                    rel = diff / max(abs(cf), abs(vf), 1.0) * 100.0
                    drifted.append({
                        "field": field,
                        "canonical": cf,
                        "v2": vf,
                        "abs_diff": diff,
                        "rel_pct": round(rel, 2),
                        "reason": (f"guest count gap {int(diff)} ≥ "
                                   f"{METRICS_DRIFT_GUEST_ABS}"),
                    })
                    max_rel = max(max_rel, rel)
                    continue
                # All other fields: noise filter + relative threshold.
                if diff < METRIC_MIN_ABS:
                    continue
                rel = diff / max(abs(cf), abs(vf), 1e-9)
                if rel <= METRIC_TOLERANCE:
                    continue
                rel_pct = rel * 100.0
                drifted.append({
                    "field": field,
                    "canonical": cf,
                    "v2": vf,
                    "abs_diff": round(diff, 4),
                    "rel_pct": round(rel_pct, 2),
                    "reason": "exceeds 2% tolerance",
                })
                max_rel = max(max_rel, rel_pct)

            if not drifted:
                continue

            cid = canonical_metrics_drift_conflict_id(emp_id, q, y)
            # Build before/after dicts limited to the drifted fields.
            stored_dict = {d["field"]: d["canonical"] for d in drifted}
            v2_dict     = {d["field"]: d["v2"] for d in drifted}

            conflicts.append({
                "conflict_id": cid,
                "kind": "canonical_metrics_drift",
                "severity_pct": round(max_rel, 2),
                "employee_id": emp_id,
                "employee_name": emp.get("name"),
                "field": "scoring_metrics",
                "stored_value": stored_dict,
                "snapshot_value": v2_dict,
                "computed_expected": None,
                "raw_inputs": {
                    "drifted_fields": drifted,
                    "v2_id": v2.get("id"),
                    "quarter": q,
                    "year": y,
                    # Hash of the canonical scoring subset captured at
                    # detection time. Stored on `keep_canonical_drift`
                    # so the card stays silenced until canonical moves.
                    "canonical_hash": self._canonical_metrics_hash(cm),
                },
                "source": {
                    "v2_id": v2.get("id"),
                    "quarter": q,
                    "year": y,
                    "snapshot_name": active_snap.get("name"),
                    "reason": (
                        f"canonical.current_metrics drifted from employees_v2 "
                        f"on {len(drifted)} scoring field"
                        f"{'s' if len(drifted) != 1 else ''} "
                        f"in active quarter {q}/{y}"
                    ),
                },
            })
        return conflicts

    async def _build_alias_cross_assignment_conflicts(
        self,
    ) -> List[Dict[str, Any]]:
        """Flag any alias string that is claimed by ≥2 active canonical
        employees. Each such alias is a routing-collision bug: POS
        uploads under that spelling race the canonical lookup, so
        attribution becomes non-deterministic.

        Resolutions:
          * revoke_alias_from {target_canonical_id} — `$pull` the
            alias from only that one canonical record so a single
            owner remains. The operator picks who keeps it (e.g.
            "Kahi" stays with Kahiaulani, gets revoked from anyone
            else who accidentally claimed it).
          * keep_stored — silence; stamps a hash of the claimant id
            list so the card stays hidden unless a NEW claimant
            appears.
          * defer — standard.
        """
        rows = await self.db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "aliases": 1},
        ).to_list(5000)

        # alias_norm -> list of (canonical_id, canonical_name, original_alias)
        claim_map: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            cid = r.get("id")
            if not cid:
                continue
            for a in (r.get("aliases") or []):
                norm = (a or "").strip().lower()
                if not norm:
                    continue
                claim_map.setdefault(norm, []).append({
                    "canonical_id":   cid,
                    "canonical_name": r.get("name"),
                    "alias":          a,
                })

        conflicts: List[Dict[str, Any]] = []
        for norm, claimants in claim_map.items():
            # Distinct canonical ids only — the same canonical listing
            # the alias twice (would be a separate de-dup bug) is not
            # cross-assignment.
            distinct_ids = {c["canonical_id"] for c in claimants}
            if len(distinct_ids) < 2:
                continue
            cid = alias_cross_assignment_conflict_id(norm)
            # Hash of the sorted claimant ids — silence stays valid
            # until the set of claimants changes.
            claim_hash = hashlib.sha1(
                ("|".join(sorted(distinct_ids))).encode()
            ).hexdigest()
            # Use the first claimant's exact-case alias for display.
            display_alias = claimants[0]["alias"]
            primary = claimants[0]  # so cards always have a default actor
            conflicts.append({
                "conflict_id": cid,
                "kind": "alias_cross_assignment",
                # Severity scales with the number of colliding owners —
                # 2 owners = 100% (already a routing bug); >2 stays at
                # 100 so multi-collisions surface at the top alongside.
                "severity_pct": 100.0,
                # employee_id/name = first claimant so existing UI code
                # that reads card.employee_name still renders something
                # meaningful at the top of the card.
                "employee_id": primary["canonical_id"],
                "employee_name": primary["canonical_name"],
                "field": "aliases",
                "stored_value": display_alias,
                "snapshot_value": None,
                "computed_expected": None,
                "raw_inputs": {
                    "alias": display_alias,
                    "alias_normalised": norm,
                    "claimants": [
                        {"canonical_id": c["canonical_id"],
                         "canonical_name": c["canonical_name"]}
                        for c in claimants
                    ],
                    "claim_hash": claim_hash,
                },
                "source": {
                    "reason": (
                        f"alias '{display_alias}' is claimed by "
                        f"{len(distinct_ids)} canonical employees — "
                        f"POS uploads under this spelling will route "
                        f"non-deterministically until exactly one owner "
                        f"remains."
                    ),
                    "claimants": [c["canonical_name"] for c in claimants],
                },
            })
        return conflicts


    async def _build_duplicate_snapshot_rows_conflicts(
        self,
    ) -> List[Dict[str, Any]]:
        """Surface snapshots whose `rows[]` array contains the same
        canonical identity multiple times.

        Detection: build an `employee_id → resolved canonical_id` map
        that follows BOTH `legacy_ids[]` and `merged_into`. Two rows
        whose raw employee_ids map to the same canonical are duplicates
        from the report's perspective even if the ids look different —
        which is exactly what happens after a canonical merge, when old
        legacy ids remain in the snapshot.

        Resolutions:
          * dedupe_snapshot_rows — keep the first occurrence per
            resolved canonical, remove the rest from `rows[]`. Guests/
            sales are NOT summed (avoid inflation).
          * keep_stored — leave the duplicates in place (silence).
        """
        # Build employee_id → resolved canonical_id mapping. Includes:
        #  - every canonical's own id
        #  - every entry in their legacy_ids[]
        #  - merged canonicals → follow merged_into to the keeper
        id_to_canon: Dict[str, str] = {}
        async for c in self.db.employees.find(
            {},
            {"_id": 0, "id": 1, "status": 1, "legacy_ids": 1,
             "merged_into": 1},
        ):
            cid = c.get("id")
            if not cid:
                continue
            target = c.get("merged_into") or cid
            id_to_canon[cid] = target
            for lid in (c.get("legacy_ids") or []):
                if lid:
                    id_to_canon[lid] = target

        conflicts: List[Dict[str, Any]] = []
        async for snap in self.db.snapshot_workflow.find(
            {"is_current": True},
            {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1, "rows": 1},
        ):
            rows = snap.get("rows") or []
            if not rows:
                continue
            # Group row indices by RESOLVED canonical (fall back to raw
            # employee_id when no canonical match — that case is handled
            # by `orphan_snapshot_ref`, but exact-id dupes still surface).
            by_canon: Dict[str, List[int]] = {}
            for idx, r in enumerate(rows):
                eid = r.get("employee_id")
                if not eid:
                    continue
                resolved = id_to_canon.get(eid, eid)
                by_canon.setdefault(resolved, []).append(idx)
            for resolved_id, idxs in by_canon.items():
                if len(idxs) < 2:
                    continue
                first = rows[idxs[0]]
                display = (first.get("frozen_display_name")
                           or first.get("frozen_report_name")
                           or resolved_id)
                # Collect distinct raw employee_ids that resolved to
                # this canonical — the card explains "rows pointing at
                # ids X and Y both resolve to the same person."
                underlying_ids = sorted({
                    rows[i].get("employee_id") for i in idxs
                    if rows[i].get("employee_id")
                })
                cid = duplicate_snapshot_rows_conflict_id(snap["id"], resolved_id)
                multi_id_note = (
                    f" via {len(underlying_ids)} different employee_ids "
                    f"that all resolve to the same canonical"
                    if len(underlying_ids) > 1 else ""
                )
                conflicts.append({
                    "conflict_id": cid,
                    "kind": "duplicate_snapshot_rows",
                    "severity_pct": 100.0,
                    "employee_id": resolved_id,
                    "employee_name": display,
                    "field": "snapshot.rows[]",
                    "stored_value": f"{len(idxs)} copies",
                    "snapshot_value": "1 copy",
                    "computed_expected": None,
                    "raw_inputs": {
                        "snapshot_id":   snap["id"],
                        "snapshot_name": snap.get("name"),
                        "quarter":       snap.get("quarter"),
                        "year":          snap.get("year"),
                        "duplicate_indices": idxs,
                        "duplicate_count":   len(idxs),
                        "resolved_canonical_id": resolved_id,
                        "underlying_employee_ids": underlying_ids,
                    },
                    "source": {
                        "reason": (
                            f"'{display}' appears {len(idxs)} times in the "
                            f"active snapshot's rows[]" + multi_id_note +
                            ". Every report that reads from the snapshot "
                            f"will show duplicate entries until deduped."
                        ),
                        "snapshot_id":   snap["id"],
                        "snapshot_name": snap.get("name"),
                        "quarter":       snap.get("quarter"),
                        "year":          snap.get("year"),
                    },
                })
        return conflicts

    async def _build_canonical_name_collision_conflicts(
        self,
    ) -> List[Dict[str, Any]]:
        """Flag any case where ≥2 active canonical employees share the
        same (lower-cased, stripped) name. These are duplicate identities
        that should be merged via the existing `merge_into` flow.

        Operator-reported (2026-06-12): "Kahi Ramos" and
        "Kahiaulani Ramos" both exist as active canonicals even though
        Kahi is the nickname for Kahiaulani (and the user said so a few
        sessions ago). No recon card surfaced this because neither
        carried the other's name as an alias.

        Resolutions:
          * merge_canonical_into {target_canonical_id} — pick the
            "keeper" canonical; the other one is set status=merged,
            its aliases[] and legacy_ids[] are appended to the keeper,
            and the keeper's name is left untouched. The recon-portal
            `merge_into` flow already exists for the legacy_duplicate
            case; this card type reuses the action verb but acts on the
            employee record itself rather than a v2 row.
          * keep_stored — silence; stamps a hash of the canonical-id set
            so the card stays hidden until a NEW canonical with the same
            name appears.

        NOTE on near-matches: we only flag EXACT name matches here, not
        fuzzy ones. Fuzzy matches (e.g. "Kahi Ramos" vs "Kahiaulani
        Ramos") are intentionally NOT auto-detected — the operator's
        domain knowledge (nicknames) is required and the merge would be
        wrong for unrelated people who share a last name. The Kahi case
        will get fully resolved when the operator merges one into the
        other via the audit ledger's manual flow.
        """
        rows = await self.db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "display_name": 1,
             "aliases": 1},
        ).to_list(5000)

        # Group canonicals by lower-stripped name.
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            n = (r.get("name") or "").strip().lower()
            if not n:
                continue
            by_name.setdefault(n, []).append(r)

        # ALSO surface "nickname-of" matches: two canonicals share the
        # same last name AND one first-name is a prefix of the other
        # (Kahi ⊂ Kahiaulani, Mike ⊂ Michael, Sam ⊂ Samantha). Limited
        # to prefix matches with len ≥ 3 so we don't false-flag random
        # initials.
        # Group by (last_name, first_name) so we can find prefix pairs.
        def _split(n):
            parts = n.strip().split()
            if not parts:
                return "", ""
            return parts[0], " ".join(parts[1:])
        by_last: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            n = (r.get("name") or "").strip().lower()
            if not n or " " not in n:
                continue
            first, last = _split(n)
            if not last:
                continue
            by_last.setdefault(last, []).append({**r, "_first": first, "_last": last})

        # Build groups for prefix collisions. Group key = (last_name,
        # min-first-name) so all canonicals where first_name starts with
        # the same root are clustered.
        prefix_groups: Dict[str, List[Dict[str, Any]]] = {}
        for last, peers in by_last.items():
            if len(peers) < 2:
                continue
            # Compare every pair within the same last name.
            seen: Dict[str, List[Dict[str, Any]]] = {}
            for p in peers:
                first = p["_first"]
                if len(first) < 3:
                    continue
                # Find any longer first-name that this one is a prefix of.
                # Group key = shortest first-name in the family.
                root = first
                for q in peers:
                    if q is p:
                        continue
                    other_first = q["_first"]
                    if len(other_first) >= len(first) and other_first.startswith(first):
                        root = first  # we are the shorter
                        break
                    elif len(first) >= len(other_first) and first.startswith(other_first):
                        root = other_first
                        break
                else:
                    continue
                seen.setdefault(f"{last}|{root}", []).append(p)
            for key, group in seen.items():
                if len(group) >= 2:
                    prefix_groups[key] = group

        conflicts: List[Dict[str, Any]] = []
        emitted_keys: set = set()
        # Emit exact-name collisions first.
        for norm, matches in by_name.items():
            if len(matches) < 2:
                continue
            ids = sorted(m["id"] for m in matches)
            cid_hash = hashlib.sha1("|".join(ids).encode()).hexdigest()
            primary = matches[0]
            emitted_keys.add(f"exact:{norm}")
            conflicts.append({
                "conflict_id": canonical_name_collision_conflict_id(norm),
                "kind": "canonical_name_collision",
                "severity_pct": 100.0,
                "employee_id": primary["id"],
                "employee_name": primary.get("name"),
                "field": "name",
                "stored_value": primary.get("name"),
                "snapshot_value": None,
                "computed_expected": None,
                "raw_inputs": {
                    "match_type":      "exact",
                    "name_normalised": norm,
                    "claimants": [
                        {"canonical_id":   m["id"],
                         "canonical_name": m.get("name"),
                         "display_name":   m.get("display_name"),
                         "aliases":        m.get("aliases") or []}
                        for m in matches
                    ],
                    "claim_hash": cid_hash,
                },
                "source": {
                    "reason": (
                        f"{len(matches)} active canonical employees share "
                        f"the exact name '{primary.get('name')}'. Pick a "
                        f"keeper and merge the others into it so reports "
                        f"stop double-counting."
                    ),
                    "claimants": [m.get("name") for m in matches],
                },
            })
        # Then emit nickname-prefix collisions, skipping anything already
        # covered by an exact match.
        for key, group in prefix_groups.items():
            last, root = key.split("|", 1)
            # Skip if any of these canonicals already in an exact group.
            already = False
            for g in group:
                en = (g.get("name") or "").strip().lower()
                if f"exact:{en}" in emitted_keys:
                    already = True
                    break
            if already:
                continue
            ids = sorted(g["id"] for g in group)
            cid_hash = hashlib.sha1(("prefix|" + "|".join(ids)).encode()).hexdigest()
            primary = group[0]
            display_root = f"{root.title()} {last.title()}"
            conflicts.append({
                "conflict_id": canonical_name_collision_conflict_id(
                    f"prefix:{key}",
                ),
                "kind": "canonical_name_collision",
                # Slightly lower severity than exact match — still a
                # merge candidate but operator should review nicknames.
                "severity_pct": 90.0,
                "employee_id": primary["id"],
                "employee_name": primary.get("name"),
                "field": "name",
                "stored_value": display_root,
                "snapshot_value": None,
                "computed_expected": None,
                "raw_inputs": {
                    "match_type":      "nickname_prefix",
                    "name_root":       display_root,
                    "claimants": [
                        {"canonical_id":   g["id"],
                         "canonical_name": g.get("name"),
                         "display_name":   g.get("display_name"),
                         "aliases":        g.get("aliases") or []}
                        for g in group
                    ],
                    "claim_hash": cid_hash,
                },
                "source": {
                    "reason": (
                        f"{len(group)} active canonical employees share the "
                        f"same last name and one first name is a prefix of "
                        f"the other (likely nickname-vs-full-name, e.g. "
                        f"Kahi/Kahiaulani). Verify they're the same person "
                        f"before merging — if they are, pick a keeper."
                    ),
                    "claimants": [g.get("name") for g in group],
                },
            })
        return conflicts


    async def queue(self) -> Dict[str, Any]:
        """Return the active + deferred queue, sorted so the most
        severe drift sits at the top. Resolved conflicts are filtered
        out unless the underlying values have moved beyond tolerance
        since the resolution (i.e. fresh drift)."""
        # Operator policy 2026-02: auto-resolve orphan snapshot rows
        # whose entire score payload is null/zero. They're placeholder
        # husks left behind by renames/merges — manually clicking
        # "Remove" on each one is just noise. Rows that carry ANY
        # actual data still surface as manual cards.
        await self._auto_resolve_zero_impact_orphans()

        metric_c    = await self._build_metric_conflicts()
        alias_c     = await self._build_alias_conflicts()
        legacy_c    = await self._build_legacy_duplicate_conflicts()
        orphan_c    = await self._build_orphan_snapshot_conflicts()
        canon_c     = await self._build_canonical_metrics_drift_conflicts()
        alias_xc    = await self._build_alias_cross_assignment_conflicts()
        dup_rows_c  = await self._build_duplicate_snapshot_rows_conflicts()
        name_dup_c  = await self._build_canonical_name_collision_conflicts()
        all_c       = (metric_c + alias_c + legacy_c + orphan_c
                       + canon_c + alias_xc + dup_rows_c + name_dup_c)

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
                          "relink_orphan", "remove_orphan",
                          "sync_canonical_from_v2", "keep_canonical_drift",
                          "revoke_alias_from",
                          "dedupe_snapshot_rows",
                          "merge_canonical_into"}:
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
        elif card["kind"] == "canonical_metrics_drift":
            result = await self._apply_canonical_metrics_drift_resolution(
                card, action, actor, reason
            )
        elif card["kind"] == "alias_cross_assignment":
            result = await self._apply_alias_cross_assignment_resolution(
                card, action, target_canonical_id, actor, reason
            )
        elif card["kind"] == "duplicate_snapshot_rows":
            result = await self._apply_duplicate_snapshot_rows_resolution(
                card, action, actor, reason
            )
        elif card["kind"] == "canonical_name_collision":
            result = await self._apply_canonical_name_collision_resolution(
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
        elif card["kind"] == "canonical_metrics_drift":
            # After `sync_canonical_from_v2` the card will no longer
            # appear in queue rebuilds (canonical now matches v2 → no
            # drift). For `keep_canonical_drift` we stamp the SHA1 of
            # the canonical scoring subset so the card stays silenced
            # until the canonical side drifts further.
            emp_id = card.get("employee_id")
            current_hash = None
            if emp_id:
                emp = await self.db.employees.find_one(
                    {"id": emp_id},
                    {"_id": 0, "current_metrics": 1},
                ) or {}
                current_hash = self._canonical_metrics_hash(
                    emp.get("current_metrics") or {}
                )
            post_stored = current_hash
            post_expected = None
        elif card["kind"] == "alias_cross_assignment":
            # `revoke_alias_from` shrinks the claimant set — next queue
            # build won't emit the card unless ≥2 still claim it. For
            # `keep_stored` we stamp the claimant-id hash so the card
            # only re-surfaces if a NEW canonical adds the alias.
            post_stored = card.get("raw_inputs", {}).get("claim_hash")
            post_expected = None
        elif card["kind"] == "duplicate_snapshot_rows":
            # After `dedupe_snapshot_rows` the snapshot's rows[] no
            # longer carries the duplicate count → next queue build
            # naturally omits the card. For `keep_stored` we stamp
            # the duplicate count so the card re-surfaces only if a
            # NEW duplicate appears (e.g. snapshot re-saved with even
            # more copies).
            post_stored = card.get("raw_inputs", {}).get("duplicate_count")
            post_expected = None
        elif card["kind"] == "canonical_name_collision":
            # `merge_canonical_into` removes one canonical from the
            # active set → name no longer collides. For `keep_stored`
            # we stamp the claimant-id-set hash so the card stays
            # silenced unless a NEW canonical with the same name appears.
            post_stored = card.get("raw_inputs", {}).get("claim_hash")
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

        if card.get("kind") == "canonical_metrics_drift":
            # Card stays silenced as long as the canonical scoring
            # subset hash matches the hash captured at resolution time.
            # Any new drift on the canonical side changes the hash and
            # re-surfaces the card.
            current_hash = (card.get("raw_inputs") or {}).get("canonical_hash")
            return (resolved.get("post_stored") == current_hash
                    and current_hash is not None)

        if card.get("kind") == "alias_cross_assignment":
            # Stays silenced as long as the claimant set is identical
            # to the one the operator dismissed. A new canonical adding
            # the alias changes the hash and re-surfaces the card.
            current_hash = (card.get("raw_inputs") or {}).get("claim_hash")
            return (resolved.get("post_stored") == current_hash
                    and current_hash is not None)

        if card.get("kind") == "duplicate_snapshot_rows":
            # Stays silenced as long as the duplicate count is the same.
            # If more copies appear later, count changes and the card
            # re-surfaces.
            current_count = (card.get("raw_inputs") or {}).get("duplicate_count")
            return (resolved.get("post_stored") == current_count
                    and current_count is not None)

        if card.get("kind") == "canonical_name_collision":
            current_hash = (card.get("raw_inputs") or {}).get("claim_hash")
            return (resolved.get("post_stored") == current_hash
                    and current_hash is not None)

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

    # Predicate fields that, when ALL falsy on an orphan row, mark the
    # row as "no score impact" and therefore safe to auto-remove.
    # Operator-authorized 2026-02; any future score-relevant field
    # added to a snapshot row MUST be appended here so the auto-sweep
    # doesn't silently drop real data.
    _ORPHAN_ZERO_IMPACT_FIELDS = (
        "total_score", "pre_dar_score", "frozen_score",
        "weighted_score", "ppa", "per_guest_avg",
        "guests", "guest_count",
        "cv_score", "nps_score", "review_tracker_bonus",
        "metric_bonus", "total_metric_bonus",
    )

    @classmethod
    def _orphan_row_has_no_impact(cls, row: Dict[str, Any]) -> bool:
        """True iff every score-bearing field on the row is null or 0.

        Used by the auto-resolver at queue-build time so placeholder
        rows left behind by renames/merges disappear without operator
        intervention. Any non-zero numeric in any of the listed fields
        keeps the row visible as a manual card.

        Looks both at the row's flat fields AND inside its
        `frozen_metrics` blob, because the snapshot schema migrated
        from flat → frozen and orphan placeholders can land in either
        shape depending on when they were created.
        """
        # Flat fields take priority — the auto-sweeper is conservative
        # and bails on the first truthy value it finds.
        for f in cls._ORPHAN_ZERO_IMPACT_FIELDS:
            v = row.get(f)
            if v is None:
                continue
            try:
                if float(v) != 0.0:
                    return False
            except (TypeError, ValueError):
                if v:
                    return False
        # And the same fields nested inside `frozen_metrics` — this is
        # where the live snapshot schema currently puts the real
        # scoring numbers.
        frozen = row.get("frozen_metrics") or {}
        if isinstance(frozen, dict):
            for f in cls._ORPHAN_ZERO_IMPACT_FIELDS:
                v = frozen.get(f)
                if v is None:
                    continue
                try:
                    if float(v) != 0.0:
                        return False
                except (TypeError, ValueError):
                    if v:
                        return False
        return True

    async def _auto_resolve_zero_impact_orphans(self) -> int:
        """Sweep ALL snapshots and remove orphan rows (snapshot rows
        whose `employee_id` doesn't resolve to any canonical via id OR
        `legacy_ids[]`) provided the row carries no score data.

        Returns the number of rows removed. Each removal lands in
        `reconciliation_audit` with action `auto_remove_orphan` so the
        operator can reconstruct what was dropped and when.
        """
        # Build the resolvable-id set EXACTLY as the orphan card
        # builder / Trust gate does, so the predicate stays consistent.
        resolvable_ids: set = set()
        async for e in self.db.employees.find(
            {}, {"_id": 0, "id": 1, "legacy_ids": 1}
        ):
            if e.get("id"):
                resolvable_ids.add(e["id"])
            for lid in (e.get("legacy_ids") or []):
                if lid:
                    resolvable_ids.add(lid)

        removed_total = 0
        async for snap in self.db.snapshot_workflow.find(
            {}, {"_id": 1, "id": 1, "name": 1, "rows": 1, "employees": 1,
                 "quarter": 1, "year": 1, "status": 1, "is_current": 1},
        ):
            rows = snap.get("rows") or []
            emps = snap.get("employees") or []
            if not rows and not emps:
                continue

            removed_ids: List[str] = []
            removed_rows_for_audit: List[Dict[str, Any]] = []
            new_rows: List[Dict[str, Any]] = []
            for row in rows:
                rid = row.get("employee_id")
                if (rid and rid not in resolvable_ids
                        and self._orphan_row_has_no_impact(row)):
                    removed_ids.append(rid)
                    removed_rows_for_audit.append(row)
                    continue
                new_rows.append(row)

            if not removed_ids:
                continue

            # Mirror the removal into snapshot.employees[] (legacy
            # array) so downstream readers don't resurrect the orphan.
            removed_id_set = set(removed_ids)
            new_emps = [e for e in emps if e.get("id") not in removed_id_set]

            await self.db.snapshot_workflow.update_one(
                {"_id": snap["_id"]},
                {"$set": {
                    "rows": new_rows,
                    "employees": new_emps,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )

            for row in removed_rows_for_audit:
                rid = row.get("employee_id")
                synthetic_card = {
                    "conflict_id": orphan_ref_conflict_id(
                        snap.get("id") or "", rid or ""
                    ),
                    "kind": "orphan_snapshot_ref",
                    "employee_id": rid,
                    "employee_name": (
                        row.get("frozen_display_name")
                        or row.get("name") or "(no name)"
                    ),
                    "field": "snapshot_row",
                }
                await self._audit(
                    synthetic_card,
                    "auto_remove_orphan",
                    before=row,
                    after=None,
                    actor="system:auto-resolve",
                    reason=(
                        "row carried no score data "
                        "(per operator policy 2026-02)"
                    ),
                )
            removed_total += len(removed_ids)

        return removed_total

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
    # Canonical metrics drift resolution
    # ------------------------------------------------------------------

    async def _apply_canonical_metrics_drift_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        """Resolve a `canonical_metrics_drift` card. Available actions:

          * sync_canonical_from_v2 — Mirror the employees_v2 row's
            scoring fields onto canonical.current_metrics. Field-level
            `$set` so CV / NPS / RT and other non-scoring keys are
            untouched. The card disappears on next refresh because the
            two sides match.
          * keep_canonical_drift — Silence: stamp the canonical
            scoring subset hash so the card stays hidden until the
            canonical side moves. CV / NPS / RT unaffected.
        """
        if action not in ("sync_canonical_from_v2", "keep_canonical_drift"):
            raise ValueError(
                f"canonical_metrics_drift does not support action {action!r}"
            )

        emp_id = card["employee_id"]
        drifted = (card.get("raw_inputs") or {}).get("drifted_fields") or []

        if action == "keep_canonical_drift":
            # No write — _stamp_resolved records the canonical hash so
            # the card stays silenced until canonical drifts further.
            await self._audit(
                card, action,
                before={d["field"]: d["canonical"] for d in drifted},
                after={d["field"]: d["canonical"] for d in drifted},
                actor=actor, reason=reason,
            )
            return {"success": True, "action": action,
                    "silenced_until_canonical_changes": True}

        # action == "sync_canonical_from_v2"
        # Build a field-level $set targeting ONLY the scoring keys that
        # actually drifted. We deliberately leave every other key in
        # current_metrics intact (CV, NPS, RT, derived ratios) so the
        # sync surgical and predictable.
        set_doc: Dict[str, Any] = {}
        before: Dict[str, Any] = {}
        after:  Dict[str, Any] = {}
        for d in drifted:
            field = d.get("field")
            v_val = d.get("v2")
            if field not in CANONICAL_SCORING_FIELDS:
                continue
            set_doc[f"current_metrics.{field}"] = v_val
            before[field] = d.get("canonical")
            after[field]  = v_val
        if not set_doc:
            raise ValueError(
                "no drifted scoring fields to sync — card may have been "
                "rebuilt against newer data; please refresh the queue"
            )
        set_doc["current_metrics.updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        await self.db.employees.update_one(
            {"id": emp_id},
            {"$set": set_doc},
        )
        await self._audit(
            card, action, before=before, after=after,
            actor=actor, reason=reason,
        )
        return {
            "success": True,
            "action": action,
            "fields_synced": list(after.keys()),
            "values": after,
        }

    # ------------------------------------------------------------------
    # Alias cross-assignment resolution
    # ------------------------------------------------------------------

    async def _apply_alias_cross_assignment_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        target_canonical_id: Optional[str],
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        """Resolve an `alias_cross_assignment` card. Available actions:

          * revoke_alias_from — `$pull` the alias from the canonical
            named by `target_canonical_id` (must be one of the
            claimants). All other claimants keep the alias. This is
            how the operator resolves "Kahi was added to two profiles
            by mistake" — they pick the legitimate owner and strip the
            others one at a time.
          * keep_stored — silence; stamps the claimant-id-set hash so
            the card stays hidden until a NEW canonical adds the alias.
        """
        if action not in ("revoke_alias_from", "keep_stored"):
            raise ValueError(
                f"alias_cross_assignment does not support action {action!r}"
            )

        alias_display = card.get("stored_value") or ""
        alias_norm = (card.get("raw_inputs") or {}).get("alias_normalised") \
            or alias_display.strip().lower()
        claimants = (card.get("raw_inputs") or {}).get("claimants") or []
        claimant_ids = {c.get("canonical_id") for c in claimants}

        if action == "keep_stored":
            await self._audit(
                card, action,
                before=alias_display,
                after=alias_display,
                actor=actor, reason=reason,
            )
            return {"success": True, "action": action,
                    "silenced_until_claimants_change": True}

        # action == "revoke_alias_from"
        if not target_canonical_id:
            raise ValueError(
                "revoke_alias_from requires target_canonical_id — pick "
                "the canonical to strip the alias from."
            )
        if target_canonical_id not in claimant_ids:
            raise ValueError(
                f"target_canonical_id {target_canonical_id} is not in "
                f"the claimant set {sorted(claimant_ids)}"
            )

        # `$pull` is case-sensitive on a string field. To make sure we
        # strip ANY exact variant the canonical might be carrying
        # (mixed-case duplicate of the same alias), we read the array
        # first, compute the case-insensitive matches, then $pullAll.
        target = await self.db.employees.find_one(
            {"id": target_canonical_id},
            {"_id": 0, "aliases": 1, "name": 1},
        ) or {}
        target_aliases = target.get("aliases") or []
        to_pull = [a for a in target_aliases
                   if (a or "").strip().lower() == alias_norm]
        if not to_pull:
            raise ValueError(
                f"canonical {target_canonical_id} no longer carries "
                f"alias '{alias_display}' — refresh the queue"
            )
        await self.db.employees.update_one(
            {"id": target_canonical_id},
            {"$pullAll": {"aliases": to_pull}},
        )
        await self._audit(
            card, action,
            before={"canonical": target.get("name"),
                    "alias": alias_display},
            after={"canonical": target.get("name"),
                   "alias": None,
                   "stripped_variants": to_pull},
            actor=actor, reason=reason,
        )
        return {
            "success": True,
            "action": action,
            "revoked_from": target.get("name"),
            "revoked_from_id": target_canonical_id,
            "stripped_variants": to_pull,
        }


    # ------------------------------------------------------------------
    # Duplicate snapshot rows resolution
    # ------------------------------------------------------------------

    async def _apply_duplicate_snapshot_rows_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        """Resolve a `duplicate_snapshot_rows` card. Available actions:

          * dedupe_snapshot_rows — Rewrite the snapshot's `rows[]`,
            keeping only the FIRST occurrence per `employee_id`. The
            other copies are removed. We do NOT sum guests/sales —
            duplicate rows almost always carry identical numbers, and
            merging would inflate totals.
          * keep_stored — silence; stamps the current duplicate count
            so the card re-surfaces only if MORE copies appear later.
        """
        if action not in ("dedupe_snapshot_rows", "keep_stored"):
            raise ValueError(
                f"duplicate_snapshot_rows does not support action {action!r}"
            )

        raw = card.get("raw_inputs") or {}
        snap_id = raw.get("snapshot_id")
        eid = card.get("employee_id")
        indices = raw.get("duplicate_indices") or []

        if action == "keep_stored":
            await self._audit(
                card, action,
                before={"snapshot_id": snap_id, "duplicate_count": len(indices)},
                after={"snapshot_id": snap_id, "duplicate_count": len(indices)},
                actor=actor, reason=reason,
            )
            return {"success": True, "action": action,
                    "silenced_until_more_duplicates_appear": True}

        # action == "dedupe_snapshot_rows"
        # Re-read the snapshot fresh so we don't race against any
        # concurrent edits. Rebuild rows[] by walking each row and
        # checking the RESOLVED canonical (via the same legacy_ids /
        # merged_into map the builder uses). Keep the first row per
        # resolved canonical for THIS card's target; drop the rest.
        # Other employees' rows are untouched.
        snap = await self.db.snapshot_workflow.find_one(
            {"id": snap_id},
            {"_id": 0, "rows": 1, "id": 1},
        )
        if not snap:
            raise ValueError(f"snapshot {snap_id} no longer exists")
        rows = snap.get("rows") or []

        # Rebuild the id → canonical map.
        id_to_canon: Dict[str, str] = {}
        async for c in self.db.employees.find(
            {},
            {"_id": 0, "id": 1, "legacy_ids": 1, "merged_into": 1},
        ):
            cid_local = c.get("id")
            if not cid_local:
                continue
            target = c.get("merged_into") or cid_local
            id_to_canon[cid_local] = target
            for lid in (c.get("legacy_ids") or []):
                if lid:
                    id_to_canon[lid] = target

        target_canon = card.get("employee_id")
        # Walk rows once. For rows whose resolved canonical matches
        # target_canon, keep only the first occurrence and drop the
        # rest. Untouched for other employees.
        kept_first_for_target: bool = False
        new_rows: List[Dict[str, Any]] = []
        removed = 0
        for r in rows:
            eid = r.get("employee_id")
            resolved = id_to_canon.get(eid, eid) if eid else None
            if resolved == target_canon:
                if not kept_first_for_target:
                    new_rows.append(r)
                    kept_first_for_target = True
                else:
                    removed += 1
                    continue
            else:
                new_rows.append(r)
        if removed == 0:
            raise ValueError(
                "snapshot has no duplicate rows for this employee — "
                "the queue may be stale, please refresh"
            )
        await self.db.snapshot_workflow.update_one(
            {"id": snap_id},
            {"$set": {"rows": new_rows}},
        )
        await self._audit(
            card, action,
            before={"row_count": len(rows), "duplicate_copies": removed + 1},
            after={"row_count": len(new_rows), "duplicate_copies": 1},
            actor=actor, reason=reason,
        )
        return {
            "success": True,
            "action": action,
            "snapshot_id": snap_id,
            "duplicate_copies_removed": removed,
            "rows_before": len(rows),
            "rows_after": len(new_rows),
        }

    # ------------------------------------------------------------------
    # Canonical name collision resolution
    # ------------------------------------------------------------------

    async def _apply_canonical_name_collision_resolution(
        self,
        card: Dict[str, Any],
        action: str,
        target_canonical_id: Optional[str],
        actor: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        """Resolve a `canonical_name_collision` card. Available actions:

          * merge_canonical_into — Pick a KEEPER from the claimant
            list. Every OTHER claimant is set to status=merged, its
            aliases[] and legacy_ids[] are appended to the keeper, and
            its own id is added to the keeper's legacy_ids[] so the
            FK-join still finds the old v2 rows under the keeper.
          * keep_stored — silence; stamps the claimant-id-set hash.
        """
        if action not in ("merge_canonical_into", "keep_stored"):
            raise ValueError(
                f"canonical_name_collision does not support action {action!r}"
            )

        claimants = (card.get("raw_inputs") or {}).get("claimants") or []
        claimant_ids = {c.get("canonical_id") for c in claimants}

        if action == "keep_stored":
            await self._audit(
                card, action,
                before={"name": card.get("stored_value"),
                        "claimants": [c.get("canonical_name") for c in claimants]},
                after={"name": card.get("stored_value"),
                       "claimants": [c.get("canonical_name") for c in claimants]},
                actor=actor, reason=reason,
            )
            return {"success": True, "action": action,
                    "silenced_until_claimants_change": True}

        # action == "merge_canonical_into"
        if not target_canonical_id:
            raise ValueError(
                "merge_canonical_into requires target_canonical_id — pick "
                "the KEEPER from the claimant list. Every other claimant "
                "will be merged into this one."
            )
        if target_canonical_id not in claimant_ids:
            raise ValueError(
                f"target_canonical_id {target_canonical_id} is not in "
                f"the claimant set {sorted(claimant_ids)}"
            )

        keeper = await self.db.employees.find_one(
            {"id": target_canonical_id},
            {"_id": 0},
        )
        if not keeper:
            raise ValueError(f"keeper {target_canonical_id} not found")

        merged_ids: List[str] = []
        new_aliases = list(keeper.get("aliases") or [])
        new_legacy = list(keeper.get("legacy_ids") or [])

        for c in claimants:
            cid = c.get("canonical_id")
            if cid == target_canonical_id:
                continue
            other = await self.db.employees.find_one(
                {"id": cid}, {"_id": 0},
            )
            if not other:
                continue
            # Fold their aliases (deduped, case-insensitive).
            existing_lower = {a.strip().lower() for a in new_aliases}
            for a in (other.get("aliases") or []):
                if (a or "").strip().lower() not in existing_lower:
                    new_aliases.append(a)
                    existing_lower.add(a.strip().lower())
            # Pull in their old name as an alias if it's different from
            # the keeper's (operator-friendly: nicknames preserved).
            on = (other.get("name") or "").strip()
            kn = (keeper.get("name") or "").strip()
            if on and on.lower() != kn.lower() and on.lower() not in existing_lower:
                new_aliases.append(on)
                existing_lower.add(on.lower())
            # Fold legacy_ids[] (including their own id so the FK-join
            # still resolves any v2 rows that lived under the old id).
            for lid in (other.get("legacy_ids") or []):
                if lid and lid not in new_legacy:
                    new_legacy.append(lid)
            if cid and cid not in new_legacy:
                new_legacy.append(cid)
            # Mark the other canonical merged.
            await self.db.employees.update_one(
                {"id": cid},
                {"$set": {
                    "status": "merged",
                    "merged_into": target_canonical_id,
                    "merged_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            merged_ids.append(cid)

        # Write the new aliases/legacy_ids onto the keeper.
        await self.db.employees.update_one(
            {"id": target_canonical_id},
            {"$set": {"aliases": new_aliases, "legacy_ids": new_legacy}},
        )

        await self._audit(
            card, action,
            before={"keeper": keeper.get("name"),
                    "merged_in": [c.get("canonical_name") for c in claimants
                                  if c.get("canonical_id") != target_canonical_id]},
            after={"keeper": keeper.get("name"),
                   "aliases": new_aliases,
                   "legacy_ids_added": merged_ids},
            actor=actor, reason=reason,
        )
        return {
            "success": True,
            "action": action,
            "keeper_id": target_canonical_id,
            "keeper_name": keeper.get("name"),
            "merged_canonical_ids": merged_ids,
            "merged_canonical_count": len(merged_ids),
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
