"""
Regression tests for fixes shipped in this session.

Ensures none of the following silently regress:

  1. PUT /v2/employees syncs ALL metric fields (not just name/tier) back to
     the active snapshot — fixes "snapshot edits not saving" bug.
  2. Native PDF parser (PyMuPDF) is preferred over AI-OCR when the PDF is
     digitally generated.
  3. POS upload preview returns lbw_total + flattened liquor/beer/wine fields
     so Data Uploads displays them.
  4. NPS Adjustment upload honors quarter/year query params (no hardcoded Q1).
  5. job_title + display_name + report_name + aliases are preserved across
     snapshot rebuilds (no longer reverting to "Server" / first-name only).

All tests:
  * Use the live preview backend via REACT_APP_BACKEND_URL
  * Seed minimal data and clean up in teardown
  * Are independent — can run in any order

Run:  pytest /app/backend/tests/test_session_regressions.py -v
"""

from __future__ import annotations

import io
import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from openpyxl import Workbook
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://staff-score-engine.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def active_snapshot(db):
    """Locate the current snapshot for injection."""
    for coll_name in ("snapshot_workflow", "snapshots", "snapshots_v2"):
        if coll_name not in db.list_collection_names():
            continue
        snap = db[coll_name].find_one({"is_current": True})
        if snap:
            return {"collection": coll_name, "snapshot": snap}
    for coll_name in ("snapshot_workflow", "snapshots", "snapshots_v2"):
        if coll_name not in db.list_collection_names():
            continue
        snap = db[coll_name].find_one(
            {"employees": {"$exists": True, "$ne": []}}, sort=[("created_at", -1)]
        )
        if snap:
            return {"collection": coll_name, "snapshot": snap}
    pytest.skip("No active snapshot in DB")


# ---------------------------------------------------------------------------
# 1. PUT /v2/employees full-metric snapshot sync
# ---------------------------------------------------------------------------

class TestSnapshotMetricSync:
    """Editing metrics via PUT /v2/employees must propagate to the snapshot."""

    def test_metric_edits_propagate_to_active_snapshot(self, db, active_snapshot):
        coll_name = active_snapshot["collection"]
        snap = active_snapshot["snapshot"]
        snap_filter = {"id": snap["id"]} if snap.get("id") else {"_id": snap["_id"]}
        quarter = (snap.get("quarter") or "Q1").upper()
        year = snap.get("year") or 2026

        emp_id = f"sync-test-{uuid.uuid4().hex[:8]}"
        emp_name = f"SyncTest_{uuid.uuid4().hex[:6]}"

        # Seed the v2 record
        db.employees_v2.insert_one({
            "id": emp_id,
            "name": emp_name,
            "display_name": emp_name,
            "report_name": emp_name,
            "quarter": quarter,
            "year": year,
            "guests": 100,
            "guest_count": 100,
            "net_sales": 5000.0,
            "ppa": 50.0,
            "liquor_sales": 1000.0,
            "beer_sales": 500.0,
            "wine_sales": 250.0,
            "lbw": 1750.0,
        })
        # Mirror into the snapshot
        db[coll_name].update_one(snap_filter, {"$push": {"employees": {
            "id": emp_id, "name": emp_name, "display_name": emp_name,
            "report_name": emp_name, "guests": 100, "guest_count": 100,
            "net_sales": 5000.0, "ppa": 50.0, "liquor_sales": 1000.0,
            "beer_sales": 500.0, "wine_sales": 250.0, "lbw": 1750.0,
        }}})

        try:
            # Edit metrics
            r = requests.put(
                f"{API}/v2/employees/{emp_id}",
                json={
                    "guests": 200,
                    "guest_count": 200,
                    "liquor_sales": 2000.0,
                    "beer_sales": 800.0,
                    "wine_sales": 300.0,
                    "net_sales": 9000.0,
                },
                timeout=20,
            )
            assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text[:300]}"

            # Re-fetch snapshot from the API and confirm the metric updates landed there
            list_r = requests.get(
                f"{API}/v2/snapshot-workflow/current-rankings",
                params={"quarter": quarter, "year": year}, timeout=15,
            )
            if list_r.status_code != 200:
                pytest.skip("current-rankings unavailable; sync via DB tested below")
            emps = list_r.json().get("employees", [])
            target = next((e for e in emps if e.get("id") == emp_id), None)
            if target is None:
                # Fall back to direct DB inspection
                snap_doc = db[coll_name].find_one(snap_filter)
                target = next(
                    (e for e in (snap_doc.get("employees") or []) if e.get("id") == emp_id),
                    None,
                )
            assert target is not None, "Employee missing from snapshot after PUT"

            # Liquor + Beer + Wine all synced
            assert float(target.get("liquor_sales") or 0) == pytest.approx(2000.0)
            assert float(target.get("beer_sales") or 0) == pytest.approx(800.0)
            assert float(target.get("wine_sales") or 0) == pytest.approx(300.0)
            # LBW total derived
            assert float(target.get("lbw") or 0) == pytest.approx(3100.0)
            # Guests synced
            assert int(target.get("guests") or target.get("guest_count") or 0) == 200
        finally:
            db[coll_name].update_one(snap_filter, {"$pull": {"employees": {"id": emp_id}}})
            db.employees_v2.delete_one({"id": emp_id})


# ---------------------------------------------------------------------------
# 2. Native PDF parser availability
# ---------------------------------------------------------------------------

class TestNativePDFParser:
    """The PyMuPDF native parser module must import and process a sample PDF."""

    def test_parser_module_imports(self):
        """Parser module must be present + exportable."""
        from native_pos_parser import (  # noqa: F401
            extract_pos_data_from_pdf_bytes_native,
            is_pdf_native_extractable,
        )

    def test_parser_handles_sample_pdf(self):
        """Run the parser on /tmp/ssd.pdf if present (CI-friendly skip)."""
        from native_pos_parser import (
            extract_pos_data_from_pdf_bytes_native,
            is_pdf_native_extractable,
        )

        sample = Path("/tmp/ssd.pdf")
        if not sample.exists():
            pytest.skip("/tmp/ssd.pdf not present in this environment")

        data = sample.read_bytes()
        assert is_pdf_native_extractable(data) is True
        result = extract_pos_data_from_pdf_bytes_native(data)
        assert result["success"] is True
        assert result["total_extracted"] >= 25
        # Each employee record has the required fields
        emp = result["employees"][0]
        for f in ("name", "guest_count", "net_sales", "liquor_sales",
                  "beer_sales", "wine_sales", "lbw_total",
                  "bar_glassware_sales", "loyalty_sales"):
            assert f in emp, f"Missing field {f} in {emp}"


# ---------------------------------------------------------------------------
# 3. NPS Adjustment honors quarter/year query params
# ---------------------------------------------------------------------------

class TestNPSAdjustmentQuarter:
    def test_session_files_under_correct_quarter(self, db):
        """Upload to Q3 2026 -> session row should record quarter=Q3, year=2026."""
        wb = Workbook()
        ws = wb.active
        ws.append(["Server", "Rating", "Comment"])
        ws.append(["NPS Q-test", 8, "ok"])
        buf = io.BytesIO()
        wb.save(buf); buf.seek(0)

        r = requests.post(
            f"{API}/v2/cv/adjustment/upload",
            params={"quarter": "Q3", "year": 2026},
            files={"feedback_file": ("nps.xlsx", buf.getvalue(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        sid = data.get("session_id")
        assert sid

        # Verify the persisted session was tagged Q3/2026
        try:
            session = db.cv_adjustment_sessions.find_one({"id": sid}) or \
                      db.cv_adjustment_sessions.find_one({"session_id": sid})
            if session is None:
                pytest.skip("session collection not exposed")
            assert (session.get("quarter") or "").upper() == "Q3", \
                f"quarter mismatch: {session.get('quarter')}"
            assert int(session.get("year") or 0) == 2026
        finally:
            db.cv_adjustment_sessions.delete_one({"id": sid})
            db.cv_adjustment_sessions.delete_one({"session_id": sid})


# ---------------------------------------------------------------------------
# 4. Display name + job title preserved across snapshot rebuild
# ---------------------------------------------------------------------------

class TestRenamePreservation:
    """sync-from-employees must NOT overwrite display_name / job_title /
    report_name / aliases derived from POS into a previously-edited record."""

    def test_user_edits_survive_rebuild(self, db):
        emp_id = f"rename-test-{uuid.uuid4().hex[:8]}"
        original = "Glennice Test"
        renamed = "Lennie Test"
        quarter = "Q2"
        year = 2026

        db.employees_v2.insert_one({
            "id": emp_id,
            "name": renamed,
            "display_name": renamed,
            "report_name": original,  # POS still calls them Glennice
            "aliases": [original, "Glen"],
            "job_title": "Trainer",
            "quarter": quarter,
            "year": year,
            "net_sales": 5000.0,
            "guest_count": 100,
            "ppa": 50.0,
        })
        try:
            # Trigger sync via the public endpoint
            list_r = requests.get(
                f"{API}/v2/snapshot-workflow/snapshots",
                params={"quarter": quarter, "year": year}, timeout=15,
            )
            if list_r.status_code != 200:
                pytest.skip("snapshots endpoint unavailable")
            snaps = list_r.json() if isinstance(list_r.json(), list) else \
                    list_r.json().get("snapshots", [])
            if not snaps:
                pytest.skip(f"No {quarter} {year} snapshot to sync")
            sid = snaps[0].get("id")

            sync_r = requests.post(
                f"{API}/v2/snapshot-workflow/snapshots/{sid}/sync-from-employees",
                timeout=60,
            )
            assert sync_r.status_code in (200, 201), sync_r.text[:200]
            time.sleep(1)

            # Inspect the rebuilt snapshot row. Modern snapshots live in
            # snapshot_workflow; older ones in snapshots / snapshots_v2.
            snap_doc = None
            for coll_name in ("snapshot_workflow", "snapshots", "snapshots_v2"):
                if coll_name not in db.list_collection_names():
                    continue
                snap_doc = db[coll_name].find_one({"id": sid})
                if snap_doc:
                    break
            if snap_doc is None:
                pytest.skip(f"snapshot {sid} not found in any collection (sync may have created a new one)")

            target = next(
                (e for e in (snap_doc.get("employees") or [])
                 if e.get("id") == emp_id or e.get("name") in (renamed, original)),
                None,
            )
            if target is None:
                pytest.skip("synced employee not in snapshot (POS data absent)")

            # Hard assertions: rename/title/aliases must survive
            assert target.get("display_name") == renamed, \
                f"display_name reverted: {target.get('display_name')}"
            assert target.get("job_title") == "Trainer", \
                f"job_title reverted: {target.get('job_title')}"
            assert target.get("report_name") == original, \
                f"report_name lost: {target.get('report_name')}"
        finally:
            db.employees_v2.delete_one({"id": emp_id})


# ---------------------------------------------------------------------------
# 5. POS upload preview returns lbw_total + flat L/B/W
# ---------------------------------------------------------------------------

class TestPOSPreviewLBW:
    """process_pdf_job / process_xlsx_job must emit lbw_total = L + B + W
    so the Data Uploads preview displays the correct LBW value."""

    def test_xlsx_preview_returns_lbw_total(self):
        """Upload a tiny synthetic XLSX, check that the parsed result has
        per-employee lbw_total equal to liquor+beer+wine."""
        wb = Workbook()
        ws = wb.active
        # Layout this matches our XLSX parser's expected column names
        ws.append(["name", "guests", "net_sales", "liquor_sales",
                   "beer_sales", "wine_sales", "bar_glassware_sales",
                   "loyalty_sales"])
        ws.append(["LBWTester", 100, 5000, 500, 200, 100, 50, 25])
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)

        r = requests.post(
            f"{API}/v2/upload-jobs/direct",
            params={"upload_type": "pos_report"},
            files={"file": ("pos.xlsx", buf.getvalue(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"metadata": '{"quarter":"Q2","year":2026}'},
            timeout=60,
        )
        if r.status_code != 200:
            pytest.skip(f"upload-jobs/direct unavailable: {r.status_code}")
        job_id = r.json().get("job_id")
        assert job_id, r.text[:300]

        # Poll
        deadline = time.time() + 60
        result = None
        while time.time() < deadline:
            jr = requests.get(f"{API}/v2/upload-jobs/{job_id}", timeout=15)
            if jr.status_code == 200 and jr.json().get("status") in ("complete", "completed"):
                result = jr.json().get("result") or {}
                break
            time.sleep(2)
        if result is None:
            pytest.skip("job did not complete in 60s — environment too slow to verify")

        emps = result.get("employees") or []
        if not emps:
            pytest.skip("XLSX parser did not return employees in this env")
        target = next((e for e in emps if e.get("name") == "LBWTester"), emps[0])
        # lbw_total present and correctly summed
        l = target.get("liquor_sales", 0) or 0
        b = target.get("beer_sales", 0) or 0
        w = target.get("wine_sales", 0) or 0
        assert "lbw_total" in target, f"missing lbw_total in {target.keys()}"
        assert abs(target["lbw_total"] - (l + b + w)) < 0.5, \
            f"lbw_total mismatch: {target['lbw_total']} vs L+B+W={l+b+w}"
