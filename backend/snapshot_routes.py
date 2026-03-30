"""
Snapshot API Routes
Implements snapshot-first workflow endpoints.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel

from snapshot_manager import (
    SnapshotStatus,
    UploadType,
    UploadStatus,
    SnapshotCreate,
    SnapshotUpdate,
    create_snapshot_record,
    create_upload_record,
    calculate_upload_progress,
    can_process_snapshot,
    format_snapshot_response,
    calculate_employee_scores,
    assign_performance_tiers,
)

logger = logging.getLogger(__name__)

# Router will be included in main server.py
snapshot_router = APIRouter(prefix="/v2/snapshot-workflow", tags=["Snapshot Workflow"])


def get_db():
    """Get database instance - will be set by main server"""
    from server import db
    return db


# ============================================================================
# SNAPSHOT CRUD
# ============================================================================

@snapshot_router.post("/snapshots", response_model=Dict[str, Any])
async def create_snapshot(data: SnapshotCreate):
    """
    Create a new snapshot in Draft status.
    This is the first step in the snapshot workflow.
    """
    db = get_db()
    
    # Create snapshot record
    snapshot = create_snapshot_record(data)
    
    # Insert into database
    await db.snapshot_workflow.insert_one(snapshot)
    
    logger.info(f"Created snapshot: {snapshot['id']} - {snapshot['name']}")
    
    return {
        "success": True,
        "snapshot": format_snapshot_response(snapshot),
        "message": f"Snapshot '{data.name}' created. Ready for uploads.",
        "next_step": "Upload POS Report to continue."
    }


@snapshot_router.get("/snapshots", response_model=List[Dict[str, Any]])
async def list_snapshots(
    quarter: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """
    List all snapshots with optional filters.
    Returns snapshots sorted by effective_date descending.
    """
    db = get_db()
    
    query = {}
    if quarter:
        query["quarter"] = quarter.upper()
    if year:
        query["year"] = year
    if status:
        query["status"] = status
    
    snapshots = await db.snapshot_workflow.find(
        query,
        {"_id": 0}
    ).sort("effective_date", -1).limit(limit).to_list(limit)
    
    # Determine which is the current snapshot
    current_id = await get_current_snapshot_id(db)
    
    return [
        format_snapshot_response(s, is_current=(s.get("id") == current_id))
        for s in snapshots
    ]


@snapshot_router.get("/snapshots/{snapshot_id}", response_model=Dict[str, Any])
async def get_snapshot(snapshot_id: str):
    """Get a specific snapshot by ID with full details."""
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one(
        {"id": snapshot_id},
        {"_id": 0}
    )
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    current_id = await get_current_snapshot_id(db)
    
    return format_snapshot_response(snapshot, is_current=(snapshot_id == current_id))


@snapshot_router.patch("/snapshots/{snapshot_id}", response_model=Dict[str, Any])
async def update_snapshot(snapshot_id: str, data: SnapshotUpdate):
    """Update snapshot metadata (only allowed for Draft/In Progress)."""
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] in [SnapshotStatus.COMPLETED.value, SnapshotStatus.PROCESSING.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot modify snapshot in {snapshot['status']} status"
        )
    
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {"$set": update_data}
    )
    
    updated = await db.snapshot_workflow.find_one({"id": snapshot_id}, {"_id": 0})
    return format_snapshot_response(updated)


@snapshot_router.delete("/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str):
    """Delete a snapshot (only allowed for Draft/Failed)."""
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] == SnapshotStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a completed snapshot. Create a replacement instead."
        )
    
    await db.snapshot_workflow.delete_one({"id": snapshot_id})
    
    return {"success": True, "message": "Snapshot deleted"}


@snapshot_router.post("/snapshots/{snapshot_id}/unlock")
async def unlock_snapshot(snapshot_id: str):
    """
    Unlock a completed snapshot to allow editing.
    Changes status from 'completed' back to 'in_progress'.
    The snapshot retains its existing uploads and results.
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] != SnapshotStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Only completed snapshots can be unlocked. Current status: {snapshot['status']}"
        )
    
    # Update status to in_progress
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "status": SnapshotStatus.IN_PROGRESS.value,
                "unlocked_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    updated = await db.snapshot_workflow.find_one({"id": snapshot_id}, {"_id": 0})
    
    logger.info(f"Unlocked snapshot: {snapshot_id} for editing")
    
    return {
        "success": True,
        "message": "Snapshot unlocked for editing. You can now modify uploads and reprocess.",
        "snapshot": format_snapshot_response(updated)
    }


# ============================================================================
# SNAPSHOT UPLOADS
# ============================================================================

@snapshot_router.post("/snapshots/{snapshot_id}/upload/{upload_type}")
async def upload_to_snapshot(
    snapshot_id: str,
    upload_type: str,
    file: UploadFile = File(None),
    parsed_data: Optional[Dict[str, Any]] = Body(None),
    filename: Optional[str] = Body(None),
    source: Optional[str] = Body(None),
):
    """
    Upload a file to a specific snapshot.
    upload_type: pos_report, customer_voice, review_tracker
    
    Can accept either:
    - A file upload (multipart/form-data)
    - Pre-parsed data (JSON body with parsed_data, filename, source)
    """
    db = get_db()
    
    # Validate snapshot exists and is in correct status
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] == SnapshotStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot upload to a completed snapshot"
        )
    
    # Validate upload type
    try:
        upload_type_enum = UploadType(upload_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid upload type. Must be: {[t.value for t in UploadType]}"
        )
    
    # Handle file upload or pre-parsed data
    file_size = 0
    final_filename = filename or "unknown"
    final_parsed_data = parsed_data
    parse_error = None
    
    if file is not None:
        # Traditional file upload - read and parse
        contents = await file.read()
        file_size = len(contents)
        final_filename = file.filename
        
        try:
            if upload_type_enum == UploadType.POS_REPORT:
                final_parsed_data = await parse_pos_file(file.filename, contents)
            elif upload_type_enum == UploadType.CUSTOMER_VOICE:
                final_parsed_data = await parse_cv_file(file.filename, contents)
            elif upload_type_enum == UploadType.REVIEW_TRACKER:
                final_parsed_data = await parse_rt_file(file.filename, contents)
        except Exception as e:
            parse_error = str(e)
            logger.error(f"Parse error for {upload_type}: {e}")
    
    elif parsed_data is not None:
        # Pre-parsed data (e.g., from PDF background job)
        final_parsed_data = parsed_data
        logger.info(f"Received pre-parsed data for {upload_type}: {len(parsed_data.get('employees', []))} employees")
    
    else:
        raise HTTPException(status_code=400, detail="Either file or parsed_data is required")
    
    # Create upload record
    upload_record = create_upload_record(
        snapshot_id=snapshot_id,
        upload_type=upload_type_enum,
        filename=final_filename,
        file_size=file_size,
        parsed_data=final_parsed_data
    )
    
    if parse_error:
        upload_record["status"] = "failed"
        upload_record["error"] = parse_error
    else:
        upload_record["status"] = "parsed"
    
    # Update snapshot
    uploads = snapshot.get("uploads", [])
    
    # Remove existing upload of same type
    uploads = [u for u in uploads if u.get("upload_type") != upload_type]
    uploads.append(upload_record)
    
    # Update upload progress
    upload_progress = snapshot.get("upload_progress", {})
    upload_progress[upload_type] = final_parsed_data is not None and not parse_error
    
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "uploads": uploads,
                "upload_progress": upload_progress,
                "status": SnapshotStatus.IN_PROGRESS.value,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    logger.info(f"Upload {upload_type} to snapshot {snapshot_id}: {len(final_parsed_data.get('employees', [])) if final_parsed_data else 0} records")
    
    return {
        "success": not parse_error,
        "message": f"Uploaded {upload_type}" if not parse_error else f"Upload failed: {parse_error}",
        "upload_type": upload_type,
        "record_count": final_parsed_data.get("record_count", len(final_parsed_data.get("employees", []))) if final_parsed_data else 0,
        "status": upload_record["status"]
    }


@snapshot_router.post("/snapshots/{snapshot_id}/parsed-data/{upload_type}")
async def push_parsed_data_to_snapshot(
    snapshot_id: str,
    upload_type: str,
    data: Dict[str, Any]
):
    """
    Push pre-parsed data to a snapshot.
    Used for background job results (e.g., PDF OCR).
    
    Body should contain:
    - parsed_data: The parsed employee/review data
    - filename: Original filename
    - source: Source of data (e.g., 'pos_ocr_job')
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] == SnapshotStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Cannot modify a completed snapshot")
    
    try:
        upload_type_enum = UploadType(upload_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid upload type: {upload_type}")
    
    parsed_data = data.get("parsed_data", {})
    filename = data.get("filename", "background_job_result")
    source = data.get("source", "background_job")
    
    if not parsed_data:
        raise HTTPException(status_code=400, detail="parsed_data is required")
    
    # Create upload record
    upload_record = create_upload_record(
        snapshot_id=snapshot_id,
        upload_type=upload_type_enum,
        filename=filename,
        file_size=0,
        parsed_data=parsed_data
    )
    upload_record["source"] = source
    upload_record["status"] = "parsed"
    
    # Update snapshot
    uploads = snapshot.get("uploads", [])
    
    # Remove existing upload of same type
    uploads = [u for u in uploads if u.get("upload_type") != upload_type]
    uploads.append(upload_record)
    
    # Update upload progress
    upload_progress = snapshot.get("upload_progress", {})
    upload_progress[upload_type] = True
    
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "uploads": uploads,
                "upload_progress": upload_progress,
                "status": SnapshotStatus.IN_PROGRESS.value,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    logger.info(f"Pushed {len(parsed_data.get('employees', []))} employees to snapshot {snapshot_id}")
    
    return {
        "success": True,
        "message": f"Pushed {upload_type} data to snapshot",
        "record_count": parsed_data.get("record_count", len(parsed_data.get("employees", [])))
    }


@snapshot_router.get("/snapshots/{snapshot_id}/uploads")
async def get_snapshot_uploads(snapshot_id: str):
    """Get all uploads for a snapshot."""
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one(
        {"id": snapshot_id},
        {"_id": 0, "uploads": 1, "upload_progress": 1}
    )
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    can_process, missing = can_process_snapshot(snapshot)
    
    return {
        "uploads": snapshot.get("uploads", []),
        "upload_progress": snapshot.get("upload_progress", {}),
        "can_process": can_process,
        "missing_uploads": missing
    }


@snapshot_router.patch("/snapshots/{snapshot_id}/pos-employee/{employee_name}")
async def update_pos_employee_data(snapshot_id: str, employee_name: str, updates: dict):
    """
    Update POS data for a specific employee in the snapshot.
    Used to correct data errors before processing.
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id}, {"_id": 0})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    # Find POS upload
    uploads = snapshot.get("uploads", [])
    pos_upload_idx = next(
        (i for i, u in enumerate(uploads) if u.get("upload_type") == "pos_report"),
        None
    )
    
    if pos_upload_idx is None:
        raise HTTPException(status_code=404, detail="No POS upload found")
    
    pos_upload = uploads[pos_upload_idx]
    parsed_data = pos_upload.get("parsed_data", {})
    employees = parsed_data.get("employees", [])
    
    # Find employee by name (case-insensitive)
    employee_name_lower = employee_name.lower().strip()
    emp_idx = next(
        (i for i, e in enumerate(employees) if e.get("name", "").lower().strip() == employee_name_lower),
        None
    )
    
    if emp_idx is None:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_name}' not found in POS data")
    
    # Update employee data
    for key, value in updates.items():
        if key in ["ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc", 
                   "guest_count", "loyalty_sales", "lsc_count", "net_sales",
                   "liquor_sales", "beer_sales", "wine_sales"]:
            employees[emp_idx][key] = value
    
    # Recalculate LSC count if loyalty_sales is updated
    if "loyalty_sales" in updates and updates["loyalty_sales"]:
        employees[emp_idx]["lsc_count"] = round(updates["loyalty_sales"] / 25)
    
    # Recalculate guests_per_lsc if both guest_count and lsc_count are available
    if employees[emp_idx].get("lsc_count") and employees[emp_idx].get("guest_count"):
        employees[emp_idx]["guests_per_lsc"] = round(
            employees[emp_idx]["guest_count"] / employees[emp_idx]["lsc_count"], 2
        )
    
    # Update the snapshot
    parsed_data["employees"] = employees
    uploads[pos_upload_idx]["parsed_data"] = parsed_data
    
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "uploads": uploads,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    updated_emp = employees[emp_idx]
    logger.info(f"Updated POS data for {employee_name}: {updates}")
    
    return {
        "success": True,
        "message": f"Updated POS data for {employee_name}",
        "employee": {
            "name": updated_emp.get("name"),
            "guests_per_lsc": updated_emp.get("guests_per_lsc"),
            "lsc_count": updated_emp.get("lsc_count"),
            "loyalty_sales": updated_emp.get("loyalty_sales")
        }
    }



@snapshot_router.put("/employees/{employee_id}")
async def update_snapshot_employee(employee_id: str, updates: dict):
    """
    Update an employee in the current active snapshot.
    Used when Employee List tab edits an employee's data.
    """
    db = get_db()
    
    # Find current active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True},
        {"_id": 0}
    )
    
    if not snapshot:
        # Fallback to most recent completed snapshot
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed"},
            {"_id": 0},
            sort=[("completed_at", -1)]
        )
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="No active snapshot found")
    
    snapshot_id = snapshot["id"]
    employees = snapshot.get("employees", [])
    
    # Find employee by ID, name, display_name, or report_name (with fuzzy matching)
    emp_idx = None
    employee_id_lower = employee_id.lower().strip()
    
    for i, emp in enumerate(employees):
        emp_id = emp.get("id", "")
        emp_name = emp.get("name", "").lower().strip()
        emp_display = emp.get("display_name", "").lower().strip()
        emp_report = emp.get("report_name", "").lower().strip()
        
        # Exact ID match
        if emp_id == employee_id:
            emp_idx = i
            break
        
        # Exact name match (any of the name fields)
        if emp_name == employee_id_lower or emp_display == employee_id_lower or emp_report == employee_id_lower:
            emp_idx = i
            break
        
        # Partial match - check if search contains or is contained in any name field
        if (employee_id_lower in emp_name or emp_name in employee_id_lower or
            employee_id_lower in emp_display or emp_display in employee_id_lower or
            employee_id_lower in emp_report or emp_report in employee_id_lower):
            emp_idx = i
            break
        
        # First name match
        search_first = employee_id_lower.split()[0] if employee_id_lower else ""
        emp_first = emp_name.split()[0] if emp_name else ""
        report_first = emp_report.split()[0] if emp_report else ""
        
        if search_first and (search_first == emp_first or search_first == report_first or 
                            search_first == emp_display):
            emp_idx = i
            break
    
    if emp_idx is None:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found in snapshot")
    
    # Update allowed fields
    allowed_fields = [
        "name", "display_name", "report_name", "job_title", "tier_label",
        "ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc",
        "guest_count", "guests", "net_sales", "loyalty_sales", "lsc_count",
        "liquor_sales", "beer_sales", "wine_sales", "bar_glassware_sales", "lbw",
        "cv_promoters", "cv_passives", "cv_detractors", "cv_score",
        "rt_mentions", "review_tracker_bonus", "nps_score",
        "aliases"
    ]
    
    for key, value in updates.items():
        if key in allowed_fields:
            employees[emp_idx][key] = value
    
    # Recalculate derived values if needed
    emp = employees[emp_idx]
    
    # Handle field aliases
    if "guests" in updates:
        emp["guest_count"] = updates["guests"]
    if "glassware_sales" in updates:
        emp["bar_glassware_sales"] = updates["glassware_sales"]
    if "lbw" in updates:
        emp["lbw"] = updates["lbw"]
    if "review_mentions" in updates:
        emp["rt_mentions"] = updates["review_mentions"]
    if "display_name" in updates:
        emp["name"] = updates["display_name"]  # Sync name with display_name
    
    # Recalculate LBW from components if any L/B/W updated
    if any(k in updates for k in ["liquor_sales", "beer_sales", "wine_sales"]):
        liquor = emp.get("liquor_sales", 0) or 0
        beer = emp.get("beer_sales", 0) or 0
        wine = emp.get("wine_sales", 0) or 0
        emp["lbw"] = liquor + beer + wine
    
    # Recalculate LSC count if loyalty_sales updated
    if "loyalty_sales" in updates and updates["loyalty_sales"]:
        emp["lsc_count"] = round(updates["loyalty_sales"] / 25)
    
    # Recalculate per-guest metrics
    guest_count = emp.get("guest_count") or emp.get("guests") or 0
    if guest_count > 0:
        lbw = emp.get("lbw", 0) or 0
        glassware = emp.get("bar_glassware_sales") or emp.get("glassware_sales") or 0
        emp["lbw_per_guest"] = round(lbw / guest_count, 2)
        emp["glassware_per_guest"] = round(glassware / guest_count, 2)
    
    # Recalculate guests_per_lsc
    lsc_count = emp.get("lsc_count", 0) or 0
    if lsc_count > 0 and guest_count > 0:
        emp["guests_per_lsc"] = round(guest_count / lsc_count, 2)
    
    # Recalculate scores using the scoring formula
    from snapshot_manager import calculate_employee_scores, assign_performance_tiers
    
    # Default benchmarks
    benchmarks = {
        "ppa": 55.0,
        "lbw": 8.0,
        "glass": 1.25,
        "lsc": 100.0
    }
    
    # Update this employee's scores
    scored_emp = calculate_employee_scores(emp, benchmarks)
    employees[emp_idx] = scored_emp
    
    # Re-assign tiers for all employees (since one employee's score change affects tiers)
    employees = assign_performance_tiers(employees)
    
    # Update the snapshot
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "employees": employees,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Get the updated employee data
    updated_emp = next((e for e in employees if e.get("id") == employee_id or e.get("name", "").lower() == employee_id.lower()), scored_emp)
    
    logger.info(f"Updated employee {employee_id} in snapshot {snapshot_id}, new score: {updated_emp.get('total_score')}")
    
    return {
        "success": True,
        "message": f"Updated employee in snapshot",
        "employee": {k: v for k, v in updated_emp.items() if k != "_id"}
    }



@snapshot_router.post("/sync-job-titles")
async def sync_job_titles_from_legacy():
    """
    Sync job titles from employees_v2 to the current active snapshot.
    Used to restore trainer/bartender designations.
    """
    db = get_db()
    
    # Get current active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True},
        {"_id": 0}
    )
    
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed"},
            {"_id": 0},
            sort=[("completed_at", -1)]
        )
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="No active snapshot found")
    
    # Get job titles from employees_v2
    job_title_map = {}
    async for emp in db.employees_v2.find({}, {"_id": 0, "name": 1, "job_title": 1, "display_name": 1}):
        name = (emp.get('display_name') or emp.get('name', '')).lower().strip()
        jt = emp.get('job_title', 'Server')
        if name and jt and jt.lower() != 'server':
            job_title_map[name] = jt
            # Also add first name as key
            first_name = name.split()[0] if name else ''
            if first_name:
                job_title_map[first_name] = jt
    
    # Update employees in snapshot
    employees = snapshot.get('employees', [])
    updated_count = 0
    updates = []
    
    for emp in employees:
        name = emp.get('name', '').lower().strip()
        first_name = name.split()[0] if name else ''
        
        # Try to find matching job title
        new_jt = job_title_map.get(name) or job_title_map.get(first_name)
        if new_jt:
            old_jt = emp.get('job_title', 'Server')
            emp['job_title'] = new_jt
            updates.append(f"{emp['name']}: {old_jt} -> {new_jt}")
            updated_count += 1
    
    # Update snapshot
    await db.snapshot_workflow.update_one(
        {"id": snapshot['id']},
        {"$set": {"employees": employees}}
    )
    
    logger.info(f"Synced {updated_count} job titles to snapshot {snapshot['id']}")
    
    return {
        "success": True,
        "message": f"Synced {updated_count} job titles from employees_v2",
        "updates": updates,
        "snapshot_id": snapshot['id']
    }




@snapshot_router.get("/historical-averages")
async def get_historical_averages():
    """
    Get historical average values for POS metrics.
    Used for data validation/review step.
    """
    db = get_db()
    
    # Get completed snapshots to calculate averages
    completed_snapshots = await db.snapshot_workflow.find(
        {"status": "completed"},
        {"_id": 0, "employees": 1}
    ).to_list(10)
    
    # Also check employees_v2 for historical data
    employees_v2 = await db.employees_v2.find(
        {},
        {"_id": 0, "ppa": 1, "lbw_per_guest": 1, "glassware_sales": 1, "glassware_per_guest": 1, "guests_per_lsc": 1, "guest_count": 1}
    ).to_list(500)
    
    # Collect all employee metrics
    all_employees = []
    for snapshot in completed_snapshots:
        all_employees.extend(snapshot.get("employees", []))
    all_employees.extend(employees_v2)
    
    if not all_employees:
        # Return reasonable defaults
        return {
            "averages": {
                "ppa": 55.0,
                "liquor_sales": 500.0,
                "beer_sales": 300.0,
                "wine_sales": 150.0,
                "glassware_sales": 250.0,
                "lsc_count": 5,
                "guest_count": 200
            }
        }
    
    # Calculate averages (excluding zeros/nulls)
    def calc_avg(field):
        values = [e.get(field, 0) for e in all_employees if e.get(field, 0) and e.get(field, 0) > 0]
        # Also check _raw field for nested data
        if not values:
            raw_field = "bar_glassware_sales" if field == "glassware_sales" else field
            values = [e.get("_raw", {}).get(raw_field, 0) for e in all_employees if e.get("_raw", {}).get(raw_field, 0) and e.get("_raw", {}).get(raw_field, 0) > 0]
        return sum(values) / len(values) if values else 0
    
    # Calculate lsc_count from loyalty_sales (each card = $25)
    lsc_counts = []
    for e in all_employees:
        lsc = e.get("lsc_count", 0)
        if not lsc and e.get("loyalty_sales"):
            lsc = round(e.get("loyalty_sales", 0) / 25)
        if lsc and lsc > 0:
            lsc_counts.append(lsc)
    avg_lsc_count = sum(lsc_counts) / len(lsc_counts) if lsc_counts else 5
    
    return {
        "averages": {
            "ppa": round(calc_avg("ppa"), 2),
            "liquor_sales": round(calc_avg("liquor_sales"), 0),
            "beer_sales": round(calc_avg("beer_sales"), 0),
            "wine_sales": round(calc_avg("wine_sales"), 0),
            "glassware_sales": round(calc_avg("glassware_sales"), 0),
            "lsc_count": round(avg_lsc_count, 0),
            "guest_count": round(calc_avg("guest_count"), 0)
        }
    }


@snapshot_router.post("/snapshots/{snapshot_id}/confirm-pos-review")
async def confirm_pos_review(snapshot_id: str, data: Dict[str, Any]):
    """
    Confirm POS data review and save any edits.
    This marks the data as reviewed so user can proceed to Step 2.
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] == SnapshotStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Cannot modify completed snapshot")
    
    employees = data.get("employees", [])
    if not employees:
        raise HTTPException(status_code=400, detail="No employee data provided")
    
    # Find the POS upload and update it with reviewed data
    uploads = snapshot.get("uploads", [])
    pos_upload_idx = next(
        (i for i, u in enumerate(uploads) if u.get("upload_type") == "pos_report"),
        None
    )
    
    if pos_upload_idx is None:
        raise HTTPException(status_code=400, detail="No POS upload found")
    
    # Update the parsed data with reviewed/edited values
    uploads[pos_upload_idx]["parsed_data"]["employees"] = employees
    uploads[pos_upload_idx]["reviewed"] = True
    uploads[pos_upload_idx]["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    
    # Save to database
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "uploads": uploads,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "success": True,
        "message": f"POS data reviewed and confirmed ({len(employees)} employees)"
    }


@snapshot_router.post("/snapshots/{snapshot_id}/import-cv-adjustment/{session_id}")
async def import_cv_adjustment_to_snapshot(snapshot_id: str, session_id: str):
    """
    Import CV Adjustment session results into a snapshot.
    This takes the adjusted NPS data (with excluded no-fault reviews) and 
    creates a CV upload record in the snapshot.
    """
    db = get_db()
    
    # Validate snapshot
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] == SnapshotStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Cannot import to a completed snapshot")
    
    # Get CV adjustment session
    cv_session = await db.cv_adjustment_sessions.find_one({"_id": session_id})
    if not cv_session:
        raise HTTPException(status_code=404, detail="CV Adjustment session not found")
    
    # Aggregate by server name from the feedback items
    # Group by server and calculate adjusted metrics
    feedback_items = cv_session.get("feedback_items", [])
    adjusted_nps = cv_session.get("adjusted_nps", {})
    
    # Build employee data from non-excluded feedback
    employee_data = {}
    for item in feedback_items:
        # Skip excluded items
        if item.get("excluded", False):
            continue
        
        # Get server name - first check assigned_server, then server_name from transaction
        server_name = item.get("assigned_server") or item.get("server_name") or "Unknown"
        
        if server_name not in employee_data:
            employee_data[server_name] = {
                "name": server_name,
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
            }
        
        # Count by NPS category
        category = item.get("nps_category", "")
        if category == "promoter":
            employee_data[server_name]["promoters"] += 1
        elif category == "passive":
            employee_data[server_name]["passives"] += 1
        elif category == "detractor":
            employee_data[server_name]["detractors"] += 1
    
    # Calculate NPS for each employee
    employees = []
    for emp in employee_data.values():
        total = emp["promoters"] + emp["passives"] + emp["detractors"]
        if total > 0:
            nps = ((emp["promoters"] - emp["detractors"]) / total) * 100
            emp["nps_score"] = round(nps, 1)
            emp["responses"] = total
        else:
            emp["nps_score"] = 0
            emp["responses"] = 0
        employees.append(emp)
    
    # Create upload record
    now = datetime.now(timezone.utc).isoformat()
    upload_record = {
        "id": str(uuid.uuid4()),
        "snapshot_id": snapshot_id,
        "upload_type": UploadType.CUSTOMER_VOICE.value,
        "filename": f"CV Adjustment Session ({session_id[:8]})",
        "file_size": 0,
        "uploaded_at": now,
        "status": UploadStatus.PARSED.value,
        "parsed_data": {
            "employees": employees,
            "source": "cv_adjustment_session",
            "session_id": session_id,
            "original_nps": cv_session.get("original_nps", {}),
            "adjusted_nps": adjusted_nps,
            "excluded_count": len([i for i in feedback_items if i.get("excluded")])
        },
        "parsed_at": now,
        "record_count": len(employees),
    }
    
    # Update snapshot
    current_uploads = snapshot.get("uploads", [])
    existing_idx = next(
        (i for i, u in enumerate(current_uploads) if u.get("upload_type") == UploadType.CUSTOMER_VOICE.value),
        None
    )
    if existing_idx is not None:
        current_uploads[existing_idx] = upload_record
    else:
        current_uploads.append(upload_record)
    
    upload_progress = calculate_upload_progress(current_uploads)
    
    new_status = snapshot["status"]
    if new_status == SnapshotStatus.DRAFT.value and any(upload_progress.values()):
        new_status = SnapshotStatus.IN_PROGRESS.value
    
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "uploads": current_uploads,
                "upload_progress": upload_progress,
                "status": new_status,
                "updated_at": now
            }
        }
    )
    
    # Mark session as applied
    await db.cv_adjustment_sessions.update_one(
        {"_id": session_id},
        {"$set": {"applied_to_snapshot": snapshot_id, "applied_at": now}}
    )
    
    return {
        "success": True,
        "message": f"Imported CV adjustment data with {len(employees)} employees",
        "employees_imported": len(employees),
        "excluded_reviews": upload_record["parsed_data"]["excluded_count"],
        "adjusted_nps": adjusted_nps
    }


# ============================================================================
# SNAPSHOT PROCESSING
# ============================================================================

@snapshot_router.post("/snapshots/{snapshot_id}/process")
async def process_snapshot(snapshot_id: str):
    """
    Process a snapshot: validate uploads, calculate scores, finalize.
    This transitions the snapshot from In Progress -> Processing -> Completed/Failed.
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    # Check if can be processed
    if snapshot["status"] == SnapshotStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Snapshot is already completed. Use reprocess if needed."
        )
    
    can_process, missing = can_process_snapshot(snapshot)
    if not can_process:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required uploads: {missing}"
        )
    
    # Set to processing
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "status": SnapshotStatus.PROCESSING.value,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$push": {
                "processing_log": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "processing_started"
                }
            }
        }
    )
    
    try:
        # Get benchmarks from quarter settings
        settings = await db.quarter_settings.find_one(
            {"quarter": snapshot["quarter"], "year": snapshot["year"]},
            {"_id": 0}
        )
        
        benchmarks = {
            "ppa": settings.get("benchmark_ppa", 55.0) if settings else 55.0,
            "lbw": settings.get("benchmark_lbw", 8.0) if settings else 8.0,
            "glass": settings.get("benchmark_glass", 1.25) if settings else 1.25,
            "lsc": settings.get("benchmark_lsc", 100.0) if settings else 100.0,
        }
        
        # Merge data from all uploads
        employees = await merge_snapshot_data(snapshot)
        
        # Calculate scores for each employee
        for emp in employees:
            calculate_employee_scores(emp, benchmarks)
        
        # Assign tiers and ranks
        employees = assign_performance_tiers(employees)
        
        # Update snapshot as completed
        now = datetime.now(timezone.utc).isoformat()
        await db.snapshot_workflow.update_one(
            {"id": snapshot_id},
            {
                "$set": {
                    "status": SnapshotStatus.COMPLETED.value,
                    "employees": employees,
                    "employee_count": len(employees),
                    "benchmarks_used": benchmarks,
                    "completed_at": now,
                    "updated_at": now
                },
                "$push": {
                    "processing_log": {
                        "timestamp": now,
                        "action": "processing_completed",
                        "employee_count": len(employees)
                    }
                }
            }
        )
        
        # Update current snapshot flag
        await update_current_snapshot(db, snapshot_id, snapshot["quarter"], snapshot["year"])
        
        logger.info(f"Snapshot {snapshot_id} processed successfully with {len(employees)} employees")
        
        return {
            "success": True,
            "message": f"Snapshot processed successfully with {len(employees)} employees",
            "employee_count": len(employees),
            "is_current": True
        }
        
    except Exception as e:
        logger.error(f"Snapshot processing failed: {e}")
        
        # Set to failed
        await db.snapshot_workflow.update_one(
            {"id": snapshot_id},
            {
                "$set": {
                    "status": SnapshotStatus.FAILED.value,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$push": {
                    "processing_log": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": "processing_failed",
                        "error": str(e)
                    }
                }
            }
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )


@snapshot_router.post("/snapshots/{snapshot_id}/reprocess")
async def reprocess_snapshot(snapshot_id: str):
    """
    Reprocess a completed or failed snapshot.
    Recalculates scores from existing upload data.
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] not in [SnapshotStatus.COMPLETED.value, SnapshotStatus.FAILED.value]:
        raise HTTPException(
            status_code=400,
            detail="Can only reprocess completed or failed snapshots"
        )
    
    # Reset to in_progress and process
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "status": SnapshotStatus.IN_PROGRESS.value,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$push": {
                "processing_log": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "reprocess_initiated"
                }
            }
        }
    )
    
    # Call process
    return await process_snapshot(snapshot_id)


# ============================================================================
# CURRENT RANKINGS
# ============================================================================

@snapshot_router.get("/current-rankings")
async def get_current_rankings(quarter: Optional[str] = None, year: Optional[int] = None):
    """
    Get rankings from the latest completed snapshot.
    This is what the Rankings page should use.
    """
    db = get_db()
    
    query = {"status": SnapshotStatus.COMPLETED.value}
    if quarter:
        query["quarter"] = quarter.upper()
    if year:
        query["year"] = year
    
    # Get latest completed snapshot by effective_date
    snapshot = await db.snapshot_workflow.find_one(
        query,
        {"_id": 0},
        sort=[("effective_date", -1), ("completed_at", -1)]
    )
    
    if not snapshot:
        return {
            "success": True,
            "has_data": False,
            "message": "No completed snapshots found",
            "employees": [],
            "snapshot": None
        }
    
    return {
        "success": True,
        "has_data": True,
        "snapshot": {
            "id": snapshot.get("id"),
            "name": snapshot.get("name"),
            "effective_date": snapshot.get("effective_date"),
            "period_start": snapshot.get("period_start"),
            "period_end": snapshot.get("period_end"),
            "quarter": snapshot.get("quarter"),
            "year": snapshot.get("year"),
            "completed_at": snapshot.get("completed_at"),
            "employee_count": snapshot.get("employee_count", 0)
        },
        "employees": snapshot.get("employees", []),
        "benchmarks": snapshot.get("benchmarks_used", {})
    }


# ============================================================================
# SLIDE GENERATION
# ============================================================================

@snapshot_router.get("/snapshots/{snapshot_id}/slide")
async def generate_snapshot_workflow_slide(
    snapshot_id: str,
    format: str = "16:9",
    background: str = "dark"
):
    """
    Generate a downloadable PNG slide for a snapshot workflow snapshot.
    """
    from snapshot_slides import generate_snapshot_slide, BACKGROUNDS
    from fastapi.responses import Response
    
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id}, {"_id": 0})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    employees = snapshot.get("employees", [])
    if not employees:
        raise HTTPException(status_code=400, detail="Snapshot has no employee data")
    
    # Sort employees by total_score
    sorted_employees = sorted(employees, key=lambda x: x.get("total_score", 0) or 0, reverse=True)
    
    # Format employees for slide generation (must have exact fields)
    slide_employees = []
    for i, emp in enumerate(sorted_employees):  # All employees for slide
        slide_employees.append({
            "rank": i + 1,
            "name": emp.get("name", "Unknown"),
            "total_score": emp.get("total_score", 0) or 0,
            "ppa": emp.get("ppa", 0) or 0,
            "lbw_per_guest": emp.get("lbw_per_guest", 0) or 0,
            "guests_per_lsc": emp.get("guests_per_lsc", 0) or 0,
            "glassware_per_guest": emp.get("glassware_per_guest", 0) or 0,
            "job_title": emp.get("job_title", "Server"),
            "tier_label": emp.get("tier_label") or emp.get("performance_tier", "Server"),
            # Score percentages for each metric
            "score_ppa": emp.get("score_ppa", 0) or 0,
            "score_lbw": emp.get("score_lbw", 0) or 0,
            "score_glass": emp.get("score_glass", 0) or 0,
            "score_lsc": emp.get("score_lsc", 0) or 0,
            # CV and RT data
            "cv_score": emp.get("cv_score", 0) or 0,
            "cv_promoters": emp.get("cv_promoters", 0) or 0,
            "cv_detractors": emp.get("cv_detractors", 0) or 0,
            "nps_score": emp.get("nps_score", 0) or 0,
            "rt_mentions": emp.get("rt_mentions", 0) or 0,
            "review_tracker_bonus": emp.get("review_tracker_bonus", 0) or 0,
            # Bonuses
            "total_metric_bonus": emp.get("total_metric_bonus", 0) or 0,
        })
    
    # Get benchmarks from snapshot or use defaults
    benchmarks = snapshot.get("benchmarks", {
        "ppa": 55.0,
        "lbw_per_guest": 6.0,
        "guests_per_lsc": 35.0,
        "glassware_per_guest": 1.2
    })
    
    # Build title
    title = f"{snapshot.get('quarter', 'Q1')} {snapshot.get('year', 2026)} Server Performance Snapshot"
    snapshot_date = snapshot.get("effective_date", "")
    
    # Generate the slide
    try:
        slide_bytes = generate_snapshot_slide(
            employees=slide_employees,
            benchmarks=benchmarks,
            snapshot_date=snapshot_date,
            background=background,
            title=title
        )
        
        return Response(
            content=slide_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{snapshot.get("name", "snapshot")}-slide.png"'
            }
        )
    except Exception as e:
        logger.error(f"Error generating slide: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate slide: {str(e)}")


@snapshot_router.post("/snapshots/{snapshot_id}/sync-from-employees")
async def sync_pos_from_employees_v2(snapshot_id: str):
    """
    Sync POS data from employees_v2 collection to the snapshot.
    This ensures the snapshot uses the same verified data as the Employee tab.
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id}, {"_id": 0})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    # Get employees from employees_v2
    employees_v2 = await db.employees_v2.find(
        {"quarter": snapshot.get("quarter", "Q1"), "year": snapshot.get("year", 2026)},
        {"_id": 0}
    ).to_list(100)
    
    if not employees_v2:
        raise HTTPException(status_code=404, detail="No employees found in employees_v2")
    
    # Find POS upload and update its parsed_data
    uploads = snapshot.get("uploads", [])
    pos_upload_idx = next(
        (i for i, u in enumerate(uploads) if u.get("upload_type") == "pos_report"),
        None
    )
    
    if pos_upload_idx is None:
        # Create a new POS upload record from employees_v2
        pos_employees = []
    else:
        pos_employees = uploads[pos_upload_idx].get("parsed_data", {}).get("employees", [])
    
    # Build employee lookup from employees_v2
    v2_lookup = {}
    for emp in employees_v2:
        name_key = emp.get("name", "").strip().lower()
        if name_key:
            v2_lookup[name_key] = emp
    
    # Update or add employees from v2
    updated_employees = []
    for emp in pos_employees:
        name_key = emp.get("name", "").strip().lower()
        v2_emp = v2_lookup.get(name_key)
        
        if v2_emp:
            # Update with v2 data
            emp.update({
                "ppa": v2_emp.get("ppa", emp.get("ppa", 0)),
                "lbw_per_guest": v2_emp.get("lbw_per_guest", emp.get("lbw_per_guest", 0)),
                "glassware_per_guest": v2_emp.get("glassware_per_guest", emp.get("glassware_per_guest", 0)),
                "guests_per_lsc": v2_emp.get("guests_per_lsc", emp.get("guests_per_lsc", 0)),
                "guest_count": v2_emp.get("guests", emp.get("guest_count", 0)),
                "net_sales": v2_emp.get("net_sales", emp.get("net_sales", 0)),
                "loyalty_sales": v2_emp.get("loyalty_sales", emp.get("loyalty_sales", 0)),
            })
            # Remove from lookup so we can add remaining v2 employees
            del v2_lookup[name_key]
        
        updated_employees.append(emp)
    
    # Add any employees from v2 that weren't in POS upload
    for name_key, v2_emp in v2_lookup.items():
        updated_employees.append({
            "name": v2_emp.get("name"),
            "ppa": v2_emp.get("ppa", 0),
            "lbw_per_guest": v2_emp.get("lbw_per_guest", 0),
            "glassware_per_guest": v2_emp.get("glassware_per_guest", 0),
            "guests_per_lsc": v2_emp.get("guests_per_lsc", 0),
            "guest_count": v2_emp.get("guests", 0),
            "net_sales": v2_emp.get("net_sales", 0),
            "loyalty_sales": v2_emp.get("loyalty_sales", 0),
            "liquor_sales": v2_emp.get("liquor_sales", 0),
            "beer_sales": v2_emp.get("beer_sales", 0),
            "wine_sales": v2_emp.get("wine_sales", 0),
        })
    
    # Update POS upload
    if pos_upload_idx is not None:
        uploads[pos_upload_idx]["parsed_data"]["employees"] = updated_employees
        uploads[pos_upload_idx]["source"] = "synced_from_employees_v2"
    else:
        uploads.append({
            "upload_type": "pos_report",
            "filename": "synced_from_employees_v2",
            "source": "employees_v2",
            "status": "parsed",
            "parsed_data": {"employees": updated_employees, "record_count": len(updated_employees)}
        })
    
    # Update snapshot
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "uploads": uploads,
                "upload_progress.pos_report": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    logger.info(f"Synced {len(updated_employees)} employees from employees_v2 to snapshot {snapshot_id}")
    
    return {
        "success": True,
        "message": f"Synced {len(updated_employees)} employees from employees_v2",
        "employee_count": len(updated_employees)
    }


# ============================================================================
# MIGRATION
# ============================================================================

@snapshot_router.post("/migrate-legacy-data")
async def migrate_legacy_data(quarter: str = "Q1", year: int = 2026):
    """
    Migrate existing employees_v2 data into a legacy snapshot.
    This preserves the old data while transitioning to the snapshot-first model.
    """
    db = get_db()
    
    # Check if already migrated
    existing = await db.snapshot_workflow.find_one({
        "name": {"$regex": "Legacy Migration"},
        "quarter": quarter.upper(),
        "year": year
    })
    
    if existing:
        return {
            "success": False,
            "message": "Legacy data already migrated for this quarter",
            "snapshot_id": existing.get("id")
        }
    
    # Fetch existing employee data
    employees_v2 = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    if not employees_v2:
        return {
            "success": False,
            "message": "No existing employee data found for this quarter"
        }
    
    # Create a legacy snapshot
    now = datetime.now(timezone.utc).isoformat()
    snapshot_id = str(uuid.uuid4())
    
    snapshot = {
        "id": snapshot_id,
        "name": f"Legacy Migration - {quarter} {year}",
        "effective_date": "2026-03-01",
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "quarter": quarter.upper(),
        "year": year,
        "status": SnapshotStatus.COMPLETED.value,
        "notes": "Automatically migrated from legacy employees_v2 data",
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
        "uploads": [{
            "id": str(uuid.uuid4()),
            "snapshot_id": snapshot_id,
            "upload_type": "legacy_migration",
            "filename": "employees_v2",
            "file_size": 0,
            "uploaded_at": now,
            "status": "migrated",
            "record_count": len(employees_v2)
        }],
        "upload_progress": {
            "pos_report": True,
            "customer_voice": True,
            "review_tracker": True,
        },
        "employees": employees_v2,
        "employee_count": len(employees_v2),
        "benchmarks_used": {},
        "processing_log": [{
            "timestamp": now,
            "action": "legacy_migration"
        }],
        "is_current": True,
        "version": 1,
    }
    
    # Unmark any existing current snapshots
    await db.snapshot_workflow.update_many(
        {"quarter": quarter.upper(), "year": year},
        {"$set": {"is_current": False}}
    )
    
    # Insert the legacy snapshot
    await db.snapshot_workflow.insert_one(snapshot)
    
    logger.info(f"Migrated {len(employees_v2)} employees to legacy snapshot {snapshot_id}")
    
    return {
        "success": True,
        "message": f"Migrated {len(employees_v2)} employees to legacy snapshot",
        "snapshot_id": snapshot_id,
        "employee_count": len(employees_v2)
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_current_snapshot_id(db) -> Optional[str]:
    """Get the ID of the current (latest completed) snapshot."""
    snapshot = await db.snapshot_workflow.find_one(
        {"status": SnapshotStatus.COMPLETED.value},
        {"id": 1},
        sort=[("effective_date", -1), ("completed_at", -1)]
    )
    return snapshot.get("id") if snapshot else None


async def update_current_snapshot(db, snapshot_id: str, quarter: str, year: int):
    """Mark a snapshot as current and unmark others."""
    # Unmark all snapshots for this quarter/year
    await db.snapshot_workflow.update_many(
        {"quarter": quarter, "year": year},
        {"$set": {"is_current": False}}
    )
    
    # Mark this one as current
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {"$set": {"is_current": True}}
    )


async def merge_snapshot_data(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Merge data from all uploads in a snapshot into employee records.
    POS data is the base, CV and RT data are merged on top.
    Preserves manually set job_titles from existing snapshot data.
    """
    employees = {}
    
    # Build lookup of existing employee data to preserve job_titles
    existing_employees = {}
    for emp in snapshot.get("employees", []):
        name_key = emp.get("name", "").lower().strip()
        if name_key:
            existing_employees[name_key] = emp
    
    for upload in snapshot.get("uploads", []):
        upload_type = upload.get("upload_type")
        parsed_data = upload.get("parsed_data", {})
        
        if upload_type == UploadType.POS_REPORT.value:
            # POS data creates the base employee records
            for emp_data in parsed_data.get("employees", []):
                name = emp_data.get("name", "").strip()
                if not name:
                    continue
                
                # Extract raw values
                guest_count = emp_data.get("guest_count", 0) or 0
                liquor_sales = emp_data.get("liquor_sales", 0) or 0
                beer_sales = emp_data.get("beer_sales", 0) or 0
                wine_sales = emp_data.get("wine_sales", 0) or 0
                glassware_sales = emp_data.get("glassware_sales", 0) or emp_data.get("bar_glassware_sales", 0) or 0
                loyalty_sales = emp_data.get("loyalty_sales", 0) or 0
                
                # ALWAYS recalculate LBW from components (don't trust pre-calculated value)
                lbw_total = liquor_sales + beer_sales + wine_sales
                
                # Calculate per-guest metrics (if not already provided)
                # LBW per guest: prioritize pre-calculated, otherwise calculate from totals
                lbw_per_guest = emp_data.get("lbw_per_guest", 0)
                if not lbw_per_guest and guest_count > 0:
                    lbw_per_guest = round(lbw_total / guest_count, 2)
                
                # Glassware per guest: prioritize pre-calculated, otherwise calculate
                glassware_per_guest = emp_data.get("glassware_per_guest", 0)
                if not glassware_per_guest and guest_count > 0:
                    glassware_per_guest = round(glassware_sales / guest_count, 2)
                
                # LSC Count (each loyalty card = $25)
                lsc_count = emp_data.get("lsc_count", 0)
                if not lsc_count and loyalty_sales > 0:
                    lsc_count = round(loyalty_sales / 25)
                
                # Guests per LSC: prioritize pre-calculated, otherwise calculate
                guests_per_lsc = emp_data.get("guests_per_lsc", 0)
                if not guests_per_lsc and lsc_count > 0:
                    guests_per_lsc = round(guest_count / lsc_count, 2)
                
                # Preserve job_title and display_name from existing employee data or POS data
                existing_emp = existing_employees.get(name.lower())
                job_title = emp_data.get("job_title") or (existing_emp.get("job_title") if existing_emp else None) or "Server"
                
                # Use existing display_name if set, otherwise default to full name
                display_name = (existing_emp.get("display_name") if existing_emp else None) or name
                # Store the full POS name as report_name for matching
                report_name = name
                
                employees[name.lower()] = {
                    "id": existing_emp.get("id") if existing_emp else str(uuid.uuid4()),
                    "name": display_name,  # Show display name
                    "display_name": display_name,
                    "report_name": report_name,  # Full POS name for matching
                    "quarter": snapshot.get("quarter"),
                    "year": snapshot.get("year"),
                    "job_title": job_title,
                    "guests": guest_count,
                    "guest_count": guest_count,
                    "net_sales": emp_data.get("net_sales", 0),
                    "ppa": emp_data.get("ppa", 0),
                    "lbw_per_guest": lbw_per_guest,
                    "glassware_per_guest": glassware_per_guest,
                    "guests_per_lsc": guests_per_lsc,
                    "lsc_count": lsc_count,
                    "loyalty_sales": loyalty_sales,
                    "food_sales": emp_data.get("food_sales", 0),
                    "liquor_sales": liquor_sales,
                    "beer_sales": beer_sales,
                    "wine_sales": wine_sales,
                    "bar_glassware_sales": glassware_sales,
                    "lbw": lbw_total,
                    # Initialize CV/RT fields
                    "cv_promoters": 0,
                    "cv_passives": 0,
                    "cv_detractors": 0,
                    "cv_score": 0,
                    "nps_score": 0,
                    "rt_mentions": 0,
                    "review_tracker_bonus": 0,
                    "dar_penalty": 0,
                }
        
        elif upload_type == UploadType.CUSTOMER_VOICE.value:
            # Merge CV/NPS Toolkit data
            cv_employees = parsed_data.get("employees", [])
            
            # Check if we have individual employee data or just store-level ("Unknown")
            has_individual_data = any(
                emp.get("name", "").strip().lower() != "unknown" and 
                emp.get("name", "").strip().lower() in employees
                for emp in cv_employees
            )
            
            if has_individual_data:
                # Individual employee CV data - merge directly
                for cv_data in cv_employees:
                    name = cv_data.get("name", "").strip().lower()
                    if name in employees:
                        # Get values from parsed data
                        promoters = cv_data.get("promoters", 0) or 0
                        passives = cv_data.get("passives", 0) or 0
                        detractors = cv_data.get("detractors", 0) or 0
                        nps_from_report = cv_data.get("nps_score", 0) or 0
                        
                        employees[name]["cv_promoters"] = promoters
                        employees[name]["cv_passives"] = passives
                        employees[name]["cv_detractors"] = detractors
                        employees[name]["cv_responses"] = cv_data.get("responses", 0) or 0
                        employees[name]["cv_avg_rating"] = cv_data.get("avg_rating", 0) or 0
                        
                        # Use NPS from report if available, otherwise calculate
                        total = promoters + passives + detractors
                        if nps_from_report != 0:
                            nps = nps_from_report
                        elif total > 0:
                            nps = ((promoters - detractors) / total) * 100
                        else:
                            nps = 0
                        
                        employees[name]["nps_score"] = round(nps, 1)
                        employees[name]["nps_score_pts"] = round(nps / 10, 1)
                        
                        # CV bonus: +1 per promoter, -2 per detractor
                        # CV Formula: (Promoters × 1) + (RT Mentions × 0.5) - (Detractors × 2)
                        cv_raw = (promoters * 1) - (detractors * 2)
                        employees[name]["cv_raw_points"] = round(cv_raw, 2)
                        employees[name]["cv_score"] = round(
                            employees[name].get("nps_score_pts", 0) + employees[name]["cv_raw_points"],
                            2
                        )
            else:
                # Store-level CV data (all attributed to "Unknown") 
                # Distribute proportionally based on guest count
                unknown_data = next((e for e in cv_employees if e.get("name", "").strip().lower() == "unknown"), None)
                if unknown_data:
                    total_promoters = unknown_data.get("promoters", 0) or 0
                    total_passives = unknown_data.get("passives", 0) or 0  
                    total_detractors = unknown_data.get("detractors", 0) or 0
                    store_nps = unknown_data.get("nps_score", 0) or 0
                    
                    # Calculate total guests for distribution
                    total_guests = sum(emp.get("guest_count", 0) or 0 for emp in employees.values())
                    
                    if total_guests > 0 and total_promoters > 0:
                        # Distribute CV data proportionally by guest count
                        for name, emp in employees.items():
                            guest_count = emp.get("guest_count", 0) or 0
                            if guest_count > 0:
                                ratio = guest_count / total_guests
                                
                                # Distribute promoters/detractors proportionally
                                promoters = round(total_promoters * ratio)
                                detractors = round(total_detractors * ratio)
                                passives = round(total_passives * ratio)
                                
                                employees[name]["cv_promoters"] = promoters
                                employees[name]["cv_passives"] = passives
                                employees[name]["cv_detractors"] = detractors
                                
                                # Calculate individual NPS from distributed data
                                # NPS = (promoters - detractors) / total * 100
                                individual_total = promoters + passives + detractors
                                if individual_total > 0:
                                    individual_nps = ((promoters - detractors) / individual_total) * 100
                                else:
                                    individual_nps = store_nps  # Fallback to store NPS
                                
                                employees[name]["nps_score"] = round(individual_nps, 1)
                                employees[name]["nps_score_pts"] = round(individual_nps / 10, 1)
                                
                                # CV bonus based on distributed promoters/detractors
                                cv_raw = (promoters * 1) - (detractors * 2)
                                employees[name]["cv_raw_points"] = round(cv_raw, 2)
                                employees[name]["cv_score"] = round(
                                    employees[name].get("nps_score_pts", 0) + employees[name]["cv_raw_points"],
                                    2
                                )
        
        elif upload_type == UploadType.REVIEW_TRACKER.value:
            # Merge RT data with fuzzy name matching
            # Build a mapping of common nicknames to full names
            # Format: 'nickname_in_reviews': 'name_in_pos'
            nickname_map = {
                'trey': 'treyanna', 'tad': 'thaddeus', 'abby': 'abigail',
                'ikey': 'eric', 'lennie': 'glennice', 'terry': 'terrance',
                'allen': 'craig',  # Allen in reviews = Craig Simmons in POS
                'matt': 'matthew', 'mike': 'michael',
                'dan': 'daniel', 'rob': 'robert', 'bob': 'robert',
                'jim': 'james', 'joe': 'joseph', 'chris': 'christopher',
                'nick': 'nicholas', 'tom': 'thomas', 'will': 'william',
                'sam': 'samuel', 'alex': 'alexander', 'ben': 'benjamin',
                'liz': 'elizabeth', 'beth': 'elizabeth', 'kate': 'katherine',
                'jen': 'jennifer', 'meg': 'megan', 'steph': 'stephanie',
            }
            
            def find_employee_match(rt_name, employees_dict):
                """Find matching employee using fuzzy logic."""
                rt_name_lower = rt_name.strip().lower()
                
                # Direct match
                if rt_name_lower in employees_dict:
                    return rt_name_lower
                
                # Split into first/last
                parts = rt_name_lower.split()
                if len(parts) >= 2:
                    first_name = parts[0]
                    last_name = parts[-1]
                    
                    # Try nickname expansion
                    expanded_first = nickname_map.get(first_name, first_name)
                    
                    # Search for match by last name + first name prefix
                    for emp_name in employees_dict.keys():
                        emp_parts = emp_name.split()
                        if len(emp_parts) >= 2:
                            emp_first = emp_parts[0]
                            emp_last = emp_parts[-1]
                            
                            # Match by last name and (first name starts with OR nickname matches)
                            if emp_last == last_name:
                                if emp_first.startswith(first_name) or emp_first.startswith(expanded_first):
                                    return emp_name
                                if first_name.startswith(emp_first[:3]) or expanded_first == emp_first:
                                    return emp_name
                
                return None
            
            for rt_data in parsed_data.get("employees", []):
                rt_name = rt_data.get("name", "").strip()
                matched_name = find_employee_match(rt_name, employees)
                
                if matched_name:
                    mentions = rt_data.get("mentions", 0)
                    employees[matched_name]["rt_mentions"] = mentions
                    employees[matched_name]["review_tracker_bonus"] = round(min(mentions * 0.5, 15), 1)  # Cap at 15
    
    return list(employees.values())


async def parse_pos_file(filename: str, contents: bytes) -> Dict[str, Any]:
    """Parse POS report file (PDF or XLSX)."""
    from pos_ocr import extract_pos_data_from_pdf, extract_pos_data_from_xlsx, validate_extracted_data
    
    if filename.lower().endswith(('.xlsx', '.xls')):
        raw_data = extract_pos_data_from_xlsx(contents)
    elif filename.lower().endswith('.pdf'):
        raw_data = await extract_pos_data_from_pdf(contents)
    else:
        raise ValueError(f"Unsupported POS file format: {filename}")
    
    validated = validate_extracted_data(raw_data)
    return validated


async def parse_cv_file(filename: str, contents: bytes) -> Dict[str, Any]:
    """
    Parse Customer Voice / NPS Toolkit file.
    Supports:
    - NPS Toolkit XLSX (Server Performance Report with Name, NPS, Received columns)
    - CSV with Employee, Promoters, Passives, Detractors columns
    """
    import csv
    from io import StringIO, BytesIO
    
    employees = []
    
    # Check file type
    if filename.lower().endswith(('.xlsx', '.xls')):
        # Parse NPS Toolkit XLSX format
        try:
            import openpyxl
            wb = openpyxl.load_workbook(BytesIO(contents), data_only=True)
            ws = wb.active
            
            # Find header row and column indices
            headers = {}
            header_row = None
            for row_idx, row in enumerate(ws.iter_rows(max_row=5, values_only=True), 1):
                row_lower = [str(c).lower() if c else '' for c in row]
                if 'name' in row_lower and ('nps' in row_lower or 'received' in row_lower):
                    header_row = row_idx
                    for col_idx, cell in enumerate(row):
                        if cell:
                            headers[str(cell).lower()] = col_idx
                    break
            
            if not header_row:
                raise ValueError("Could not find header row with Name and NPS columns")
            
            # Parse data rows
            name_col = headers.get('name', 0)
            nps_col = headers.get('nps', headers.get('nps score', 6))
            received_col = headers.get('received', headers.get('responses', 3))
            avg_rating_col = headers.get('avg rating', headers.get('average rating', 5))
            
            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                name = row[name_col] if name_col < len(row) else None
                if not name or name == 'None' or 'manager' in str(name).lower():
                    continue
                
                # Get NPS score (already calculated in the report)
                try:
                    nps = float(row[nps_col]) if nps_col < len(row) and row[nps_col] else 0
                except (ValueError, TypeError):
                    nps = 0
                
                # Get number of responses
                try:
                    received = int(float(row[received_col])) if received_col < len(row) and row[received_col] else 0
                except (ValueError, TypeError):
                    received = 0
                
                # Get avg rating
                try:
                    avg_rating = float(row[avg_rating_col]) if avg_rating_col < len(row) and row[avg_rating_col] else 0
                except (ValueError, TypeError):
                    avg_rating = 0
                
                # Estimate promoters/passives/detractors from NPS and received count
                # NPS = (promoters - detractors) / total * 100
                # We'll estimate based on NPS score
                if received > 0:
                    # Estimate breakdown based on NPS
                    if nps >= 75:
                        promoters = received
                        passives = 0
                        detractors = 0
                    elif nps >= 50:
                        promoters = int(received * 0.8)
                        passives = int(received * 0.15)
                        detractors = received - promoters - passives
                    elif nps >= 0:
                        # NPS = (P - D) / Total * 100, P + Pa + D = Total
                        # Estimate: P = (NPS/100 + 1) * Total / 2
                        promoters = max(0, int((nps/100 + 1) * received / 2))
                        detractors = max(0, int((1 - nps/100) * received / 2))
                        passives = received - promoters - detractors
                    else:
                        # Negative NPS
                        detractors = max(1, int(abs(nps) / 100 * received))
                        promoters = max(0, received - detractors)
                        passives = 0
                else:
                    promoters = 0
                    passives = 0
                    detractors = 0
                
                employees.append({
                    "name": str(name).strip(),
                    "nps_score": nps,
                    "responses": received,
                    "avg_rating": avg_rating,
                    "promoters": promoters,
                    "passives": passives,
                    "detractors": detractors,
                })
            
            logger.info(f"Parsed NPS Toolkit XLSX: {len(employees)} employees")
            
        except Exception as e:
            logger.error(f"Error parsing NPS Toolkit XLSX: {e}")
            raise ValueError(f"Failed to parse NPS Toolkit file: {str(e)}")
    
    else:
        # Parse CSV format (legacy)
        try:
            text = contents.decode('utf-8')
        except UnicodeDecodeError:
            text = contents.decode('latin-1')
        
        reader = csv.DictReader(StringIO(text))
        
        for row in reader:
            name = row.get("Employee", row.get("employee", row.get("Name", row.get("name", ""))))
            if not name:
                continue
            
            employees.append({
                "name": name,
                "promoters": int(row.get("Promoters", row.get("promoters", 0)) or 0),
                "passives": int(row.get("Passives", row.get("passives", 0)) or 0),
                "detractors": int(row.get("Detractors", row.get("detractors", 0)) or 0),
                "nps_score": float(row.get("NPS", row.get("nps", row.get("nps_score", 0))) or 0),
            })
    
    return {"employees": employees, "record_count": len(employees)}


async def parse_rt_file(filename: str, contents: bytes) -> Dict[str, Any]:
    """
    Parse ReviewTracker CSV file.
    Extracts employee mentions from review text using GPT-4o name detection.
    """
    import csv
    from io import StringIO
    
    # Decode contents
    try:
        text = contents.decode('utf-8')
    except UnicodeDecodeError:
        text = contents.decode('latin-1')
    
    reader = csv.DictReader(StringIO(text))
    reviews = []
    employee_mentions = {}
    
    # Get list of known employee names from the database for matching
    db = get_db()
    known_employees = await db.employees_v2.find(
        {"quarter": "Q1", "year": 2026},
        {"_id": 0, "name": 1}
    ).to_list(100)
    known_names = [e.get("name", "").lower() for e in known_employees if e.get("name")]
    
    # Also try from snapshot_workflow if no employees_v2
    if not known_names:
        latest_snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed"},
            {"_id": 0, "employees": 1},
            sort=[("effective_date", -1)]
        )
        if latest_snapshot:
            known_names = [e.get("name", "").lower() for e in latest_snapshot.get("employees", []) if e.get("name")]
    
    for row in reader:
        # Get review text from various possible column names
        review_text = row.get("Review", row.get("review", row.get("Content", row.get("content", ""))))
        if not review_text or review_text.strip() == "":
            continue
        
        review_text_lower = review_text.lower()
        
        # Track which employees were mentioned in this review (avoid double-counting)
        mentioned_in_review = set()
        
        # Build name variations for special cases
        name_variations = {
            "starwars": ["starwars", "star wars", "star"],
            "treyanne": ["treyanne", "trey"],
            "thaddeus": ["thaddeus", "tad", "thad"],
            "abigail": ["abigail", "abby"],
            "glennice": ["glennice", "lennie"],
            "terrance": ["terrance", "terry"],
            "matthew": ["matthew", "matt"],
            "eric": ["eric", "ikey"],
            "robert": ["robert", "rob", "bob"],
            "daniel": ["daniel", "dan"],
        }
        
        # Check each known employee
        for name in known_names:
            if not name or name in mentioned_in_review:
                continue
            
            # Get first name for matching
            first_name = name.split()[0].lower() if name else ""
            if not first_name or len(first_name) < 3:
                continue
            
            # Get variations to search for
            variations = name_variations.get(first_name, [first_name])
            
            # Check if any variation appears in review
            found = False
            for variant in variations:
                # Use word boundary check
                import re
                pattern = r'\b' + re.escape(variant) + r'\b'
                if re.search(pattern, review_text_lower):
                    found = True
                    break
            
            if found:
                # Store the original capitalized name
                original_name = next(
                    (e.get("name") for e in known_employees if e.get("name", "").lower() == name),
                    name.title()
                )
                if original_name not in employee_mentions:
                    employee_mentions[original_name] = 0
                employee_mentions[original_name] += 1
                mentioned_in_review.add(name)
        
        reviews.append({
            "text": review_text[:200],
            "rating": row.get("Rating", row.get("rating", "")),
            "date": row.get("Published", row.get("published", row.get("Date", ""))),
        })
    
    employees = [
        {"name": name, "mentions": count}
        for name, count in employee_mentions.items()
    ]
    
    logger.info(f"Parsed RT file: {len(reviews)} reviews, {len(employees)} employees mentioned")
    
    return {
        "employees": employees, 
        "record_count": len(employees),
        "total_reviews": len(reviews),
        "reviews_sample": reviews[:10]  # Include sample for debugging
    }
