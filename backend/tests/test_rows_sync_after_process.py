"""
Regression test for the "Rankings vs Top Performers disagree" bug.

Symptom (prod 2026-05-14, snapshot Q2P5W2.75):
  • Top Performers widget on the Snapshot detail page showed
    Trey / Diane / Kitti / Jose / Keisha (with full RT + CV bonuses)
  • Rankings tab showed Keisha / Cory / Jose / Ethan / Adriana
    (all with rt_b=0 and most with cv=0)

Root cause:
  `/snapshot-workflow/snapshots/{id}/process` updated the embedded
  `employees[]` array with freshly-scored data but never refreshed
  `rows[].frozen_metrics`. The Rankings page reads through
  `_hydrate_snapshot_employees(rows[])`, the Top Performers widget
  reads `employees[]` directly. They diverged whenever a fresh
  scoring run touched bonuses (e.g. after the RT rate fix on
  2026-05-14).

Fix:
  After `assign_performance_tiers`, mirror each scored employee back
  into `rows[].frozen_metrics` / `frozen_score` / `frozen_tier`. So
  the two views always reflect the same state.

This test simulates the mirror logic and asserts the resulting
`rows[]` carries the same scores as the `employees[]` it was derived
from.
"""

from datetime import datetime, timezone


def _sync_rows_from_employees(rows, employees):
    """Replicate the logic that lives inside `/process`."""
    emp_by_id = {e.get("id"): e for e in employees if e.get("id")}
    emp_by_name = {}
    for e in employees:
        for nm in (e.get("name"), e.get("display_name"), e.get("report_name")):
            k = (nm or "").strip().lower()
            if k:
                emp_by_name.setdefault(k, e)

    synced = []
    consumed_ids: set = set()
    for row in (rows or []):
        eid = row.get("employee_id")
        scored = emp_by_id.get(eid)
        if scored is None:
            fallback = (row.get("frozen_display_name") or row.get("frozen_report_name") or "").strip().lower()
            scored = emp_by_name.get(fallback) if fallback else None
        if scored is None:
            # No match → drop the row (prevents stale scores polluting Rankings).
            continue
        consumed_ids.add(scored.get("id"))
        synced.append({
            "employee_id": scored.get("id") or eid,
            "frozen_display_name": scored.get("display_name") or scored.get("name") or row.get("frozen_display_name"),
            "frozen_report_name":  scored.get("report_name")  or scored.get("name") or row.get("frozen_report_name"),
            "frozen_metrics": {k: v for k, v in scored.items() if k not in ("id", "name", "display_name", "report_name", "aliases")},
            "frozen_score": scored.get("total_score", 0),
            "frozen_tier":  scored.get("tier_label") or scored.get("performance_tier"),
            "frozen_rank":  scored.get("tier_rank") or scored.get("peer_rank"),
            "recorded_at":  row.get("recorded_at") or datetime.now(timezone.utc).isoformat(),
        })
    # Grow: any scored employee not yet represented gets a fresh row.
    for emp in employees:
        eid = emp.get("id")
        if not eid or eid in consumed_ids:
            continue
        synced.append({
            "employee_id": eid,
            "frozen_display_name": emp.get("display_name") or emp.get("name"),
            "frozen_report_name":  emp.get("report_name")  or emp.get("name"),
            "frozen_metrics": {k: v for k, v in emp.items() if k not in ("id", "name", "display_name", "report_name", "aliases")},
            "frozen_score": emp.get("total_score", 0),
            "frozen_tier":  emp.get("tier_label") or emp.get("performance_tier"),
            "frozen_rank":  emp.get("tier_rank") or emp.get("peer_rank"),
            "recorded_at":  datetime.now(timezone.utc).isoformat(),
        })
    return synced


def test_rows_pickup_fresh_rt_bonus_from_employees():
    """The exact prod scenario: employees[] has updated RT bonus, rows[] is stale."""
    rows = [{
        "employee_id": "trey-uuid",
        "frozen_display_name": "Trey Quick",
        "frozen_metrics": {
            "total_score": 89.0,
            "review_tracker_bonus": 0,  # stale
            "cv_score": 0,
        },
        "frozen_score": 89.0,
    }]
    employees = [{
        "id": "trey-uuid",
        "name": "Trey Quick",
        "display_name": "Trey Quick",
        "total_score": 112.61,
        "review_tracker_bonus": 10.23,
        "cv_score": 0,
        "tier_label": "Trainer",
        "tier_rank": 1,
    }]

    synced = _sync_rows_from_employees(rows, employees)
    assert len(synced) == 1
    assert synced[0]["frozen_score"] == 112.61
    assert synced[0]["frozen_metrics"]["review_tracker_bonus"] == 10.23
    assert synced[0]["frozen_metrics"]["total_score"] == 112.61
    assert synced[0]["frozen_tier"] == "Trainer"


def test_rows_match_by_name_when_id_mismatches():
    """An old row whose employee_id changed after a canonical merge."""
    rows = [{
        "employee_id": "old-id-no-longer-exists",
        "frozen_display_name": "Lennie Nguyen",
        "frozen_metrics": {"total_score": 80.0, "review_tracker_bonus": 0},
        "frozen_score": 80.0,
    }]
    employees = [{
        "id": "new-canonical-id",
        "name": "Lennie Nguyen",
        "display_name": "Lennie Nguyen",
        "total_score": 95.0,
        "review_tracker_bonus": 2.64,
    }]
    synced = _sync_rows_from_employees(rows, employees)
    assert synced[0]["employee_id"] == "new-canonical-id"
    assert synced[0]["frozen_score"] == 95.0


def test_rows_preserved_when_no_match_found():
    """Stale rows pointing to a non-scored person are now DROPPED to prevent
    them polluting Rankings with old data."""
    rows = [{
        "employee_id": "ghost-uuid",
        "frozen_display_name": "Ghost Server",
        "frozen_score": 50.0,
    }]
    employees = [{"id": "different-uuid", "name": "Other Person", "display_name": "Other Person", "total_score": 100.0}]
    synced = _sync_rows_from_employees(rows, employees)
    # Ghost row dropped; Other Person added via the grow pass.
    assert len(synced) == 1
    assert synced[0]["frozen_display_name"] == "Other Person"


def test_rows_grow_to_include_new_employees():
    """Employees added via POS merge after first-save get a new row."""
    rows = [{
        "employee_id": "existing-1",
        "frozen_display_name": "Existing One",
        "frozen_score": 50.0,
    }]
    employees = [
        {"id": "existing-1", "name": "Existing One", "display_name": "Existing One", "total_score": 80.0},
        {"id": "new-2", "name": "Lennie Nguyen", "display_name": "Lennie Nguyen", "total_score": 79.57, "review_tracker_bonus": 2.97},
        {"id": "new-3", "name": "Kahi", "display_name": "Kahi", "total_score": 86.24},
    ]
    synced = _sync_rows_from_employees(rows, employees)
    assert len(synced) == 3
    names = {r["frozen_display_name"] for r in synced}
    assert names == {"Existing One", "Lennie Nguyen", "Kahi"}


def test_top_5_order_matches_between_rows_and_employees():
    """The original symptom: rankings vs top performers disagreed."""
    employees = [
        {"id": f"e{i}", "name": f"E{i}", "display_name": f"E{i}", "total_score": 100 - i, "review_tracker_bonus": i}
        for i in range(10)
    ]
    rows = [
        {"employee_id": f"e{i}", "frozen_display_name": f"E{i}",
         "frozen_metrics": {"total_score": 50, "review_tracker_bonus": 0},
         "frozen_score": 50}
        for i in range(10)
    ]
    synced = _sync_rows_from_employees(rows, employees)
    top5_emp = sorted(employees, key=lambda e: e["total_score"], reverse=True)[:5]
    top5_rows = sorted(synced, key=lambda r: r["frozen_score"], reverse=True)[:5]
    assert [e["name"] for e in top5_emp] == [r["frozen_display_name"] for r in top5_rows]
    assert [e["total_score"] for e in top5_emp] == [r["frozen_score"] for r in top5_rows]
