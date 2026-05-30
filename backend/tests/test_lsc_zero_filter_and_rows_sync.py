"""
Regression tests for the Q2P5W4 scoring bug report:

1. Kahi Ramos PPA must be sane (no $39M corruption regression).
2. Kitti Xavier's `guests_per_lsc` must equal `guests / lsc_count`.
3. The `/sync-snapshot-rows` admin endpoint exists, is admin-gated,
   defaults to in_progress-only scope, and refuses to touch finalized
   snapshots even when `include_completed=true`.
"""

import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"
ADMIN_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


# -------- Scoring sanity on current Q2 snapshot --------


def test_kahi_ppa_is_sane():
    """Kahi Ramos PPA must be a plausible restaurant value, not a
    multi-million-dollar artifact of corrupted net_sales."""
    r = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q2",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    emps = r.json().get("employees", [])
    kahi = next((e for e in emps if "kahi" in (e.get("name") or "").lower()), None)
    assert kahi is not None, "Kahi Ramos not found in Q2 current snapshot"
    assert kahi.get("ppa") is not None
    # Sanity: a per-guest spend over $200 is almost certainly corrupted.
    assert 0 < kahi["ppa"] < 200, f"Kahi ppa={kahi['ppa']} looks corrupted"
    # net_sales should match guests * ppa within rounding.
    ns = kahi.get("net_sales") or 0
    g = kahi.get("guests") or kahi.get("guest_count") or 1
    assert abs((ns / g) - kahi["ppa"]) < 0.1, (
        f"Kahi net_sales={ns} / guests={g} drifts from stored ppa={kahi['ppa']}"
    )


def test_kitti_guests_per_lsc_matches_inputs():
    """guests_per_lsc must equal guests / lsc_count for every employee."""
    r = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q2",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    emps = r.json().get("employees", [])
    kitti = next((e for e in emps if "kitti" in (e.get("name") or "").lower()), None)
    assert kitti is not None
    guests = kitti.get("guests") or kitti.get("guest_count")
    lsc = kitti.get("lsc_count")
    gpl = kitti.get("guests_per_lsc")
    assert guests and lsc and gpl, f"Kitti missing inputs: g={guests} lsc={lsc} gpl={gpl}"
    expected = round(guests / lsc, 2)
    assert abs(gpl - expected) < 0.05, (
        f"Kitti gpl={gpl} != guests/lsc={expected} ({guests}/{lsc})"
    )


# -------- /sync-snapshot-rows endpoint --------


def test_sync_snapshot_rows_requires_admin():
    r = requests.post(f"{BASE}/api/v2/admin/sync-snapshot-rows", timeout=20)
    assert r.status_code == 401


def test_sync_snapshot_rows_dry_run_default_scope_in_progress_only():
    """Default behaviour: only in_progress snapshots are scanned."""
    r = requests.post(
        f"{BASE}/api/v2/admin/sync-snapshot-rows",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("dry_run") is True
    for entry in d.get("results", []):
        assert entry.get("status") == "in_progress", (
            f"Default scope leaked: {entry.get('name')} status={entry.get('status')}"
        )


def test_sync_snapshot_rows_skips_finalized_even_with_include_completed():
    """Finalized snapshots must NEVER be in the result set."""
    r = requests.post(
        f"{BASE}/api/v2/admin/sync-snapshot-rows?include_completed=true",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    for entry in d.get("results", []):
        assert entry.get("status") != "finalized", (
            f"Finalized snapshot leaked: {entry.get('name')}"
        )
