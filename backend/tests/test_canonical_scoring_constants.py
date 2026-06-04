"""
Lock-down test for the canonical scoring spec the user confirmed:
  • Weights: PPA 25%, LSC 25%, LBW 20%, GLASS 15% (total = 85%)
  • Metric Bonus: 0.25 pts per 1% above benchmark, cap 5 pts/metric
  • Review Tracker: 0.33 pts per mention, cap 20 pts

Any code change that drifts away from these constants — whether in the
default QuarterSettings, hardcoded inline math, or the module-level
constants — should fail this test.

Why this exists
---------------
Prior to 2026-05-14 we had three sites with stale 0.15/0.10 weights for
LBW/GLASS (server.py x2 and routes/audit.py x1) and many sites still
using 0.3 pts/mention for RT. This test prevents that drift from
silently reappearing.
"""

from scoring_engine import (
    QuarterSettings,
    RT_POINTS_PER_MENTION,
    RT_MAX_POINTS,
)


def test_canonical_weights():
    s = QuarterSettings(quarter="Q2", year=2026)
    assert s.weight_ppa == 0.25
    assert s.weight_lsc == 0.25
    assert s.weight_lbw == 0.20
    assert s.weight_glass == 0.15
    # Sum should be 85% (the remaining 15% comes from CV bonuses + RT)
    total = s.weight_ppa + s.weight_lsc + s.weight_lbw + s.weight_glass
    assert round(total, 2) == 0.85


def test_canonical_metric_bonus_rate_and_cap():
    s = QuarterSettings(quarter="Q2", year=2026)
    assert s.bonus_rate == 0.25     # 0.25 pts per 1% above benchmark
    assert s.bonus_cap == 5.0       # max 5 pts/metric


def test_canonical_review_tracker_rate_and_cap():
    s = QuarterSettings(quarter="Q2", year=2026)
    assert s.rt_points_per_mention == 0.33
    assert s.rt_max_points == 20.0
    # Module-level fallbacks must agree
    assert RT_POINTS_PER_MENTION == 0.33
    assert RT_MAX_POINTS == 20
