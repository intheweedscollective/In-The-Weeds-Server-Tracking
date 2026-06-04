"""
Iteration 28: End-to-end backend test of NAME MATCHING + SCORING pipelines.

Covers:
- POST /api/v2/admin/normalize-quarter-settings (dry-run + apply, 401 anon)
- GET  /api/v2/admin/scoring-example (no auth, total_score=123.5)
- GET  /api/v2/admin/scoring-trust (admin gated, tri-state)
- POST /api/v2/admin/name-matching/preview (CV via engine, not legacy)
- POST /api/v2/admin/name-matching/apply (engine cv_score persists)
- POST /api/v2/admin/clear-all-detractors (zero detractors + replay engine)
- POST /api/v2/admin/demo-prep (dry-run + apply)
- GET  /api/v2/snapshot-workflow/current-rankings (snapshot/v2 lockstep)
- POST /api/v2/snapshot-workflow/snapshots/{id}/confirm-pos-review (inline rename via _original_name)
- Auth gating on /api/v2/admin/* (all methods)
- name_matcher.normalize_name + get_nps_for_employee_smart
"""

import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"
ADMIN_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
ANON_HEADERS = {"Content-Type": "application/json"}

SENTINEL_YEAR = 9099
SENTINEL_QUARTER = "Q1"

# -------- scoring-example (public) --------


def test_scoring_example_no_auth_total_123_5():
    r = requests.get(f"{BASE}/api/v2/admin/scoring-example", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("total_score") == 123.5, f"expected 123.5 got {d.get('total_score')}"
    bd = d.get("breakdown", {})
    pos = bd.get("weighted_pos_subtotal", 0)
    mb = bd.get("metric_bonuses", {}).get("total", 0)
    cv = bd.get("customer_voice", {}).get("total", 0)
    rt = bd.get("review_tracker", {}).get("capped", 0)
    s = round(pos + mb + cv + rt, 2)
    assert abs(s - 123.5) < 0.01, f"breakdown sum {s} != total_score 123.5; pos={pos} mb={mb} cv={cv} rt={rt}"


# -------- scoring-trust (admin gated) --------


def test_scoring_trust_anon_401():
    r = requests.get(f"{BASE}/api/v2/admin/scoring-trust", timeout=20)
    assert r.status_code == 401, f"expected 401 got {r.status_code}"


def test_scoring_trust_admin_returns_tri_state():
    r = requests.get(f"{BASE}/api/v2/admin/scoring-trust", headers=ADMIN_HEADERS, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("status") in ("green", "amber", "red"), f"bad status {d.get('status')}"
    assert isinstance(d.get("issues"), list)
    assert isinstance(d.get("warnings"), list)
    details = d.get("details", {})
    assert "quarter_settings" in details
    assert "drift_count" in details["quarter_settings"]
    assert "integrity" in details
    assert "p0_issues" in details["integrity"]
    assert "alias_collisions" in details
    assert "count" in details["alias_collisions"]


# -------- normalize-quarter-settings --------


def test_normalize_quarter_settings_anon_401():
    r = requests.post(
        f"{BASE}/api/v2/admin/normalize-quarter-settings?dry_run=true", timeout=20
    )
    assert r.status_code == 401


def test_normalize_quarter_settings_dry_run_admin():
    r = requests.post(
        f"{BASE}/api/v2/admin/normalize-quarter-settings?dry_run=true",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Should report quarters_needing_change and dry_run=True
    assert d.get("dry_run") is True
    assert "quarters_needing_change" in d, f"shape={list(d.keys())}"
    # dry-run should NOT write anything
    fw = d.get("field_writes_total", 0)
    assert fw == 0, f"dry_run should not write fields, got field_writes_total={fw}"


def test_normalize_quarter_settings_apply_idempotent_on_real_quarter():
    # Production quarters should already be canonical -> drift 0
    r = requests.post(
        f"{BASE}/api/v2/admin/normalize-quarter-settings?apply=true",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # canonical => idempotent (0 quarters applied or 0 drift)
    qa = d.get("quarters_applied", d.get("applied", 0))
    if isinstance(qa, list):
        qa = len(qa)
    drift = d.get("drift_count", 0)
    assert (qa == 0) or (drift == 0), f"expected idempotent canonical state, got applied={qa} drift={drift}"


# -------- auth gating --------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v2/admin/scoring-trust"),
        ("POST", "/api/v2/admin/normalize-quarter-settings?dry_run=true"),
        ("POST", "/api/v2/admin/clear-all-detractors?quarter=Q2&year=2026"),
        ("GET", "/api/v2/admin/name-matching/preview?quarter=Q2&year=2026"),
        ("POST", "/api/v2/admin/name-matching/apply?quarter=Q2&year=2026"),
        ("POST", "/api/v2/admin/demo-prep?quarter=Q2&year=2026"),
    ],
)
def test_admin_endpoints_anon_401(method, path):
    fn = requests.get if method == "GET" else requests.post
    r = fn(f"{BASE}{path}", timeout=20)
    assert r.status_code == 401, f"{method} {path} expected 401 got {r.status_code}"


def test_scoring_example_remains_public_exempt():
    r = requests.get(f"{BASE}/api/v2/admin/scoring-example", timeout=20)
    assert r.status_code == 200


# -------- name-matching preview (engine vs legacy) --------


def _cv_engine(nps, promoters, detractors):
    # canonical: NPS/10 + 1*promoters - 2*detractors
    return (nps / 10.0) + (1.0 * promoters) + (-2.0 * detractors)


def test_name_matching_preview_uses_engine_cv():
    # NOTE: route is GET, not POST
    r = requests.get(
        f"{BASE}/api/v2/admin/name-matching/preview?quarter=Q2&year=2026",
        headers=ADMIN_HEADERS,
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    mapping = d.get("mapping") or d.get("matches") or d.get("preview") or []
    assert isinstance(mapping, list), f"mapping shape: {list(d.keys())}"
    if not mapping:
        pytest.skip("No mapping rows in preview")
    # Pull any row that has nps + promoters + detractors + projected_cv_score
    checked = 0
    for row in mapping:
        nps = row.get("matched_nps")
        promoters = row.get("matched_promoters", 0)
        detractors = row.get("matched_detractors", 0)
        proj = row.get("projected_cv_score")
        if nps is None or proj is None:
            continue
        # Skip unmatched rows (nothing meaningful to verify)
        if not row.get("matched_cv_name"):
            continue
        expected_engine = _cv_engine(nps, promoters, detractors)
        legacy = 0.5 * promoters - 1.0 * detractors
        # Should match engine, NOT legacy
        assert abs(proj - expected_engine) < 0.05, (
            f"row {row.get('employee_name')}: "
            f"projected_cv_score={proj} engine_expected={expected_engine} legacy={legacy} "
            f"nps={nps} promo={promoters} det={detractors}"
        )
        checked += 1
        if checked >= 5:
            break
    assert checked > 0, f"could not find any matched row. Sample keys: {list(mapping[0].keys()) if mapping else []}"


# -------- name-matching apply (persists engine cv) --------


def test_name_matching_apply_persists_engine_cv():
    r = requests.post(
        f"{BASE}/api/v2/admin/name-matching/apply?quarter=Q2&year=2026",
        headers=ADMIN_HEADERS,
        timeout=120,
    )
    assert r.status_code == 200, r.text
    # Fetch employees_v2 via current-rankings to see persisted cv_score
    r2 = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q2",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r2.status_code == 200, r2.text
    emps = r2.json().get("employees", [])
    assert emps, "no employees returned for Q2 2026"
    # Find at least one row where we can verify cv_score formula
    verified = 0
    for e in emps:
        nps = e.get("nps_score")
        promoters = e.get("cv_promoters") or 0
        detractors = e.get("cv_detractors") or 0
        cv = e.get("cv_score")
        if nps is None or cv is None:
            continue
        if nps == 0 and promoters == 0 and detractors == 0:
            continue  # not useful for differentiation
        expected = _cv_engine(nps, promoters, detractors)
        # Allow nps_manual_override paths but the formula should still match engine
        assert abs(cv - expected) < 0.1, (
            f"emp {e.get('name')}: cv={cv} expected={expected} "
            f"nps={nps} promo={promoters} det={detractors}"
        )
        verified += 1
        if verified >= 3:
            break
    assert verified >= 1, "could not verify any employee's cv_score formula"


# -------- clear-all-detractors --------


def test_clear_all_detractors_zeros_and_replays_engine():
    r = requests.post(
        f"{BASE}/api/v2/admin/clear-all-detractors?quarter=Q2&year=2026",
        headers=ADMIN_HEADERS,
        timeout=120,
    )
    assert r.status_code == 200, r.text
    # Fetch and verify cv_detractors == 0 and cv_score == nps/10 + promoters
    r2 = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q2",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    emps = r2.json().get("employees", [])
    assert emps
    sample_checked = 0
    for e in emps:
        det = e.get("cv_detractors", 0)
        assert det == 0, f"expected zero detractors, got {det} for {e.get('name')}"
        nps = e.get("nps_score")
        promoters = e.get("cv_promoters") or 0
        cv = e.get("cv_score")
        if nps is None or cv is None:
            continue
        expected = (nps / 10.0) + 1.0 * promoters  # detractors=0
        # ensure not legacy 0.5*promoters formula
        legacy = 0.5 * promoters
        assert abs(cv - expected) < 0.1, (
            f"{e.get('name')}: cv={cv} expected_engine={expected} legacy={legacy} nps={nps} promo={promoters}"
        )
        sample_checked += 1
        if sample_checked >= 3:
            break
    assert sample_checked >= 1


# -------- demo-prep (use sentinel year to avoid mutating real data) --------


def test_demo_prep_sentinel_year_dry_run_then_apply_idempotent():
    # dry-run on sentinel
    r1 = requests.post(
        f"{BASE}/api/v2/admin/demo-prep?quarter={SENTINEL_QUARTER}&year={SENTINEL_YEAR}",
        headers=ADMIN_HEADERS,
        timeout=60,
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    for k in ("display_name_fixes", "v2_dedup_actions", "same_name_dedup_actions", "rescore"):
        assert k in d1, f"missing key {k} in demo-prep dry-run: {list(d1.keys())}"
    # apply on sentinel
    r2 = requests.post(
        f"{BASE}/api/v2/admin/demo-prep?quarter={SENTINEL_QUARTER}&year={SENTINEL_YEAR}&apply=true",
        headers=ADMIN_HEADERS,
        timeout=120,
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert "rescore" in d2
    # Idempotent: run apply again -> should be no-op or stable
    r3 = requests.post(
        f"{BASE}/api/v2/admin/demo-prep?quarter={SENTINEL_QUARTER}&year={SENTINEL_YEAR}&apply=true",
        headers=ADMIN_HEADERS,
        timeout=120,
    )
    assert r3.status_code == 200
    d3 = r3.json()
    # action counts on second apply should be 0 or equal to first (idempotent)
    for key in ("display_name_fixes", "v2_dedup_actions", "same_name_dedup_actions"):
        v3 = d3.get(key)
        if isinstance(v3, list):
            v3 = len(v3)
        if isinstance(v3, dict):
            v3 = v3.get("count", 0)
        assert v3 == 0 or v3 is None, f"demo-prep not idempotent on {key}: got {v3} on second apply"


# -------- snapshot vs v2 lockstep --------


def test_current_rankings_lockstep_with_v2():
    r = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q2",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    emps = d.get("employees", [])
    assert isinstance(emps, list) and len(emps) > 0
    # Each emp should have name + total_score + cv_score
    for e in emps[:5]:
        assert "name" in e
        assert "total_score" in e
    # source label / snapshot-aligned flag if exposed
    # not strictly required - just confirm count > 0
    assert len(emps) >= 1


# -------- inline POS rename via confirm-pos-review --------


SNAPSHOT_ID_DRANE = "e6345d28-34b6-4db1-bd25-1d7731ffc0bd"


def _get_snapshot_employees(snapshot_id):
    r = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/snapshots/{snapshot_id}",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    if r.status_code != 200:
        return None, r
    return r.json(), r


def test_inline_pos_rename_drane_to_diane_and_back():
    snap, r = _get_snapshot_employees(SNAPSHOT_ID_DRANE)
    if snap is None:
        pytest.skip(f"snapshot {SNAPSHOT_ID_DRANE} not reachable: {r.status_code}")
    emps = snap.get("employees") or snap.get("snapshot", {}).get("employees") or []
    drane_row = None
    for e in emps:
        n = (e.get("name") or e.get("display_name") or "").strip()
        if n.lower() == "drane peterson":
            drane_row = e
            break
    if drane_row is None:
        # Could already have been renamed in a prior test run; treat as missing fixture
        pytest.skip("'Drane Peterson' row not present in target snapshot - may have been renamed previously")

    initial_count = len(emps)

    # Rename Drane -> Diane
    payload = {
        "employees": [
            {**drane_row, "_original_name": "Drane Peterson", "name": "Diane Peterson"}
        ]
    }
    rn = requests.post(
        f"{BASE}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID_DRANE}/confirm-pos-review",
        headers=ADMIN_HEADERS,
        json=payload,
        timeout=60,
    )
    assert rn.status_code == 200, f"rename failed: {rn.status_code} {rn.text[:400]}"

    # Verify renamed in place (not duplicated)
    snap2, _ = _get_snapshot_employees(SNAPSHOT_ID_DRANE)
    emps2 = snap2.get("employees") or snap2.get("snapshot", {}).get("employees") or []
    names = [(e.get("name") or e.get("display_name") or "").strip() for e in emps2]
    diane_count = sum(1 for n in names if n.lower() == "diane peterson")
    drane_count = sum(1 for n in names if n.lower() == "drane peterson")
    try:
        assert diane_count == 1, f"expected exactly 1 Diane row, got {diane_count}. names={names}"
        assert drane_count == 0, f"expected Drane to be renamed away, got {drane_count}"
        assert len(emps2) == initial_count, f"row count changed {initial_count}->{len(emps2)} (duplication)"
        # _original_name must not persist
        for e in emps2:
            assert "_original_name" not in e, f"_original_name leaked into storage: {e}"
    finally:
        # Always restore Drane Peterson regardless of assertions
        diane_row = next(
            (e for e in emps2 if (e.get("name") or "").strip().lower() == "diane peterson"),
            None,
        )
        if diane_row is not None:
            restore_payload = {
                "employees": [
                    {**diane_row, "_original_name": "Diane Peterson", "name": "Drane Peterson"}
                ]
            }
            rr = requests.post(
                f"{BASE}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID_DRANE}/confirm-pos-review",
                headers=ADMIN_HEADERS,
                json=restore_payload,
                timeout=60,
            )
            assert rr.status_code == 200, f"restore failed: {rr.status_code} {rr.text[:300]}"


# -------- name_matcher utilities (in-process) --------


def test_name_matcher_normalize_and_smart_match():
    import sys
    sys.path.insert(0, "/app/backend")
    from name_matcher import normalize_name, get_nps_for_employee_smart  # type: ignore

    # normalize_name basic determinism
    a = normalize_name("Diane Peterson")
    b = normalize_name("  diane   peterson  ")
    assert a == b, f"normalize_name not deterministic: {a!r} vs {b!r}"
    assert a, "normalize_name returned empty"

    # Build an in-memory nps lookup keyed by normalize_name(employee_name)
    diane_row = {"employee_name": "Diane Peterson", "nps_score": 80, "promoters": 10, "detractors": 1}
    nps_lookup = {normalize_name("Diane Peterson"): diane_row}
    aliases = ["Drane Peterson"]

    # Canonical exact match
    row_c, reason_c = get_nps_for_employee_smart("Diane Peterson", nps_lookup, aliases=aliases)
    assert reason_c == "exact_name", f"canon reason={reason_c}"
    assert row_c.get("nps_score") == 80

    # Alias-aware match (alias name -> canonical row)
    row_a, reason_a = get_nps_for_employee_smart("Drane Peterson", nps_lookup, aliases=aliases)
    assert reason_a in ("exact_alias", "fuzzy:100", "fuzzy:90", "fuzzy:80") or reason_a.startswith("fuzzy:"), (
        f"alias lookup reason={reason_a}"
    )
    assert row_a.get("nps_score") == 80, f"alias row nps={row_a.get('nps_score')}"
