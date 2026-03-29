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
    
    if source:
        upload_record["source"] = source
    
    if parse_error:
        upload_record["status"] = UploadStatus.FAILED.value
        upload_record["error"] = parse_error
    elif final_parsed_data:
        upload_record["status"] = UploadStatus.PARSED.value
    
    # Update snapshot with new upload
    current_uploads = snapshot.get("uploads", [])
    
    # Replace existing upload of same type or add new
    existing_idx = next(
        (i for i, u in enumerate(current_uploads) if u.get("upload_type") == upload_type),
        None
    )
    if existing_idx is not None:
        current_uploads[existing_idx] = upload_record
    else:
        current_uploads.append(upload_record)
    
    # Calculate new progress
    upload_progress = calculate_upload_progress(current_uploads)
    
    # Determine new status
    new_status = snapshot["status"]
    if new_status == SnapshotStatus.DRAFT.value and any(upload_progress.values()):
        new_status = SnapshotStatus.IN_PROGRESS.value
    
    # Update snapshot
    await db.snapshot_workflow.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "uploads": current_uploads,
                "upload_progress": upload_progress,
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Return result
    can_process, missing = can_process_snapshot({
        "upload_progress": upload_progress,
        **snapshot
    })
    
    return {
        "success": parse_error is None,
        "upload": upload_record,
        "upload_progress": upload_progress,
        "can_process": can_process,
        "missing_uploads": missing,
        "message": parse_error or f"Successfully uploaded {file.filename}",
        "record_count": upload_record.get("record_count", 0)
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
        {"_id": 0, "ppa": 1, "lbw_per_guest": 1, "glassware_per_guest": 1, "guests_per_lsc": 1, "guest_count": 1}
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
                "lbw_per_guest": 8.0,
                "glassware_per_guest": 1.25,
                "lsc_count": 5,
                "guest_count": 200
            }
        }
    
    # Calculate averages (excluding zeros/nulls)
    def calc_avg(field):
        values = [e.get(field, 0) for e in all_employees if e.get(field, 0) and e.get(field, 0) > 0]
        return sum(values) / len(values) if values else 0
    
    return {
        "averages": {
            "ppa": round(calc_avg("ppa"), 2),
            "lbw_per_guest": round(calc_avg("lbw_per_guest"), 2),
            "glassware_per_guest": round(calc_avg("glassware_per_guest"), 2),
            "lsc_count": round(calc_avg("lsc_count"), 0),
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
        
        # Get server name - might be from transaction matching or check number
        server_name = item.get("server_name") or "Unknown"
        
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
    """
    employees = {}
    
    for upload in snapshot.get("uploads", []):
        upload_type = upload.get("upload_type")
        parsed_data = upload.get("parsed_data", {})
        
        if upload_type == UploadType.POS_REPORT.value:
            # POS data creates the base employee records
            for emp_data in parsed_data.get("employees", []):
                name = emp_data.get("name", "").strip()
                if not name:
                    continue
                
                employees[name.lower()] = {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "quarter": snapshot.get("quarter"),
                    "year": snapshot.get("year"),
                    "job_title": emp_data.get("job_title", "Server"),
                    "guests": emp_data.get("guest_count", 0),
                    "guest_count": emp_data.get("guest_count", 0),
                    "net_sales": emp_data.get("net_sales", 0),
                    "ppa": emp_data.get("ppa", 0),
                    "lbw_per_guest": emp_data.get("lbw_per_guest", 0),
                    "glassware_per_guest": emp_data.get("glassware_per_guest", 0),
                    "guests_per_lsc": emp_data.get("guests_per_lsc", 0),
                    "lsc_count": emp_data.get("lsc_count", 0),
                    "loyalty_sales": emp_data.get("loyalty_sales", 0),
                    "food_sales": emp_data.get("food_sales", 0),
                    "liquor_sales": emp_data.get("liquor_sales", 0),
                    "beer_sales": emp_data.get("beer_sales", 0),
                    "wine_sales": emp_data.get("wine_sales", 0),
                    "bar_glassware_sales": emp_data.get("bar_glassware_sales", 0),
                    "lbw": emp_data.get("lbw_total", 0),
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
            for cv_data in parsed_data.get("employees", []):
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
                    
                    # CV bonus: +0.5 per promoter, -1 per detractor
                    cv_raw = (promoters * 0.5) - (detractors * 1)
                    employees[name]["cv_raw_points"] = round(max(cv_raw, 0), 2)
                    employees[name]["cv_score"] = round(
                        employees[name].get("nps_score_pts", 0) + employees[name]["cv_raw_points"],
                        2
                    )
        
        elif upload_type == UploadType.REVIEW_TRACKER.value:
            # Merge RT data
            for rt_data in parsed_data.get("employees", []):
                name = rt_data.get("name", "").strip().lower()
                if name in employees:
                    mentions = rt_data.get("mentions", 0)
                    employees[name]["rt_mentions"] = mentions
                    employees[name]["review_tracker_bonus"] = round(mentions * 0.5, 1)
    
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
        
        # Simple name matching - look for employee names in review text
        for name in known_names:
            if not name:
                continue
            
            # Get first name for matching
            first_name = name.split()[0].lower() if name else ""
            
            # Check if first name appears in review
            if first_name and len(first_name) > 2 and first_name in review_text_lower:
                # Store the original capitalized name
                original_name = next(
                    (e.get("name") for e in known_employees if e.get("name", "").lower() == name),
                    name.title()
                )
                if original_name not in employee_mentions:
                    employee_mentions[original_name] = 0
                employee_mentions[original_name] += 1
        
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
