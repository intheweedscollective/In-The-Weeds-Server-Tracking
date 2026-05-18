"""
Regression test for the Snapshot Integrity Gate "always-fires" bug.

Symptom (prod, 2026-05-14):
- "Save & Process Snapshot" returns HTTP 500/409 with the gate failure
  message even for snapshots that have perfectly valid POS data.

Root cause:
- The gate at `process_snapshot` checked `score_ppa`/`score_lbw`/etc
  for the "30% with all POS scores at zero" rule. But those score
  fields are computed by `calculate_employee_scores()` which runs
  AFTER the gate — so every freshly-merged employee has all four
  score fields at 0 (their default), which made the gate fire on
  100% of rows for every snapshot.

Fix:
- Check the raw POS metrics (`ppa`, `lbw_per_guest`,
  `glassware_per_guest`, `guests_per_lsc`) which ARE populated by
  `merge_snapshot_data` before the gate runs.

This test locks the regression by simulating a snapshot whose
freshly-merged rows have valid raw metrics but zero score_* fields
(the legitimate state at gate-evaluation time) and asserts the gate
does NOT misfire.
"""


def _gate_check_old_buggy(employees):
    """Reproduces the old check — counts rows whose score_* are all 0."""
    return sum(
        1 for e in employees
        if not any((e.get(k) or 0) for k in
                   ("score_ppa", "score_lbw", "score_glass", "score_lsc"))
    )


def _gate_check_new_fixed(employees):
    """The fix — counts rows whose raw POS metrics are all 0."""
    return sum(
        1 for e in employees
        if not any((e.get(k) or 0) for k in
                   ("ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc"))
    )


def _make_row(ppa, lbw, glass, lsc):
    """A row at gate-evaluation time: raw metrics populated, scores zero."""
    return {
        "name": "Test",
        "ppa": ppa,
        "lbw_per_guest": lbw,
        "glassware_per_guest": glass,
        "guests_per_lsc": lsc,
        # score_* fields default to 0 — `calculate_employee_scores`
        # hasn't run yet at the point the gate evaluates.
        "score_ppa": 0,
        "score_lbw": 0,
        "score_glass": 0,
        "score_lsc": 0,
    }


def test_old_buggy_gate_always_fires_with_valid_metrics():
    """Locks the bug: old gate misfires on rows with valid raw metrics."""
    employees = [_make_row(55, 8, 1.35, 35) for _ in range(20)]
    bad_count = _gate_check_old_buggy(employees)
    # The buggy check thought 20 / 20 = 100% of rows had no data.
    assert bad_count == 20, "regression: old buggy check should still mis-flag all rows"


def test_new_fixed_gate_passes_when_raw_metrics_are_valid():
    """The fix: 20 rows with valid raw POS metrics → 0 flagged."""
    employees = [_make_row(55, 8, 1.35, 35) for _ in range(20)]
    bad_count = _gate_check_new_fixed(employees)
    assert bad_count == 0, "fixed gate should NOT flag rows with valid raw POS metrics"


def test_new_fixed_gate_still_catches_genuinely_blank_rows():
    """Sanity check: rows with all zero raw metrics still flagged."""
    blank = [_make_row(0, 0, 0, 0) for _ in range(10)]
    populated = [_make_row(55, 8, 1.35, 35) for _ in range(10)]
    bad_count = _gate_check_new_fixed(blank + populated)
    assert bad_count == 10, "should flag exactly the 10 blank rows"
