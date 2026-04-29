"""
Regression test for the P0 "Save Snapshot reverts edits + resurrects
duplicates" bug.

Scenario:
  1. Snapshot has TWO duplicate POS rows for the same person.
  2. User deletes ghost via DELETE /v2/employees/{ghost_id}.
  3. User edits NPS for survivor via PUT /v2/employees/{survivor_id}.
  4. User clicks "Save Snapshot" -> /sync-from-employees -> /process.
  5. Expected: ghost stays gone, NPS edit persists.

This isolates the bug discussed in the handoff and the next /process call.
"""
from __future__ import annotations
import os
import time
import uuid
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://staff-score-engine.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _find_active_snapshot(db):
    snap = db.snapshot_workflow.find_one({"is_current": True})
    if snap:
        return snap
    return db.snapshot_workflow.find_one(
        {"employees": {"$exists": True}}, sort=[("updated_at", -1)]
    )


def main():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    snap = _find_active_snapshot(db)
    assert snap, "No snapshot to test against"
    snap_id = snap["id"]
    quarter = snap.get("quarter", "Q2").upper()
    year = snap.get("year", 2026)
    print(f"[setup] Using snapshot {snap_id} {quarter} {year}")

    survivor_name = f"SaveBugSurvivor_{uuid.uuid4().hex[:6]}"
    ghost_name = f"SaveBugGhost_{uuid.uuid4().hex[:6]}"
    survivor_id = f"survivor-{uuid.uuid4().hex[:8]}"
    ghost_id = f"ghost-{uuid.uuid4().hex[:8]}"

    survivor_v2 = {
        "id": survivor_id, "name": survivor_name, "display_name": survivor_name,
        "report_name": survivor_name, "quarter": quarter, "year": year,
        "job_title": "Server", "guests": 100, "guest_count": 100,
        "net_sales": 5000.0, "ppa": 50.0,
        "liquor_sales": 500.0, "beer_sales": 200.0, "wine_sales": 100.0,
        "bar_glassware_sales": 100.0, "loyalty_sales": 100.0,
        "lbw": 800.0, "nps_score": 0.0,
    }
    ghost_v2 = dict(survivor_v2, id=ghost_id, name=ghost_name,
                    display_name=ghost_name, report_name=ghost_name,
                    nps_score=0.0)

    db.employees_v2.insert_many([survivor_v2, ghost_v2])
    # Mirror both into snapshot.employees
    db.snapshot_workflow.update_one(
        {"id": snap_id},
        {"$push": {"employees": {"$each": [
            {**survivor_v2, "tier_label": "Server"},
            {**ghost_v2, "tier_label": "Server"},
        ]}}}
    )
    # Mirror both into pos_upload's parsed_data — this is the source of the
    # ghost-resurrection bug: even after delete, this list keeps the row.
    snap_doc = db.snapshot_workflow.find_one({"id": snap_id})
    uploads = snap_doc.get("uploads") or []
    pos_idx = next((i for i, u in enumerate(uploads) if u.get("upload_type") == "pos_report"), None)
    if pos_idx is None:
        uploads.append({
            "upload_type": "pos_report", "status": "parsed",
            "parsed_data": {"employees": [], "record_count": 0}
        })
        pos_idx = len(uploads) - 1
    pos_emps = uploads[pos_idx].get("parsed_data", {}).get("employees", []) or []
    for e in (survivor_v2, ghost_v2):
        pos_emps.append({
            "name": e["name"], "guest_count": e["guest_count"],
            "net_sales": e["net_sales"], "ppa": e["ppa"],
            "liquor_sales": e["liquor_sales"], "beer_sales": e["beer_sales"],
            "wine_sales": e["wine_sales"], "bar_glassware_sales": e["bar_glassware_sales"],
            "loyalty_sales": e["loyalty_sales"], "lbw_total": e["lbw"],
        })
    uploads[pos_idx].setdefault("parsed_data", {})["employees"] = pos_emps
    uploads[pos_idx]["parsed_data"]["record_count"] = len(pos_emps)
    db.snapshot_workflow.update_one({"id": snap_id}, {"$set": {"uploads": uploads}})

    try:
        # --- 1. Delete the ghost
        r = requests.delete(f"{API}/v2/employees/{ghost_id}", timeout=15)
        assert r.status_code == 200, f"delete failed: {r.status_code} {r.text[:200]}"
        print(f"[step1] Deleted ghost: {r.json()}")

        # --- 2. Edit liquor + NPS on survivor via the master PUT endpoint.
        # NPS edit triggers nps_manual_override=true so reprocess won't
        # redistribute store-level CV data over it.
        r = requests.put(
            f"{API}/v2/employees/{survivor_id}",
            json={"liquor_sales": 999.0, "beer_sales": 88.0, "wine_sales": 77.0,
                  "nps_score": 87.5},
            timeout=20,
        )
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text[:200]}"
        print(f"[step2] PUT liquor=999 beer=88 wine=77 nps=87.5")

        # --- 3. Save Snapshot: sync-from-employees + process
        r = requests.post(
            f"{API}/v2/snapshot-workflow/snapshots/{snap_id}/sync-from-employees",
            timeout=30,
        )
        assert r.status_code == 200, f"sync failed: {r.status_code} {r.text[:200]}"
        sync_payload = r.json()
        print(f"[step3a] sync result: {sync_payload}")
        time.sleep(0.5)

        # Re-process. Try /process first; if completed, /reprocess.
        for endpoint in ("process", "reprocess"):
            r = requests.post(
                f"{API}/v2/snapshot-workflow/snapshots/{snap_id}/{endpoint}",
                timeout=60,
            )
            if r.status_code == 200:
                print(f"[step3b] {endpoint} result: {r.json().get('employee_count')}")
                break
            print(f"[step3b] {endpoint} -> {r.status_code} {r.text[:120]}")

        time.sleep(0.5)

        # --- 4. Inspect rebuilt snapshot
        snap_doc = db.snapshot_workflow.find_one({"id": snap_id})
        emps = snap_doc.get("employees") or []
        survivors = [e for e in emps if e.get("display_name") == survivor_name
                     or e.get("name") == survivor_name]
        ghosts = [e for e in emps if e.get("display_name") == ghost_name
                  or e.get("name") == ghost_name]

        print(f"[verify] survivors found: {len(survivors)}; ghosts found: {len(ghosts)}")

        # === Assertions ===
        assert len(ghosts) == 0, f"FAIL: ghost {ghost_name} resurrected after Save Snapshot!"
        assert len(survivors) == 1, f"FAIL: survivor count = {len(survivors)} (expected 1)"
        s = survivors[0]
        liq = float(s.get("liquor_sales") or 0)
        beer = float(s.get("beer_sales") or 0)
        wine = float(s.get("wine_sales") or 0)
        assert liq == 999.0, f"FAIL: liquor reverted to {liq} (expected 999.0)"
        assert beer == 88.0, f"FAIL: beer reverted to {beer} (expected 88.0)"
        assert wine == 77.0, f"FAIL: wine reverted to {wine} (expected 77.0)"
        # LBW total should reflect the new components
        lbw = float(s.get("lbw") or 0)
        assert abs(lbw - (999.0 + 88.0 + 77.0)) < 0.5, \
            f"FAIL: lbw total {lbw} != L+B+W = {999.0 + 88.0 + 77.0}"
        # NPS edit must survive store-level CV redistribution
        nps = float(s.get("nps_score") or 0)
        assert nps == 87.5, f"FAIL: NPS reverted to {nps} (expected 87.5)"
        assert s.get("nps_manual_override") is True, \
            "FAIL: nps_manual_override flag missing"

        # Also check pos_upload's parsed_data.employees has been pruned
        snap_doc2 = db.snapshot_workflow.find_one({"id": snap_id})
        pos_emps2 = next(
            (u.get("parsed_data", {}).get("employees", [])
             for u in snap_doc2.get("uploads", [])
             if u.get("upload_type") == "pos_report"),
            []
        )
        ghost_in_pos = [e for e in pos_emps2 if (e.get("name") or "").lower() == ghost_name.lower()]
        assert not ghost_in_pos, f"FAIL: ghost still in pos_upload.parsed_data.employees"

        print("\n✅ PASS — Save Snapshot fix works:")
        print(f"   - Ghost {ghost_name} stayed deleted")
        print(f"   - Survivor LBW edits (L=999, B=88, W=77) preserved")
        print(f"   - LBW total recomputed correctly: {lbw}")
        print(f"   - Survivor NPS edit ({nps}) survived CV redistribution")
        print(f"   - POS upload.parsed_data.employees pruned correctly")

    finally:
        # Cleanup
        db.employees_v2.delete_many({"id": {"$in": [survivor_id, ghost_id]}})
        db.snapshot_workflow.update_one(
            {"id": snap_id},
            {"$pull": {"employees": {"name": {"$in": [survivor_name, ghost_name]}}}}
        )
        # Clean ghost from any pos_upload list
        snap_doc = db.snapshot_workflow.find_one({"id": snap_id})
        for i, u in enumerate(snap_doc.get("uploads", [])):
            if u.get("upload_type") != "pos_report":
                continue
            emps = u.get("parsed_data", {}).get("employees", []) or []
            cleaned = [
                e for e in emps
                if (e.get("name") or "").strip().lower() not in
                {survivor_name.lower(), ghost_name.lower()}
            ]
            if len(cleaned) != len(emps):
                db.snapshot_workflow.update_one(
                    {"id": snap_id},
                    {"$set": {f"uploads.{i}.parsed_data.employees": cleaned}}
                )


if __name__ == "__main__":
    main()
