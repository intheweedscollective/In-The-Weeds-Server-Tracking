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
    """Get database instance from shared module to avoid circular imports"""
    from database import get_database
    return get_database()


async def find_employee(db, employee_id: str):
    """
    Find an employee by ID with snapshot fallback.
    Handles the case where the frontend sends a snapshot_workflow ID 
    that doesn't match the employees_v2 ID.
    Returns (employee_doc, mongo_id) or raises 404.
    """
    # Try direct ID match first
    emp = await db.employees_v2.find_one({"id": employee_id})
    if emp:
        return emp
    
    # Fallback: find via snapshot_workflow
    snapshot = await db.snapshot_workflow.find_one(
        {"employees.id": employee_id},
        {"employees.$": 1}
    )
    if snapshot and snapshot.get("employees"):
        snap_name = snapshot["employees"][0].get("name", "")
        if snap_name:
            # Search by name, report_name, or display_name
            emp = await db.employees_v2.find_one({
                "$or": [
                    {"name": {"$regex": f"^{re.escape(snap_name)}$", "$options": "i"}},
                    {"report_name": {"$regex": f"^{re.escape(snap_name)}$", "$options": "i"}},
                    {"display_name": {"$regex": f"^{re.escape(snap_name)}$", "$options": "i"}},
                ]
            })
            if emp:
                return emp
    
    raise HTTPException(status_code=404, detail="Employee not found")



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
    """
    Get employees for a quarter. Reads from the canonical `employees`
    collection via EmployeeService (Phase 2A). Returns the same shape
    the frontend used to receive from `employees_v2` so the Employees
    tab page works without UI changes.

    Behaviour:
      - Only active employees (`status="active"`).
      - `display_name` overrides `name` in the response.
      - Falls back to legacy `employees_v2` if the canonical collection
        is empty for this quarter (defense in depth — should not happen
        after Phase 1 migration ran).
    """
    from services.employee_service import EmployeeService
    db = get_db()
    svc = EmployeeService(db)

    actives = await svc.list_active(quarter=quarter, year=year)
    if not actives:
        # Phase-1 safety net: if the canonical collection has no rows for
        # this quarter yet, fall back to the legacy collection. Logged so
        # we can tell from production logs when it triggers.
        logger.warning(
            "employees: canonical empty for %s %s, falling back to employees_v2",
            quarter, year,
        )
        legacy = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0},
        ).skip(skip).limit(limit).to_list(limit)
        for emp in legacy:
            if emp.get("display_name") and emp.get("display_name") != emp.get("name"):
                emp["name"] = emp["display_name"]
        total = await db.employees_v2.count_documents(
            {"year": year, "quarter": quarter.upper()},
        )
        return {"employees": legacy, "total": total, "limit": limit, "skip": skip,
                "source": "legacy_fallback"}

    # Project canonical -> legacy-compatible shape so the frontend's
    # current expectations keep working.
    out: List[dict] = []
    for emp in actives:
        cm = emp.get("current_metrics") or {}
        flat = {k: v for k, v in emp.items() if k != "current_metrics"}
        flat.update(cm)
        # display_name preference (matches legacy behaviour above).
        if flat.get("display_name") and flat["display_name"] != flat.get("name"):
            flat["name"] = flat["display_name"]
        out.append(flat)

    total = len(out)
    page = out[skip: skip + limit] if limit else out
    return {"employees": page, "total": total, "limit": limit, "skip": skip,
            "source": "canonical"}


@employee_router.get("/{employee_id}")
async def get_employee_v2(employee_id: str):
    """Get a single employee by canonical id (with legacy_id alias support)."""
    from services.employee_service import EmployeeService
    db = get_db()
    svc = EmployeeService(db)

    emp = await svc.get_by_id(employee_id)
    if not emp:
        # Maybe the caller passed an old legacy UUID — try matching against
        # legacy_ids before giving up.
        emp = await svc.col.find_one({"legacy_ids": employee_id}, {"_id": 0})
    if not emp:
        # Final fallback: legacy collection (Phase-1 safety net).
        legacy = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
        if not legacy:
            raise HTTPException(status_code=404, detail="Employee not found")
        if legacy.get("display_name") and legacy["display_name"] != legacy.get("name"):
            legacy["name"] = legacy["display_name"]
        return legacy

    # Project canonical -> legacy-compatible shape.
    cm = emp.get("current_metrics") or {}
    flat = {k: v for k, v in emp.items() if k != "current_metrics"}
    flat.update(cm)
    if flat.get("display_name") and flat["display_name"] != flat.get("name"):
        flat["name"] = flat["display_name"]
    return flat


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
    emp_dict.pop("_id", None)

    # Route through the canonical EmployeeService so this person gets a
    # stable, immutable identity in the new `employees` collection AND
    # the legacy `employees_v2` row is mirrored automatically. The service
    # is idempotent on canonical name, so a re-add of a previously-
    # terminated employee reactivates the same id (no duplicate).
    from services.employee_service import EmployeeService
    svc = EmployeeService(db)
    canonical = await svc.create_employee({
        "id": emp_dict["id"],
        "name": data.name,
        "display_name": emp_dict.get("display_name") or data.name.split()[0],
        "report_name": emp_dict.get("report_name") or data.name,
        "job_title": data.job_title,
        "current_metrics": {
            **{k: v for k, v in emp_dict.items()
               if k not in ("id", "name", "display_name", "report_name",
                            "job_title", "aliases", "created_at",
                            "updated_at", "year", "quarter")},
            "quarter": data.quarter.upper(),
            "year": data.year,
        },
    })
    # The id returned by the service is the authoritative one — use it
    # everywhere downstream so the snapshot embed picks up the canonical id.
    emp_dict["id"] = canonical["id"]
    emp_dict["display_name"] = canonical.get("display_name") or emp_dict.get("display_name")

    # Mirror the v2 row (preserves legacy fields like tier_label that the
    # canonical model doesn't carry yet). create_employee above wrote a
    # bare v2 row; this update adds the legacy-only fields back on top.
    await db.employees_v2.update_one(
        {"id": canonical["id"]},
        {"$set": emp_dict},
        upsert=True,
    )

    # ALSO inject the new row into the CURRENT snapshot's embedded
    # `employees` array. Without this, the Employees tab page (which reads
    # `/v2/snapshot-workflow/current-rankings` → snapshot.employees) and the
    # snapshot detail/slide views won't show the new person — the user
    # reported "profiles that were added for the two new employees are not
    # showing up". Also pull the name off the snapshot's deleted_names
    # blocklist in case the user is re-adding someone they previously
    # terminated.
    snap_q = data.quarter.upper()
    snap_y = data.year
    target_snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": snap_q, "year": snap_y}
    )
    if not target_snapshot:
        target_snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": snap_q, "year": snap_y},
            sort=[("completed_at", -1)],
        )
    if target_snapshot:
        # Make sure derived display fields are present so the snapshot UI
        # can show them without bouncing back through merge_snapshot_data.
        emp_dict.setdefault("display_name", emp_dict.get("name"))
        emp_dict.setdefault("report_name", emp_dict.get("name"))

        already_in = any(
            (e.get("id") == emp_dict["id"])
            or ((e.get("name") or "").lower() == emp_dict["name"].lower())
            for e in target_snapshot.get("employees", []) or []
        )
        if not already_in:
            await db.snapshot_workflow.update_one(
                {"_id": target_snapshot["_id"]},
                {
                    "$push": {"employees": emp_dict},
                    "$pull": {
                        "deleted_names": {
                            "$regex": f"^{re.escape(employee.name)}$",
                            "$options": "i",
                        }
                    },
                    "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                },
            )
            # Recompute employee_count
            await db.snapshot_workflow.update_one(
                {"_id": target_snapshot["_id"]},
                [{"$set": {"employee_count": {"$size": {"$ifNull": ["$employees", []]}}}}],
            )
            logger.info(
                f"create_employee: added '{employee.name}' to current snapshot "
                f"{target_snapshot.get('id')}"
            )
        else:
            # Already in snapshot — at least make sure they're off the blocklist.
            await db.snapshot_workflow.update_one(
                {"_id": target_snapshot["_id"]},
                {"$pull": {
                    "deleted_names": {
                        "$regex": f"^{re.escape(employee.name)}$",
                        "$options": "i",
                    }
                }},
            )
    
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


# NOTE: PUT /{employee_id} is handled by server.py's api_router.put("/v2/employees/{employee_id}")
# to avoid route conflicts. Do NOT add a PUT endpoint here.


@employee_router.delete("/{employee_id}")
async def delete_employee(employee_id: str):
    """
    Delete a single employee. Routes through `EmployeeService.delete_completely`
    which performs the full canonical soft-delete:
      - `employees.status = "terminated"` (kept for history)
      - Removed from `employees_v2`
      - Pulled from every snapshot's `employees[]` (by id, legacy_ids, and name)
      - Added to every active snapshot's `deleted_names` blocklist
      - Recomputes `employee_count` on every snapshot
    Idempotent.
    """
    from services.employee_service import EmployeeService
    db = get_db()
    svc = EmployeeService(db)

    # Resolve via canonical first (covers legacy id lookups via legacy_ids).
    canonical = await svc.get_by_id(employee_id)
    if not canonical:
        canonical = await svc.col.find_one({"legacy_ids": employee_id}, {"_id": 0})

    if canonical:
        result = await svc.delete_completely(canonical["id"])
        return {"success": True, "message": f"Employee {canonical.get('name', 'Unknown')} deleted", **result}

    # Legacy fallback: id only exists in employees_v2. Resolve the name,
    # mint a canonical entry for it (so future deletes go through the
    # service path), then run the full delete_completely path.
    legacy = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not legacy:
        # Last resort: route through find_employee (snapshot id lookup).
        legacy = await find_employee(db, employee_id)
        legacy.pop("_id", None)
    if not legacy:
        raise HTTPException(status_code=404, detail="Employee not found")

    canonical = await svc.create_employee({
        "id": legacy.get("id"),
        "name": legacy.get("name"),
        "display_name": legacy.get("display_name") or legacy.get("name", "").split()[0],
        "report_name": legacy.get("report_name") or legacy.get("name"),
        "job_title": legacy.get("job_title") or "Server",
    })
    result = await svc.delete_completely(canonical["id"])
    return {"success": True, "message": f"Employee {legacy.get('name', 'Unknown')} deleted", **result}


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
    
    employee = await find_employee(db, employee_id)
    current_name = employee.get("name", "")
    report_name = employee.get("report_name") or current_name
    
    await db.employees_v2.update_one(
        {"_id": employee["_id"]},
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
    # Clamp at zero — survey counts can't be negative. Without this, a
    # decrement spinner on the edit form could produce nonsense like
    # cv_detractors=-7, which inverts the sign of the CV formula and
    # inflates scores by +14 instead of deducting 14.
    cv_promoters = max(0, int(data.get("cv_promoters", 0) or 0))
    cv_detractors = max(0, int(data.get("cv_detractors", 0) or 0))
    cv_passives = max(0, int(data.get("cv_passives", 0) or 0))
    
    # Calculate NPS % from the provided values
    total_responses = cv_promoters + cv_passives + cv_detractors
    if total_responses > 0:
        nps_score = ((cv_promoters - cv_detractors) / total_responses) * 100
    else:
        nps_score = data.get("nps_score", 0) or 0
    
    # Find and update employee
    employee_doc = await find_employee(db, employee_id)
    
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
