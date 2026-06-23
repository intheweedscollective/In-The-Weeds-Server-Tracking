"""
Tests for the 2026-02 auto-resolve of zero-impact orphan snapshot rows.

Policy: when the reconciliation queue is requested, any snapshot row
whose `employee_id` doesn't resolve to a canonical employee AND whose
score payload is entirely null/0 is silently removed and audited. Rows
with any non-zero score data still surface as manual cards.

Covers:
1. Zero-impact orphan row (all score fields null/0) is auto-removed.
2. Orphan row with a real `total_score` is NOT auto-removed and still
   shows up in the manual queue.
3. Auto-removal lands in `reconciliation_audit` with the synthetic
   conflict_id matching what the card builder would emit.
4. The sweep also strips the orphan from `snapshot.employees[]`.
"""

import asyncio
import os
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

from services.reconciliation_service import (
    ReconciliationService,
    orphan_ref_conflict_id,
)


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    # Each test gets a fresh loop; matches the pattern used in
    # `test_phase3_stage_a.py` (Py3.11 raises if MainThread has none).
    return asyncio.new_event_loop().run_until_complete(coro)


def test_zero_impact_orphan_is_auto_removed():
    async def go():
        db = _db()
        snap_id = "auto-orphan-test-" + uuid.uuid4().hex[:8]
        dead_id = "dead-" + uuid.uuid4().hex[:8]
        keeper_id = "keeper-" + uuid.uuid4().hex[:6]

        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"AutoOrphanTest-{snap_id[:6]}",
            "status": "in_progress",
            "is_current": False,
            "quarter": "Q9", "year": 2099,
            "rows": [
                # Zero-impact orphan: every score field absent or zero.
                {"employee_id": dead_id, "frozen_display_name": "Ghost A",
                 "total_score": 0, "ppa": 0, "guests": 0},
                # Orphan w/ real score — must NOT be auto-removed.
                {"employee_id": keeper_id,
                 "frozen_display_name": "Real Row",
                 "total_score": 87.4, "ppa": 12.0, "guests": 200},
            ],
            "employees": [
                {"id": dead_id, "name": "Ghost A", "total_score": 0},
            ],
        })
        try:
            svc = ReconciliationService(db)
            removed = await svc._auto_resolve_zero_impact_orphans()
            assert removed >= 1

            snap = await db.snapshot_workflow.find_one({"id": snap_id})
            assert snap is not None
            ids = [r.get("employee_id") for r in (snap.get("rows") or [])]
            assert dead_id not in ids, (
                f"zero-impact orphan should be auto-removed; rows={ids}"
            )
            # The orphan with real data must still be present.
            assert keeper_id in ids, (
                "orphan with real score must be preserved for manual review"
            )
            emp_ids = [e.get("id") for e in (snap.get("employees") or [])]
            assert dead_id not in emp_ids, (
                "orphan removal must also strip the legacy employees[] entry"
            )
            # Audit trail must capture the auto-removal.
            audit = await db.reconciliation_audit.find_one({
                "conflict_id": orphan_ref_conflict_id(snap_id, dead_id),
                "action": "auto_remove_orphan",
            })
            assert audit is not None, "auto-removal must be audited"
            assert audit["actor"] == "system:auto-resolve"
            assert audit["before"]["employee_id"] == dead_id
            assert audit["after"] is None
        finally:
            await db.snapshot_workflow.delete_one({"id": snap_id})
            await db.reconciliation_audit.delete_many({
                "conflict_id": orphan_ref_conflict_id(snap_id, dead_id),
            })

    _run(go())


def test_queue_triggers_auto_resolve():
    """`queue()` must invoke the sweep, so a zero-impact orphan never
    appears in the queue's `active` list."""
    async def go():
        db = _db()
        snap_id = "auto-orphan-queue-" + uuid.uuid4().hex[:8]
        dead_id = "queue-dead-" + uuid.uuid4().hex[:8]
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": f"QueueOrphan-{snap_id[:6]}",
            "status": "in_progress",
            "is_current": False,
            "quarter": "Q9", "year": 2099,
            "rows": [
                {"employee_id": dead_id, "frozen_display_name": "Quiet Ghost",
                 "total_score": None, "ppa": None, "guests": None},
            ],
            "employees": [],
        })
        try:
            svc = ReconciliationService(db)
            q = await svc.queue()
            cid = orphan_ref_conflict_id(snap_id, dead_id)
            active_ids = {c.get("conflict_id") for c in q.get("active", [])}
            assert cid not in active_ids, (
                "zero-impact orphan must be swept before the queue is built"
            )
        finally:
            await db.snapshot_workflow.delete_one({"id": snap_id})
            await db.reconciliation_audit.delete_many({
                "conflict_id": orphan_ref_conflict_id(snap_id, dead_id),
            })

    _run(go())


def test_predicate_rejects_any_nonzero_field():
    """The static predicate is the safety net — any non-zero
    score-bearing field must keep the row visible for manual review."""
    P = ReconciliationService._orphan_row_has_no_impact
    # All-null / all-zero → safe to auto-remove.
    assert P({}) is True
    assert P({"total_score": 0, "ppa": 0, "guests": 0}) is True
    assert P({"total_score": None, "frozen_score": None}) is True
    # Any non-zero score-bearing field → NOT safe.
    assert P({"total_score": 0.1}) is False
    assert P({"frozen_score": 70.0}) is False
    assert P({"ppa": 12.0}) is False
    assert P({"guests": 1}) is False
    assert P({"cv_score": -1.0}) is False
    assert P({"metric_bonus": 5.0}) is False
    # Non-zero data buried in `frozen_metrics` must also block.
    assert P({"frozen_metrics": {"total_score": 89.94}}) is False
    assert P({"frozen_metrics": {"ppa": 12.0}}) is False
    # Empty `frozen_metrics` is fine.
    assert P({"frozen_metrics": {}}) is True
    assert P({"frozen_metrics": {"total_score": 0, "ppa": 0}}) is True
