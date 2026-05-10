"""
Regression test: confirm_pos_review must ADD manually-entered new employees
to the snapshot, not silently drop them.

Bug reported by user: "I manually added two employees and they are not
appearing after a confirmed save."

Root cause was in snapshot_routes.confirm_pos_review:
    for new_emp in employees_data:
        existing = emp_lookup.get(name)
        if existing:
            # update fields...
        # NO ELSE BRANCH — new employees fell off

Fix: when no existing match is found, build a fresh row with the supplied
POS fields, run an initial score pass, and append it to existing_employees.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_confirm_pos_review_adds_new_manual_employee(monkeypatch):
    """A new name in employees_data must end up in snapshot.employees."""
    from snapshot_routes import confirm_pos_review

    # Fake snapshot doc: has Alice already, NO Bob (bob is the manual add).
    snapshot_doc = {
        "id": "snap-1",
        "quarter": "Q2",
        "year": 2026,
        "deleted_names": [],
        "uploads": [
            {
                "upload_type": "pos_report",
                "parsed_data": {
                    "employees": [{"name": "Alice Adams", "ppa": 55.0}],
                    "record_count": 1,
                }
            }
        ],
        "employees": [
            {"id": "alice-id", "name": "Alice Adams", "display_name": "Alice",
             "report_name": "Alice Adams", "ppa": 55.0, "guest_count": 100}
        ],
    }

    update_one_calls = []

    class _FakeWorkflow:
        async def find_one(self, *a, **k):
            return snapshot_doc

        async def update_one(self, query, update, **k):
            update_one_calls.append((query, update))
            return MagicMock(matched_count=1)

    class _FakeQuarterSettings:
        async def find_one(self, *a, **k):
            return {
                "benchmark_ppa": 55.0, "benchmark_lbw": 8.0,
                "benchmark_glass": 1.35, "benchmark_lsc": 100.0,
                "weight_ppa": 0.25, "weight_lbw": 0.20,
                "weight_glass": 0.15, "weight_lsc": 0.25,
                "weight_cv": 0.15, "bonus_rate": 0.2, "bonus_cap": 5.0,
            }

    class _FakeEmployeesV2:
        async def update_one(self, *a, **k):
            return MagicMock(matched_count=1, upserted_id=None)

    class _FakeDB:
        snapshot_workflow = _FakeWorkflow()
        quarter_settings = _FakeQuarterSettings()
        employees_v2 = _FakeEmployeesV2()

    monkeypatch.setattr("snapshot_routes.get_db", lambda: _FakeDB())

    # New payload: includes Alice (existing) and Bob (NEW manual add)
    payload = {
        "employees": [
            {"name": "Alice Adams", "ppa": 60.0, "guest_count": 110},
            {
                "name": "Bob Smith",
                "display_name": "Bob",
                "report_name": "Bob Smith",
                "ppa": 50.0,
                "net_sales": 4000,
                "guest_count": 80,
                "liquor_sales": 400,
                "beer_sales": 200,
                "wine_sales": 100,
                "glassware_sales": 100,
                "lsc_count": 8,
                "loyalty_sales": 200,
                "job_title": "Server",
            }
        ]
    }

    result = _run(confirm_pos_review("snap-1", payload))
    assert result["success"] is True

    # We should have at least one update_one to snapshot_workflow.
    assert update_one_calls, "expected at least one snapshot_workflow.update_one"

    # Find the call that wrote the employees array.
    saved_employees = None
    for _q, upd in update_one_calls:
        emps = (upd.get("$set") or {}).get("employees")
        if emps:
            saved_employees = emps
    assert saved_employees is not None, "snapshot_workflow should be saved with employees"

    names = set()
    for e in saved_employees:
        for k in ("name", "display_name", "report_name"):
            v = (e.get(k) or "").lower()
            if v:
                names.add(v)
    assert "alice adams" in names or "alice" in names, "Alice should still be present"
    assert "bob smith" in names or "bob" in names, (
        "Bob was a manual add — confirm_pos_review must persist him "
        "in snapshot.employees, not drop him on the floor."
    )

    bob = next(
        e for e in saved_employees
        if "bob" in (e.get("name") or "").lower()
        or "bob" in (e.get("report_name") or "").lower()
    )
    # Verify the fresh row was given an id and reasonable score-ready fields.
    assert bob.get("id"), "Bob should be assigned a UUID id"
    assert bob.get("ppa") == 50.0
    assert bob.get("guest_count") == 80
    # CV / RT default to zero for a manual add.
    assert bob.get("cv_promoters", 0) == 0
    assert bob.get("rt_mentions", 0) == 0


def test_confirm_pos_review_manual_readd_removes_from_blocklist(monkeypatch):
    """Manually adding a previously-deleted employee should clear them
    from snapshot.deleted_names so they don't get re-skipped later."""
    from snapshot_routes import confirm_pos_review

    snapshot_doc = {
        "id": "snap-2",
        "quarter": "Q2",
        "year": 2026,
        "deleted_names": ["Bob Smith"],  # already on blocklist
        "uploads": [
            {
                "upload_type": "pos_report",
                "parsed_data": {"employees": [], "record_count": 0}
            }
        ],
        "employees": [],
    }

    update_calls = []

    class _FakeWorkflow:
        async def find_one(self, *a, **k):
            return snapshot_doc

        async def update_one(self, query, update, **k):
            update_calls.append(update)
            return MagicMock(matched_count=1)

    class _FakeQS:
        async def find_one(self, *a, **k):
            return None

    class _FakeEmployeesV2:
        async def update_one(self, *a, **k):
            return MagicMock(matched_count=1, upserted_id=None)

    class _FakeDB:
        snapshot_workflow = _FakeWorkflow()
        quarter_settings = _FakeQS()
        employees_v2 = _FakeEmployeesV2()

    monkeypatch.setattr("snapshot_routes.get_db", lambda: _FakeDB())

    payload = {
        "employees": [
            {"name": "Bob Smith", "ppa": 55, "guest_count": 90, "job_title": "Server"}
        ]
    }
    _run(confirm_pos_review("snap-2", payload))

    # Walk update calls to find the deleted_names write
    saved_blocklist = None
    for upd in update_calls:
        if "deleted_names" in (upd.get("$set") or {}):
            saved_blocklist = upd["$set"]["deleted_names"]
    assert saved_blocklist is not None, "confirm_pos_review should always write deleted_names"
    assert "Bob Smith" not in saved_blocklist, (
        "Bob was manually re-added, so he must no longer appear on the deleted blocklist."
    )
