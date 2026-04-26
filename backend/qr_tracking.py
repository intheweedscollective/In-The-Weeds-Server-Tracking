"""
QR Track Hub - Isolated module for QR code tracking
Tracks employee QR code scans for Yelp and Google reviews
"""

import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
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
    # Get main employees
    main_employees = await _db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"name": 1}
    ).to_list(100)
    
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
                {"$inc": {field: 1}}
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
                {"$inc": {"tripadvisor_clicks": 1}}
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
                {"$inc": {"google_clicks": 1}}
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
    
    # Track asynchronously without waiting
    try:
        await _db.qr_scans.insert_one({
            "id": str(uuid.uuid4()),
            "employee_id": employee_id,
            "platform": "google",
            "scanned_at": datetime.now(timezone.utc).isoformat()
        })
    except:
        pass
    
    return RedirectResponse(url=GOOGLE_REVIEW_URL, status_code=302)

@qr_router.get("/scans")
async def get_recent_scans(limit: int = 50):
    """Get recent scans"""
    scans = await _db.qr_scans.find({}, {"_id": 0}).sort("scanned_at", -1).limit(limit).to_list(limit)
    return scans

@qr_router.delete("/scans/reset-all")
async def reset_all_qr_scans():
    """
    Reset ALL QR scan data:
    - Deletes all scan records from qr_scans collection
    - Resets all employee click counts to 0
    """
    # Delete all scan records
    scans_result = await _db.qr_scans.delete_many({})
    
    # Reset all employee click counts
    employees_result = await _db.qr_employees.update_many(
        {},
        {"$set": {"google_clicks": 0, "yelp_clicks": 0, "tripadvisor_clicks": 0}}
    )
    
    return {
        "success": True,
        "scans_deleted": scans_result.deleted_count,
        "employees_reset": employees_result.modified_count
    }


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
    main_employees = await _db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"name": 1}
    ).to_list(100)
    
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
    v2_emps = await _db.employees_v2.find(
        {"quarter": (quarter or "").upper(), "year": year},
        {"_id": 0, "name": 1, "display_name": 1, "report_name": 1,
         "rt_mentions": 1, "review_tracker_mentions": 1,
         "rt_yelp_mentions": 1, "rt_google_mentions": 1, "rt_tripadvisor_mentions": 1},
    ).to_list(500)

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

