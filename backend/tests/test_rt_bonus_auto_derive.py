"""
Regression test: `calculate_employee_scores` MUST always recompute the
RT bonus from `rt_mentions` × `rt_points_per_mention`, NOT trust any
stale value already on the employee row.

Why this exists
---------------
Production bug on 2026-05-14 (Q2P5W2.75 snapshot):
  • Trey Quick had `rt_mentions=34` but `review_tracker_bonus=0`
  • Kahi had `rt_mentions=3` but `review_tracker_bonus=0.3` (off ratio)

Root cause:
  Prior version of `calculate_employee_scores` read the bonus from the
  row dict instead of deriving it. The bonus was only ever set by the
  RT-upload merge path; rows that were edited or migrated between
  shapes could end up with stale bonus values.

Fix:
  `calculate_employee_scores` now always derives the bonus from
  mentions × benchmark rate (cap-clamped). Single source of truth.
"""

from snapshot_manager import calculate_employee_scores


_BENCHMARKS = {
    "ppa": 55.0, "lbw": 8.0, "glass": 1.35, "lsc": 100.0,
    "weight_ppa": 0.25, "weight_lsc": 0.25, "weight_lbw": 0.20, "weight_glass": 0.15,
    "rt_points_per_mention": 0.33, "rt_max_points": 20.0,
}


def test_rt_bonus_overrides_stale_zero():
    """A row with mentions=34 but bonus=0 must be corrected to 34 × 0.33 = 11.22."""
    emp = {
        "name": "Trey Quick",
        "ppa": 50, "lbw_per_guest": 7, "glassware_per_guest": 1.2, "guests_per_lsc": 100,
        "rt_mentions": 34,
        "review_tracker_bonus": 0,  # stale/wrong
    }
    calculate_employee_scores(emp, _BENCHMARKS)
    assert emp["review_tracker_bonus"] == 11.22, emp["review_tracker_bonus"]


def test_rt_bonus_overrides_wrong_ratio():
    """Kahi: mentions=3 with bonus=0.3 (legacy 0.1 ratio) must become 0.99."""
    emp = {
        "name": "Kahi",
        "ppa": 50, "lbw_per_guest": 7, "glassware_per_guest": 1.2, "guests_per_lsc": 100,
        "rt_mentions": 3,
        "review_tracker_bonus": 0.3,
    }
    calculate_employee_scores(emp, _BENCHMARKS)
    assert emp["review_tracker_bonus"] == 0.99


def test_rt_bonus_respects_cap():
    """Cap at 20 even with very high mentions."""
    emp = {
        "name": "Top Mentioner",
        "ppa": 50, "lbw_per_guest": 7, "glassware_per_guest": 1.2, "guests_per_lsc": 100,
        "rt_mentions": 999,
    }
    calculate_employee_scores(emp, _BENCHMARKS)
    assert emp["review_tracker_bonus"] == 20.0


def test_rt_bonus_zero_when_no_mentions():
    """No mentions → bonus 0."""
    emp = {
        "name": "Quiet Server",
        "ppa": 50, "lbw_per_guest": 7, "glassware_per_guest": 1.2, "guests_per_lsc": 100,
        "rt_mentions": 0,
    }
    calculate_employee_scores(emp, _BENCHMARKS)
    assert emp["review_tracker_bonus"] == 0.0


def test_rt_bonus_falls_back_to_review_mentions_field():
    """Legacy rows used `review_mentions` instead of `rt_mentions`."""
    emp = {
        "name": "Legacy Row",
        "ppa": 50, "lbw_per_guest": 7, "glassware_per_guest": 1.2, "guests_per_lsc": 100,
        "review_mentions": 10,  # legacy field name
    }
    calculate_employee_scores(emp, _BENCHMARKS)
    assert emp["review_tracker_bonus"] == 3.30
