"""
Regression tests for the QR Click Recovery file-upload endpoints.

Covers the operator-facing flow end-to-end:
  1. POST /v2/admin/qr-recovery/import with a small JSON payload in
     dry-run mode → returns counts but writes nothing.
  2. POST same payload with dry_run=false in staging mode → rows land
     in qr_scans_pre_march_recovered, NOT in qr_scans.
  3. POST again with the same payload → all rows are skipped as
     in-collection duplicates (id-keyed dedupe).
  4. GET /v2/admin/qr-recovery/staging-summary returns the right
     totals + by-platform breakdown + earliest/latest.
  5. POST /v2/admin/qr-recovery/promote-staging moves rows into
     qr_scans + qr_click_log_immutable, dedupe still holds.
  6. Re-running promote is a no-op (idempotent).
  7. POST /v2/admin/qr-recovery/clear-staging wipes staging.
  8. Direct-merge mode also dedupes against the LIVE collections.
  9. Malformed rows are reported, not crashed on.
 10. Anonymous request → 401.
"""

import asyncio
import io
import json
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"
ADMIN = {"Authorization": f"Bearer {TOKEN}"}
URL = f"{BASE}/api/v2/admin/qr-recovery"


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _scan_row(employee_id: str, platform: str = "google",
              scanned_at: str = "2026-02-14T17:42:03+00:00",
              row_id: str | None = None) -> dict:
    return {
        "id": row_id or str(uuid.uuid4()),
        "employee_id": employee_id,
        "employee_name": "Test Server",
        "platform": platform,
        "scanned_at": scanned_at,
    }


def _post_import(rows, mode="staging", dry_run=False):
    payload = json.dumps(rows).encode("utf-8")
    files = {"file": ("recovery.json", io.BytesIO(payload), "application/json")}
    data = {"mode": mode, "dry_run": "true" if dry_run else "false"}
    r = requests.post(f"{URL}/import", headers=ADMIN, files=files, data=data, timeout=30)
    return r


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


@pytest.fixture
def cleanup_collections(loop):
    """Reset the recovery surface between tests so order doesn't matter."""
    async def _wipe():
        db = _db()
        await db.qr_scans_pre_march_recovered.delete_many({})
        # Don't touch the existing qr_scans / qr_click_log_immutable — but
        # do remove any test-fixture rows we inserted (we'll re-tag them
        # via `recovered_via=qr_recovery_import_test` so we can locate them).
        await db.qr_scans.delete_many({"recovered_via": "qr_recovery_import_test"})
        await db.qr_click_log_immutable.delete_many({"recovered_via": "qr_recovery_import_test"})
        await db.qr_recovery_audit.delete_many({"actor": "owner@intheweedscollective.com",
                                                "filename": "recovery.json"})
    loop.run_until_complete(_wipe())
    yield
    loop.run_until_complete(_wipe())


def _tag(row):
    row["recovered_via"] = "qr_recovery_import_test"
    return row


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


def test_import_requires_admin():
    payload = json.dumps([_scan_row("emp-1")]).encode()
    files = {"file": ("x.json", io.BytesIO(payload), "application/json")}
    r = requests.post(f"{URL}/import", files=files,
                      data={"mode": "staging", "dry_run": "true"}, timeout=20)
    assert r.status_code == 401, r.text


def test_staging_summary_requires_admin():
    r = requests.get(f"{URL}/staging-summary", timeout=15)
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(loop, cleanup_collections):
    rows = [_tag(_scan_row("emp-A")), _tag(_scan_row("emp-B", "yelp"))]
    r = _post_import(rows, mode="staging", dry_run=True)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is True
    assert d["accepted"] == 2
    assert d["mode"] == "staging"

    async def _confirm():
        db = _db()
        n = await db.qr_scans_pre_march_recovered.count_documents({})
        assert n == 0, f"dry-run wrote {n} rows — must write zero"
    loop.run_until_complete(_confirm())


# ---------------------------------------------------------------------------
# Staging mode — happy path + dedupe
# ---------------------------------------------------------------------------


def test_staging_mode_writes_only_to_staging(loop, cleanup_collections):
    row_id = str(uuid.uuid4())
    rows = [_tag(_scan_row("emp-A", row_id=row_id))]
    r = _post_import(rows, mode="staging", dry_run=False)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["accepted"] == 1
    assert "qr_scans_pre_march_recovered" in (d.get("target") or "")

    async def _check():
        db = _db()
        in_staging = await db.qr_scans_pre_march_recovered.count_documents({"id": row_id})
        in_live = await db.qr_scans.count_documents({"id": row_id})
        in_immut = await db.qr_click_log_immutable.count_documents({"id": row_id})
        assert in_staging == 1, "row missing from staging"
        assert in_live == 0, "staging mode must NOT write to qr_scans"
        assert in_immut == 0, "staging mode must NOT write to qr_click_log_immutable"
    loop.run_until_complete(_check())

    # Second import with the same id — must be skipped as duplicate.
    r2 = _post_import(rows, mode="staging", dry_run=False)
    d2 = r2.json()
    assert d2["accepted"] == 0
    assert d2["skipped_duplicates"] >= 1


# ---------------------------------------------------------------------------
# Promote staging → live
# ---------------------------------------------------------------------------


def test_promote_staging_moves_rows_to_live(loop, cleanup_collections):
    row_id = str(uuid.uuid4())
    rows = [_tag(_scan_row("emp-A", row_id=row_id))]
    _post_import(rows, mode="staging", dry_run=False).raise_for_status()

    r = requests.post(f"{URL}/promote-staging", headers=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["written_to_qr_scans"] == 1
    assert d["written_to_immutable"] == 1

    async def _check():
        db = _db()
        assert await db.qr_scans.count_documents({"id": row_id}) == 1
        assert await db.qr_click_log_immutable.count_documents({"id": row_id}) == 1
        # Staging is NOT cleared by promote — explicit clear-staging required.
        assert await db.qr_scans_pre_march_recovered.count_documents({"id": row_id}) == 1
    loop.run_until_complete(_check())

    # Idempotent: re-promote is a no-op.
    r2 = requests.post(f"{URL}/promote-staging", headers=ADMIN, timeout=20)
    d2 = r2.json()
    assert d2["written_to_qr_scans"] == 0
    assert d2["written_to_immutable"] == 0


def test_clear_staging_wipes(loop, cleanup_collections):
    _post_import([_tag(_scan_row("emp-A")), _tag(_scan_row("emp-B"))],
                 mode="staging", dry_run=False).raise_for_status()
    r = requests.post(f"{URL}/clear-staging", headers=ADMIN, timeout=20)
    d = r.json()
    assert d["deleted"] >= 2

    async def _check():
        db = _db()
        assert await db.qr_scans_pre_march_recovered.count_documents({}) == 0
    loop.run_until_complete(_check())


# ---------------------------------------------------------------------------
# Direct merge — must dedupe against the live collections
# ---------------------------------------------------------------------------


def test_direct_merge_skips_dupes_in_live(loop, cleanup_collections):
    row_id = str(uuid.uuid4())
    rows = [_tag(_scan_row("emp-A", row_id=row_id))]
    # First merge — should land in qr_scans + immutable.
    r1 = _post_import(rows, mode="merge", dry_run=False)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["accepted"] == 1
    assert "qr_scans" in d1["target"]
    # Second merge with same id — must be a no-op.
    r2 = _post_import(rows, mode="merge", dry_run=False)
    d2 = r2.json()
    assert d2["accepted"] == 0
    assert d2["skipped_duplicates"] >= 1


# ---------------------------------------------------------------------------
# Malformed rows
# ---------------------------------------------------------------------------


def test_malformed_rows_are_reported_not_crashed_on(cleanup_collections):
    rows = [
        _tag(_scan_row("emp-A")),                       # good
        {"id": "x", "employee_id": "e",                 # bad platform
         "platform": "wikipedia",
         "scanned_at": "2026-02-14T17:42:03+00:00"},
        {"id": "y", "employee_id": "z",
         "platform": "google", "scanned_at": "not-a-date"},  # bad timestamp
        "this isn't an object at all",
    ]
    r = _post_import(rows, mode="staging", dry_run=True)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["accepted"] == 1
    assert d["malformed_count"] == 3
    reasons = " ".join(m["reason"] for m in d["malformed"])
    assert "invalid platform" in reasons
    assert "not a valid ISO-8601" in reasons
    assert "not an object" in reasons


def test_invalid_json_returns_400(cleanup_collections):
    files = {"file": ("bad.json", io.BytesIO(b"{this is not json"), "application/json")}
    r = requests.post(f"{URL}/import", headers=ADMIN,
                      files=files, data={"mode": "staging", "dry_run": "false"},
                      timeout=15)
    assert r.status_code == 400, r.text
    assert "invalid JSON" in r.text


def test_top_level_must_be_array(cleanup_collections):
    files = {"file": ("notarr.json", io.BytesIO(b'{"foo": "bar"}'),
                      "application/json")}
    r = requests.post(f"{URL}/import", headers=ADMIN,
                      files=files, data={"mode": "staging", "dry_run": "false"},
                      timeout=15)
    assert r.status_code == 400, r.text
    assert "must be an array" in r.text


# ---------------------------------------------------------------------------
# Staging summary
# ---------------------------------------------------------------------------


def test_staging_summary_reports_counts_and_dates(loop, cleanup_collections):
    rows = [
        _tag(_scan_row("emp-A", "google", "2026-01-05T12:00:00+00:00")),
        _tag(_scan_row("emp-B", "google", "2026-02-20T12:00:00+00:00")),
        _tag(_scan_row("emp-C", "yelp",   "2026-03-15T12:00:00+00:00")),
    ]
    _post_import(rows, mode="staging", dry_run=False).raise_for_status()
    r = requests.get(f"{URL}/staging-summary", headers=ADMIN, timeout=20)
    d = r.json()
    assert d["total"] == 3
    assert d["by_platform"].get("google") == 2
    assert d["by_platform"].get("yelp") == 1
    assert d["earliest"].startswith("2026-01-05")
    assert d["latest"].startswith("2026-03-15")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def test_audit_log_records_each_action(loop, cleanup_collections):
    _post_import([_tag(_scan_row("emp-A"))], mode="staging", dry_run=True).raise_for_status()
    _post_import([_tag(_scan_row("emp-B"))], mode="staging", dry_run=False).raise_for_status()
    requests.post(f"{URL}/clear-staging", headers=ADMIN, timeout=20).raise_for_status()

    r = requests.get(f"{URL}/audit?limit=10", headers=ADMIN, timeout=15)
    entries = r.json().get("entries", [])
    actions = [e.get("action") for e in entries[:5]]
    # Newest first → clear → import.staging → import.dry_run
    assert "clear_staging" in actions
    assert "import.staging" in actions or "import.dry_run" in actions
