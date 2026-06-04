"""
Regression test for the "Process Snapshot — silent 500" bug.

Symptom (prod, 2026-05-14):
- User clicks "Save & Process Snapshot" on Data Uploads
- Frontend logs an `API ERROR 500` and an unhandled promise rejection

Root cause:
- `merge_snapshot_data` called `.lower().strip()` on the result of
  `emp.get("display_name", "")`. `dict.get(k, default)` only returns
  the default when `k` is missing — if it's present with `None`
  (common in legacy `employees_v2` rows), `.lower()` raises.

Fix:
- Coerce with `(emp.get(k) or "")` so `None` becomes `""` first.

This test reproduces the crash and asserts the merge now succeeds.
"""

import asyncio

from snapshot_routes import merge_snapshot_data


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_merge_snapshot_data_tolerates_none_display_name():
    """A row with `display_name: None` (legacy v2 shape) must not crash."""
    snapshot = {
        "id": "test-snap",
        "status": "in_progress",
        "quarter": "Q1",
        "year": 2026,
        "uploads": [],
        "employees": [
            {
                "id": "emp-1",
                "name": "Robert Mckinnon",
                "display_name": None,    # previously crashed `.lower()`
                "report_name": None,
            },
            {
                "id": "emp-2",
                "name": "Trey Quick",
                "display_name": "Trey",
                "report_name": "Quick, Trey",
            },
        ],
    }

    result = _run(merge_snapshot_data(snapshot))
    assert isinstance(result, list)


def test_merge_snapshot_data_tolerates_missing_keys():
    """Rows missing display_name/report_name entirely must also pass."""
    snapshot = {
        "id": "test-snap-2",
        "status": "in_progress",
        "quarter": "Q1",
        "year": 2026,
        "uploads": [],
        "employees": [
            {"id": "x", "name": "Solo Field"},
        ],
    }
    result = _run(merge_snapshot_data(snapshot))
    assert isinstance(result, list)


if __name__ == "__main__":
    test_merge_snapshot_data_tolerates_none_display_name()
    test_merge_snapshot_data_tolerates_missing_keys()
    print("OK")
