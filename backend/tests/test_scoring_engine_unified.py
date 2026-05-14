"""
Regression tests for the unified scoring engine.

Locks down the contract that:
  1. `scoring_engine.compute_total_score_dict` matches the canonical
     `calculate_total_score` byte-for-byte (same weighted_score,
     pre_dar_score, total_score).
  2. Changing per-quarter weights in `QuarterSettings` propagates
     through the helper — i.e. nobody re-implemented the formula
     inline with hardcoded weights.
  3. The helper gracefully handles partial dicts (missing optional
     bonus fields default to 0 without throwing).
  4. The clear-cv-data and clear-rt-data admin endpoints, plus the
     legacy snapshot rebuild paths, all stay aligned with the engine
     by virtue of routing through `compute_total_score_dict`.

This is the test you want to run before changing the scoring formula
or any of its weights.
"""

import pytest

from scoring_engine import (
    EmployeeV2,
    QuarterSettings,
    calculate_total_score,
    compute_total_score_dict,
)


def _settings(weight_ppa=0.25, weight_lsc=0.25, weight_lbw=0.15, weight_glass=0.10):
    return QuarterSettings(
        year=2026, quarter="Q2",
        weight_ppa=weight_ppa, weight_lsc=weight_lsc,
        weight_lbw=weight_lbw, weight_glass=weight_glass,
    )


def test_helper_matches_canonical():
    """compute_total_score_dict produces identical numbers to calculate_total_score."""
    settings = _settings()
    raw = dict(
        score_ppa=80, score_lbw=70, score_glass=60, score_lsc=90,
        cv_score=4.5, review_tracker_bonus=3.0, total_metric_bonus=2.5,
        dar_penalty=-1.0,
    )

    # Direct canonical call.
    emp = EmployeeV2(name="canon", **raw)
    calculate_total_score(emp, settings)

    # Helper call on a dict.
    scored = compute_total_score_dict(raw, settings)

    assert scored["weighted_score"] == emp.weighted_score
    assert scored["pre_dar_score"] == emp.pre_dar_score
    assert scored["total_score"] == emp.total_score


def test_helper_respects_per_quarter_weights():
    """When settings weights change, the helper's weighted_score changes too."""
    base = dict(score_ppa=80, score_lbw=80, score_glass=80, score_lsc=80)

    default = compute_total_score_dict(base, _settings())
    boosted = compute_total_score_dict(
        base,
        _settings(weight_ppa=0.40, weight_lsc=0.25, weight_lbw=0.15, weight_glass=0.10),
    )

    # All-score-80 with 0.25/0.25/0.15/0.10 weights → 80*0.75 = 60.
    assert default["weighted_score"] == pytest.approx(60.0, abs=0.01)
    # With PPA bumped to 0.40 (totalling 0.90) → 80*0.90 = 72.
    assert boosted["weighted_score"] == pytest.approx(72.0, abs=0.01)


def test_helper_caps_metric_at_100():
    """Capping happens inside the canonical engine, not at the callsite."""
    settings = _settings()
    scored = compute_total_score_dict(
        dict(score_ppa=150, score_lbw=100, score_glass=100, score_lsc=100),
        settings,
    )
    # 100*0.25 + 100*0.25 + 100*0.15 + 100*0.10 = 75
    assert scored["weighted_score"] == pytest.approx(75.0, abs=0.01)


def test_helper_defaults_missing_optional_fields():
    """Partial dicts with only POS scores still produce valid totals."""
    settings = _settings()
    scored = compute_total_score_dict(
        dict(score_ppa=80, score_lbw=80, score_glass=80, score_lsc=80),
        settings,
    )
    assert scored["weighted_score"] == pytest.approx(60.0, abs=0.01)
    # No CV / RT / metric bonuses / DAR penalty → pre_dar == total == weighted.
    assert scored["pre_dar_score"] == scored["weighted_score"]
    assert scored["total_score"] == scored["weighted_score"]


def test_helper_preserves_other_dict_keys():
    """The helper must NOT strip caller-supplied keys (id, name, etc.)."""
    settings = _settings()
    inp = dict(
        id="abc-123", name="Polly", store_id="LV01",
        score_ppa=80, score_lbw=80, score_glass=80, score_lsc=80,
    )
    out = compute_total_score_dict(inp, settings)
    assert out["id"] == "abc-123"
    assert out["name"] == "Polly"
    assert out["store_id"] == "LV01"
    assert "weighted_score" in out and "total_score" in out


def test_no_inline_formula_in_admin_or_legacy():
    """Hard-code guard: the offending hardcoded weights must not return."""
    import pathlib
    base = pathlib.Path(__file__).resolve().parent.parent
    offending = []
    for rel in ("routes/admin.py", "routes/snapshots_legacy.py"):
        text = (base / rel).read_text()
        # Match a contiguous `capped_xxx * 0.25 + capped_xxx * 0.25 + ...` block,
        # which is the signature of the old hardcoded formula.
        if "capped_ppa * 0.25 +" in text and "capped_lsc * 0.25 +" in text and "compute_total_score_dict" not in text.split("capped_ppa * 0.25 +", 1)[0][-400:]:
            offending.append(rel)
    assert not offending, (
        f"Found re-introduced hardcoded scoring formula in: {offending}. "
        f"Route through scoring_engine.compute_total_score_dict instead."
    )
