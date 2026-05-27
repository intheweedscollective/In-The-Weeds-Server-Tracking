"""
Regression test for the per-guest backfill in
`snapshot_manager.calculate_employee_scores`.

The edit path pre-derives `lbw_per_guest`, `glassware_per_guest`, and
`guests_per_lsc`. The upload path does not. Without backfill, an
upload-path employee would land with score_lbw / score_glass / score_lsc
all zero — and would silently rank dead last with the same raw sales
that produced a top score via the edit path. This test locks the fix.
"""

import sys
sys.path.insert(0, "/app/backend")

from snapshot_manager import calculate_employee_scores  # noqa: E402


BENCHMARKS = {
    "ppa": 55.0, "lbw": 8.0, "glass": 1.35, "lsc": 100.0,
    "weight_ppa": 0.25, "weight_lsc": 0.25,
    "weight_lbw": 0.20, "weight_glass": 0.15,
}


def test_backfills_lbw_from_component_sales():
    """liquor + beer + wine should backfill lbw_per_guest if missing."""
    emp = {
        "name": "Upload Path Probe",
        "ppa": 60, "guest_count": 100,
        "liquor_sales": 400, "beer_sales": 250, "wine_sales": 200,
        # lbw_per_guest deliberately missing
    }
    out = calculate_employee_scores(emp, BENCHMARKS)
    # (400+250+200)/100 = 8.50 → 106.25% of 8.0 benchmark
    assert emp["lbw_per_guest"] == 8.50, f"got {emp['lbw_per_guest']}"
    assert out["score_lbw"] > 100, "LBW score should clear 100% — backfill failed"


def test_backfills_glassware_from_either_sales_field():
    """Both bar_glassware_sales and glassware_sales should work as sources."""
    a = {"name": "A", "ppa": 60, "guest_count": 100, "bar_glassware_sales": 150}
    calculate_employee_scores(a, BENCHMARKS)
    assert a["glassware_per_guest"] == 1.50

    b = {"name": "B", "ppa": 60, "guest_count": 100, "glassware_sales": 200}
    calculate_employee_scores(b, BENCHMARKS)
    assert b["glassware_per_guest"] == 2.00


def test_backfills_guests_per_lsc_from_lsc_count():
    """lsc_count should backfill guests_per_lsc (inverse ratio)."""
    emp = {"name": "C", "ppa": 60, "guest_count": 1000, "lsc_count": 12}
    calculate_employee_scores(emp, BENCHMARKS)
    # 1000 guests / 12 signups = 83.33 — better than 100 benchmark
    assert abs(emp["guests_per_lsc"] - 83.33) < 0.01


def test_does_not_override_edit_path_values():
    """If the edit path already set the per-guest metric, the backfill must NOT touch it."""
    emp = {
        "name": "Edit Path Probe",
        "ppa": 60, "guest_count": 100,
        # Edit path already set these — backfill must preserve.
        "lbw_per_guest": 7.20,
        "glassware_per_guest": 1.10,
        "guests_per_lsc": 95.0,
        # Raw sales also present (would override if guard is broken)
        "liquor_sales": 9999, "beer_sales": 9999, "wine_sales": 9999,
        "bar_glassware_sales": 9999,
        "lsc_count": 9999,
    }
    calculate_employee_scores(emp, BENCHMARKS)
    assert emp["lbw_per_guest"] == 7.20, "backfill clobbered edit-path lbw"
    assert emp["glassware_per_guest"] == 1.10, "backfill clobbered edit-path glass"
    assert emp["guests_per_lsc"] == 95.0, "backfill clobbered edit-path lsc"


def test_zero_guests_skips_backfill_safely():
    """guest_count=0 must not divide-by-zero. Per-guest stays falsy."""
    emp = {
        "name": "No Shifts",
        "ppa": 0, "guest_count": 0,
        "liquor_sales": 100, "beer_sales": 50, "wine_sales": 25,
    }
    out = calculate_employee_scores(emp, BENCHMARKS)
    assert not emp.get("lbw_per_guest")
    assert out["score_lbw"] == 0


if __name__ == "__main__":
    test_backfills_lbw_from_component_sales()
    test_backfills_glassware_from_either_sales_field()
    test_backfills_guests_per_lsc_from_lsc_count()
    test_does_not_override_edit_path_values()
    test_zero_guests_skips_backfill_safely()
    print("All per-guest backfill tests PASSED")
