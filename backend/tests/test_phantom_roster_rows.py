"""
Tests for the 2026-02 phantom-row roster coverage feature in
`_hydrate_snapshot_employees`.

Policy: a snapshot's POS upload only contains employees who actually
worked that period. Operator-reported (2026-02): missing employees on
dashboard. Fix: append zero-score "phantom" rows for active canonical
employees who aren't in the snapshot, flagged with
`no_pos_data_this_period=True`.
"""

import asyncio
import os
import uuid

from motor.motor_asyncio import AsyncIOMotorClient


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_phantom_rows_appear_for_active_employees_missing_from_snapshot():
    async def go():
        import sys
        sys.path.insert(0, "/app/backend")
        from snapshot_routes import _hydrate_snapshot_employees

        db = _db()
        # Seed one canonical employee who is active but won't be in
        # the snapshot. Suffix the name to avoid colliding with
        # production data — the predicate matches by both id AND name
        # so a unique suffix is necessary.
        ghost_id = "ghost-" + uuid.uuid4().hex[:8]
        ghost_name = f"PhantomGhost_{ghost_id[-6:]}"
        await db.employees.insert_one({
            "id": ghost_id,
            "name": ghost_name,
            "display_name": ghost_name,
            "status": "active",
            "job_title": "Server",
            "aliases": [],
            "legacy_ids": [],
            "current_metrics": {},
        })

        # Use the live current snapshot — phantom logic must see the
        # ghost is not in `present_canonical_ids` and append a row.
        snap = await db.snapshot_workflow.find_one({"is_current": True})
        if not snap:
            # Fixture environment: skip cleanly.
            await db.employees.delete_one({"id": ghost_id})
            return

        try:
            hyd = await _hydrate_snapshot_employees(db, snap)
            phantom = next(
                (e for e in hyd if e.get("id") == ghost_id),
                None,
            )
            assert phantom is not None, (
                f"phantom row for active employee {ghost_name!r} missing"
            )
            assert phantom.get("no_pos_data_this_period") is True
            assert (phantom.get("final_score") or 0) == 0
            assert (phantom.get("total_score") or 0) == 0
            assert phantom.get("tier_label") in (
                "Trainer", "Bartender", "C-Server"
            )
        finally:
            await db.employees.delete_one({"id": ghost_id})

    _run(go())


def test_phantom_rows_skipped_for_finalized_snapshots():
    """Finalized snapshots must render exactly as frozen — no phantom
    rows allowed or historical PDFs / reviews would silently change."""
    async def go():
        import sys
        sys.path.insert(0, "/app/backend")
        from snapshot_routes import _hydrate_snapshot_employees

        db = _db()
        snap_id = "finalize-test-" + uuid.uuid4().hex[:8]
        await db.snapshot_workflow.insert_one({
            "id": snap_id,
            "name": "FinalizeGate",
            "status": "finalized",
            "is_current": False,
            "quarter": "Q9", "year": 2099,
            "rows": [], "employees": [],
        })
        try:
            snap = await db.snapshot_workflow.find_one({"id": snap_id})
            hyd = await _hydrate_snapshot_employees(db, snap)
            phantoms = [
                e for e in hyd
                if e.get("no_pos_data_this_period")
            ]
            assert phantoms == [], (
                "finalized snapshot must NOT add phantom rows; "
                f"got {len(phantoms)}"
            )
        finally:
            await db.snapshot_workflow.delete_one({"id": snap_id})

    _run(go())
