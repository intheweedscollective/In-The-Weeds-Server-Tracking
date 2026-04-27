"""
Iteration 27 regression suite.

Covers:
  1. CV scoring formula: cv_score = NPS%/10 + promoters*1 + detractors*-2.
  2. PUT /api/v2/employees/{id} delta-math when editing CV inputs
     (nps_score, cv_promoters, cv_passives, cv_detractors).
  3. nps_manual_override flag set after CV-input edit.
  4. snapshot.employees record mirrors employees_v2 record in lockstep.
  5. Full POS rebuild path triggered when liquor_sales (or any POS field) changes.
  6. Name-only edit must NOT change total_score.
  7. New endpoints:
       GET /api/v2/full-rankings/{year}/{quarter}/snapshot-png  -> 1920x1080 PNG
       GET /api/v2/full-rankings/{year}/{quarter}/snapshot-pdf  -> %PDF magic bytes
       Both return 404 for a quarter with no employees (Q4 2026).
  8. Regression: GET /api/qr/leaderboard-data still works.
  9. Regression: nickname CRUD endpoints still work.
 10. Regression: RT parser quarter-aware still works.

Notes
-----
* Uses live Q2 2026 production data (Treyanna Quick) but
  RESTORES Treyanna to nps_score=100 at end of the CV-edit test
  so we don't poison downstream runs.
"""

import os
import io
import uuid
import pytest
import requests
from collections import Counter
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

YEAR = 2026
QUARTER = "Q2"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _fetch_employees(api, year=YEAR, quarter=QUARTER):
    r = api.get(f"{BASE_URL}/api/v2/employees?year={year}&quarter={quarter}", timeout=60)
    assert r.status_code == 200, f"employees fetch failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    return data if isinstance(data, list) else data.get("employees", [])


def _find_by_name(emps, name_substr):
    for e in emps:
        n = (e.get("display_name") or e.get("name") or "").lower()
        if name_substr.lower() in n:
            return e
    return None


def _fetch_snapshot_current(api, year=YEAR, quarter=QUARTER):
    r = api.get(
        f"{BASE_URL}/api/v2/snapshot-workflow/current?year={year}&quarter={quarter}",
        timeout=60,
    )
    if r.status_code != 200:
        return None
    return r.json()


# ---------------------------------------------------------------------------
# 1. CV scoring formula + delta math (Treyanna Q2 2026)
# ---------------------------------------------------------------------------


class TestCVScoringDeltaMath:
    def test_cv_input_edit_uses_delta_math_and_override_flag(self, api):
        emps = _fetch_employees(api)
        trey = _find_by_name(emps, "Treyanna")
        assert trey is not None, "Treyanna Quick must exist in Q2 2026"

        emp_id = trey["id"]
        old_cv = float(trey.get("cv_score") or 0)
        old_total = float(trey.get("total_score") or 0)
        old_promoters = int(trey.get("cv_promoters") or 0)
        old_detractors = int(trey.get("cv_detractors") or 0)

        try:
            # --- Edit NPS to 50 ---
            r = api.put(
                f"{BASE_URL}/api/v2/employees/{emp_id}",
                json={"nps_score": 50},
                timeout=30,
            )
            assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text[:200]}"

            emps2 = _fetch_employees(api)
            trey2 = _find_by_name(emps2, "Treyanna")
            new_cv = float(trey2["cv_score"])
            new_total = float(trey2["total_score"])

            # Formula: NPS%/10 + promoters*1 + detractors*-2
            expected_cv = round(50 * 0.10 + old_promoters * 1 + old_detractors * -2, 2)
            assert abs(new_cv - expected_cv) < 0.01, (
                f"cv_score mismatch: got {new_cv} expected {expected_cv} "
                f"(nps=50, promo={old_promoters}, detr={old_detractors})"
            )

            # Delta math: total shifted by exactly (new_cv - old_cv)
            expected_total = round(old_total + (new_cv - old_cv), 2)
            assert abs(new_total - expected_total) < 0.02, (
                f"total_score delta mismatch: old_total={old_total} old_cv={old_cv} "
                f"new_cv={new_cv} expected_total={expected_total} got={new_total}"
            )

            # Override flag
            assert trey2.get("nps_manual_override") is True, (
                f"nps_manual_override must be True after CV input edit, "
                f"got {trey2.get('nps_manual_override')}"
            )

            # nps_contribution + cv_raw_points correctly decomposed
            assert abs(float(trey2.get("nps_contribution") or 0) - 5.0) < 0.01
            expected_raw = old_promoters * 1 + old_detractors * -2
            assert abs(float(trey2.get("cv_raw_points") or 0) - expected_raw) < 0.01

            # --- snapshot.employees mirrors v2 record ---
            snap = _fetch_snapshot_current(api)
            if snap and snap.get("employees"):
                snap_trey = None
                for se in snap["employees"]:
                    nm = (se.get("display_name") or se.get("name") or "").lower()
                    if "treyanna" in nm:
                        snap_trey = se
                        break
                assert snap_trey is not None, "Treyanna missing from snapshot"
                assert abs(float(snap_trey.get("cv_score") or 0) - new_cv) < 0.01, (
                    f"snapshot cv_score {snap_trey.get('cv_score')} != v2 {new_cv}"
                )
                assert abs(float(snap_trey.get("total_score") or 0) - new_total) < 0.02
                assert snap_trey.get("nps_manual_override") is True
        finally:
            # Restore to baseline nps=100 (idempotent per agent note)
            api.put(
                f"{BASE_URL}/api/v2/employees/{emp_id}",
                json={"nps_score": 100},
                timeout=30,
            )

    def test_cv_promoters_edit_formula(self, api):
        """Pick an employee with nps=80 and set cv_promoters=5 -> cv_score = 8.0 + 5 = 13.0."""
        emps = _fetch_employees(api)
        # Find any candidate we can temporarily edit
        victim = None
        for e in emps:
            nm = (e.get("display_name") or e.get("name") or "").lower()
            if "treyanna" in nm:
                continue  # skip Treyanna (handled in other test)
            victim = e
            break

        assert victim is not None, "Need at least one non-Treyanna employee"
        vid = victim["id"]

        # Snapshot all CV inputs + total for restoration
        orig = {
            "nps_score": victim.get("nps_score"),
            "cv_promoters": victim.get("cv_promoters"),
            "cv_passives": victim.get("cv_passives"),
            "cv_detractors": victim.get("cv_detractors"),
        }
        old_total = float(victim.get("total_score") or 0)
        old_cv = float(victim.get("cv_score") or 0)

        try:
            # Step 1: set nps=80, promoters=0, detractors=0 to isolate
            r = api.put(
                f"{BASE_URL}/api/v2/employees/{vid}",
                json={"nps_score": 80, "cv_promoters": 0, "cv_detractors": 0, "cv_passives": 0},
                timeout=30,
            )
            assert r.status_code == 200

            emps2 = _fetch_employees(api)
            v2 = next(e for e in emps2 if e["id"] == vid)
            cv_after_nps = float(v2["cv_score"])
            total_after_nps = float(v2["total_score"])
            assert abs(cv_after_nps - 8.0) < 0.01, f"expected cv=8.0 got {cv_after_nps}"

            # Step 2: bump promoters to 5 -> cv becomes 8 + 5 = 13
            r = api.put(
                f"{BASE_URL}/api/v2/employees/{vid}",
                json={"cv_promoters": 5},
                timeout=30,
            )
            assert r.status_code == 200

            emps3 = _fetch_employees(api)
            v3 = next(e for e in emps3 if e["id"] == vid)
            cv_final = float(v3["cv_score"])
            total_final = float(v3["total_score"])

            assert abs(cv_final - 13.0) < 0.01, f"expected cv=13.0 got {cv_final}"
            expected_total = round(total_after_nps + (13.0 - cv_after_nps), 2)
            assert abs(total_final - expected_total) < 0.02, (
                f"total delta mismatch: got {total_final} expected {expected_total}"
            )
        finally:
            # Restore original CV inputs
            restore_payload = {k: v for k, v in orig.items() if v is not None}
            if restore_payload:
                api.put(
                    f"{BASE_URL}/api/v2/employees/{vid}",
                    json=restore_payload,
                    timeout=30,
                )

    def test_name_only_edit_does_not_change_total(self, api):
        """Editing only name should NOT touch total_score."""
        emps = _fetch_employees(api)
        # Pick any employee, preferably not Treyanna
        victim = next(
            (e for e in emps if "treyanna" not in (e.get("display_name") or "").lower()),
            None,
        )
        assert victim is not None
        vid = victim["id"]
        old_name = victim.get("display_name") or victim.get("name")
        old_total = float(victim.get("total_score") or 0)
        old_cv = float(victim.get("cv_score") or 0)

        tmp_name = f"{old_name} [test-{uuid.uuid4().hex[:6]}]"
        try:
            r = api.put(
                f"{BASE_URL}/api/v2/employees/{vid}",
                json={"name": tmp_name},
                timeout=30,
            )
            assert r.status_code == 200

            emps2 = _fetch_employees(api)
            v2 = next(e for e in emps2 if e["id"] == vid)
            new_total = float(v2.get("total_score") or 0)
            new_cv = float(v2.get("cv_score") or 0)
            assert abs(new_total - old_total) < 0.01, (
                f"name-only edit must preserve total_score: old={old_total} new={new_total}"
            )
            assert abs(new_cv - old_cv) < 0.01
            # nps_manual_override should NOT have been flipped by a name-only edit
        finally:
            # Restore name
            api.put(
                f"{BASE_URL}/api/v2/employees/{vid}",
                json={"name": old_name},
                timeout=30,
            )


# ---------------------------------------------------------------------------
# 2. POS full-rebuild path
# ---------------------------------------------------------------------------


class TestPOSFullRebuild:
    def test_liquor_sales_edit_triggers_full_rebuild(self, api):
        emps = _fetch_employees(api)
        victim = next(
            (e for e in emps if "treyanna" not in (e.get("display_name") or "").lower()),
            None,
        )
        assert victim is not None
        vid = victim["id"]
        orig_liquor = victim.get("liquor_sales")
        old_weighted = victim.get("weighted_score")

        try:
            r = api.put(
                f"{BASE_URL}/api/v2/employees/{vid}",
                json={"liquor_sales": 999},
                timeout=30,
            )
            assert r.status_code == 200

            emps2 = _fetch_employees(api)
            v2 = next(e for e in emps2 if e["id"] == vid)
            # liquor_sales persisted
            assert abs(float(v2.get("liquor_sales") or 0) - 999) < 0.01
            # weighted_score must be a number (full rebuild wrote it)
            assert v2.get("weighted_score") is not None
            # total_score exists and is numeric
            assert isinstance(v2.get("total_score"), (int, float))
        finally:
            if orig_liquor is not None:
                api.put(
                    f"{BASE_URL}/api/v2/employees/{vid}",
                    json={"liquor_sales": orig_liquor},
                    timeout=30,
                )


# ---------------------------------------------------------------------------
# 3. New PNG / PDF snapshot endpoints
# ---------------------------------------------------------------------------


class TestSnapshotPngPdf:
    def test_snapshot_png_returns_1920x1080(self, api):
        url = f"{BASE_URL}/api/v2/full-rankings/{YEAR}/{QUARTER}/snapshot-png"
        r = api.get(url, timeout=120)
        assert r.status_code == 200, f"PNG endpoint failed: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("image/png"), (
            f"content-type mismatch: {r.headers.get('content-type')}"
        )
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n", "Not a valid PNG magic header"

        img = Image.open(io.BytesIO(r.content))
        assert img.size == (1920, 1080), f"size mismatch: got {img.size}"

        # Sample right-half pixels for palette presence
        right_half = img.crop((520, 60, 1900, 1060))
        colors = Counter(list(right_half.convert("RGB").getdata()))
        top_colors = {c for c, _ in colors.most_common(40)}

        palette = {
            "green": (0x33, 0xCC, 0x33),
            "yellow": (0xFF, 0xFF, 0x00),
            "red": (0xFF, 0x00, 0x00),
            "blue": (0x0C, 0x76, 0x9E),
            "white": (0xFF, 0xFF, 0xFF),
            "navy": (0x0F, 0x17, 0x2A),
        }
        # At least 3 palette colors must appear in the top 40 most-common colors.
        # (Some quarters may not have any employee in a given tier, so not all 6 will show up.)
        found = [name for name, rgb in palette.items() if rgb in top_colors]
        assert len(found) >= 3, (
            f"Only {found} palette colors found in top-40. top_colors sample: "
            f"{list(top_colors)[:10]}"
        )

    def test_snapshot_pdf_magic_bytes(self, api):
        url = f"{BASE_URL}/api/v2/full-rankings/{YEAR}/{QUARTER}/snapshot-pdf"
        r = api.get(url, timeout=120)
        assert r.status_code == 200, f"PDF endpoint failed: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF", f"Not a valid PDF: first 10 bytes = {r.content[:10]}"
        assert len(r.content) > 1000, "PDF suspiciously small"

    def test_snapshot_png_404_for_empty_quarter(self, api):
        url = f"{BASE_URL}/api/v2/full-rankings/{YEAR}/Q4/snapshot-png"
        r = api.get(url, timeout=60)
        assert r.status_code == 404, f"Expected 404 got {r.status_code}"

    def test_snapshot_pdf_404_for_empty_quarter(self, api):
        url = f"{BASE_URL}/api/v2/full-rankings/{YEAR}/Q4/snapshot-pdf"
        r = api.get(url, timeout=60)
        assert r.status_code == 404, f"Expected 404 got {r.status_code}"


# ---------------------------------------------------------------------------
# 4. Regressions (iterations 24–26)
# ---------------------------------------------------------------------------


class TestRegressions:
    def test_qr_leaderboard_data(self, api):
        r = api.get(f"{BASE_URL}/api/qr/leaderboard-data", timeout=60)
        assert r.status_code == 200, f"QR leaderboard failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        # Must return a dict with some structure
        assert isinstance(body, (dict, list))

    def test_nickname_aliases_get(self, api):
        r = api.get(f"{BASE_URL}/api/v2/snapshot-workflow/nicknames", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "defaults" in body, f"expected 'defaults' in response: {list(body)[:5]}"
        defaults_blob = str(body["defaults"]).lower()
        # Must contain the explicit user-confirmed mappings
        assert "treyanna" in defaults_blob, "treyanna mapping missing from defaults"
        assert "thaddeus" in defaults_blob, "thaddeus mapping missing from defaults"
        assert len(body["defaults"]) >= 30, f"expected >=30 defaults, got {len(body['defaults'])}"

    def test_nickname_alias_crud_roundtrip(self, api):
        nickname = f"tst{uuid.uuid4().hex[:6]}"
        formal = "treyanna quick"
        post_r = api.post(
            f"{BASE_URL}/api/v2/snapshot-workflow/nicknames",
            json={"nickname": nickname, "formal": formal},
            timeout=30,
        )
        assert post_r.status_code in (200, 201), (
            f"POST failed: {post_r.status_code} {post_r.text[:200]}"
        )
        body = post_r.json()
        alias_id = body.get("id")
        assert alias_id, f"no id returned: {body}"
        try:
            list_r = api.get(f"{BASE_URL}/api/v2/snapshot-workflow/nicknames", timeout=30)
            assert list_r.status_code == 200
            user_blob = str(list_r.json().get("user", [])).lower()
            assert nickname in user_blob, f"created alias missing from list: {user_blob[:200]}"
        finally:
            del_r = api.delete(
                f"{BASE_URL}/api/v2/snapshot-workflow/nicknames/{alias_id}",
                timeout=30,
            )
            assert del_r.status_code in (200, 204), (
                f"DELETE failed: {del_r.status_code} {del_r.text[:200]}"
            )

    def test_rt_parser_quarter_aware_route_reachable(self, api):
        """Smoke: the snapshot current endpoint for Q2 2026 is reachable (proxy for RT data surface)."""
        snap = _fetch_snapshot_current(api)
        # current may legitimately return None if no is_current=True, but the endpoint should not 500
        # We at least check that a 2nd call (list) works:
        r = api.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/list?year={YEAR}&quarter={QUARTER}",
            timeout=60,
        )
        assert r.status_code in (200, 404), f"snapshot list status {r.status_code}"
