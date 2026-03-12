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
    from fastapi.responses import RedirectResponse
    
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
            return RedirectResponse(url=redirect_url)
    
    return {"success": True, "message": f"Recorded {platform} scan for {employee.get('name')}"}

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


def register_qr_routes(app_router, db):
    """Set up the QR tracking module"""
    set_qr_db(db)
    app_router.include_router(qr_router)

