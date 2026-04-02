"""
Employee CRUD Routes
Handles employee create, read, update, delete operations and display name management.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
import re

logger = logging.getLogger(__name__)

# Router will be included in main server.py
employee_router = APIRouter(prefix="/v2/employees", tags=["Employees"])

def get_db():
    """Get database instance - will be set by main server"""
    from server import db
    return db


# ============================================================================
# MODELS
# ============================================================================

class EmployeeCreate(BaseModel):
    """Model for creating a new employee"""
    name: str
    job_title: str = "server"
    year: int = 2026
    quarter: str = "Q1"
    guests: float = 0
    net_sales: float = 0
    lbw: float = 0
    glassware_sales: float = 0
    lsc_count: int = 0
    cv_promoters: int = 0
    cv_passives: int = 0
    cv_detractors: int = 0
    review_mentions: int = 0


class EmployeeUpdate(BaseModel):
    """Model for updating an employee"""
    name: Optional[str] = None
    display_name: Optional[str] = None  # Custom name shown in dashboards/reports
    report_name: Optional[str] = None   # Original name from POS reports (used for matching)
    job_title: Optional[str] = None
    aliases: Optional[List[str]] = None  # Nicknames for name matching
    guests: Optional[float] = None
    net_sales: Optional[float] = None
    lbw: Optional[float] = None
    glassware_sales: Optional[float] = None
    lsc_count: Optional[int] = None
    nps_score: Optional[float] = None  # NPS % score (0-100)
    cv_promoters: Optional[int] = None
    cv_passives: Optional[int] = None
    cv_detractors: Optional[int] = None
    review_mentions: Optional[int] = None


class DARUpdate(BaseModel):
    written_warnings: int = 0
    suspensions: int = 0


# ============================================================================
# CRUD ENDPOINTS
# ============================================================================

@employee_router.get("")
async def get_employees_v2(year: int = 2026, quarter: str = "Q1", limit: int = 100, skip: int = 0):
    """Get all V2 employees for a quarter"""
    db = get_db()
    employees = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).skip(skip).limit(limit).to_list(limit)
    
    total = await db.employees_v2.count_documents({"year": year, "quarter": quarter.upper()})
    
    return {
        "employees": employees,
        "total": total,
        "limit": limit,
        "skip": skip
    }


@employee_router.get("/{employee_id}")
async def get_employee_v2(employee_id: str):
    """Get a single V2 employee by ID"""
    db = get_db()
    employee = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


@employee_router.post("")
async def create_employee(data: EmployeeCreate):
    """
    Create a new employee and calculate their scores.
    """
    from scoring_engine import (
        EmployeeV2, QuarterSettings, calculate_derived_metrics, calculate_customer_voice_score,
        calculate_review_tracker_bonus, calculate_normalized_scores,
        calculate_bonus_points, calculate_total_score
    )
    
    db = get_db()
    
    # Get quarter settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": data.year, "quarter": data.quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=400, detail=f"No settings found for {data.quarter} {data.year}. Create settings first.")
    
    settings = QuarterSettings(**settings_doc)
    
    # Create employee object
    employee = EmployeeV2(
        id=str(uuid.uuid4()),
        name=data.name,
        job_title=data.job_title.lower(),
        year=data.year,
        quarter=data.quarter.upper(),
        guests=data.guests,
        net_sales=data.net_sales,
        lbw=data.lbw,
        glassware_sales=data.glassware_sales,
        lsc_count=data.lsc_count,
        cv_promoters=data.cv_promoters,
        cv_passives=data.cv_passives,
        cv_detractors=data.cv_detractors,
        review_mentions=data.review_mentions
    )
    
    # Run through scoring pipeline
    employee = calculate_derived_metrics(employee)
    employee = calculate_customer_voice_score(employee)
    employee = calculate_review_tracker_bonus(employee)
    employee = calculate_normalized_scores(employee, settings)
    employee = calculate_bonus_points(employee, settings)
    employee = calculate_total_score(employee, settings)
    
    # Assign tier
    score = employee.pre_dar_score or 0
    job = employee.job_title.lower()
    if job in ['trainer', 'bartender']:
        tier_label = job.title()
    elif score >= settings.a_server_min_score:
        tier_label = "A-Server"
    elif score >= settings.b_server_min_score:
        tier_label = "B-Server"
    else:
        tier_label = "C-Server"
    
    # Save to database
    emp_dict = employee.model_dump()
    emp_dict['tier_label'] = tier_label
    emp_dict['created_at'] = datetime.now(timezone.utc).isoformat()
    await db.employees_v2.insert_one(emp_dict)
    
    # Recalculate peer rankings for all employees in this quarter
    all_employees = await db.employees_v2.find(
        {"year": data.year, "quarter": data.quarter.upper()},
        {"_id": 0}
    ).to_list(1000)
    
    # Sort and assign peer ranks
    sorted_emps = sorted(all_employees, key=lambda x: x.get('pre_dar_score', 0) or 0, reverse=True)
    for rank, emp in enumerate(sorted_emps, 1):
        await db.employees_v2.update_one(
            {"id": emp['id']},
            {"$set": {"peer_rank": rank}}
        )
    
    return {"success": True, "employee_id": employee.id, "message": f"Created {employee.name} with score {employee.total_score}"}


@employee_router.put("/{employee_id}")
async def update_employee(employee_id: str, data: EmployeeUpdate):
    """
    Update an existing employee and recalculate their scores.
    """
    from scoring_engine import (
        EmployeeV2, QuarterSettings, calculate_derived_metrics, calculate_customer_voice_score,
        calculate_review_tracker_bonus, calculate_normalized_scores,
        calculate_bonus_points, calculate_total_score
    )
    from server import sync_employees_to_most_recent_snapshot
    
    db = get_db()
    
    # Get existing employee
    emp_doc = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not emp_doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Get quarter settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": emp_doc['year'], "quarter": emp_doc['quarter']},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=400, detail="No settings found for this quarter")
    
    settings = QuarterSettings(**settings_doc)
    
    # Update fields that were provided
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        emp_doc[key] = value
    
    # Convert to EmployeeV2 and recalculate
    if isinstance(emp_doc.get('created_at'), str):
        emp_doc['created_at'] = datetime.fromisoformat(emp_doc['created_at'])
    
    employee = EmployeeV2(**emp_doc)
    
    # Re-run scoring pipeline
    employee = calculate_derived_metrics(employee)
    employee = calculate_customer_voice_score(employee)
    employee = calculate_review_tracker_bonus(employee)
    employee = calculate_normalized_scores(employee, settings)
    employee = calculate_bonus_points(employee, settings)
    employee = calculate_total_score(employee, settings)
    
    # Reassign tier
    score = employee.pre_dar_score or 0
    job = employee.job_title.lower()
    if job in ['trainer', 'bartender']:
        tier_label = job.title()
    elif score >= settings.a_server_min_score:
        tier_label = "A-Server"
    elif score >= settings.b_server_min_score:
        tier_label = "B-Server"
    else:
        tier_label = "C-Server"
    
    # Update in database
    emp_dict = employee.model_dump()
    emp_dict['tier_label'] = tier_label
    emp_dict['created_at'] = emp_dict['created_at'].isoformat() if isinstance(emp_dict['created_at'], datetime) else emp_dict['created_at']
    await db.employees_v2.update_one(
        {"id": employee_id},
        {"$set": emp_dict}
    )
    
    # ALSO update the snapshot's embedded employee data
    await db.snapshots.update_many(
        {
            "year": emp_doc['year'],
            "quarter": emp_doc['quarter'],
            "employees.id": employee_id
        },
        {
            "$set": {
                "employees.$.name": emp_dict.get('name', ''),
                "employees.$.job_title": emp_dict['job_title'],
                "employees.$.tier_label": tier_label,
                "employees.$.total_score": emp_dict.get('total_score', 0),
                "employees.$.pre_dar_score": emp_dict.get('pre_dar_score', 0),
                "employees.$.weighted_score": emp_dict.get('weighted_score', 0),
                "employees.$.cv_score": emp_dict.get('cv_score', 0),
                "employees.$.cv_promoters": emp_dict.get('cv_promoters', 0),
                "employees.$.cv_detractors": emp_dict.get('cv_detractors', 0),
                "employees.$.review_tracker_bonus": emp_dict.get('review_tracker_bonus', 0),
                "employees.$.review_mentions": emp_dict.get('review_mentions', 0),
                "employees.$.total_metric_bonus": emp_dict.get('total_metric_bonus', 0),
                "employees.$.nps_score": emp_dict.get('nps_score', 0)
            }
        }
    )
    
    # Sync all employees to snapshot to ensure proper sorting
    await sync_employees_to_most_recent_snapshot(emp_doc['quarter'], emp_doc['year'])
    
    logger.info(f"Updated employee {employee.name} in both employees_v2 and snapshots")
    
    # Recalculate peer rankings
    all_employees = await db.employees_v2.find(
        {"year": emp_doc['year'], "quarter": emp_doc['quarter']},
        {"_id": 0}
    ).to_list(1000)
    
    sorted_emps = sorted(all_employees, key=lambda x: x.get('pre_dar_score', 0) or 0, reverse=True)
    for rank, emp in enumerate(sorted_emps, 1):
        await db.employees_v2.update_one(
            {"id": emp['id']},
            {"$set": {"peer_rank": rank}}
        )
    
    return {"success": True, "message": f"Updated {employee.name} - new score: {employee.total_score}"}


@employee_router.delete("/{employee_id}")
async def delete_employee(employee_id: str):
    """Delete a single employee"""
    db = get_db()
    result = await db.employees_v2.delete_one({"id": employee_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"success": True, "message": "Employee deleted"}


@employee_router.delete("")
async def clear_employees_v2(year: Optional[int] = None, quarter: Optional[str] = None):
    """Clear V2 employees (optionally for specific quarter)"""
    db = get_db()
    query = {}
    if year:
        query["year"] = year
    if quarter:
        query["quarter"] = quarter.upper()
    
    result = await db.employees_v2.delete_many(query)
    
    # If clearing a specific quarter, unlock the settings
    if year and quarter:
        await db.quarter_settings.update_one(
            {"year": year, "quarter": quarter.upper()},
            {"$set": {"is_locked": False, "locked_at": None}}
        )
    
    return {
        "success": True,
        "deleted_count": result.deleted_count,
        "message": f"Cleared {result.deleted_count} employees"
    }


# ============================================================================
# DISPLAY NAME ENDPOINTS
# ============================================================================

@employee_router.put("/{employee_id}/display-name")
async def update_employee_display_name(employee_id: str, data: dict):
    """
    Update an employee's display name (the name shown in dashboards and reports).
    The report_name (from POS) is preserved for matching future uploads.
    
    Body: { "display_name": "Their Preferred Name" }
    """
    db = get_db()
    display_name = data.get("display_name", "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    
    employee = await db.employees_v2.find_one({"id": employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Set report_name if not already set (for backward compatibility)
    current_name = employee.get("name", "")
    report_name = employee.get("report_name") or current_name
    
    await db.employees_v2.update_one(
        {"id": employee_id},
        {"$set": {
            "display_name": display_name,
            "report_name": report_name,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    return {
        "success": True,
        "message": f"Updated display name to '{display_name}'",
        "employee_id": employee_id,
        "display_name": display_name,
        "report_name": report_name
    }


# ============================================================================
# CV (Customer Voice) ENDPOINTS
# ============================================================================

@employee_router.put("/{employee_id}/cv-stats")
async def update_employee_cv_stats(employee_id: str, data: dict):
    """
    Manually update an employee's CV (Customer Voice) statistics.
    Allows adjusting NPS score, promoter and detractor counts directly.
    
    CV Score = NPS pts (0-10) + Promoter/Detractor Bonus
    - NPS pts: NPS% / 10 (e.g., 77% = 7.7 pts)
    - Promoter bonus: +1 per promoter (9-10 rating)
    - Detractor penalty: -2 per detractor (≤6 rating)
    """
    from scoring_engine import (
        EmployeeV2, QuarterSettings, calculate_derived_metrics, calculate_customer_voice_score,
        calculate_review_tracker_bonus, calculate_normalized_scores,
        calculate_bonus_points, calculate_total_score
    )
    from server import sync_employees_to_most_recent_snapshot
    
    db = get_db()
    quarter = data.get("quarter", "Q1")
    year = data.get("year", 2026)
    cv_promoters = int(data.get("cv_promoters", 0))
    cv_detractors = int(data.get("cv_detractors", 0))
    cv_passives = int(data.get("cv_passives", 0))
    
    # Calculate NPS % from the provided values
    total_responses = cv_promoters + cv_passives + cv_detractors
    if total_responses > 0:
        nps_score = ((cv_promoters - cv_detractors) / total_responses) * 100
    else:
        nps_score = data.get("nps_score", 0) or 0
    
    # Find and update employee
    employee_doc = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not employee_doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Get settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": employee_doc['year'], "quarter": employee_doc['quarter']},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=400, detail="No settings found for this quarter")
    
    settings = QuarterSettings(**settings_doc)
    
    # Update employee with new CV stats
    employee_doc['cv_promoters'] = cv_promoters
    employee_doc['cv_detractors'] = cv_detractors
    employee_doc['cv_passives'] = cv_passives
    employee_doc['nps_score'] = nps_score
    
    # Convert to model and recalculate
    if isinstance(employee_doc.get('created_at'), str):
        employee_doc['created_at'] = datetime.fromisoformat(employee_doc['created_at'])
    
    employee = EmployeeV2(**employee_doc)
    employee = calculate_derived_metrics(employee)
    employee = calculate_customer_voice_score(employee)
    employee = calculate_review_tracker_bonus(employee)
    employee = calculate_normalized_scores(employee, settings)
    employee = calculate_bonus_points(employee, settings)
    employee = calculate_total_score(employee, settings)
    
    # Reassign tier
    score = employee.pre_dar_score or 0
    job = employee.job_title.lower()
    if job in ['trainer', 'bartender']:
        tier_label = job.title()
    elif score >= settings.a_server_min_score:
        tier_label = "A-Server"
    elif score >= settings.b_server_min_score:
        tier_label = "B-Server"
    else:
        tier_label = "C-Server"
    
    # Save to DB
    emp_dict = employee.model_dump()
    emp_dict['tier_label'] = tier_label
    emp_dict['created_at'] = emp_dict['created_at'].isoformat() if isinstance(emp_dict['created_at'], datetime) else emp_dict['created_at']
    
    await db.employees_v2.update_one(
        {"id": employee_id},
        {"$set": emp_dict}
    )
    
    # Sync to snapshot
    await sync_employees_to_most_recent_snapshot(employee_doc['quarter'], employee_doc['year'])
    
    return {
        "success": True,
        "employee_id": employee_id,
        "employee_name": employee.name,
        "cv_promoters": cv_promoters,
        "cv_detractors": cv_detractors,
        "cv_passives": cv_passives,
        "nps_score": nps_score,
        "cv_score": employee.cv_score,
        "new_total_score": employee.total_score,
        "tier_label": tier_label,
        "message": "CV stats updated and scores recalculated"
    }


# ============================================================================
# DAR (Disciplinary Action Reports) ENDPOINTS
# ============================================================================

@employee_router.put("/{employee_id}/dar")
async def update_employee_dar(employee_id: str, data: DARUpdate):
    """
    Update DAR (Disciplinary Action Reports) for an employee.
    Admin-only endpoint. DAR penalties are applied but hidden from rankings.
    
    - Written Warning: -3 points
    - Suspension: -5 points
    """
    from scoring_engine import DAR_WRITTEN_WARNING, DAR_SUSPENSION
    
    db = get_db()
    
    # Find employee
    employee = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Calculate new DAR penalty
    warning_penalty = data.written_warnings * DAR_WRITTEN_WARNING
    suspension_penalty = data.suspensions * DAR_SUSPENSION
    dar_penalty = warning_penalty + suspension_penalty
    
    # Recalculate total score with new DAR
    pre_dar_score = employee.get("pre_dar_score", employee.get("total_score", 0))
    new_total_score = round(pre_dar_score + dar_penalty, 2)
    
    # Update employee record
    await db.employees_v2.update_one(
        {"id": employee_id},
        {"$set": {
            "dar_written_warnings": data.written_warnings,
            "dar_suspensions": data.suspensions,
            "dar_penalty": dar_penalty,
            "total_score": new_total_score
        }}
    )
    
    return {
        "success": True,
        "employee_id": employee_id,
        "dar_written_warnings": data.written_warnings,
        "dar_suspensions": data.suspensions,
        "dar_penalty": dar_penalty,
        "pre_dar_score": pre_dar_score,
        "total_score": new_total_score,
        "message": "DAR updated successfully. Note: Rankings are based on pre-DAR scores."
    }


@employee_router.get("/{employee_id}/dar")
async def get_employee_dar(employee_id: str):
    """
    Get DAR details for an employee (admin-only view).
    """
    db = get_db()
    employee = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    return {
        "employee_id": employee_id,
        "employee_name": employee.get("name"),
        "dar_written_warnings": employee.get("dar_written_warnings", 0),
        "dar_suspensions": employee.get("dar_suspensions", 0),
        "dar_penalty": employee.get("dar_penalty", 0),
        "pre_dar_score": employee.get("pre_dar_score"),
        "total_score": employee.get("total_score")
    }
