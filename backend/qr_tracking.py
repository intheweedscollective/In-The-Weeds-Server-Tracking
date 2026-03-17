"""
QR Track Hub - Isolated module for QR code tracking
Tracks employee QR code scans for Yelp and Google reviews
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid

# Pydantic models
class QREmployee(BaseModel):
    id: Optional[str] = None
    name: str
    yelp_clicks: int = 0
    google_clicks: int = 0
    created_at: Optional[str] = None

class QRSettings(BaseModel):
    yelp_url: str = ""
    google_url: str = ""
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
    platform: str  # 'yelp' or 'google'
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
    employees.sort(key=lambda x: (x.get('yelp_clicks', 0) + x.get('google_clicks', 0)), reverse=True)
    return employees

@qr_router.post("/employees")
async def create_qr_employee(employee: QREmployee):
    """Create a new QR employee"""
    emp_dict = employee.dict()
    emp_dict['id'] = str(uuid.uuid4())
    emp_dict['created_at'] = datetime.now(timezone.utc).isoformat()
    emp_dict['yelp_clicks'] = 0
    emp_dict['google_clicks'] = 0
    
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

@qr_router.post("/employees/{employee_id}/reset")
async def reset_qr_employee_clicks(employee_id: str):
    """Reset an employee's click counts"""
    await _db.qr_employees.update_one(
        {"id": employee_id},
        {"$set": {"yelp_clicks": 0, "google_clicks": 0}}
    )
    return {"success": True}


# ==================== SCAN TRACKING ====================

@qr_router.get("/scan/{employee_id}/{platform}")
async def track_scan(employee_id: str, platform: str):
    """Track a QR code scan and redirect to review page"""
    from fastapi.responses import RedirectResponse, HTMLResponse
    
    if platform not in ['yelp', 'google']:
        return {"error": "Invalid platform"}
    
    employee = await _db.qr_employees.find_one({"id": employee_id})
    if not employee:
        return {"error": "Employee not found"}
    
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
    
    settings = await _db.qr_settings.find_one({"id": "global_settings"})
    if settings:
        redirect_url = settings.get(f"{platform}_url", "")
        if redirect_url:
            return RedirectResponse(url=redirect_url, status_code=302)
    
    # If no URL configured, show a helpful message
    platform_name = "Google" if platform == "google" else "Yelp"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Thanks for scanning!</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; 
                   background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                   color: white; min-height: 100vh; margin: 0;
                   display: flex; align-items: center; justify-content: center; }}
            .card {{ background: rgba(255,255,255,0.1); border-radius: 16px;
                    padding: 32px; text-align: center; max-width: 320px; }}
            h1 {{ font-size: 24px; margin-bottom: 16px; }}
            p {{ color: #94a3b8; line-height: 1.6; }}
            .name {{ color: #22c55e; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>✓ Scan Recorded!</h1>
            <p>Thank you for scanning <span class="name">{employee.get('name')}</span>'s QR code.</p>
            <p style="margin-top: 16px; font-size: 14px;">
                {platform_name} review link not configured yet.<br>
                Please contact the manager.
            </p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@qr_router.get("/scans")
async def get_recent_scans(limit: int = 50):
    """Get recent scans"""
    scans = await _db.qr_scans.find({}, {"_id": 0}).sort("scanned_at", -1).limit(limit).to_list(limit)
    return scans


# ==================== SETTINGS ====================

@qr_router.get("/settings")
async def get_qr_settings():
    """Get QR settings"""
    settings = await _db.qr_settings.find_one({"id": "global_settings"}, {"_id": 0})
    if not settings:
        return {
            "id": "global_settings",
            "yelp_url": "",
            "google_url": "",
            "qr_style": "circle",
            "qr_color": "#000000",
            "qr_bg_color": "#FFFFFF",
            "qr_frame": "rounded",
            "qr_frame_color": "#000000",
            "qr_logo": "shrimp_icon",
            "qr_size": 300
        }
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
    total_scans = total_yelp + total_google
    
    employees.sort(key=lambda x: (x.get('yelp_clicks', 0) + x.get('google_clicks', 0)), reverse=True)
    top_10 = employees[:10]
    
    return {
        "total_scans": total_scans,
        "yelp_scans": total_yelp,
        "google_scans": total_google,
        "total_employees": len(employees),
        "top_10": [{
            "name": e.get('name'),
            "yelp_clicks": e.get('yelp_clicks', 0),
            "google_clicks": e.get('google_clicks', 0),
            "total": e.get('yelp_clicks', 0) + e.get('google_clicks', 0)
        } for e in top_10]
    }

@qr_router.get("/top10")
async def get_top_10_scans():
    """Get top 10 employees by total scans - for dashboard integration"""
    employees = await _db.qr_employees.find({}, {"_id": 0}).to_list(100)
    employees.sort(key=lambda x: (x.get('yelp_clicks', 0) + x.get('google_clicks', 0)), reverse=True)
    
    return [{
        "rank": i + 1,
        "name": e.get('name'),
        "yelp_clicks": e.get('yelp_clicks', 0),
        "google_clicks": e.get('google_clicks', 0),
        "total": e.get('yelp_clicks', 0) + e.get('google_clicks', 0)
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
    
    # Get base URL from environment or use default
    base_url = os.environ.get("REACT_APP_BACKEND_URL", "https://staff-score-engine.preview.emergentagent.com")
    
    # Create a temporary file for the ZIP
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    
    try:
        with zipfile.ZipFile(temp_file.name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for emp in employees:
                emp_id = emp.get("id")
                emp_name = emp.get("name", "Unknown")
                
                # Create safe filename
                safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', emp_name)
                
                # Generate Yelp QR
                yelp_tracking_url = f"{base_url}/api/qr/scan/{emp_id}/yelp"
                yelp_qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=10,
                    border=2
                )
                yelp_qr.add_data(yelp_tracking_url)
                yelp_qr.make(fit=True)
                yelp_img = yelp_qr.make_image(fill_color=settings.get("qr_color", "#000000"), 
                                              back_color=settings.get("qr_bg_color", "#FFFFFF"))
                
                yelp_buffer = BytesIO()
                yelp_img.save(yelp_buffer, format='PNG')
                zip_file.writestr(f"{safe_name}_yelp_qr.png", yelp_buffer.getvalue())
                
                # Generate Google QR
                google_tracking_url = f"{base_url}/api/qr/scan/{emp_id}/google"
                google_qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=10,
                    border=2
                )
                google_qr.add_data(google_tracking_url)
                google_qr.make(fit=True)
                google_img = google_qr.make_image(fill_color=settings.get("qr_color", "#000000"),
                                                  back_color=settings.get("qr_bg_color", "#FFFFFF"))
                
                google_buffer = BytesIO()
                google_img.save(google_buffer, format='PNG')
                zip_file.writestr(f"{safe_name}_google_qr.png", google_buffer.getvalue())
        
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

