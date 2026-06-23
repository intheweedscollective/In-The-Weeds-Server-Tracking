"""
Regression: `_suggest_canonical` was producing nonsense merge
suggestions for unrelated names because the Levenshtein-only bonus
could clear the score threshold on its own.

User reported (production, 2026-02-05): "Lindsey Gonzales" v2 row
suggested merge into "Lennie Nguyen" canonical — they share no
tokens, just happen to be ~10 edits apart, and the old scoring
formula `overlap*10 + max(0, 20-d)` gave them a score of exactly
10 (cleared the threshold of 10 purely on the distance bonus).

These tests pin the credibility filter: a suggestion is only
returned when the v2 name and the canonical name share at least
one full token OR the whole-string distance is ≤ 4 (true typo).
"""

from services.reconciliation_service import ReconciliationService


def _canon_dict(items):
    """Helper: build the canon_by_id mapping `_suggest_canonical`
    expects."""
    return {c["id"]: c for c in items}


# ---------------------------------------------------------------------------
# Bogus matches must NOT be surfaced
# ---------------------------------------------------------------------------


def test_unrelated_names_no_token_overlap_returns_none():
    """Lindsey Gonzales vs Lennie Nguyen — no shared word, distance
    too large to be a typo. Old code returned the latter as a merge
    target; the filter must now return None."""
    canon = _canon_dict([
        {"id": "c1", "name": "Lennie Nguyen"},
        {"id": "c2", "name": "Joe Bishop"},
        {"id": "c3", "name": "Allen Simmons"},
    ])
    suggestion = ReconciliationService._suggest_canonical(
        "Lindsey Gonzales", canon,
    )
    assert suggestion is None, (
        f"Unrelated name should produce no suggestion, got "
        f"{suggestion and suggestion.get('name')}"
    )


def test_matthew_spath_vs_trey_quick_returns_none():
    """Another real-world bogus pair from the production report.
    'Matthew Spath' and 'Trey Quick' share no tokens and are well
    above 4 edits apart — must not suggest."""
    canon = _canon_dict([
        {"id": "c1", "name": "Trey Quick"},
        {"id": "c2", "name": "Bryan Lee"},
    ])
    suggestion = ReconciliationService._suggest_canonical(
        "Matthew Spath", canon,
    )
    assert suggestion is None


# ---------------------------------------------------------------------------
# Genuine typos must still be surfaced
# ---------------------------------------------------------------------------


def test_shared_last_name_still_suggested():
    """'Kahiauani Ramos' (typo) → 'Kahiaulani Ramos' (canonical):
    they share 'ramos', which is the dominant cue for legacy-typo
    merges. Must still resolve."""
    canon = _canon_dict([
        {"id": "c1", "name": "Kahiaulani Ramos"},
        {"id": "c2", "name": "Lennie Nguyen"},
    ])
    suggestion = ReconciliationService._suggest_canonical(
        "Kahiauani Ramos", canon,
    )
    assert suggestion and suggestion["id"] == "c1"


def test_tight_distance_single_token_still_suggested():
    """A single-token spelling typo within 4 edits of a canonical's
    name should still be picked up even without token overlap."""
    canon = _canon_dict([
        {"id": "c1", "name": "Treyanna"},
        {"id": "c2", "name": "Allen Simmons"},
    ])
    suggestion = ReconciliationService._suggest_canonical(
        "Treyana", canon,   # 1-edit typo
    )
    assert suggestion and suggestion["id"] == "c1"


def test_completely_different_short_name_returns_none():
    """A genuinely new staff member with a unique name must not be
    force-matched into an unrelated canonical just because the
    queue contains a few short names."""
    canon = _canon_dict([
        {"id": "c1", "name": "Jay"},
        {"id": "c2", "name": "Bo"},
    ])
    suggestion = ReconciliationService._suggest_canonical(
        "Chase Winston", canon,
    )
    assert suggestion is None
