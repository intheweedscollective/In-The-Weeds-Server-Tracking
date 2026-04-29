"""
One-shot reconciliation for Q2 2026.

Aligns employees_v2, snapshot_workflow, and pos_upload.parsed_data so all
three views (Dashboard, Reports, Employee List) show the same 30 employees
from the real `ssd 4-23.pdf` POS report + the user-supplied NPS Toolkit
Customer Voice file.

Steps:
  1. Wipe stale Q2 2026 employees_v2 records (4 junk rows from prior testing).
  2. Demote the stale 'Q2 2026 Snapshot' (5131256b) from is_current.
  3. Promote the in-progress 'Q2P4W3' snapshot (72030efa) to is_current.
  4. Upload the supplied NPS Toolkit XLSX as customer_voice for 72030efa.
  5. Run /process to build snapshot.employees from the 30 POS records + CV.
  6. Sync snapshot.employees -> employees_v2 (rebuild from authoritative source).
  7. Verify Treyanna + Diane numbers align across all 3 views.

Run: python /app/backend/scripts/reconcile_q2_2026.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from pymongo import MongoClient

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://staff-score-engine.preview.emergentagent.com",
).rstrip("/")
API = f"{BACKEND}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CV_FILE = Path("/tmp/q2_cv_report.xlsx")
QUARTER, YEAR = "Q2", 2026
STALE_SNAP = "5131256b-c06e-4746-81f8-38906706fbf4"
REAL_SNAP = "72030efa-0df3-478d-9284-d0a02f1c90a3"


def banner(msg):
    print(f"\n{'=' * 70}\n  {msg}\n{'=' * 70}")


def main():
    db = MongoClient(MONGO_URL)[DB_NAME]

    # ---------- 1. Clear Q2 employees_v2 ----------
    banner("Step 1: Wiping stale Q2 2026 employees_v2 (4 junk rows)")
    before = list(db.employees_v2.find(
        {"quarter": QUARTER, "year": YEAR},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1}
    ))
    for r in before:
        print(f"  DELETE  id={r.get('id')} name={r.get('name')!r} display={r.get('display_name')!r}")
    res = db.employees_v2.delete_many({"quarter": QUARTER, "year": YEAR})
    print(f"  -> deleted {res.deleted_count} rows")

    # ---------- 2. Demote stale snapshot ----------
    banner(f"Step 2: Demoting stale snapshot {STALE_SNAP}")
    res = db.snapshot_workflow.update_one(
        {"id": STALE_SNAP},
        {"$set": {"is_current": False, "status": "deleted"}}
    )
    print(f"  matched={res.matched_count}, modified={res.modified_count}")

    # ---------- 3. Promote real snapshot ----------
    banner(f"Step 3: Promoting real snapshot {REAL_SNAP} to is_current")
    res = db.snapshot_workflow.update_one(
        {"id": REAL_SNAP},
        {"$set": {"is_current": True, "status": "in_progress"}}
    )
    print(f"  matched={res.matched_count}, modified={res.modified_count}")
    # Make sure no other Q2 2026 snapshot is also is_current
    db.snapshot_workflow.update_many(
        {"quarter": QUARTER, "year": YEAR, "id": {"$ne": REAL_SNAP}},
        {"$set": {"is_current": False}}
    )

    # ---------- 4. Upload CV file ----------
    banner("Step 4: Uploading CV NPS Toolkit XLSX to real snapshot")
    if not CV_FILE.exists():
        print(f"  ERROR: {CV_FILE} not found"); sys.exit(1)
    with CV_FILE.open("rb") as fh:
        r = requests.post(
            f"{API}/v2/snapshot-workflow/snapshots/{REAL_SNAP}/upload/customer_voice",
            files={"file": ("Server_Performance_Report.xlsx", fh.read(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=60,
        )
    if r.status_code != 200:
        print(f"  CV upload failed: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    body = r.json()
    print(f"  CV upload OK — record_count={body.get('record_count')}, "
          f"employees_in_payload={len((body.get('parsed_data') or {}).get('employees', []))}")

    # ---------- 5. Process snapshot ----------
    banner("Step 5: /process — builds snapshot.employees from POS + CV")
    r = requests.post(
        f"{API}/v2/snapshot-workflow/snapshots/{REAL_SNAP}/process", timeout=120,
    )
    if r.status_code == 400 and "already completed" in r.text.lower():
        # Try reprocess
        r = requests.post(
            f"{API}/v2/snapshot-workflow/snapshots/{REAL_SNAP}/reprocess", timeout=120,
        )
    if r.status_code != 200:
        print(f"  Process failed: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    print(f"  Process OK — {r.json().get('employee_count')} employees")
    time.sleep(0.5)

    # ---------- 6. Rebuild employees_v2 from snapshot ----------
    banner("Step 6: Rebuilding employees_v2 from authoritative snapshot")
    snap = db.snapshot_workflow.find_one({"id": REAL_SNAP})
    snap_emps = snap.get("employees") or []
    print(f"  snapshot.employees count = {len(snap_emps)}")

    inserted = 0
    for e in snap_emps:
        v2_doc = {k: v for k, v in e.items() if k not in ("_id",)}
        v2_doc["quarter"] = QUARTER
        v2_doc["year"] = YEAR
        # Ensure required fields
        if not v2_doc.get("id"):
            import uuid
            v2_doc["id"] = str(uuid.uuid4())
        # `name` should mirror display_name in v2 so dashboard matches snapshot
        v2_doc["name"] = v2_doc.get("display_name") or v2_doc.get("name")
        v2_doc.setdefault("guest_count", v2_doc.get("guests"))
        v2_doc.setdefault("guests", v2_doc.get("guest_count"))
        # Upsert by id
        db.employees_v2.replace_one(
            {"id": v2_doc["id"], "quarter": QUARTER, "year": YEAR},
            v2_doc, upsert=True
        )
        inserted += 1
    print(f"  upserted {inserted} into employees_v2")

    # ---------- 7. Verify ----------
    banner("Step 7: Verification — Treyanna, Diane, Lakeisha")
    for target in ("Treyanna", "Diane", "Lakeisha"):
        v2 = db.employees_v2.find_one({
            "quarter": QUARTER, "year": YEAR,
            "$or": [
                {"name": {"$regex": target, "$options": "i"}},
                {"display_name": {"$regex": target, "$options": "i"}},
                {"report_name": {"$regex": target, "$options": "i"}},
            ]
        }, {"_id": 0})
        snap_emp = next(
            (e for e in snap_emps
             if target.lower() in (e.get("name", "") + e.get("display_name", "")).lower()),
            None
        )
        print(f"\n  --- {target} ---")
        if v2:
            print(f"    employees_v2: ppa={v2.get('ppa')} guests={v2.get('guest_count')} "
                  f"lbw={v2.get('lbw')} nps={v2.get('nps_score')} "
                  f"rt={v2.get('rt_mentions')} score={v2.get('total_score')} "
                  f"tier={v2.get('tier_label')}")
        else:
            print(f"    employees_v2: NOT FOUND")
        if snap_emp:
            print(f"    snapshot:     ppa={snap_emp.get('ppa')} guests={snap_emp.get('guest_count')} "
                  f"lbw={snap_emp.get('lbw')} nps={snap_emp.get('nps_score')} "
                  f"rt={snap_emp.get('rt_mentions')} score={snap_emp.get('total_score')} "
                  f"tier={snap_emp.get('tier_label')}")
        else:
            print(f"    snapshot:     NOT FOUND")

    banner("DONE — Q2 2026 reconciled")
    print(f"  Active snapshot: {REAL_SNAP}")
    print(f"  employees_v2:    {db.employees_v2.count_documents({'quarter': QUARTER, 'year': YEAR})}")
    print(f"  snapshot.emps:   {len(snap_emps)}")


if __name__ == "__main__":
    main()
