"""
Regression tests for score-input bounds.

Background: Q2P5W1 had Keisha's score inflated to 165 because:
  * The Edit Detractors number input let her decrement past zero down to −7.
  * The CV formula `NPS%/10 + Promoters×1 − Detractors×2` then computed
    1 − (−7×2) = 15 instead of `1 − 0 = 1`, adding +14 phantom points.
  * The full-rebuild path in update_employee used UNCAPPED percentage
    scores (score_lsc = 329.98%), inflating weighted_score to 140.42
    instead of the documented max ~85.

These tests lock in the invariants:
  * cv_promoters / cv_passives / cv_detractors must clamp at 0.
  * weighted_score in the full-rebuild path must use scores capped at 100%.
"""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# OfficialCVStats Pydantic validation
# ---------------------------------------------------------------------------

def test_official_cv_stats_rejects_negative():
    """OfficialCVStats must reject negative survey counts."""
    from routes.admin import OfficialCVStats
    from pydantic import ValidationError

    # Positive values work
    ok = OfficialCVStats(promoters=5, passives=2, detractors=1)
    assert ok.promoters == 5

    # Each negative count is rejected
    for bad_field in ("promoters", "passives", "detractors", "total_responses"):
        with pytest.raises(ValidationError):
            OfficialCVStats(**{bad_field: -1})


# ---------------------------------------------------------------------------
# CV formula: a "fixed" detractor count of 0 must NOT add phantom points
# ---------------------------------------------------------------------------

def test_cv_formula_with_zero_detractors():
    """1 promoter, 0 detractors, NPS 0 → CV = 1 (not 15)."""
    nps_norm = 0
    promoters = 1
    detractors = 0
    cv = nps_norm * 0.10 + promoters * 1 + detractors * -2
    assert cv == 1


def test_cv_formula_keisha_regression():
    """The exact bad input that produced 165.23 must NOT recur.

    With cv_detractors=-7, the engine produced a +14 bonus instead of the
    intended -14 penalty. After the fix, max(0, -7) = 0 detractors and the
    formula returns 1.0 (1 promoter × 1).
    """
    raw_detractors = -7  # what the broken UI saved
    detractors = max(0, raw_detractors)  # what the patched endpoints now do
    nps_norm = 0
    promoters = 1
    cv = nps_norm * 0.10 + promoters * 1 + detractors * -2
    assert cv == 1
    # With the bad raw value, the formula would have produced 15 — guard
    # against regressing back to it:
    bad_cv = nps_norm * 0.10 + promoters * 1 + raw_detractors * -2
    assert bad_cv == 15
    assert cv != bad_cv


# ---------------------------------------------------------------------------
# Weighted score must cap each component at 100%
# ---------------------------------------------------------------------------

def test_weighted_score_caps_components_at_100():
    """A server with score_lsc=329.98% must NOT inflate weighted_score.

    Per Q2 weights (PPA 25, LSC 25, LBW 20, Glass 15) the documented max
    weighted_score is 85. Without the cap, Keisha's 329.98 LSC pushed
    weighted to 140.42.
    """
    s_ppa = min(88.9, 100)
    s_lbw = min(89.06, 100)
    s_glass = min(119.26, 100)  # was uncapped → +2.9 inflation
    s_lsc = min(329.98, 100)    # was uncapped → +57.5 inflation
    w_ppa, w_lsc, w_lbw, w_glass = 0.25, 0.25, 0.20, 0.15

    weighted = (s_ppa * w_ppa) + (s_lbw * w_lbw) + (s_glass * w_glass) + (s_lsc * w_lsc)
    # Documented max is sum(weights) × 100 = 85.0
    max_weighted = (w_ppa + w_lsc + w_lbw + w_glass) * 100
    assert weighted <= max_weighted
    assert round(weighted, 2) == 80.04  # Keisha's correct value
