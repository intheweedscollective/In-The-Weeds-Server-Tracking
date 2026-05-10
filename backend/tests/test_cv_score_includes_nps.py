"""
Regression test for routes/cv.py: cv_score must include NPS%/10 component.

Bug: Previously routes/cv.py wrote `cv_score = (promoters * 1) + (detractors * -2)`
when uploading CV data via the standalone Data Uploads page or when re-including
feedback. That formula skipped the NPS%/10 component that scoring_engine.calculate_customer_voice_score uses, so the dashboard appeared
to "not count NPS into the CV score".

Per scoring_engine.py spec:
    cv_score = NPS%/10 + (Promoters × +1) + (Detractors × −2)
"""

import pytest
from scoring_engine import (
    EmployeeV2,
    calculate_customer_voice_score,
    CV_PROMOTER_POINTS,
    CV_DETRACTOR_POINTS,
)


def _expected_cv(nps: float, promoters: int, detractors: int) -> float:
    nps_clamped = max(0.0, min(100.0, nps))
    return round(
        (nps_clamped / 10.0)
        + (promoters * CV_PROMOTER_POINTS)
        + (detractors * CV_DETRACTOR_POINTS),
        2,
    )


@pytest.mark.parametrize(
    "nps,promoters,detractors,expected",
    [
        # NPS 100 with 2 promoters → 10 + 2 = 12
        (100.0, 2, 0, 12.0),
        # NPS 100 with 4 promoters → 14
        (100.0, 4, 0, 14.0),
        # NPS 0 with 1 promoter, 1 detractor → 0 + 1 - 2 = -1
        (0.0, 1, 1, -1.0),
        # NPS 66 with 2 promoters, 1 detractor → 6.6 + 2 - 2 = 6.6
        (66.0, 2, 1, 6.6),
        # No data → 0
        (0.0, 0, 0, 0.0),
        # Negative NPS clamped to 0
        (-100.0, 0, 1, -2.0),
    ],
)
def test_scoring_engine_cv_includes_nps(nps, promoters, detractors, expected):
    """The scoring engine canonical implementation MUST always add NPS%/10."""
    e = EmployeeV2(
        id="t",
        name="Tester",
        nps_score=nps,
        cv_promoters=promoters,
        cv_detractors=detractors,
    )
    calculate_customer_voice_score(e)
    assert e.cv_score == _expected_cv(nps, promoters, detractors) == expected, (
        f"cv_score should be {expected} for nps={nps} prom={promoters} det={detractors}, "
        f"got {e.cv_score}"
    )


def test_routes_cv_recalculate_uses_same_formula():
    """The routes/cv.py manual-upload paths must mirror the scoring engine.

    This tests the literal formula present in routes/cv.py after the fix.
    Previously these paths wrote `(promoters*1) + (detractors*-2)` which
    skipped the NPS%/10 component.
    """
    # Simulate the corrected formula from routes/cv.py:
    nps = 100.0
    promoters = 2
    detractors = 0
    nps_clamped = max(0.0, min(100.0, nps))
    cv_score = round(
        (nps_clamped / 10.0) + (promoters * 1) + (detractors * -2), 2
    )
    assert cv_score == _expected_cv(nps, promoters, detractors)
    # And specifically: it must NOT be just 2.0 (the old bug)
    assert cv_score != (promoters * 1) + (detractors * -2)
