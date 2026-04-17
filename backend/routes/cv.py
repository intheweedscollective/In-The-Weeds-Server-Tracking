"""
Customer Voice (CV) Routes Module
Handles CV feedback, NPS scoring, and adjustment workflows.
Extracted from server.py for better maintainability.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
import logging
import io

logger = logging.getLogger(__name__)

cv_router = APIRouter(prefix="/v2/cv", tags=["Customer Voice"])

def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# ============================================================
# CV SYNC ENDPOINTS (DEPRECATED - Manual upload now preferred)
# ============================================================

@cv_router.post("/sync")
async def sync_loyalty_voice(quarter: str = "Q1", year: int = 2026):
    """
    DEPRECATED: Use manual upload instead.
    Upload Customer Voice data via /api/v2/cv/server-performance/upload or the Data Uploads page.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "This sync endpoint has been deprecated. Please use the manual upload feature. Navigate to Data Uploads page and upload your Customer Voice XLSX file.",
        "alternative": "/api/v2/cv/server-performance/upload"
    }


@cv_router.get("/nps")
async def get_cv_nps_scores(quarter: str = "Q1", year: int = 2026):
    """Get all NPS scores for a quarter from Loyalty Voice sync."""
    db = get_db()
    nps_records = await db.cv_nps.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(500)
    
    return {
        "nps_records": nps_records,
        "total": len(nps_records),
        "quarter": quarter.upper(),
        "year": year
    }


@cv_router.get("/stats")
async def get_cv_stats(quarter: str = "Q1", year: int = 2026):
    """Get NPS statistics from Loyalty Voice.
    Uses official CV stats if set (for 100% accuracy with LV dashboard),
    otherwise falls back to scraped data.
    """
    db = get_db()
    
    # Check for official stats first
    official = await db.official_cv_stats.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    # Get NPS records (always needed for breakdown)
    nps_records = await db.cv_nps.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(500)
    
    # Sort by NPS for breakdown
    sorted_records = sorted(nps_records, key=lambda x: x.get("nps_score", 0), reverse=True)
    
    # Calculate totals from records
    total_promoters = sum(r.get("promoters", 0) for r in nps_records)
    total_passives = sum(r.get("passives", 0) for r in nps_records)
    total_detractors = sum(r.get("detractors", 0) for r in nps_records)
    total_responses = total_promoters + total_passives + total_detractors
    
    # Calculate NPS
    if total_responses > 0:
        calculated_nps = round(((total_promoters - total_detractors) / total_responses) * 100, 1)
    else:
        calculated_nps = 0
    
    # Use official stats if available, otherwise calculated
    if official:
        stats = {
            "source": "official",
            "total_responses": official.get("total_responses", total_responses),
            "promoters": official.get("promoters", total_promoters),
            "passives": official.get("passives", total_passives),
            "detractors": official.get("detractors", total_detractors),
            "nps_score": official.get("nps_score", calculated_nps),
            "set_at": official.get("set_at")
        }
    else:
        stats = {
            "source": "calculated",
            "total_responses": total_responses,
            "promoters": total_promoters,
            "passives": total_passives,
            "detractors": total_detractors,
            "nps_score": calculated_nps
        }
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "stats": stats,
        "server_count": len(nps_records),
        "top_performers": sorted_records[:5],
        "needs_attention": sorted_records[-5:] if len(sorted_records) >= 5 else sorted_records
    }


@cv_router.get("/employee/{employee_name}/nps")
async def get_employee_cv_nps(employee_name: str, quarter: str = "Q1", year: int = 2026):
    """Get CV NPS details for a specific employee."""
    db = get_db()
    
    # Search with case-insensitive regex
    nps_record = await db.cv_nps.find_one(
        {
            "employee_name": {"$regex": f"^{employee_name}$", "$options": "i"},
            "quarter": quarter.upper(),
            "year": year
        },
        {"_id": 0}
    )
    
    if not nps_record:
        return {
            "found": False,
            "employee_name": employee_name,
            "quarter": quarter.upper(),
            "year": year
        }
    
    return {
        "found": True,
        "data": nps_record
    }


@cv_router.get("/sync/status")
async def get_cv_sync_status():
    """Get the status of the last CV sync."""
    db = get_db()
    
    status = await db.cv_sync_status.find_one(
        {},
        {"_id": 0},
        sort=[("synced_at", -1)]
    )
    
    return status or {"status": "never_synced", "message": "No sync has been performed yet"}


@cv_router.post("/feedback/sync")
async def sync_cv_feedback(quarter: str = "Q1", year: int = 2026):
    """
    DEPRECATED: Use manual upload instead.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "This sync endpoint has been deprecated. Please use the manual upload feature.",
        "alternative": "/api/v2/cv/server-performance/upload"
    }


@cv_router.get("/feedback")
async def get_cv_feedback(quarter: str = "Q1", year: int = 2026, limit: int = 100, include_excluded: bool = False):
    """Get CV feedback records for a quarter."""
    db = get_db()
    
    query = {"quarter": quarter.upper(), "year": year}
    if not include_excluded:
        query["excluded"] = {"$ne": True}
    
    feedback = await db.cv_feedback.find(
        query,
        {"_id": 0}
    ).sort("submitted_at", -1).limit(limit).to_list(limit)
    
    # Get counts
    total = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year})
    excluded = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year, "excluded": True})
    
    return {
        "feedback": feedback,
        "showing": len(feedback),
        "total": total,
        "excluded_count": excluded,
        "quarter": quarter.upper(),
        "year": year
    }


@cv_router.get("/feedback/stats")
async def get_cv_feedback_stats(quarter: str = "Q1", year: int = 2026):
    """Get statistics about CV feedback for a quarter."""
    db = get_db()
    
    # Get all feedback
    feedback = await db.cv_feedback.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    # Calculate stats
    total = len(feedback)
    excluded = len([f for f in feedback if f.get("excluded")])
    included = total - excluded
    
    promoters = len([f for f in feedback if not f.get("excluded") and f.get("rating", 0) >= 9])
    passives = len([f for f in feedback if not f.get("excluded") and 7 <= f.get("rating", 0) <= 8])
    detractors = len([f for f in feedback if not f.get("excluded") and f.get("rating", 0) <= 6])
    
    nps = round(((promoters - detractors) / included) * 100, 1) if included > 0 else 0
    
    # Server breakdown
    server_counts = {}
    for f in feedback:
        if not f.get("excluded"):
            server = f.get("server_name", "Unassigned")
            server_counts[server] = server_counts.get(server, 0) + 1
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "total_feedback": total,
        "included": included,
        "excluded": excluded,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "nps": nps,
        "servers_with_feedback": len(server_counts),
        "top_servers": sorted(server_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    }


@cv_router.get("/points/{employee_id}")
async def get_employee_cv_points(employee_id: str, quarter: str = "Q1", year: int = 2026):
    """Get CV points breakdown for an employee."""
    db = get_db()
    
    employee = await db.employees_v2.find_one(
        {"id": employee_id, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    promoters = employee.get("cv_promoters", 0)
    detractors = employee.get("cv_detractors", 0)
    
    # CV points formula: (Promoters × 1) + (Detractors × -2)
    cv_points = (promoters * 1) + (detractors * -2)
    
    return {
        "employee_id": employee_id,
        "name": employee.get("name"),
        "cv_promoters": promoters,
        "cv_passives": employee.get("cv_passives", 0),
        "cv_detractors": detractors,
        "nps_score": employee.get("nps_score", 0),
        "cv_points": cv_points,
        "formula": f"({promoters} × 1) + ({detractors} × -2) = {cv_points}"
    }


@cv_router.post("/feedback/{feedback_id}/exclude")
async def exclude_cv_feedback(feedback_id: str):
    """Exclude a CV feedback record from scoring."""
    db = get_db()
    
    # Find the feedback
    feedback = await db.cv_feedback.find_one({"id": feedback_id})
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    if feedback.get("excluded"):
        return {"success": True, "message": "Feedback already excluded", "id": feedback_id}
    
    # Mark as excluded
    await db.cv_feedback.update_one(
        {"id": feedback_id},
        {"$set": {
            "excluded": True,
            "excluded_at": datetime.now(timezone.utc).isoformat(),
            "excluded_reason": "manual"
        }}
    )
    
    # Recalculate server's NPS if assigned
    server_name = feedback.get("server_name")
    quarter = feedback.get("quarter")
    year = feedback.get("year")
    
    if server_name and quarter and year:
        await _recalculate_server_cv_stats(server_name, quarter, year)
    
    return {
        "success": True,
        "message": "Feedback excluded",
        "id": feedback_id,
        "server_name": server_name
    }


@cv_router.post("/feedback/{feedback_id}/include")
async def include_cv_feedback(feedback_id: str):
    """Re-include a previously excluded CV feedback record."""
    db = get_db()
    
    # Find the feedback
    feedback = await db.cv_feedback.find_one({"id": feedback_id})
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    if not feedback.get("excluded"):
        return {"success": True, "message": "Feedback already included", "id": feedback_id}
    
    # Remove excluded flag
    await db.cv_feedback.update_one(
        {"id": feedback_id},
        {"$unset": {"excluded": "", "excluded_at": "", "excluded_reason": ""}}
    )
    
    # Recalculate server's NPS if assigned
    server_name = feedback.get("server_name")
    quarter = feedback.get("quarter")
    year = feedback.get("year")
    
    if server_name and quarter and year:
        await _recalculate_server_cv_stats(server_name, quarter, year)
    
    return {
        "success": True,
        "message": "Feedback re-included",
        "id": feedback_id,
        "server_name": server_name
    }


async def _recalculate_server_cv_stats(server_name: str, quarter: str, year: int):
    """Helper to recalculate CV stats for a server after feedback changes."""
    db = get_db()
    
    # Get all non-excluded feedback for this server
    feedback = await db.cv_feedback.find({
        "server_name": {"$regex": f"^{server_name}$", "$options": "i"},
        "quarter": quarter.upper(),
        "year": year,
        "excluded": {"$ne": True}
    }).to_list(100)
    
    promoters = len([f for f in feedback if f.get("rating", 0) >= 9])
    passives = len([f for f in feedback if 7 <= f.get("rating", 0) <= 8])
    detractors = len([f for f in feedback if f.get("rating", 0) <= 6])
    total = len(feedback)
    
    nps = round(((promoters - detractors) / total) * 100, 2) if total > 0 else 0
    
    # Update employee record
    await db.employees_v2.update_one(
        {
            "name": {"$regex": f"^{server_name}$", "$options": "i"},
            "quarter": quarter.upper(),
            "year": year
        },
        {"$set": {
            "cv_promoters": promoters,
            "cv_passives": passives,
            "cv_detractors": detractors,
            "nps_score": nps,
            "cv_score": (promoters * 1) + (detractors * -2)
        }}
    )
    
    # Update cv_nps record
    await db.cv_nps.update_one(
        {
            "employee_name": {"$regex": f"^{server_name}$", "$options": "i"},
            "quarter": quarter.upper(),
            "year": year
        },
        {"$set": {
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "total_responses": total,
            "nps_score": nps,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )


@cv_router.post("/server-performance/upload")
async def upload_cv_server_performance(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload Customer Voice Server Performance report (XLSX format).
    This is the preferred method for importing CV data.
    """
    db = get_db()
    
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="File must be Excel (.xlsx, .xls) or CSV (.csv)")
    
    try:
        import pandas as pd
        
        contents = await file.read()
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Normalize column names
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        
        # Map columns to expected names - handle various NPS report formats
        if 'server_name' not in df.columns:
            col_mapping = {}
            for col in df.columns:
                col_lower = col.lower()
                if any(x in col_lower for x in ['server', 'name', 'employee', 'staff', 'team_member']):
                    if 'server_name' not in col_mapping.values():
                        col_mapping[col] = 'server_name'
                elif 'promoter' in col_lower:
                    col_mapping[col] = 'promoters'
                elif 'passive' in col_lower:
                    col_mapping[col] = 'passives'
                elif 'detractor' in col_lower:
                    col_mapping[col] = 'detractors'
                elif 'nps' in col_lower or 'score' in col_lower:
                    col_mapping[col] = 'nps_score'
                elif 'total' in col_lower and 'response' in col_lower:
                    col_mapping[col] = 'total_responses'
            
            df = df.rename(columns=col_mapping)
        
        if 'server_name' not in df.columns:
            return {
                "success": False,
                "detail": f"Could not find server name column. Found columns: {', '.join(df.columns)}. Expected a column with 'server', 'name', or 'employee' in it.",
                "columns_found": list(df.columns)
            }
        
        # Process each row
        imported = 0
        updated = 0
        errors = []
        
        for _, row in df.iterrows():
            try:
                server_name = str(row.get('server_name', '')).strip()
                if not server_name or server_name.lower() in ['nan', 'none', '']:
                    continue
                
                promoters = int(row.get('promoters', 0) or 0)
                passives = int(row.get('passives', 0) or 0)
                detractors = int(row.get('detractors', 0) or 0)
                total = promoters + passives + detractors
                
                # Skip rows with no response data — don't overwrite existing data with zeros
                if total == 0:
                    continue
                
                nps = round(((promoters - detractors) / total) * 100, 2)
                
                # Check if record exists
                existing = await db.cv_nps.find_one({
                    "employee_name": {"$regex": f"^{server_name}$", "$options": "i"},
                    "quarter": quarter.upper(),
                    "year": year
                })
                
                record = {
                    "employee_name": server_name,
                    "quarter": quarter.upper(),
                    "year": year,
                    "promoters": promoters,
                    "passives": passives,
                    "detractors": detractors,
                    "total_responses": total,
                    "nps_score": nps,
                    "source": "manual_upload",
                    "uploaded_at": datetime.now(timezone.utc).isoformat()
                }
                
                if existing:
                    await db.cv_nps.update_one(
                        {"_id": existing["_id"]},
                        {"$set": record}
                    )
                    updated += 1
                else:
                    record["id"] = str(uuid.uuid4())
                    await db.cv_nps.insert_one(record)
                    imported += 1
                
                # Also update employee record if exists - try multiple name match strategies
                emp_match = await db.employees_v2.find_one({
                    "$or": [
                        {"name": {"$regex": f"^{server_name}$", "$options": "i"}},
                        {"display_name": {"$regex": f"^{server_name}$", "$options": "i"}},
                        {"report_name": {"$regex": f"^{server_name}$", "$options": "i"}},
                    ],
                    "quarter": quarter.upper(),
                    "year": year
                })
                
                # Try first-name match if no exact match
                if not emp_match:
                    first_name = server_name.split()[0] if server_name else ""
                    if first_name and len(first_name) > 2:
                        emp_match = await db.employees_v2.find_one({
                            "$or": [
                                {"name": {"$regex": f"^{first_name}\\b", "$options": "i"}},
                                {"display_name": {"$regex": f"^{first_name}\\b", "$options": "i"}},
                            ],
                            "quarter": quarter.upper(),
                            "year": year
                        })
                
                if emp_match:
                    await db.employees_v2.update_one(
                        {"_id": emp_match["_id"]},
                        {"$set": {
                            "cv_promoters": promoters,
                            "cv_passives": passives,
                            "cv_detractors": detractors,
                            "nps_score": nps,
                            "cv_score": (promoters * 1) + (detractors * -2)
                        }}
                    )
                
            except Exception as e:
                errors.append({"row": server_name, "error": str(e)})
        
        return {
            "success": True,
            "quarter": quarter.upper(),
            "year": year,
            "summary": {
                "employees_updated": imported + updated,
                "total_responses": sum(1 for _ in df.iterrows()) if 'df' in dir() else 0,
                "total_promoters": int(df.get('promoters', pd.Series([0])).sum()) if 'promoters' in df.columns else 0,
                "total_detractors": int(df.get('detractors', pd.Series([0])).sum()) if 'detractors' in df.columns else 0,
            },
            "imported": imported,
            "updated": updated,
            "errors": errors[:10] if errors else [],
            "total_processed": imported + updated
        }
        
    except Exception as e:
        logger.error(f"CV upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# CV ADJUSTMENT SESSION ENDPOINTS
# ============================================================

@cv_router.post("/adjustment/upload")
async def upload_cv_adjustment_file(
    feedback_file: UploadFile = File(...),
    transaction_file: Optional[UploadFile] = File(None),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload a CV feedback file for adjustment/review.
    Creates an adjustment session for manual review.
    """
    db = get_db()
    
    try:
        import pandas as pd
        
        contents = await feedback_file.read()
        
        if feedback_file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Normalize columns
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        
        # Create session
        session_id = str(uuid.uuid4())
        
        items = []
        for idx, row in df.iterrows():
            item = {
                "id": str(uuid.uuid4()),
                "index": idx,
                "rating": int(row.get('rating', row.get('nps_rating', 0)) or 0),
                "comment": str(row.get('comment', row.get('feedback', row.get('comments', ''))) or ''),
                "server_name": str(row.get('server_name', row.get('server', row.get('employee', ''))) or ''),
                "submitted_at": str(row.get('date', row.get('submitted_at', '')) or ''),
                "status": "pending",  # pending, approved, excluded
                "auto_detected": False,
                "detection_reasons": []
            }
            
            # Auto-detect non-server issues
            try:
                from cv_adjustment import detect_non_server_issues
                is_non_server, reasons, category = detect_non_server_issues(item["comment"])
                if is_non_server:
                    item["auto_detected"] = True
                    item["detection_reasons"] = reasons
                    item["detection_category"] = category
            except ImportError:
                pass
            
            items.append(item)
        
        session = {
            "id": session_id,
            "quarter": quarter.upper(),
            "year": year,
            "filename": feedback_file.filename,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "items": items,
            "summary": {
                "total": len(items),
                "pending": len(items),
                "approved": 0,
                "excluded": 0,
                "auto_detected": len([i for i in items if i.get("auto_detected")])
            }
        }
        
        await db.cv_adjustment_sessions.insert_one(session)
        
        # Return without _id field
        return {
            "success": True,
            "session_id": session_id,
            "summary": {
                "total_feedback": len(items),
                "auto_detected": session["summary"]["auto_detected"],
            },
            "feedback_items": items,
            "total_items": len(items),
            "auto_detected_issues": session["summary"]["auto_detected"]
        }
        
    except Exception as e:
        logger.error(f"CV adjustment upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@cv_router.get("/adjustment/sessions")
async def get_cv_adjustment_sessions(quarter: str = "Q1", year: int = 2026):
    """Get all CV adjustment sessions for a quarter."""
    db = get_db()
    
    sessions = await db.cv_adjustment_sessions.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "items": 0}  # Exclude items for list view
    ).sort("created_at", -1).to_list(50)
    
    return {
        "sessions": sessions,
        "count": len(sessions)
    }


@cv_router.get("/adjustment/session/{session_id}")
async def get_cv_adjustment_session(session_id: str):
    """Get a specific CV adjustment session with all items."""
    db = get_db()
    
    session = await db.cv_adjustment_sessions.find_one(
        {"id": session_id},
        {"_id": 0}
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session


@cv_router.post("/adjustment/session/{session_id}/update-item")
async def update_cv_adjustment_item(
    session_id: str,
    item_id: str,
    status: str,
    server_name: Optional[str] = None
):
    """Update a single item in a CV adjustment session."""
    db = get_db()
    
    if status not in ["pending", "approved", "excluded"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    # Find session
    session = await db.cv_adjustment_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update item
    items = session.get("items", [])
    updated = False
    
    for item in items:
        if item["id"] == item_id:
            item["status"] = status
            if server_name:
                item["server_name"] = server_name
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Recalculate summary
    summary = {
        "total": len(items),
        "pending": len([i for i in items if i["status"] == "pending"]),
        "approved": len([i for i in items if i["status"] == "approved"]),
        "excluded": len([i for i in items if i["status"] == "excluded"]),
        "auto_detected": len([i for i in items if i.get("auto_detected")])
    }
    
    await db.cv_adjustment_sessions.update_one(
        {"id": session_id},
        {"$set": {"items": items, "summary": summary}}
    )
    
    return {"success": True, "item_id": item_id, "new_status": status, "summary": summary}


@cv_router.post("/adjustment/sessions/{session_id}/assign-server")
async def assign_server_to_cv_item(
    session_id: str,
    item_id: str,
    server_name: str
):
    """Assign a server name to a CV feedback item."""
    db = get_db()
    
    session = await db.cv_adjustment_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    items = session.get("items", [])
    updated = False
    
    for item in items:
        if item["id"] == item_id:
            item["server_name"] = server_name
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    
    await db.cv_adjustment_sessions.update_one(
        {"id": session_id},
        {"$set": {"items": items}}
    )
    
    return {"success": True, "item_id": item_id, "server_name": server_name}


@cv_router.post("/adjustment/session/{session_id}/apply")
async def apply_cv_adjustment_session(session_id: str):
    """Apply an adjustment session - import approved items to cv_feedback."""
    db = get_db()
    
    session = await db.cv_adjustment_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    quarter = session.get("quarter")
    year = session.get("year")
    items = session.get("items", [])
    
    imported = 0
    excluded = 0
    errors = []
    
    for item in items:
        try:
            if item["status"] == "approved":
                # Import to cv_feedback
                feedback_doc = {
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "quarter": quarter,
                    "year": year,
                    "rating": item.get("rating", 0),
                    "comment": item.get("comment", ""),
                    "server_name": item.get("server_name", ""),
                    "submitted_at": item.get("submitted_at"),
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "source": "adjustment_session"
                }
                
                await db.cv_feedback.insert_one(feedback_doc)
                imported += 1
                
                # Update server's CV stats
                if item.get("server_name"):
                    await _recalculate_server_cv_stats(item["server_name"], quarter, year)
                    
            elif item["status"] == "excluded":
                excluded += 1
                
        except Exception as e:
            errors.append({"item_id": item["id"], "error": str(e)})
    
    # Mark session as applied
    await db.cv_adjustment_sessions.update_one(
        {"id": session_id},
        {"$set": {
            "status": "applied",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "apply_results": {
                "imported": imported,
                "excluded": excluded,
                "errors": len(errors)
            }
        }}
    )
    
    return {
        "success": True,
        "session_id": session_id,
        "imported": imported,
        "excluded": excluded,
        "errors": errors[:10] if errors else []
    }


# Detection keywords for auto-detection
SERVER_KEYWORDS = [
    "server", "waiter", "waitress", "service", "attentive", "friendly",
    "rude", "slow", "fast", "helpful", "professional", "unprofessional"
]

NON_SERVER_KEYWORDS = [
    "food", "cold", "undercooked", "overcooked", "taste", "flavor",
    "parking", "wait time", "reservation", "price", "expensive", "cheap",
    "bathroom", "restroom", "dirty", "clean", "ambiance", "noise", "loud",
    "kitchen", "chef", "manager", "host", "hostess"
]


@cv_router.get("/adjustment/keywords")
async def get_cv_detection_keywords():
    """Get the keywords used for auto-detection."""
    return {
        "server_keywords": SERVER_KEYWORDS,
        "non_server_keywords": NON_SERVER_KEYWORDS
    }


@cv_router.post("/adjustment/test-detection")
async def test_cv_detection(comment: str):
    """Test the auto-detection algorithm on a specific comment."""
    try:
        from cv_adjustment import detect_non_server_issues
        is_non_server, reasons, category = detect_non_server_issues(comment)
    except ImportError:
        # Fallback simple detection
        comment_lower = comment.lower()
        is_non_server = any(kw in comment_lower for kw in NON_SERVER_KEYWORDS)
        reasons = [kw for kw in NON_SERVER_KEYWORDS if kw in comment_lower]
        category = "food_quality" if any(kw in comment_lower for kw in ["food", "cold", "taste"]) else "other"
    
    return {
        "comment": comment,
        "is_non_server_issue": is_non_server,
        "reasons": reasons,
        "category": category
    }
