"""
QR Track Hub - Isolated module for QR code tracking
Tracks employee QR code scans for Yelp and Google reviews
"""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
import logging

# Pydantic models
class QREmployee(BaseModel):
    id: Optional[str] = None
    name: str
    yelp_clicks: int = 0
    google_clicks: int = 0
    tripadvisor_clicks: int = 0
    created_at: Optional[str] = None

class QRSettings(BaseModel):
    yelp_url: str = ""
    google_url: str = ""
    tripadvisor_url: str = ""
    qr_style: str = "circle"
    qr_color: str = "#000000"
    qr_bg_color: str = "#FFFFFF"
    qr_frame: str = "rounded"
    qr_frame_color: str = "#000000"
    qr_logo: str = "shrimp_icon"
    qr_size: int = 300

class ScanRecord(BaseModel):
    id: Optional[str] = None
    employee_id: str
    employee_name: str
    platform: str  # 'yelp', 'google' or 'tripadvisor'
    scanned_at: str
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None


# Global db reference - will be set by register_qr_routes
_db = None

def set_qr_db(db):
    global _db
    _db = db


# ---------------------------------------------------------------------------
# Auto-sync helper — keeps the qr_employees collection in step with the
# canonical employee list. Hooked into snapshot save / finalize / employee
# CRUD / merge so admins never need to click "Sync".
# ---------------------------------------------------------------------------
#
# Behaviour:
#   ADD     — every active canonical employee that isn't already in
#             qr_employees gets a fresh row with 0 clicks.
#   REMOVE  — qr_employees rows whose name doesn't resolve to an active
#             canonical record are archived (moved to qr_employees_archive
#             with an archived_at timestamp) so the click history is never
#             lost. Useful when someone gets terminated or merged.
#   MERGE   — if a duplicate qr row exists for someone who got merged via
#             `EmployeeService.merge_employees`, its clicks roll up onto
#             the survivor's qr row before the duplicate is archived.
#   NEVER   — touches click counters on rows that survive the sync.

async def auto_sync_qr_with_canonical(db=None) -> Dict[str, Any]:
    """Idempotent. Returns {added, archived, merged_clicks}."""
    target = db if db is not None else _db
    if target is None:
        return {"added": 0, "archived": 0, "merged_clicks": 0}

    from services.employee_service import EmployeeService
    svc = EmployeeService(target)

    # 1) Build canonical name index.
    canon_actives = await svc.list_active()
    canon_by_name: Dict[str, Dict[str, Any]] = {}
    for c in canon_actives:
        for n in [c.get("name"), c.get("display_name"),
                  c.get("report_name"), *(c.get("aliases") or [])]:
            key = (n or "").strip().lower()
            if key:
                canon_by_name.setdefault(key, c)

    # 2) Walk qr_employees: archive orphans, roll up duplicates.
    qr_rows = await target.qr_employees.find({}, {"_id": 0}).to_list(2000)
    keep_by_canonical_name: Dict[str, Dict[str, Any]] = {}
    archived = 0
    merged_clicks = 0

    for q in qr_rows:
        qname = (q.get("name") or "").strip()
        canon = canon_by_name.get(qname.lower())
        if not canon:
            # Orphan — archive.
            await target.qr_employees_archive.insert_one({
                **q,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "archived_reason": "no_canonical_match",
            })
            await target.qr_employees.delete_one({"id": q["id"]})
            archived += 1
            continue

        canonical_name_key = (canon.get("name") or "").lower()
        survivor = keep_by_canonical_name.get(canonical_name_key)
        if survivor is None:
            # First qr row for this canonical employee → make it survivor
            # and ensure its display name matches the canonical record.
            if qname != canon.get("name"):
                await target.qr_employees.update_one(
                    {"id": q["id"]},
                    {"$set": {"name": canon.get("name")}},
                )
                q["name"] = canon.get("name")
            keep_by_canonical_name[canonical_name_key] = q
        else:
            # Roll duplicate's clicks onto the survivor, then archive.
            survivor_id = survivor["id"]
            inc = {
                "yelp_clicks":       int(q.get("yelp_clicks") or 0),
                "google_clicks":     int(q.get("google_clicks") or 0),
                "tripadvisor_clicks":int(q.get("tripadvisor_clicks") or 0),
            }
            if any(inc.values()):
                await target.qr_employees.update_one(
                    {"id": survivor_id}, {"$inc": inc}
                )
                merged_clicks += sum(inc.values())
                survivor["yelp_clicks"] = (survivor.get("yelp_clicks") or 0) + inc["yelp_clicks"]
                survivor["google_clicks"] = (survivor.get("google_clicks") or 0) + inc["google_clicks"]
                survivor["tripadvisor_clicks"] = (survivor.get("tripadvisor_clicks") or 0) + inc["tripadvisor_clicks"]
            await target.qr_employees_archive.insert_one({
                **q,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "archived_reason": "duplicate_of_" + survivor_id,
            })
            await target.qr_employees.delete_one({"id": q["id"]})
            archived += 1

    # 3) Add missing canonical employees.
    added = 0
    for canon in canon_actives:
        key = (canon.get("name") or "").lower()
        if key in keep_by_canonical_name:
            continue
        new_row = {
            "id": str(uuid.uuid4()),
            "name": canon.get("name"),
            "yelp_clicks": 0,
            "google_clicks": 0,
            "tripadvisor_clicks": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await target.qr_employees.insert_one(new_row)
        keep_by_canonical_name[key] = new_row
        added += 1

    return {"added": added, "archived": archived, "merged_clicks": merged_clicks}


# Create QR router
qr_router = APIRouter(prefix="/qr", tags=["QR Tracking"])


# ==================== EMPLOYEES ====================

@qr_router.get("/employees")
async def get_qr_employees():
    """Get all QR employees sorted by total clicks"""
    employees = await _db.qr_employees.find({}, {"_id": 0}).to_list(100)
    employees.sort(key=lambda x: (x.get('yelp_clicks', 0) + x.get('google_clicks', 0) + x.get('tripadvisor_clicks', 0)), reverse=True)
    return employees

@qr_router.post("/employees")
async def create_qr_employee(employee: QREmployee):
    """Create a new QR employee"""
    emp_dict = employee.dict()
    emp_dict['id'] = str(uuid.uuid4())
    emp_dict['created_at'] = datetime.now(timezone.utc).isoformat()
    emp_dict['yelp_clicks'] = 0
    emp_dict['google_clicks'] = 0
    emp_dict['tripadvisor_clicks'] = 0
    
    await _db.qr_employees.insert_one(emp_dict)
    emp_dict.pop('_id', None)
    return emp_dict

@qr_router.post("/employees/bulk")
async def bulk_create_qr_employees(names: List[str]):
    """Bulk create QR employees from a list of names"""
    created = []
    for name in names:
        existing = await _db.qr_employees.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        if not existing:
            emp = {
                "id": str(uuid.uuid4()),
                "name": name.strip(),
                "yelp_clicks": 0,
                "google_clicks": 0,
                "tripadvisor_clicks": 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await _db.qr_employees.insert_one(emp)
            created.append(name)
    return {"created": len(created), "names": created}

@qr_router.delete("/employees/{employee_id}")
async def delete_qr_employee(employee_id: str):
    """Delete a QR employee"""
    result = await _db.qr_employees.delete_one({"id": employee_id})
    return {"deleted": result.deleted_count > 0}

@qr_router.put("/employees/{employee_id}/rename")
async def rename_qr_employee(employee_id: str, new_name: str):
    """Rename a QR employee (preserves click counts)"""
    result = await _db.qr_employees.update_one(
        {"id": employee_id},
        {"$set": {"name": new_name}}
    )
    return {"updated": result.modified_count > 0, "new_name": new_name}

@qr_router.post("/employees/sync-names-from-main")
async def sync_qr_names_from_main(quarter: str = "Q1", year: int = 2026):
    """
    Sync QR employee names to match main employee list.
    Matches by first name and updates to full name.
    Preserves all click counts.
    """
    # Get main employees (filtered through canonical service so terminated
    # employees don't get re-added to QR)
    from services.employee_service import EmployeeService
    main_employees = await _db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1}
    ).to_list(100)
    main_employees = await EmployeeService(_db).filter_active_only(main_employees)
    
    # Build first name -> full name mapping
    first_to_full = {}
    for emp in main_employees:
        full_name = emp.get('name', '')
        if ' ' in full_name:
            first_name = full_name.split()[0].lower()
            first_to_full[first_name] = full_name
    
    # Special cases for nicknames
    special_cases = {
        'keisha': 'Lakeisha Martin',
        'starwars': 'Starwars McKinnon-Herrera'
    }
    first_to_full.update(special_cases)
    
    # Get QR employees
    qr_employees = await _db.qr_employees.find({}).to_list(500)
    
    updated = []
    added = []
    
    for emp in qr_employees:
        qr_name = emp.get('name', '')
        qr_name_lower = qr_name.lower().strip()
        
        # If first-name only, try to match to full name
        if ' ' not in qr_name and qr_name_lower in first_to_full:
            new_name = first_to_full[qr_name_lower]
            await _db.qr_employees.update_one(
                {"id": emp["id"]},
                {"$set": {"name": new_name}}
            )
            updated.append({
                "old": qr_name,
                "new": new_name,
                "clicks": emp.get('google_clicks', 0) + emp.get('yelp_clicks', 0) + emp.get('tripadvisor_clicks', 0)
            })
    
    # Check for missing employees and add them
    qr_names_lower = set()
    for emp in await _db.qr_employees.find({}).to_list(500):
        qr_names_lower.add(emp.get('name', '').lower())
    
    for emp in main_employees:
        full_name = emp.get('name', '')
        if full_name.lower() not in qr_names_lower:
            new_emp = {
                "id": str(uuid.uuid4()),
                "name": full_name,
                "yelp_clicks": 0,
                "google_clicks": 0,
                "tripadvisor_clicks": 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await _db.qr_employees.insert_one(new_emp)
            added.append(full_name)
    
    return {
        "success": True,
        "renamed": len(updated),
        "added": len(added),
        "details": {
            "renamed_employees": updated,
            "added_employees": added
        }
    }

@qr_router.post("/employees/cleanup")
async def cleanup_qr_employees():
    """
    Clean up invalid QR employees:
    - Remove entries like 'TOTAL', 'OVERALL'
    - Remove OCR error duplicates
    - Keep only valid employee names
    """
    employees = await _db.qr_employees.find({}, {"_id": 0}).to_list(500)
    
    # Invalid names to delete
    invalid_patterns = ['total', 'overall', 'total / overall']
    
    # OCR error patterns
    ocr_errors = ['planoarte', 'dhaka!', 'crandah', 'crandah']
    
    to_delete = []
    seen_normalized = set()
    
    for emp in employees:
        name = emp.get('name', '').strip()
        name_lower = name.lower()
        
        # Check if invalid
        if name_lower in invalid_patterns:
            to_delete.append({'id': emp['id'], 'name': name, 'reason': 'Invalid name'})
            continue
        
        # Check for OCR errors
        has_error = False
        for error in ocr_errors:
            if error in name_lower:
                to_delete.append({'id': emp['id'], 'name': name, 'reason': 'OCR error'})
                has_error = True
                break
        if has_error:
            continue
        
        # Normalize name for duplicate check
        normalized = name_lower.replace('—', '-').replace('–', '-').replace('é', 'e')
        
        if normalized in seen_normalized:
            to_delete.append({'id': emp['id'], 'name': name, 'reason': 'Duplicate'})
            continue
        
        seen_normalized.add(normalized)
    
    # Delete invalid entries
    deleted_count = 0
    for item in to_delete:
        result = await _db.qr_employees.delete_one({"id": item['id']})
        if result.deleted_count > 0:
            deleted_count += 1
    
    remaining = await _db.qr_employees.count_documents({})
    
    return {
        "deleted_count": deleted_count,
        "deleted_items": to_delete,
        "remaining_count": remaining
    }

@qr_router.post("/employees/{employee_id}/reset")
async def reset_qr_employee_clicks(employee_id: str):
    """Reset an employee's click counts"""
    await _db.qr_employees.update_one(
        {"id": employee_id},
        {"$set": {"yelp_clicks": 0, "google_clicks": 0, "tripadvisor_clicks": 0}}
    )
    return {"success": True}


# ==================== SCAN TRACKING ====================

# Review URLs - read from environment, with fallback
GOOGLE_REVIEW_URL = os.environ.get("GOOGLE_REVIEW_URL", "https://search.google.com/local/writereview?placeid=ChIJB6hQQjHEyIARLUX1F3jayRo")
TRIPADVISOR_REVIEW_URL = os.environ.get("TRIPADVISOR_REVIEW_URL", "https://www.tripadvisor.com/UserReview")

@qr_router.get("/scan/{employee_id}/{platform}")
async def track_scan(employee_id: str, platform: str):
    """Track a QR code scan and redirect to review page"""
    from fastapi.responses import RedirectResponse
    
    # Default to Google if platform is invalid
    if platform not in ['yelp', 'google', 'tripadvisor']:
        platform = 'google'
    
    # Try to track the scan (but don't fail if employee not found)
    try:
        employee = await _db.qr_employees.find_one({"id": employee_id})
        if employee:
            field = f"{platform}_clicks"
            await _db.qr_employees.update_one(
                {"id": employee_id},
                {"$inc": {field: 1, "total_clicks": 1},
                 "$set": {"last_scan_at": datetime.now(timezone.utc).isoformat()}}
            )
            
            scan = {
                "id": str(uuid.uuid4()),
                "employee_id": employee_id,
                "employee_name": employee.get("name", "Unknown"),
                "platform": platform,
                "scanned_at": datetime.now(timezone.utc).isoformat()
            }
            await _db.qr_scans.insert_one(scan)
    except Exception as e:
        # Log but don't fail - redirect is more important
        logging.error(f"Failed to track scan: {e}")
    
    # Get redirect URL - use settings if available, otherwise env/hardcoded fallback
    # Platform-specific default ensures tripadvisor doesn't fall through to Google.
    platform_defaults = {
        "google": GOOGLE_REVIEW_URL,
        "tripadvisor": TRIPADVISOR_REVIEW_URL,
        "yelp": "",
    }
    redirect_url = platform_defaults.get(platform) or GOOGLE_REVIEW_URL
    
    try:
        settings = await _db.qr_settings.find_one({"id": "global_settings"})
        if settings:
            url = settings.get(f"{platform}_url", "")
            if url:
                redirect_url = url
    except Exception as e:
        logging.error(f"Failed to get settings: {e}")
    
    # ALWAYS redirect - never show an error page
    return RedirectResponse(url=redirect_url, status_code=302)


@qr_router.get("/ta/{employee_id}")
async def tripadvisor_scan_redirect(employee_id: str):
    """
    Simplified TripAdvisor QR scan endpoint - always redirects to TripAdvisor reviews.
    Mirrors /go/{id} behaviour for maximum compatibility.
    """
    from fastapi.responses import RedirectResponse
    
    try:
        employee = await _db.qr_employees.find_one({"id": employee_id})
        if employee:
            await _db.qr_employees.update_one(
                {"id": employee_id},
                {"$inc": {"tripadvisor_clicks": 1, "total_clicks": 1},
                 "$set": {"last_scan_at": datetime.now(timezone.utc).isoformat()}}
            )
            await _db.qr_scans.insert_one({
                "id": str(uuid.uuid4()),
                "employee_id": employee_id,
                "employee_name": employee.get("name", "Unknown"),
                "platform": "tripadvisor",
                "scanned_at": datetime.now(timezone.utc).isoformat()
            })
            logging.info(f"QR scan tracked: {employee.get('name')} (tripadvisor)")
        else:
            logging.warning(f"QR scan: Employee not found: {employee_id}")
    except Exception as e:
        logging.error(f"QR scan tracking error: {e}")
    
    try:
        settings = await _db.qr_settings.find_one({"id": "global_settings"})
        if settings and settings.get("tripadvisor_url"):
            return RedirectResponse(url=settings["tripadvisor_url"], status_code=302)
    except Exception:
        pass
    
    return RedirectResponse(url=TRIPADVISOR_REVIEW_URL, status_code=302)


@qr_router.get("/go/{employee_id}")
async def quick_scan_redirect(employee_id: str):
    """
    Simplified QR scan endpoint - always redirects to Google reviews.
    Use this for maximum compatibility on all devices.
    """
    from fastapi.responses import RedirectResponse
    
    # Try to track (non-blocking)
    try:
        employee = await _db.qr_employees.find_one({"id": employee_id})
        if employee:
            await _db.qr_employees.update_one(
                {"id": employee_id},
                {"$inc": {"google_clicks": 1, "total_clicks": 1},
                 "$set": {"last_scan_at": datetime.now(timezone.utc).isoformat()}}
            )
            await _db.qr_scans.insert_one({
                "id": str(uuid.uuid4()),
                "employee_id": employee_id,
                "employee_name": employee.get("name", "Unknown"),
                "platform": "google",
                "scanned_at": datetime.now(timezone.utc).isoformat()
            })
            logging.info(f"QR scan tracked: {employee.get('name')} (google)")
        else:
            logging.warning(f"QR scan: Employee not found: {employee_id}")
    except Exception as e:
        logging.error(f"QR scan tracking error: {e}")
    
    # Get URL from settings or use hardcoded fallback
    try:
        settings = await _db.qr_settings.find_one({"id": "global_settings"})
        if settings and settings.get("google_url"):
            return RedirectResponse(url=settings["google_url"], status_code=302)
    except:
        pass
    
    return RedirectResponse(url=GOOGLE_REVIEW_URL, status_code=302)


@qr_router.get("/r/{employee_id}")
async def ultra_simple_redirect(employee_id: str):
    """
    Ultra-simple redirect - minimal processing for maximum compatibility.
    Shortest possible URL path for QR codes.
    """
    from fastapi.responses import RedirectResponse

    # Track + ALSO increment the per-employee counter. The previous version
    # only inserted into qr_scans, leaving qr_employees.google_clicks frozen
    # at whatever value it had — which is why /api/qr/stats and the leader-
    # board kept showing stale numbers while the raw event log accumulated
    # new entries. Look up the employee so we can carry their name on the
    # raw scan record too (used by the Recent Activity feed).
    try:
        employee = await _db.qr_employees.find_one({"id": employee_id})
        if employee:
            await _db.qr_employees.update_one(
                {"id": employee_id},
                {"$inc": {"google_clicks": 1, "total_clicks": 1},
                 "$set": {"last_scan_at": datetime.now(timezone.utc).isoformat()}}
            )
            employee_name = employee.get("name", "Unknown")
        else:
            employee_name = "Unknown"
        await _db.qr_scans.insert_one({
            "id": str(uuid.uuid4()),
            "employee_id": employee_id,
            "employee_name": employee_name,
            "platform": "google",
            "scanned_at": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logging.error(f"/qr/r tracking error: {e}")
    
    return RedirectResponse(url=GOOGLE_REVIEW_URL, status_code=302)

@qr_router.get("/scans")
async def get_recent_scans(limit: int = 50):
    """Get recent scans"""
    scans = await _db.qr_scans.find({}, {"_id": 0}).sort("scanned_at", -1).limit(limit).to_list(limit)
    return scans

@qr_router.delete("/scans/reset-all")
async def reset_all_qr_scans():
    """
    Reset ALL QR scan data.

    - Archives every existing `qr_scans` event into `qr_scans_archive` before
      deletion so the data is recoverable. Each archived doc gets an
      `archived_at` timestamp and the same `archive_batch_id` so you can
      restore a specific reset.
    - Then deletes the live scan records and zeros every employee's
      `google_clicks` / `yelp_clicks` / `tripadvisor_clicks` / `total_clicks`.

    Why archive? The user reported losing accumulated engagement data after
    a reset. Production data should never be destroyed without a recovery
    path.
    """
    from datetime import datetime, timezone
    batch_id = str(uuid.uuid4())
    archived_at = datetime.now(timezone.utc).isoformat()

    # Copy every live scan into the archive (no-op if collection is empty).
    archived = 0
    cursor = _db.qr_scans.find({}, {"_id": 0})
    batch: List[Dict[str, Any]] = []
    async for scan in cursor:
        scan["archive_batch_id"] = batch_id
        scan["archived_at"] = archived_at
        batch.append(scan)
        if len(batch) >= 500:
            await _db.qr_scans_archive.insert_many(batch)
            archived += len(batch)
            batch.clear()
    if batch:
        await _db.qr_scans_archive.insert_many(batch)
        archived += len(batch)

    # Delete all live scan records.
    scans_result = await _db.qr_scans.delete_many({})

    # Reset all employee click counts (including total_clicks for completeness).
    employees_result = await _db.qr_employees.update_many(
        {},
        {"$set": {
            "google_clicks": 0,
            "yelp_clicks": 0,
            "tripadvisor_clicks": 0,
            "total_clicks": 0,
        }}
    )

    return {
        "success": True,
        "archive_batch_id": batch_id,
        "scans_archived": archived,
        "scans_deleted": scans_result.deleted_count,
        "employees_reset": employees_result.modified_count,
        "note": "Use POST /api/qr/scans/restore-archive with archive_batch_id to recover.",
    }


@qr_router.post("/scans/restore-archive")
async def restore_qr_archive(payload: Dict[str, Any]):
    """
    Restore a previously-archived batch of QR scans back into `qr_scans`
    and recompute every employee's click counters from the live data.

    Body: { "archive_batch_id": "<uuid from reset response>" }
          OR { "all": true } to restore EVERY archive batch.
    """
    batch_id = payload.get("archive_batch_id")
    if not batch_id and not payload.get("all"):
        raise HTTPException(
            status_code=400,
            detail="Provide `archive_batch_id` or `all: true`.",
        )

    query = {} if payload.get("all") else {"archive_batch_id": batch_id}
    restored = 0
    batch: List[Dict[str, Any]] = []
    async for scan in _db.qr_scans_archive.find(query, {"_id": 0}):
        scan.pop("archive_batch_id", None)
        scan.pop("archived_at", None)
        batch.append(scan)
        if len(batch) >= 500:
            await _db.qr_scans.insert_many(batch)
            restored += len(batch)
            batch.clear()
    if batch:
        await _db.qr_scans.insert_many(batch)
        restored += len(batch)

    # Drop the archive copy of what we just restored, since it lives back in
    # `qr_scans` now.
    await _db.qr_scans_archive.delete_many(query)

    # Rebuild counters from the now-restored live scans (delegates to the
    # same logic as the recompute-counters endpoint).
    counters_synced = await _rebuild_qr_counters_from_scans()

    return {
        "success": True,
        "scans_restored": restored,
        "counters_synced": counters_synced,
    }


@qr_router.post("/scans/recompute-counters")
async def recompute_qr_counters_endpoint():
    """
    Rebuild every `qr_employees` click counter from the raw `qr_scans`
    event log. Use this when the counters drift from reality — e.g. after
    a deploy that exposed a tracking-path bug, or before a board meeting.
    Idempotent and safe to re-run.
    """
    synced = await _rebuild_qr_counters_from_scans()
    return {"success": True, "employees_synced": synced}


@qr_router.get("/scans/archive-batches")
async def list_qr_scan_archives():
    """List archive batches available for restore."""
    pipeline = [
        {"$group": {
            "_id": "$archive_batch_id",
            "scan_count": {"$sum": 1},
            "archived_at": {"$max": "$archived_at"},
            "earliest_scan": {"$min": "$scanned_at"},
            "latest_scan": {"$max": "$scanned_at"},
        }},
        {"$sort": {"archived_at": -1}},
    ]
    out = []
    async for row in _db.qr_scans_archive.aggregate(pipeline):
        out.append({
            "archive_batch_id": row["_id"],
            "scan_count": row["scan_count"],
            "archived_at": row.get("archived_at"),
            "earliest_scan": row.get("earliest_scan"),
            "latest_scan": row.get("latest_scan"),
        })
    return {"batches": out}


async def _rebuild_qr_counters_from_scans() -> int:
    """
    Recompute google/yelp/tripadvisor/total_clicks on `qr_employees` from
    the raw `qr_scans` event log. Returns the number of employees synced.
    Internal helper, used by /scans/recompute-counters and the archive
    restore endpoint.
    """
    pipeline = [
        {"$group": {
            "_id": {"emp": "$employee_id", "platform": "$platform"},
            "count": {"$sum": 1},
            "last": {"$max": "$scanned_at"},
        }},
    ]
    by_emp: Dict[str, Dict[str, Any]] = {}
    async for row in _db.qr_scans.aggregate(pipeline):
        emp_id = row["_id"]["emp"]
        platform = (row["_id"]["platform"] or "google").lower()
        if not emp_id:
            continue
        entry = by_emp.setdefault(emp_id, {})
        if platform in {"google", "yelp", "tripadvisor"}:
            entry[f"{platform}_clicks"] = row["count"]
        last = row["last"]
        if last and last > entry.get("last_scan_at", ""):
            entry["last_scan_at"] = last

    # Zero everyone, then write the rebuilt counts. Without the zero pass
    # an employee whose last scan was deleted would keep their old number.
    await _db.qr_employees.update_many(
        {},
        {"$set": {"google_clicks": 0, "yelp_clicks": 0, "tripadvisor_clicks": 0, "total_clicks": 0}},
    )

    synced = 0
    for emp_id, entry in by_emp.items():
        google = entry.get("google_clicks", 0)
        yelp = entry.get("yelp_clicks", 0)
        ta = entry.get("tripadvisor_clicks", 0)
        update = {
            "google_clicks": google,
            "yelp_clicks": yelp,
            "tripadvisor_clicks": ta,
            "total_clicks": google + yelp + ta,
        }
        if entry.get("last_scan_at"):
            update["last_scan_at"] = entry["last_scan_at"]
        r = await _db.qr_employees.update_one({"id": emp_id}, {"$set": update})
        if r.matched_count:
            synced += 1
    return synced


# ==================== SETTINGS ====================

@qr_router.get("/settings")
async def get_qr_settings():
    """Get QR settings"""
    settings = await _db.qr_settings.find_one({"id": "global_settings"}, {"_id": 0})
    defaults = {
        "id": "global_settings",
        "yelp_url": "",
        "google_url": "",
        "tripadvisor_url": "",
        "qr_style": "circle",
        "qr_color": "#000000",
        "qr_bg_color": "#FFFFFF",
        "qr_frame": "rounded",
        "qr_frame_color": "#000000",
        "qr_logo": "shrimp_icon",
        "qr_size": 300
    }
    if not settings:
        return defaults
    # Backfill any missing fields (e.g. older docs without tripadvisor_url)
    for k, v in defaults.items():
        settings.setdefault(k, v)
    return settings

@qr_router.post("/settings")
async def update_qr_settings(settings: QRSettings):
    """Update QR settings"""
    settings_dict = settings.dict()
    settings_dict['id'] = 'global_settings'
    settings_dict['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    await _db.qr_settings.update_one(
        {"id": "global_settings"},
        {"$set": settings_dict},
        upsert=True
    )
    return {"success": True}


# ==================== STATISTICS ====================

@qr_router.get("/stats")
async def get_qr_stats():
    """Get QR tracking statistics"""
    employees = await _db.qr_employees.find({}, {"_id": 0}).to_list(100)
    
    total_yelp = sum(e.get('yelp_clicks', 0) for e in employees)
    total_google = sum(e.get('google_clicks', 0) for e in employees)
    total_tripadvisor = sum(e.get('tripadvisor_clicks', 0) for e in employees)
    total_scans = total_yelp + total_google + total_tripadvisor
    
    employees.sort(key=lambda x: (x.get('yelp_clicks', 0) + x.get('google_clicks', 0) + x.get('tripadvisor_clicks', 0)), reverse=True)
    top_10 = employees[:10]
    
    return {
        "total_scans": total_scans,
        "yelp_scans": total_yelp,
        "google_scans": total_google,
        "tripadvisor_scans": total_tripadvisor,
        "total_employees": len(employees),
        "top_10": [{
            "name": e.get('name'),
            "yelp_clicks": e.get('yelp_clicks', 0),
            "google_clicks": e.get('google_clicks', 0),
            "tripadvisor_clicks": e.get('tripadvisor_clicks', 0),
            "total": e.get('yelp_clicks', 0) + e.get('google_clicks', 0) + e.get('tripadvisor_clicks', 0)
        } for e in top_10]
    }

@qr_router.get("/top10")
async def get_top_10_scans():
    """Get top 10 employees by total scans - for dashboard integration"""
    employees = await _db.qr_employees.find({}, {"_id": 0}).to_list(100)
    employees.sort(key=lambda x: (x.get('yelp_clicks', 0) + x.get('google_clicks', 0) + x.get('tripadvisor_clicks', 0)), reverse=True)
    
    return [{
        "rank": i + 1,
        "name": e.get('name'),
        "yelp_clicks": e.get('yelp_clicks', 0),
        "google_clicks": e.get('google_clicks', 0),
        "tripadvisor_clicks": e.get('tripadvisor_clicks', 0),
        "total": e.get('yelp_clicks', 0) + e.get('google_clicks', 0) + e.get('tripadvisor_clicks', 0)
    } for i, e in enumerate(employees[:10])]


# ==================== SYNC WITH MAIN EMPLOYEES ====================

@qr_router.post("/sync-from-employees")
async def sync_qr_from_main_employees(quarter: str = "Q1", year: int = 2026):
    """Sync QR employees from main employee list"""
    # Phase 2B: route through canonical EmployeeService — terminated /
    # merged employees never get propagated into QR.
    from services.employee_service import EmployeeService
    main_employees = await _db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1}
    ).to_list(100)
    main_employees = await EmployeeService(_db).filter_active_only(main_employees)
    
    created = 0
    for emp in main_employees:
        name = emp.get('name', '').strip()
        if not name:
            continue
        
        existing = await _db.qr_employees.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        if not existing:
            qr_emp = {
                "id": str(uuid.uuid4()),
                "name": name,
                "yelp_clicks": 0,
                "google_clicks": 0,
                "tripadvisor_clicks": 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await _db.qr_employees.insert_one(qr_emp)
            created += 1
    
    return {"success": True, "synced": created, "total_main": len(main_employees)}


# ==================== DOWNLOAD ALL QR CODES ====================

@qr_router.get("/download-all-zip")
async def download_all_qr_codes_zip():
    """
    Generate and download a ZIP file containing all QR codes.
    This endpoint serves the file with proper headers for iOS Safari compatibility.
    """
    import qrcode
    from io import BytesIO
    import zipfile
    from fastapi.responses import StreamingResponse
    import re
    import tempfile
    import os
    
    # Get settings
    settings = await _db.qr_settings.find_one({}, {"_id": 0})
    if not settings:
        settings = {
            "yelp_url": "",
            "google_url": "",
            "qr_color": "#000000",
            "qr_bg_color": "#FFFFFF"
        }
    
    # Get all employees
    employees = await _db.qr_employees.find({}, {"_id": 0}).to_list(500)
    
    if not employees:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content={"error": "No employees found"},
            status_code=404
        )
    
    # Get base URL from environment (try BACKEND_URL first, then REACT_APP_BACKEND_URL)
    base_url = os.environ.get("BACKEND_URL") or os.environ.get("REACT_APP_BACKEND_URL", "")
    
    # Create a temporary file for the ZIP
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    
    try:
        with zipfile.ZipFile(temp_file.name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Platform -> URL-path mapping for tracking endpoints.
            platforms = [
                ("google", lambda eid: f"{base_url}/api/qr/go/{eid}"),
                ("yelp", lambda eid: f"{base_url}/api/qr/scan/{eid}/yelp"),
                ("tripadvisor", lambda eid: f"{base_url}/api/qr/ta/{eid}"),
            ]
            for emp in employees:
                emp_id = emp.get("id")
                emp_name = emp.get("name", "Unknown")
                safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', emp_name)

                for platform, url_builder in platforms:
                    tracking_url = url_builder(emp_id)
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_H,
                        box_size=10,
                        border=2
                    )
                    qr.add_data(tracking_url)
                    qr.make(fit=True)
                    img = qr.make_image(
                        fill_color=settings.get("qr_color", "#000000"),
                        back_color=settings.get("qr_bg_color", "#FFFFFF"),
                    )
                    buf = BytesIO()
                    img.save(buf, format='PNG')
                    zip_file.writestr(f"{safe_name}_{platform}_qr.png", buf.getvalue())
        
        # Read the file and create streaming response
        def iterfile():
            with open(temp_file.name, mode="rb") as file_like:
                yield from file_like
            # Clean up temp file after streaming
            os.unlink(temp_file.name)
        
        file_size = os.path.getsize(temp_file.name)
        
        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": 'attachment; filename="qr_codes.zip"',
                "Content-Length": str(file_size),
                "Content-Type": "application/octet-stream",
                "Cache-Control": "private, no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Content-Type-Options": "nosniff",
                "Accept-Ranges": "bytes"
            }
        )
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        raise


def register_qr_routes(app_router, db):
    """Set up the QR tracking module"""
    set_qr_db(db)
    app_router.include_router(qr_router)


@qr_router.get("/leaderboard/slide")
async def download_qr_leaderboard_slide(
    quarter: str = "Q2",
    year: int = 2026,
    title: str | None = None,
):
    """Render and return a 16:9 PNG of the QR Click vs RT-Mentions report."""
    from fastapi.responses import Response
    from qr_leaderboard_slide import generate_qr_leaderboard_slide

    qr_emps = await _db.qr_employees.find({}, {"_id": 0}).to_list(500)

    # Merge ReviewTracker mentions from employees_v2 (which is where RT
    # mentions are persisted by the snapshot pipeline). We index by
    # lowercased name for forgiving cross-collection matching.
    # Phase 2B: filter v2 readers through canonical service.
    from services.employee_service import EmployeeService
    v2_emps = await _db.employees_v2.find(
        {"quarter": (quarter or "").upper(), "year": year},
        {"_id": 0, "name": 1, "display_name": 1, "report_name": 1,
         "rt_mentions": 1, "review_tracker_mentions": 1,
         "rt_yelp_mentions": 1, "rt_google_mentions": 1, "rt_tripadvisor_mentions": 1},
    ).to_list(500)
    v2_emps = await EmployeeService(_db).filter_active_only(v2_emps)

    def keys_for(rec):
        out = set()
        for f in ("name", "display_name", "report_name"):
            v = (rec.get(f) or "").strip().lower()
            if v:
                out.add(v)
                # Also add first name for nickname tolerance
                first = v.split()[0]
                if first:
                    out.add(first)
        return out

    v2_index: dict[str, dict] = {}
    for v in v2_emps:
        for k in keys_for(v):
            v2_index.setdefault(k, v)

    # Make sure every employees_v2 person appears (even those with 0 clicks)
    # so the slide truly lists ALL employees.
    qr_index: dict[str, dict] = {}
    for q in qr_emps:
        for k in keys_for(q):
            qr_index.setdefault(k, q)

    # Build the merged list keyed by name
    seen_keys: set[str] = set()
    merged: list[dict] = []

    def absorb(rec, mentions_record):
        # Augment a copy with rt_mentions fields from v2
        out = dict(rec)
        if mentions_record:
            for f in ("rt_mentions", "review_tracker_mentions",
                      "rt_yelp_mentions", "rt_google_mentions",
                      "rt_tripadvisor_mentions"):
                if mentions_record.get(f) is not None:
                    out[f] = mentions_record.get(f)
        return out

    # Pass 1: all qr_employees first (preserves their click data)
    for q in qr_emps:
        ks = keys_for(q)
        if not ks:
            continue
        if any(k in seen_keys for k in ks):
            continue
        seen_keys.update(ks)
        v2_match = next((v2_index[k] for k in ks if k in v2_index), None)
        merged.append(absorb(q, v2_match))

    # Pass 2: employees_v2 records that weren't in qr_employees
    for v in v2_emps:
        ks = keys_for(v)
        if not ks:
            continue
        if any(k in seen_keys for k in ks):
            continue
        seen_keys.update(ks)
        merged.append(absorb({
            "name": v.get("display_name") or v.get("name") or v.get("report_name"),
            "yelp_clicks": 0, "google_clicks": 0, "tripadvisor_clicks": 0,
        }, v))

    png = generate_qr_leaderboard_slide(merged, quarter=quarter, year=year, title=title)
    safe_q = (quarter or "Q").replace("/", "_")
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="qr_clicks_vs_mentions_{safe_q}_{year}.png"'
        },
    )


@qr_router.get("/leaderboard-data")
async def get_leaderboard_with_mentions(
    quarter: str = "Q2",
    year: int = 2026,
):
    """
    Returns the merged clicks-vs-mentions list used by both the on-screen
    leaderboard and the downloadable slide. Every employee from
    qr_employees AND employees_v2 (for the given quarter/year) appears
    exactly once, with both click counts and review mention counts
    populated. Sorted by conversion rate desc -> mentions desc -> clicks
    desc so the same row order shows up in the UI and the PNG.
    """
    qr_emps = await _db.qr_employees.find({}, {"_id": 0}).to_list(500)
    from services.employee_service import EmployeeService
    v2_emps = await _db.employees_v2.find(
        {"quarter": (quarter or "").upper(), "year": year},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1, "report_name": 1,
         "rt_mentions": 1, "review_tracker_mentions": 1,
         "rt_yelp_mentions": 1, "rt_google_mentions": 1, "rt_tripadvisor_mentions": 1},
    ).to_list(500)
    v2_emps = await EmployeeService(_db).filter_active_only(v2_emps)

    def keys_for(rec):
        out = set()
        for f in ("name", "display_name", "report_name"):
            v = (rec.get(f) or "").strip().lower()
            if v:
                out.add(v)
                first = v.split()[0]
                if first:
                    out.add(first)
        return out

    v2_index: dict[str, dict] = {}
    for v in v2_emps:
        for k in keys_for(v):
            v2_index.setdefault(k, v)

    seen_keys: set[str] = set()
    merged: list[dict] = []

    def mentions_total(v2_rec):
        if not v2_rec:
            return 0
        return int(
            (v2_rec.get("rt_mentions") or 0)
            + (v2_rec.get("review_tracker_mentions") or 0)
            + (v2_rec.get("rt_yelp_mentions") or 0)
            + (v2_rec.get("rt_google_mentions") or 0)
            + (v2_rec.get("rt_tripadvisor_mentions") or 0)
        )

    # Pass 1: every qr_employee (with their clicks) merged with v2 mentions
    for q in qr_emps:
        ks = keys_for(q)
        if not ks or any(k in seen_keys for k in ks):
            continue
        seen_keys.update(ks)
        v2_match = next((v2_index[k] for k in ks if k in v2_index), None)
        yelp = q.get("yelp_clicks") or 0
        google = q.get("google_clicks") or 0
        ta = q.get("tripadvisor_clicks") or 0
        clicks = yelp + google + ta
        m = mentions_total(v2_match)
        merged.append({
            "id": q.get("id"),
            "name": q.get("name"),
            "yelp_clicks": yelp,
            "google_clicks": google,
            "tripadvisor_clicks": ta,
            "total_clicks": clicks,
            "rt_mentions": m,
            "conversion_rate": round((m / clicks * 100), 1) if clicks else 0.0,
        })

    # Pass 2: employees_v2 records absent from qr_employees (clicks=0)
    for v in v2_emps:
        ks = keys_for(v)
        if not ks or any(k in seen_keys for k in ks):
            continue
        seen_keys.update(ks)
        m = mentions_total(v)
        merged.append({
            "id": v.get("id"),
            "name": v.get("display_name") or v.get("name") or v.get("report_name"),
            "yelp_clicks": 0,
            "google_clicks": 0,
            "tripadvisor_clicks": 0,
            "total_clicks": 0,
            "rt_mentions": m,
            "conversion_rate": 0.0,
        })

    # Sort: conversion rate desc -> mentions desc -> clicks desc.
    # Employees with 0 clicks pinned to the bottom regardless of mentions.
    merged.sort(
        key=lambda e: (
            -1 if e["total_clicks"] == 0 else e["conversion_rate"],
            e["rt_mentions"],
            e["total_clicks"],
        ),
        reverse=True,
    )
    return {"employees": merged, "quarter": quarter.upper(), "year": year, "count": len(merged)}


