"""
DAR (Disciplinary Action Reports) & Quarter Finalization Routes
Handles end-of-quarter finalization, DAR deductions, and quarterly reviews.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
import asyncio
import uuid
import base64

logger = logging.getLogger(__name__)

# Router will be included in main server.py
finalization_router = APIRouter(prefix="/v2", tags=["Finalization & DAR"])

def get_db():
    """Get database instance from shared module to avoid circular imports"""
    from database import get_database
    return get_database()

# ============================================================================
# MODELS
# ============================================================================

class DAREntry(BaseModel):
    employee_id: str
    employee_name: str
    written_warnings: int = 0
    suspensions: int = 0

class DARSubmission(BaseModel):
    entries: List[DAREntry]

class DARUpdate(BaseModel):
    written_warnings: int = 0
    suspensions: int = 0

# ============================================================================
# FINALIZATION ENDPOINTS
# ============================================================================

@finalization_router.get("/finalization/{year}/{quarter}")
async def get_quarter_finalization(year: int, quarter: str):
    """Get finalization data for a quarter, including DAR entries."""
    db = get_db()
    finalization = await db.quarter_finalizations.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    
    if finalization:
        return finalization
    
    # Return empty structure if not finalized yet
    return {
        "quarter": quarter.upper(),
        "year": year,
        "is_finalized": False,
        "dar_entries": [],
        "final_rankings": []
    }


@finalization_router.get("/dar/{year}/{quarter}")
async def get_dar_entries(year: int, quarter: str):
    """Get DAR entries for a quarter (even if not finalized)."""
    db = get_db()
    # Check if there's a saved DAR draft
    dar_data = await db.dar_entries.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    
    if dar_data:
        return dar_data.get("entries", [])
    
    return []


@finalization_router.post("/dar/{year}/{quarter}")
async def save_dar_entries(year: int, quarter: str, submission: DARSubmission):
    """Save DAR entries as a draft (before finalizing)."""
    db = get_db()
    await db.dar_entries.update_one(
        {"year": year, "quarter": quarter.upper()},
        {
            "$set": {
                "year": year,
                "quarter": quarter.upper(),
                "entries": [entry.model_dump() for entry in submission.entries],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"message": "DAR entries saved", "count": len(submission.entries)}


@finalization_router.post("/finalize/{year}/{quarter}")
async def finalize_quarter(year: int, quarter: str, submission: DARSubmission, generate_reviews: bool = True):
    """
    Finalize a quarter by applying DAR deductions and locking final rankings.
    - Written Warning DAR: -3 points each
    - Suspension DAR: -5 points each
    
    This creates the final rankings for end-of-quarter reviews.
    Uses SNAPSHOT-FIRST architecture - reads from active snapshot.
    If generate_reviews=True, automatically generates AI reviews for all employees.
    """
    db = get_db()
    from scoring_engine import EmployeeV2, QuarterSettings
    from server import generate_review_content_v2, generate_pdf_v2
    
    # SNAPSHOT-FIRST: Get employees from active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not snapshot:
        # Fallback to latest completed snapshot
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter.upper(), "year": year},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )
    
    if not snapshot or not snapshot.get("employees"):
        # Final fallback to legacy employees_v2
        employees = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        ).to_list(1000)
    else:
        employees = snapshot.get("employees", [])
    
    if not employees:
        raise HTTPException(status_code=404, detail="No employees found for this quarter")
    
    # Build DAR lookup
    dar_lookup = {}
    for entry in submission.entries:
        dar_lookup[entry.employee_id] = {
            "written_warnings": entry.written_warnings,
            "suspensions": entry.suspensions
        }
    
    # Calculate final rankings with DAR deductions
    final_rankings = []
    for emp in employees:
        emp_id = emp.get("id")
        dar = dar_lookup.get(emp_id, {"written_warnings": 0, "suspensions": 0})
        
        pre_dar_score = emp.get("pre_dar_score", emp.get("total_score", 0)) or 0
        written_deduction = dar["written_warnings"] * 3
        suspension_deduction = dar["suspensions"] * 5
        total_deduction = written_deduction + suspension_deduction
        final_score = max(0, pre_dar_score - total_deduction)
        
        final_rankings.append({
            "employee_id": emp_id,
            "employee_name": emp.get("name"),
            "job_title": emp.get("job_title", "Server"),
            "pre_dar_score": pre_dar_score,
            "written_warnings": dar["written_warnings"],
            "suspensions": dar["suspensions"],
            "total_deduction": total_deduction,
            "final_score": final_score
        })
    
    # Sort by final score descending
    final_rankings.sort(key=lambda x: -x["final_score"])
    
    # Add final rank position
    for idx, emp in enumerate(final_rankings):
        emp["final_rank"] = idx + 1
    
    # Save finalization
    finalization_doc = {
        "year": year,
        "quarter": quarter.upper(),
        "is_finalized": True,
        "finalized_at": datetime.now(timezone.utc).isoformat(),
        "dar_entries": [entry.model_dump() for entry in submission.entries],
        "final_rankings": final_rankings,
        "total_employees": len(final_rankings),
        "total_dar_deductions": sum(e["total_deduction"] for e in final_rankings),
        "reviews_generated": False,
        "snapshot_id": snapshot.get("id") if snapshot else None
    }
    
    await db.quarter_finalizations.update_one(
        {"year": year, "quarter": quarter.upper()},
        {"$set": finalization_doc},
        upsert=True
    )
    
    # SNAPSHOT-FIRST: Update the active snapshot with finalization status
    if snapshot and snapshot.get("id"):
        # Update employees in snapshot with final scores (DAR applied)
        final_score_lookup = {r["employee_id"]: r for r in final_rankings}
        updated_employees = []
        for emp in snapshot.get("employees", []):
            emp_id = emp.get("id")
            if emp_id in final_score_lookup:
                emp_final = final_score_lookup[emp_id]
                emp["final_score"] = emp_final["final_score"]
                emp["dar_written_warnings"] = emp_final["written_warnings"]
                emp["dar_suspensions"] = emp_final["suspensions"]
                emp["dar_deduction"] = emp_final["total_deduction"]
                emp["final_rank"] = emp_final["final_rank"]
            updated_employees.append(emp)
        
        await db.snapshot_workflow.update_one(
            {"id": snapshot["id"]},
            {
                "$set": {
                    "status": "finalized",
                    "finalized_at": datetime.now(timezone.utc).isoformat(),
                    "employees": updated_employees,
                    "dar_applied": True
                }
            }
        )
    
    # Also save the DAR entries separately
    await db.dar_entries.update_one(
        {"year": year, "quarter": quarter.upper()},
        {
            "$set": {
                "year": year,
                "quarter": quarter.upper(),
                "entries": [entry.model_dump() for entry in submission.entries],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    # Auto-generate reviews for all employees if requested
    reviews_queued = 0
    if generate_reviews:
        # Queue review generation (runs in background)
        asyncio.create_task(_generate_all_quarterly_reviews(db, year, quarter.upper(), employees))
        reviews_queued = len(employees)
    
    return {
        "message": f"Quarter {quarter} {year} finalized successfully",
        "total_employees": len(final_rankings),
        "total_dar_deductions": sum(e["total_deduction"] for e in final_rankings),
        "final_rankings": final_rankings,
        "reviews_queued": reviews_queued
    }


async def _generate_all_quarterly_reviews(db, year: int, quarter: str, employees: List[Dict]):
    """Background task to generate AI reviews for all employees in a quarter."""
    from scoring_engine import EmployeeV2, QuarterSettings
    from server import generate_review_content_v2, generate_pdf_v2
    
    try:
        # Get quarter settings
        settings_doc = await db.quarter_settings.find_one(
            {"year": year, "quarter": quarter},
            {"_id": 0}
        )
        settings = QuarterSettings(**settings_doc) if settings_doc else None
        
        generated_count = 0
        error_count = 0
        
        for emp_data in employees:
            try:
                # Check if review already exists
                existing = await db.reviews_v2.find_one({
                    "employee_id": emp_data.get("id"),
                    "quarter": quarter,
                    "year": year
                })
                
                if existing:
                    continue  # Skip if already has a review
                
                # Convert to EmployeeV2 model
                employee = EmployeeV2(**emp_data)
                
                # Generate review content
                review_content = await generate_review_content_v2(employee, settings, quarter, year)
                
                # Generate PDF
                pdf_bytes = generate_pdf_v2(employee, settings, review_content, quarter, year)
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                
                # Save review to database
                review_doc = {
                    "id": str(uuid.uuid4()),
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "review_content": review_content,
                    "quarter": quarter,
                    "year": year,
                    "pdf_base64": pdf_base64,
                    "auto_generated": True,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db.reviews_v2.insert_one(review_doc)
                generated_count += 1
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error generating review for {emp_data.get('name')}: {str(e)}")
                error_count += 1
        
        # Update finalization record with review status
        await db.quarter_finalizations.update_one(
            {"year": year, "quarter": quarter},
            {
                "$set": {
                    "reviews_generated": True,
                    "reviews_count": generated_count,
                    "reviews_errors": error_count,
                    "reviews_completed_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        logger.info(f"Generated {generated_count} reviews for {quarter} {year} ({error_count} errors)")
        
    except Exception as e:
        logger.error(f"Error in batch review generation: {str(e)}")


@finalization_router.delete("/finalize/{year}/{quarter}")
async def unfinalize_quarter(year: int, quarter: str):
    """Remove finalization (reopen quarter for edits)."""
    db = get_db()
    result = await db.quarter_finalizations.delete_one(
        {"year": year, "quarter": quarter.upper()}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No finalization found for this quarter")
    
    return {"message": f"Quarter {quarter} {year} reopened for edits"}


@finalization_router.get("/reviews/quarterly/{year}/{quarter}")
async def get_quarterly_reviews(year: int, quarter: str):
    """Get all generated quarterly reviews for a quarter."""
    db = get_db()
    reviews = await db.reviews_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0, "pdf_base64": 0}  # Exclude PDF data for listing
    ).to_list(1000)
    
    # Get finalization status
    finalization = await db.quarter_finalizations.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0, "final_rankings": 0}
    )
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "finalization_status": finalization,
        "reviews": reviews,
        "total_reviews": len(reviews)
    }


@finalization_router.get("/reviews/quarterly/{year}/{quarter}/{employee_id}")
async def get_employee_quarterly_review(year: int, quarter: str, employee_id: str):
    """Get a specific employee's quarterly review including PDF."""
    db = get_db()
    review = await db.reviews_v2.find_one(
        {"year": year, "quarter": quarter.upper(), "employee_id": employee_id},
        {"_id": 0}
    )
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found for this employee")
    
    return review


@finalization_router.post("/reviews/quarterly/{year}/{quarter}/regenerate")
async def regenerate_quarterly_review(year: int, quarter: str, employee_id: str):
    """Regenerate a specific employee's quarterly review."""
    db = get_db()
    from scoring_engine import EmployeeV2, QuarterSettings
    from server import generate_review_content_v2, generate_pdf_v2
    
    # Get employee data
    employee_data = await db.employees_v2.find_one(
        {"id": employee_id, "year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    
    if not employee_data:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Get settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    settings = QuarterSettings(**settings_doc) if settings_doc else None
    
    employee = EmployeeV2(**employee_data)
    
    # Generate review
    review_content = await generate_review_content_v2(employee, settings, quarter.upper(), year)
    pdf_bytes = generate_pdf_v2(employee, settings, review_content, quarter.upper(), year)
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    # Update or insert review
    review_doc = {
        "id": str(uuid.uuid4()),
        "employee_id": employee.id,
        "employee_name": employee.name,
        "review_content": review_content,
        "quarter": quarter.upper(),
        "year": year,
        "pdf_base64": pdf_base64,
        "regenerated": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.reviews_v2.update_one(
        {"employee_id": employee_id, "year": year, "quarter": quarter.upper()},
        {"$set": review_doc},
        upsert=True
    )
    
    return {"success": True, "message": "Review regenerated", "review_id": review_doc["id"]}


# ============================================================================
# EMPLOYEE DAR ENDPOINTS
# ============================================================================

@finalization_router.put("/employees/{employee_id}/dar")
async def update_employee_dar(employee_id: str, data: DARUpdate):
    """
    Update DAR entries for a specific employee.
    Admin-only endpoint for disciplinary tracking.
    """
    db = get_db()
    # Update in employees_v2
    result = await db.employees_v2.update_one(
        {"id": employee_id},
        {
            "$set": {
                "dar_written_warnings": data.written_warnings,
                "dar_suspensions": data.suspensions,
                "dar_updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Calculate deduction for response
    total_deduction = (data.written_warnings * 3) + (data.suspensions * 5)
    
    return {
        "success": True,
        "message": "DAR updated",
        "written_warnings": data.written_warnings,
        "suspensions": data.suspensions,
        "total_deduction": total_deduction
    }


@finalization_router.get("/employees/{employee_id}/dar")
async def get_employee_dar(employee_id: str):
    """Get DAR entries for a specific employee."""
    db = get_db()
    employee = await db.employees_v2.find_one(
        {"id": employee_id},
        {"_id": 0, "dar_written_warnings": 1, "dar_suspensions": 1, "dar_updated_at": 1}
    )
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    written = employee.get("dar_written_warnings", 0)
    suspensions = employee.get("dar_suspensions", 0)
    
    return {
        "employee_id": employee_id,
        "written_warnings": written,
        "suspensions": suspensions,
        "total_deduction": (written * 3) + (suspensions * 5),
        "updated_at": employee.get("dar_updated_at")
    }
