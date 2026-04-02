"""
Snapshot API Routes
Implements snapshot-first workflow endpoints.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body, Request
import json
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
    ).sort([("effective_date", -1), ("completed_at", -1)]).limit(limit).to_list(limit)
    
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
    request: Request,
    file: UploadFile = File(None),
):
    """
    Upload a file to a specific snapshot.
    upload_type: pos_report, customer_voice, review_tracker
    
    Can accept either:
    - A file upload (multipart/form-data)
    - Pre-parsed data (JSON body with parsed_data, filename, source)
    
    For PDF files, use the background job flow:
    1. POST /api/v2/pos-pdf/parse to start processing
    2. Poll /api/v2/pos-pdf/job/{job_id} for results
    3. POST /api/v2/snapshot-workflow/snapshots/{id}/parsed-data/{type} to save results
    """
    db = get_db()
    
    # Validate snapshot exists and is in correct status
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if snapshot["status"] == SnapshotStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot upload to a completed snapshot. Click 'Unlock' first."
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
    final_filename = "unknown"
    final_parsed_data = None
    parse_error = None
    
    # Check if this is a JSON request (pre-parsed data)
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        # Handle JSON body with pre-parsed data
        try:
            body = await request.json()
            final_parsed_data = body.get("parsed_data")
            final_filename = body.get("filename", "background_job_result")
            source = body.get("source", "background_job")
            
            if not final_parsed_data:
                raise HTTPException(status_code=400, detail="parsed_data is required in JSON body")
            
            logger.info(f"Received pre-parsed JSON data for {upload_type}: {len(final_parsed_data.get('employees', []))} employees")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    
    elif file is not None:
        # Traditional file upload - read and parse
        contents = await file.read()
        file_size = len(contents)
        final_filename = file.filename
        
        # Check if it's a PDF - should use background job flow
        if final_filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="PDF files must use the background processing flow. "
                       "POST to /api/v2/pos-pdf/parse first, then save results via /parsed-data/ endpoint."
            )
        
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
    
    else:
        raise HTTPException(
            status_code=400, 
            detail="Either a file upload or JSON body with parsed_data is required"
        )
    
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
    
    # Recalculate per-guest metrics when any relevant field is updated
    guest_count = emp.get("guest_count") or emp.get("guests") or 0
    if guest_count > 0:
        # Always recalculate LBW per guest
        lbw = emp.get("lbw", 0) or 0
        emp["lbw_per_guest"] = round(lbw / guest_count, 2)
        
        # Always recalculate glassware per guest
        glassware = emp.get("bar_glassware_sales") or emp.get("glassware_sales") or 0
        emp["glassware_per_guest"] = round(glassware / guest_count, 2)
        
        logger.info(f"Recalculated per-guest metrics for {emp.get('name')}: lbw_per_guest={emp['lbw_per_guest']}, glassware_per_guest={emp['glassware_per_guest']}")
    
    # Recalculate guests_per_lsc
    lsc_count = emp.get("lsc_count", 0) or 0
    if lsc_count > 0 and guest_count > 0:
        emp["guests_per_lsc"] = round(guest_count / lsc_count, 2)
    
    # Recalculate CV score if any CV fields were updated
    if any(k in updates for k in ["cv_promoters", "cv_passives", "cv_detractors", "nps_score"]):
        promoters = emp.get("cv_promoters", 0) or 0
        detractors = emp.get("cv_detractors", 0) or 0
        nps_score = emp.get("nps_score", 0) or 0
        
        # NPS pts: max 10 based on NPS percentage
        nps_pts = min(nps_score / 10, 10.0) if nps_score else 0
        
        # CV Score = NPS pts (max 10) + Promoters × 1 - Detractors × 2
        cv_score = round(nps_pts + (promoters * 1) - (detractors * 2), 2)
        emp["cv_score"] = cv_score
        emp["nps_score_pts"] = round(nps_pts, 2)
        emp["cv_raw_points"] = promoters - (detractors * 2)
        
        logger.info(f"Recalculated CV score for {emp.get('name')}: promoters={promoters}, detractors={detractors}, nps={nps_score}, cv_score={cv_score}")
    
    # Recalculate RT bonus if rt_mentions updated
    if "rt_mentions" in updates or "review_mentions" in updates:
        rt_mentions = emp.get("rt_mentions", 0) or 0
        # RT Bonus = mentions × 0.5, capped at 15 pts
        emp["review_tracker_bonus"] = min(rt_mentions * 0.5, 15.0)
        logger.info(f"Recalculated RT bonus for {emp.get('name')}: mentions={rt_mentions}, bonus={emp['review_tracker_bonus']}")
    
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
    
    # ALSO sync critical fields back to employees_v2 to prevent data drift
    # This ensures fix-snapshot-names won't overwrite with stale data
    updated_emp = employees[emp_idx]
    sync_fields = ["display_name", "report_name", "job_title", "name"]
    sync_data = {k: updated_emp.get(k) for k in sync_fields if updated_emp.get(k)}
    
    if sync_data:
        # Try multiple matching strategies to find the employee in employees_v2
        report_name = updated_emp.get("report_name", "").strip()
        display_name = updated_emp.get("display_name", "").strip()
        
        # Update employees_v2 with the corrected data
        update_result = await db.employees_v2.update_one(
            {
                "$or": [
                    {"name": {"$regex": f"^{report_name}$", "$options": "i"}},
                    {"report_name": {"$regex": f"^{report_name}$", "$options": "i"}},
                    {"display_name": display_name},
                    {"name": {"$regex": f"^{display_name}", "$options": "i"}}
                ],
                "year": snapshot.get("year", 2026),
                "quarter": snapshot.get("quarter", "Q1").upper()
            },
            {"$set": sync_data}
        )
        if update_result.modified_count > 0:
            logger.info(f"Synced employee {employee_id} data back to employees_v2")
    
    # Get the updated employee data
    updated_emp = next((e for e in employees if e.get("id") == employee_id or e.get("name", "").lower() == employee_id.lower()), scored_emp)
    
    logger.info(f"Updated employee {employee_id} in snapshot {snapshot_id}, new score: {updated_emp.get('total_score')}")
    
    return {
        "success": True,
        "message": f"Updated employee in snapshot",
        "employee": {k: v for k, v in updated_emp.items() if k != "_id"}
    }




@snapshot_router.delete("/employees/{employee_id}")
async def delete_snapshot_employee(employee_id: str):
    """
    Delete an employee from the current active snapshot.
    Used to remove duplicates or incorrect entries.
    """
    db = get_db()
    
    # Find current active snapshot
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
    
    snapshot_id = snapshot["id"]
    employees = snapshot.get("employees", [])
    
    # Find and remove employee
    original_count = len(employees)
    employees = [e for e in employees if e.get("id") != employee_id and e.get("name", "").lower() != employee_id.lower()]
    
    if len(employees) == original_count:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found in snapshot")
    
    # Update snapshot
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {"$set": {"employees": employees}}
    )
    
    logger.info(f"Deleted employee {employee_id} from snapshot {snapshot_id}")
    


@snapshot_router.post("/rebuild-from-pos")
async def rebuild_snapshot_from_pos():
    """
    Completely rebuild the snapshot employees from POS data.
    Sets first names as display, full names as report_name.
    """
    db = get_db()
    
    # Get current snapshot
    snapshot = await db.snapshot_workflow.find_one({"is_current": True}, {"_id": 0})
    if not snapshot:
        raise HTTPException(status_code=404, detail="No active snapshot found")
    
    # Get POS data
    pos_employees = []
    for u in snapshot.get("uploads", []):
        if u.get("upload_type") == "pos_report":
            pos_employees = u.get("parsed_data", {}).get("employees", [])
            break
    
    if not pos_employees:
        raise HTTPException(status_code=400, detail="No POS data found in snapshot")
    
    # Get existing employees to preserve scores/CV/RT data
    existing_by_name = {}
    for emp in snapshot.get("employees", []):
        # Index by multiple possible name keys
        for key in [emp.get("name", "").lower(), emp.get("report_name", "").lower(), emp.get("display_name", "").lower()]:
            if key:
                existing_by_name[key] = emp
    
    # Rebuild employees from POS
    new_employees = []
    seen = set()
    
    for pos_emp in pos_employees:
        full_name = pos_emp.get("name", "").strip()
        if not full_name or full_name.lower() in seen:
            continue
        seen.add(full_name.lower())
        
        first_name = full_name.split()[0]
        
        # Find existing data
        existing = existing_by_name.get(full_name.lower()) or existing_by_name.get(first_name.lower()) or {}
        
        # Calculate metrics
        guest_count = pos_emp.get("guest_count", 0) or 0
        liquor = pos_emp.get("liquor_sales", 0) or 0
        beer = pos_emp.get("beer_sales", 0) or 0
        wine = pos_emp.get("wine_sales", 0) or 0
        lbw_total = liquor + beer + wine
        glassware = pos_emp.get("glassware_sales", 0) or pos_emp.get("bar_glassware_sales", 0) or 0
        loyalty = pos_emp.get("loyalty_sales", 0) or 0
        lsc_count = round(loyalty / 25) if loyalty > 0 else 0
        
        lbw_per_guest = round(lbw_total / guest_count, 2) if guest_count > 0 else 0
        glass_per_guest = round(glassware / guest_count, 2) if guest_count > 0 else 0
        guests_per_lsc = round(guest_count / lsc_count, 2) if lsc_count > 0 else 0
        
        emp = {
            "id": existing.get("id") or str(uuid.uuid4()),
            "name": first_name,
            "display_name": first_name,
            "report_name": full_name,
            "job_title": existing.get("job_title") or "Server",
            "quarter": snapshot.get("quarter"),
            "year": snapshot.get("year"),
            "guest_count": guest_count,
            "guests": guest_count,
            "net_sales": pos_emp.get("net_sales", 0) or 0,
            "ppa": pos_emp.get("ppa", 0) or 0,
            "liquor_sales": liquor,
            "beer_sales": beer,
            "wine_sales": wine,
            "lbw": lbw_total,
            "lbw_per_guest": lbw_per_guest,
            "bar_glassware_sales": glassware,
            "glassware_per_guest": glass_per_guest,
            "loyalty_sales": loyalty,
            "lsc_count": lsc_count,
            "guests_per_lsc": guests_per_lsc,
            # Preserve CV/RT data
            "cv_promoters": existing.get("cv_promoters", 0),
            "cv_passives": existing.get("cv_passives", 0),
            "cv_detractors": existing.get("cv_detractors", 0),
            "cv_score": existing.get("cv_score", 0),
            "nps_score": existing.get("nps_score", 0),
            "nps_score_pts": existing.get("nps_score_pts", 0),
            "rt_mentions": existing.get("rt_mentions", 0),
            "review_tracker_bonus": existing.get("review_tracker_bonus", 0),
        }
        new_employees.append(emp)
    
    # Calculate scores
    from snapshot_manager import calculate_employee_scores, assign_performance_tiers
    benchmarks = {"ppa": 55.0, "lbw": 8.0, "glass": 1.25, "lsc": 100.0}
    
    scored_employees = []
    for emp in new_employees:
        scored = calculate_employee_scores(emp, benchmarks)
        scored_employees.append(scored)
    
    # Assign tiers
    final_employees = assign_performance_tiers(scored_employees)
    
    # Update snapshot
    await db.snapshot_workflow.update_one(
        {"id": snapshot["id"]},
        {"$set": {
            "employees": final_employees,
            "status": "completed",
            "is_current": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "success": True,
        "employee_count": len(final_employees),
        "employees": [{"name": e["name"], "report_name": e["report_name"]} for e in final_employees]
    }


    return {
        "success": True,
        "message": f"Deleted employee from snapshot",
        "remaining_count": len(employees)
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


@snapshot_router.post("/fix-snapshot-names")
async def fix_snapshot_names():
    """
    Fix display names and tiers in the active snapshot.
    Syncs display_name and job_title from employees_v2, re-assigns tiers, and sorts properly.
    """
    db = get_db()
    
    # Find active snapshot
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
    
    # Build lookup from employees_v2 for display_name and job_title
    # Use multiple keys: full name, first name, display_name, report_name
    name_lookup = {}
    async for emp in db.employees_v2.find({}, {"_id": 0}):
        emp_data = {
            "display_name": emp.get("display_name") or emp.get("name", "").split()[0],
            "job_title": emp.get("job_title", "Server")
        }
        
        # Add multiple keys for flexible matching
        name = emp.get("name", "").lower().strip()
        display = (emp.get("display_name") or "").lower().strip()
        report = (emp.get("report_name") or "").lower().strip()
        first_name = name.split()[0] if name else ""
        
        if name: name_lookup[name] = emp_data
        if display and display != name: name_lookup[display] = emp_data
        if report and report != name: name_lookup[report] = emp_data
        if first_name and first_name != name: name_lookup[first_name] = emp_data
    
    # Update employees in snapshot
    employees = snapshot.get('employees', [])
    changes = []
    
    for emp in employees:
        emp_name = emp.get('name', '').lower().strip()
        emp_report = emp.get('report_name', '').lower().strip()
        emp_first = emp_name.split()[0] if emp_name else ""
        
        # Find match using multiple strategies
        lookup = (name_lookup.get(emp_name) or 
                  name_lookup.get(emp_report) or 
                  name_lookup.get(emp_first))
        
        if lookup:
            old_display = emp.get('display_name')
            old_job = emp.get('job_title')
            
            # Set display_name from lookup (or derive from first name) - ONLY if not already set
            current_display = emp.get('display_name', '')
            if not current_display or current_display == 'None' or ' ' in current_display:
                new_display = lookup.get('display_name') or emp_name.split()[0].title()
                if new_display and new_display != 'None':
                    emp['display_name'] = new_display
                    emp['name'] = new_display  # Sync name with display_name
            
            # ONLY set job_title from lookup if current job_title is generic "Server"
            # This preserves Trainer/Bartender assignments that were already set
            current_job = emp.get('job_title', 'Server').lower()
            lookup_job = lookup.get('job_title', 'Server').lower()
            
            # Only update if: current is generic AND lookup has a specific role
            if current_job == 'server' and lookup_job in ['trainer', 'bartender']:
                emp['job_title'] = lookup_job
            
            if old_display != emp.get('display_name') or old_job != emp.get('job_title'):
                changes.append(f"{emp_report or emp_name}: display='{emp.get('display_name')}', job='{emp.get('job_title')}'")
        else:
            # No lookup found - derive display_name from first word of name
            current_name = emp.get('name', '')
            first_name = current_name.split()[0].title() if current_name else 'Unknown'
            emp['display_name'] = first_name
            emp['name'] = first_name
            emp['report_name'] = current_name  # Preserve original as report_name
            changes.append(f"{current_name}: derived display='{first_name}', no job match")
    
    # Re-calculate scores and assign tiers (which also sorts)
    from snapshot_manager import assign_performance_tiers
    employees = assign_performance_tiers(employees)
    
    # Update snapshot
    await db.snapshot_workflow.update_one(
        {"id": snapshot['id']},
        {
            "$set": {
                "employees": employees,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    logger.info(f"Fixed {len(changes)} employee names/tiers in snapshot {snapshot['id']}")
    
    return {
        "success": True,
        "message": f"Fixed {len(changes)} employees in snapshot",
        "changes": changes[:20],  # Limit output
        "employee_count": len(employees),
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
    This marks the data as reviewed AND updates the snapshot employees directly.
    """
    db = get_db()
    
    snapshot = await db.snapshot_workflow.find_one({"id": snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    employees_data = data.get("employees", [])
    if not employees_data:
        raise HTTPException(status_code=400, detail="No employee data provided")
    
    logger.info(f"confirm_pos_review: Received {len(employees_data)} employees to update")
    
    # Find the POS upload and update it with reviewed data
    uploads = snapshot.get("uploads", [])
    pos_upload_idx = next(
        (i for i, u in enumerate(uploads) if u.get("upload_type") == "pos_report"),
        None
    )
    
    if pos_upload_idx is not None:
        # MERGE the incoming employee data with existing POS data (don't replace all)
        existing_pos_employees = uploads[pos_upload_idx].get("parsed_data", {}).get("employees", [])
        
        # Build a lookup of existing POS employees by name
        pos_emp_lookup = {}
        for i, emp in enumerate(existing_pos_employees):
            name_key = emp.get("name", "").lower().strip()
            pos_emp_lookup[name_key] = i
        
        # Update existing or add new
        for new_emp in employees_data:
            name = new_emp.get("name", "").lower().strip()
            if name in pos_emp_lookup:
                # Update existing employee in POS data
                idx = pos_emp_lookup[name]
                existing_pos_employees[idx].update(new_emp)
                logger.info(f"confirm_pos_review: Updated POS data for '{name}'")
            else:
                # Add new employee to POS data
                existing_pos_employees.append(new_emp)
                logger.info(f"confirm_pos_review: Added new employee '{name}' to POS data")
        
        uploads[pos_upload_idx]["parsed_data"]["employees"] = existing_pos_employees
        uploads[pos_upload_idx]["parsed_data"]["record_count"] = len(existing_pos_employees)
        uploads[pos_upload_idx]["reviewed"] = True
        uploads[pos_upload_idx]["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"confirm_pos_review: POS upload now has {len(existing_pos_employees)} employees")
    
    # ALSO update the snapshot employees directly (always, not just when completed)
    # This ensures edits take effect immediately without needing to reprocess
    existing_employees = snapshot.get("employees", [])
    logger.info(f"confirm_pos_review: Found {len(existing_employees)} existing employees in snapshot")
    if existing_employees:
        # Build lookup by name for matching
        emp_lookup = {}
        for emp in existing_employees:
            name_key = emp.get("name", "").lower().strip()
            report_key = emp.get("report_name", "").lower().strip()
            if name_key:
                emp_lookup[name_key] = emp
            if report_key and report_key != name_key:
                emp_lookup[report_key] = emp
        
        # Update matching employees with new POS data
        from snapshot_manager import calculate_employee_scores, assign_performance_tiers
        
        # Get benchmarks
        settings = await db.quarter_settings.find_one(
            {"year": snapshot.get("year", 2026), "quarter": snapshot.get("quarter", "Q1").upper()},
            {"_id": 0}
        )
        benchmarks = {
            "ppa": settings.get("benchmark_ppa", 55.0) if settings else 55.0,
            "lbw": settings.get("benchmark_lbw", 8.0) if settings else 8.0,
            "glass": settings.get("benchmark_glass", 1.25) if settings else 1.25,
            "lsc": settings.get("benchmark_lsc", 100.0) if settings else 100.0,
        }
        
        for new_emp in employees_data:
            name = new_emp.get("name", "").lower().strip()
            existing = emp_lookup.get(name)
            
            logger.info(f"confirm_pos_review: Looking for '{name}' in lookup. Found: {existing is not None}")
            
            if existing:
                # Update POS fields
                old_ppa = existing.get("ppa")
                old_glassware = existing.get("bar_glassware_sales")
                for field in ["guest_count", "guests", "net_sales", "ppa", "liquor_sales", "beer_sales", 
                              "wine_sales", "lbw_total", "lbw_per_guest", "glassware_sales", "bar_glassware_sales",
                              "glassware_per_guest", "loyalty_sales", "lsc_count", "guests_per_lsc"]:
                    if field in new_emp and new_emp[field] is not None:
                        existing[field] = new_emp[field]
                
                # Sync field aliases
                if "glassware_sales" in new_emp:
                    existing["bar_glassware_sales"] = new_emp["glassware_sales"]
                if "guests" in new_emp:
                    existing["guest_count"] = new_emp["guests"]
                
                logger.info(f"confirm_pos_review: Updated '{name}' PPA from {old_ppa} to {existing.get('ppa')}, glassware from {old_glassware} to {existing.get('bar_glassware_sales')}")
                
                # Recalculate derived values (LBW per guest, etc.)
                guest_count = existing.get("guest_count") or existing.get("guests") or 0
                if guest_count > 0:
                    lbw = existing.get("lbw") or (
                        (existing.get("liquor_sales") or 0) + 
                        (existing.get("beer_sales") or 0) + 
                        (existing.get("wine_sales") or 0)
                    )
                    existing["lbw"] = lbw
                    existing["lbw_per_guest"] = round(lbw / guest_count, 2)
                    
                    glassware = existing.get("bar_glassware_sales") or existing.get("glassware_sales") or 0
                    existing["glassware_per_guest"] = round(glassware / guest_count, 2)
                
                lsc_count = existing.get("lsc_count") or 0
                if lsc_count > 0 and guest_count > 0:
                    existing["guests_per_lsc"] = round(guest_count / lsc_count, 2)
                
                # Recalculate scores
                old_score = existing.get("total_score")
                calculate_employee_scores(existing, benchmarks)
                logger.info(f"confirm_pos_review: Recalculated '{name}' score from {old_score} to {existing.get('total_score')}")
        
        # Re-assign tiers
        existing_employees = assign_performance_tiers(existing_employees)
    
    # Save to database
    update_data = {
        "uploads": uploads,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if existing_employees:
        update_data["employees"] = existing_employees
    
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {"$set": update_data}
    )
    
    return {
        "success": True,
        "message": f"POS data reviewed and confirmed ({len(employees_data)} employees)"
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
    Get rankings from the current active snapshot.
    If there's an is_current=True snapshot, use that (even if in_progress).
    Otherwise, fall back to the latest completed snapshot.
    This ensures edits made to the active snapshot are visible.
    """
    db = get_db()
    
    # First try to find the current active snapshot (regardless of status)
    current_query = {"is_current": True}
    if quarter:
        current_query["quarter"] = quarter.upper()
    if year:
        current_query["year"] = year
    
    snapshot = await db.snapshot_workflow.find_one(
        current_query,
        {"_id": 0}
    )
    
    # If no current snapshot, fall back to latest completed
    if not snapshot:
        completed_query = {"status": SnapshotStatus.COMPLETED.value}
        if quarter:
            completed_query["quarter"] = quarter.upper()
        if year:
            completed_query["year"] = year
        
        snapshot = await db.snapshot_workflow.find_one(
            completed_query,
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
    
    # Sort employees by tier before returning
    employees = snapshot.get("employees", [])
    
    # Define tier order
    TIER_ORDER = {
        'Trainer': 1,
        'Bartender': 2,
        'A-Server': 3,
        'B-Server': 4,
        'C-Server': 5,
        'Server': 6
    }
    
    def sort_key(emp):
        tier = emp.get('tier_label', 'Server')
        tier_rank = TIER_ORDER.get(tier, 99)
        score = emp.get('total_score', 0) or 0
        return (tier_rank, -score)  # Sort by tier first, then by score descending
    
    sorted_employees = sorted(employees, key=sort_key)
    
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
        "employees": sorted_employees,
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
    Preserves manually set job_titles, display_names, and other edits from existing snapshot data.
    """
    employees = {}
    
    # Build lookup of existing employee data to preserve edits
    # Use multiple keys for flexible matching (full name, first name, report_name)
    existing_employees = {}
    for emp in snapshot.get("employees", []):
        name = emp.get("name", "").lower().strip()
        display_name = emp.get("display_name", "").lower().strip()
        report_name = emp.get("report_name", "").lower().strip()
        first_name = name.split()[0] if name else ""
        
        # Add to lookup with multiple keys
        if name: existing_employees[name] = emp
        if display_name and display_name != name: existing_employees[display_name] = emp
        if report_name and report_name != name: existing_employees[report_name] = emp
        if first_name and first_name != name: existing_employees[first_name] = emp
    
    for upload in snapshot.get("uploads", []):
        upload_type = upload.get("upload_type")
        parsed_data = upload.get("parsed_data", {})
        
        if upload_type == UploadType.POS_REPORT.value:
            # POS data creates the base employee records
            for emp_data in parsed_data.get("employees", []):
                name = emp_data.get("name", "").strip()
                if not name:
                    continue
                
                # Find existing employee using multiple matching strategies
                name_lower = name.lower()
                first_name_lower = name_lower.split()[0] if name_lower else ""
                existing_emp = (existing_employees.get(name_lower) or 
                               existing_employees.get(first_name_lower))
                
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
                lbw_per_guest = emp_data.get("lbw_per_guest", 0)
                if not lbw_per_guest and guest_count > 0:
                    lbw_per_guest = round(lbw_total / guest_count, 2)
                
                glassware_per_guest = emp_data.get("glassware_per_guest", 0)
                if not glassware_per_guest and guest_count > 0:
                    glassware_per_guest = round(glassware_sales / guest_count, 2)
                
                lsc_count = emp_data.get("lsc_count", 0)
                if not lsc_count and loyalty_sales > 0:
                    lsc_count = round(loyalty_sales / 25)
                
                guests_per_lsc = emp_data.get("guests_per_lsc", 0)
                if not guests_per_lsc and lsc_count > 0:
                    guests_per_lsc = round(guest_count / lsc_count, 2)
                
                # PRESERVE job_title from existing employee - THIS IS CRITICAL
                # Only use POS job_title if no existing job_title or it's generic "Server"
                existing_job = existing_emp.get("job_title", "Server").lower() if existing_emp else "server"
                pos_job = emp_data.get("job_title", "Server")
                
                # If existing job is trainer/bartender, preserve it (don't override with POS data)
                if existing_job in ["trainer", "bartender"]:
                    job_title = existing_job
                else:
                    job_title = pos_job or "Server"
                
                # PRESERVE display_name from existing employee
                # If user set a custom display_name (like "Abby"), keep it
                existing_display = existing_emp.get("display_name", "") if existing_emp else ""
                if existing_display and existing_display.lower() != name.lower() and ' ' not in existing_display:
                    # User has set a custom first-name-only display_name
                    display_name = existing_display
                else:
                    display_name = existing_emp.get("display_name", name) if existing_emp else name
                
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
                    # PRESERVE CV/RT fields from existing employee if they were manually set
                    "cv_promoters": existing_emp.get("cv_promoters", 0) if existing_emp else 0,
                    "cv_passives": existing_emp.get("cv_passives", 0) if existing_emp else 0,
                    "cv_detractors": existing_emp.get("cv_detractors", 0) if existing_emp else 0,
                    "cv_score": existing_emp.get("cv_score", 0) if existing_emp else 0,
                    "nps_score": existing_emp.get("nps_score", 0) if existing_emp else 0,
                    # PRESERVE RT mentions - critical for manual corrections
                    "rt_mentions": existing_emp.get("rt_mentions", 0) if existing_emp else 0,
                    "review_tracker_bonus": existing_emp.get("review_tracker_bonus", 0) if existing_emp else 0,
                    "dar_penalty": existing_emp.get("dar_penalty", 0) if existing_emp else 0,
                    # Preserve calculated scores if they exist
                    "total_metric_bonus": existing_emp.get("total_metric_bonus", 0) if existing_emp else 0,
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



@snapshot_router.post("/recalculate-tiers")
async def recalculate_tiers(year: int = 2026, quarter: str = "Q1"):
    """
    Recalculate performance tiers for all employees in the active snapshot
    using the current quarter settings thresholds.
    """
    db = get_db()
    
    # Get quarter settings for thresholds
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    
    a_min = settings.get("a_server_min_score", 85) if settings else 85
    b_min = settings.get("b_server_min_score", 70) if settings else 70
    
    # Get active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No active snapshot found for {quarter} {year}")
    
    employees = snapshot.get("employees", [])
    if not employees:
        raise HTTPException(status_code=404, detail="No employees in snapshot")
    
    # Reassign tiers using new thresholds
    updated_employees = assign_performance_tiers(employees, a_min=a_min, b_min=b_min)
    
    # Update snapshot with new tier assignments
    await db.snapshot_workflow.update_one(
        {"id": snapshot["id"]},
        {"$set": {"employees": updated_employees}}
    )
    
    # Count by tier
    tier_counts = {}
    for emp in updated_employees:
        tier = emp.get("tier_label", "Unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    return {
        "success": True,
        "message": f"Recalculated tiers with A>={a_min}, B>={b_min}, C<{b_min}",
        "tier_counts": tier_counts,
        "total_employees": len(updated_employees)
    }
