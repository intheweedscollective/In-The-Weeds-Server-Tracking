"""
Admin Routes Module
Administrative endpoints for data management, sync, integrity, and fixes.
Extracted from server.py for better maintainability.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import uuid
import re
import os

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/v2/admin", tags=["Admin"])

def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# ============================================================
# PYDANTIC MODELS
# ============================================================

class OfficialRTStats(BaseModel):
    """Official ReviewTrackers stats as shown in their UI."""
    google_reviews: int = 0
    google_rating: float = 0.0
    yelp_reviews: int = 0
    yelp_rating: float = 0.0
    tripadvisor_reviews: int = 0
    tripadvisor_rating: float = 0.0
    opentable_reviews: int = 0
    opentable_rating: float = 0.0
    facebook_reviews: int = 0
    facebook_rating: float = 0.0
    quarter: str = "Q1"
    year: int = 2026


class OfficialCVStats(BaseModel):
    """Official Customer Voice (Loyalty Voice) stats as shown in their UI."""
    nps_score: float = 0.0
    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    total_responses: int = 0
    quarter: str = "Q1"
    year: int = 2026


# ============================================================
# EMPLOYEE DATA SYNC & IMPORT
# ============================================================

@admin_router.post("/sync-employees-from-json")
async def sync_employees_from_json(
    quarter: str = "Q1",
    year: int = 2026,
    delete_existing: bool = True
):
    """
    Sync employees from the exported JSON file.
    This is used to sync preview data to production.
    
    WARNING: If delete_existing=True, this will DELETE all existing employees
    for this quarter/year before importing!
    """
    import json
    db = get_db()
    
    # Read the exported employees
    try:
        with open('/tmp/correct_employees.json', 'r') as f:
            employees_to_import = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Export file not found. Run export first.")
    
    if not employees_to_import:
        raise HTTPException(status_code=400, detail="No employees in export file")
    
    results = {
        "deleted": 0,
        "imported": 0,
        "errors": []
    }
    
    # Delete existing if requested
    if delete_existing:
        delete_result = await db.employees_v2.delete_many({
            "quarter": quarter.upper(),
            "year": year
        })
        results["deleted"] = delete_result.deleted_count
        logger.info(f"Deleted {delete_result.deleted_count} existing employees")
    
    # Import each employee
    for emp in employees_to_import:
        try:
            # Remove _id if present (let MongoDB generate new one)
            emp.pop('_id', None)
            emp.pop('id', None)
            
            # Ensure quarter/year match
            emp['quarter'] = quarter.upper()
            emp['year'] = year
            
            await db.employees_v2.insert_one(emp)
            results["imported"] += 1
        except Exception as e:
            results["errors"].append(f"{emp.get('name')}: {str(e)}")
    
    logger.info(f"Imported {results['imported']} employees")
    
    return {
        "status": "success",
        "quarter": quarter,
        "year": year,
        "deleted_count": results["deleted"],
        "imported_count": results["imported"],
        "errors": results["errors"] if results["errors"] else None
    }


@admin_router.delete("/delete-all-employees")
async def delete_all_employees(quarter: str = "Q1", year: int = 2026, confirm: str = ""):
    """
    Delete ALL employees for a specific quarter/year.
    Requires confirm='YES_DELETE_ALL' to proceed.
    """
    if confirm != "YES_DELETE_ALL":
        raise HTTPException(
            status_code=400, 
            detail="Must pass confirm='YES_DELETE_ALL' to delete all employees"
        )
    
    db = get_db()
    result = await db.employees_v2.delete_many({
        "quarter": quarter.upper(),
        "year": year
    })
    
    return {
        "status": "deleted",
        "deleted_count": result.deleted_count,
        "quarter": quarter,
        "year": year
    }


@admin_router.post("/bulk-import-employees")
async def bulk_import_employees(employees: List[dict], quarter: str = "Q1", year: int = 2026):
    """
    Bulk import employees from a JSON array.
    Used to sync data between preview and production.
    """
    if not employees:
        raise HTTPException(status_code=400, detail="No employees provided")
    
    db = get_db()
    imported = 0
    errors = []
    
    for emp in employees:
        try:
            # Remove MongoDB _id if present
            emp.pop('_id', None)
            emp.pop('id', None)
            
            # Generate new ID
            emp['id'] = str(uuid.uuid4())
            
            # Ensure quarter/year match
            emp['quarter'] = quarter.upper()
            emp['year'] = year
            
            await db.employees_v2.insert_one(emp)
            imported += 1
        except Exception as e:
            errors.append(f"{emp.get('name', 'Unknown')}: {str(e)}")
    
    return {
        "status": "success",
        "imported": imported,
        "errors": errors if errors else None
    }


@admin_router.post("/import-employee-raw")
async def import_employee_raw(employee: dict, quarter: str = "Q1", year: int = 2026):
    """
    Import a single employee with ALL fields preserved (no recalculation).
    Used to sync exact data between preview and production.
    """
    db = get_db()
    try:
        # Remove MongoDB _id if present
        employee.pop('_id', None)
        employee.pop('id', None)
        
        # Generate new ID
        employee['id'] = str(uuid.uuid4())
        
        # Ensure quarter/year match
        employee['quarter'] = quarter.upper()
        employee['year'] = year
        
        await db.employees_v2.insert_one(employee)
        
        return {
            "status": "success",
            "name": employee.get('name'),
            "total_score": employee.get('total_score'),
            "rt_mentions": employee.get('rt_mentions'),
            "cv_score": employee.get('cv_score')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# DISPLAY NAME & DATA FIXES
# ============================================================

@admin_router.post("/fix-display-names")
async def batch_fix_display_names(data: dict):
    """
    Batch update display names for employees with OCR/typo issues.
    
    Body: {
        "quarter": "Q1",
        "year": 2026,
        "fixes": {
            "Sheridan Dhaka!": "Sheriden Dhakal",
            "Starwars Mckinnon-Herrera": "Stanvars McKinnon-Herrera"
        }
    }
    """
    db = get_db()
    quarter = data.get("quarter", "Q1").upper()
    year = data.get("year", 2026)
    fixes = data.get("fixes", {})
    
    if not fixes:
        raise HTTPException(status_code=400, detail="No fixes provided")
    
    updated = []
    not_found = []
    
    for old_name, new_display_name in fixes.items():
        # Find employee by current name
        employee = await db.employees_v2.find_one({
            "name": {"$regex": f"^{re.escape(old_name)}$", "$options": "i"},
            "quarter": quarter,
            "year": year
        })
        
        if employee:
            # Update with new display name, preserve report_name
            await db.employees_v2.update_one(
                {"id": employee["id"]},
                {"$set": {
                    "display_name": new_display_name,
                    "report_name": employee.get("report_name") or employee.get("name"),
                    "name": new_display_name,  # Also update main name for display
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            updated.append({"old": old_name, "new": new_display_name})
        else:
            not_found.append(old_name)
    
    return {
        "success": True,
        "updated": updated,
        "not_found": not_found,
        "message": f"Updated {len(updated)} employee names"
    }


@admin_router.post("/clear-all-detractors")
async def clear_all_detractors(year: int = 2026, quarter: str = "Q1"):
    """
    Clear all detractor counts for all employees and recalculate their scores.
    Detractors should only be added manually via DAR entry or employee edit function.
    
    This endpoint:
    1. Sets cv_detractors to 0 for all employees
    2. Recalculates cv_score (removing detractor penalty)
    3. Recalculates total_score
    4. Syncs changes to the most recent snapshot
    """
    db = get_db()
    quarter = quarter.upper()
    
    # Find all employees with detractors > 0
    employees_with_detractors = await db.employees_v2.find({
        "quarter": quarter,
        "year": year,
        "cv_detractors": {"$gt": 0}
    }).to_list(length=None)
    
    updated_employees = []
    
    for emp in employees_with_detractors:
        old_detractors = emp.get("cv_detractors", 0)
        old_cv_score = emp.get("cv_score", 0)
        old_total = emp.get("total_score", 0)
        
        # Recalculate CV score without detractors
        nps_score = emp.get("nps_score", 0) or 0
        nps_pts = round(nps_score / 10, 1) if nps_score > 0 else 0.0
        nps_pts = min(nps_pts, 10.0)
        
        cv_promoters = emp.get("cv_promoters", 0) or 0
        # Promoter bonus: +0.5 per promoter (CV Formula)
        promo_bonus = cv_promoters * 0.5
        new_cv_score = round(promo_bonus, 2)  # No detractors, no NPS component
        
        # Recalculate total score
        weighted_score = emp.get("weighted_score", 0) or 0
        total_metric_bonus = emp.get("total_metric_bonus", 0) or 0
        rt_bonus = emp.get("review_tracker_bonus", 0) or 0
        new_total = round(weighted_score + new_cv_score + total_metric_bonus + rt_bonus, 2)
        
        # Update employee
        await db.employees_v2.update_one(
            {"_id": emp["_id"]},
            {"$set": {
                "cv_detractors": 0,
                "cv_score": new_cv_score,
                "total_score": new_total,
                "pre_dar_score": new_total,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        updated_employees.append({
            "name": emp.get("name"),
            "old_detractors": old_detractors,
            "old_cv_score": old_cv_score,
            "new_cv_score": new_cv_score,
            "old_total": old_total,
            "new_total": new_total
        })
    
    return {
        "success": True,
        "message": f"Cleared detractors for {len(updated_employees)} employees",
        "employees_updated": updated_employees
    }


# ============================================================
# SCORE FIXING UTILITIES
# ============================================================

async def _fix_ppa_values(quarter: str, year: int) -> int:
    """
    Recalculate PPA for all employees from net_sales / guest_count.
    Also syncs 'guests' field from 'guest_count' to fix data inconsistency.
    Returns number of employees updated.
    """
    db = get_db()
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    updated = 0
    for emp in employees:
        net_sales = emp.get('net_sales', 0) or 0
        # Use guest_count as the source of truth (from latest upload)
        guests = emp.get('guest_count', 0) or emp.get('guests', 0) or 0
        
        if guests > 0:
            correct_ppa = round(net_sales / guests, 2)
            stored_ppa = emp.get('ppa', 0) or 0
            stored_guests = emp.get('guests', 0) or 0
            
            # Update if PPA is different OR guests field doesn't match guest_count
            if abs(correct_ppa - stored_ppa) > 0.01 or stored_guests != guests:
                await db.employees_v2.update_one(
                    {"_id": emp["_id"]},
                    {"$set": {
                        "ppa": correct_ppa,
                        "guests": guests  # Sync guests from guest_count
                    }}
                )
                updated += 1
    
    return updated


@admin_router.post("/fix-ppa")
async def fix_ppa_endpoint(quarter: str = "Q1", year: int = 2026):
    """
    Recalculate all PPA values from net_sales / guest_count.
    PPA = Net Sales / Number of Guests
    """
    db = get_db()
    
    # Get before stats
    employees_before = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    ppa_before = [e.get('ppa', 0) or 0 for e in employees_before]
    avg_before = sum(ppa_before) / len(ppa_before) if ppa_before else 0
    
    # Fix PPA values
    updated = await _fix_ppa_values(quarter, year)
    
    # Get after stats
    employees_after = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    ppa_after = [e.get('ppa', 0) or 0 for e in employees_after]
    avg_after = sum(ppa_after) / len(ppa_after) if ppa_after else 0
    
    # Build details
    details = []
    for before, after in zip(
        sorted(employees_before, key=lambda x: x.get('name', '')),
        sorted(employees_after, key=lambda x: x.get('name', ''))
    ):
        old_ppa = before.get('ppa', 0) or 0
        new_ppa = after.get('ppa', 0) or 0
        if abs(old_ppa - new_ppa) > 0.01:
            details.append({
                "name": after.get('name'),
                "old_ppa": old_ppa,
                "new_ppa": new_ppa,
                "change": round(new_ppa - old_ppa, 2)
            })
    
    return {
        "success": True,
        "employees_updated": updated,
        "avg_ppa_before": round(avg_before, 2),
        "avg_ppa_after": round(avg_after, 2),
        "change": round(avg_after - avg_before, 2),
        "details": sorted(details, key=lambda x: abs(x['change']), reverse=True)
    }


@admin_router.post("/fix-all-rankings")
async def fix_all_rankings(quarter: str = "Q1", year: int = 2026):
    """
    EMERGENCY FIX: Recalculate ALL employee rankings and sync to ONLY the most recent snapshot.
    Historical snapshots are preserved for comparison.
    """
    from scoring_engine import EmployeeV2, QuarterSettings, run_full_scoring
    
    db = get_db()
    logger.info(f"=== FIXING ALL RANKINGS for {quarter} {year} ===")
    
    # First, fix PPA values
    ppa_fixed = await _fix_ppa_values(quarter, year)
    logger.info(f"Fixed PPA for {ppa_fixed} employees")
    
    # Get settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    # Get all employees
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(500)
    
    if not employees_docs:
        return {"error": "No employees found", "fixed": 0}
    
    # Convert to EmployeeV2 objects
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    
    # Run full scoring pipeline
    employees = run_full_scoring(employees, settings)
    
    # Update each employee in database
    updated_count = 0
    for emp in employees:
        emp_dict = emp.model_dump()
        await db.employees_v2.update_one(
            {"id": emp.id},
            {"$set": emp_dict}
        )
        updated_count += 1
    
    logger.info(f"Updated {updated_count} employees")
    
    # Sync to the most recent snapshot
    most_recent = await db.snapshot_workflow.find_one(
        {"year": year, "quarter": quarter.upper(), "status": {"$in": ["completed", "in_progress"]}},
        sort=[("effective_date", -1), ("completed_at", -1)]
    )
    
    snapshot_synced = None
    if most_recent:
        # Get fresh employee data
        fresh_employees = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        ).to_list(500)
        
        await db.snapshot_workflow.update_one(
            {"_id": most_recent["_id"]},
            {"$set": {
                "employees": fresh_employees,
                "synced_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        snapshot_synced = str(most_recent["_id"])
        logger.info(f"Synced to snapshot {snapshot_synced}")
    
    return {
        "success": True,
        "ppa_fixed": ppa_fixed,
        "employees_updated": updated_count,
        "snapshot_synced": snapshot_synced,
        "message": f"Fixed rankings for {updated_count} employees"
    }


# ============================================================
# DATA CLEARING UTILITIES
# ============================================================

@admin_router.delete("/clear-cv-data")
async def clear_cv_data(quarter: str = "Q1", year: int = 2026):
    """
    Clear all Customer Voice data and reset employee CV scores.
    """
    db = get_db()
    try:
        # Clear cv_feedback collection
        cv_result = await db.cv_feedback.delete_many({})
        
        # Clear cv_nps collection
        nps_result = await db.cv_nps.delete_many({})
        
        # Reset CV fields on all employees for this quarter/year
        emp_result = await db.employees_v2.update_many(
            {"quarter": quarter, "year": year},
            {"$set": {
                "cv_promoters": 0,
                "cv_detractors": 0,
                "cv_score": 0,
                "nps_score": 0,
                "nps_score_pts": 0
            }}
        )
        
        # Recalculate total scores
        employees = await db.employees_v2.find({
            "quarter": quarter,
            "year": year
        }).to_list(200)
        
        for emp in employees:
            weighted_score = emp.get("weighted_score", 0) or 0
            total_metric_bonus = emp.get("total_metric_bonus", 0) or 0
            rt_bonus = emp.get("review_tracker_bonus", 0) or 0
            # CV is now 0
            total_score = weighted_score + total_metric_bonus + rt_bonus
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {"total_score": round(total_score, 2)}}
            )
        
        return {
            "success": True,
            "cv_feedback_deleted": cv_result.deleted_count,
            "cv_nps_deleted": nps_result.deleted_count,
            "employees_reset": emp_result.modified_count,
            "message": "Customer Voice data cleared"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear CV data: {str(e)}")


@admin_router.delete("/clear-rt-data")
async def clear_rt_data(quarter: str = "Q1", year: int = 2026):
    """
    Clear all Review Tracker data and reset employee RT mention counts.
    """
    db = get_db()
    try:
        # Clear customer_reviews collection
        reviews_result = await db.customer_reviews.delete_many({})
        
        # Reset RT fields on all employees for this quarter/year
        emp_result = await db.employees_v2.update_many(
            {"quarter": quarter, "year": year},
            {"$set": {
                "rt_mentions": 0,
                "review_mentions": 0,
                "review_tracker_bonus": 0
            }}
        )
        
        # Recalculate total scores
        employees = await db.employees_v2.find({
            "quarter": quarter,
            "year": year
        }).to_list(200)
        
        for emp in employees:
            weighted_score = emp.get("weighted_score", 0) or 0
            cv_score = emp.get("cv_score", 0) or 0
            total_metric_bonus = emp.get("total_metric_bonus", 0) or 0
            # RT is now 0
            total_score = weighted_score + cv_score + total_metric_bonus
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {"total_score": round(total_score, 2)}}
            )
        
        return {
            "success": True,
            "reviews_deleted": reviews_result.deleted_count,
            "employees_reset": emp_result.modified_count,
            "message": "Review Tracker data cleared"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear RT data: {str(e)}")


# ============================================================
# NAME MATCHING UTILITIES
# ============================================================

@admin_router.get("/name-matching/preview")
async def preview_name_matching(quarter: str = "Q1", year: int = 2026):
    """
    Preview how employee names will be matched to CV NPS names.
    Shows the mapping and confidence scores without applying changes.
    """
    from name_matcher import get_nps_for_employee_smart, normalize_name
    
    db = get_db()
    
    # Get employee names
    employees = await db.employees_v2.find(
        {"quarter": quarter, "year": year},
        {"_id": 0, "name": 1, "nps_score": 1, "cv_score": 1, "cv_promoters": 1, "aliases": 1}
    ).to_list(1000)
    
    # Get CV NPS names
    nps_records = await db.cv_nps.find(
        {"quarter": quarter, "year": year},
        {"_id": 0, "employee_name": 1, "nps_score": 1, "promoters": 1, "detractors": 1}
    ).to_list(1000)
    
    cv_names = [n["employee_name"] for n in nps_records]
    
    # Build NPS lookup
    nps_lookup = {normalize_name(n["employee_name"]): n for n in nps_records}
    
    # Build mapping
    mapping_results = []
    for emp in employees:
        emp_name = emp["name"]
        aliases = emp.get("aliases", [])
        nps_data, match_reason = get_nps_for_employee_smart(emp_name, nps_lookup, aliases)
        
        current_nps = emp.get("nps_score") or 0
        current_cv = emp.get("cv_score") or 0
        matched_nps = nps_data.get("nps_score") or 0
        matched_promoters = nps_data.get("promoters") or 0
        matched_detractors = nps_data.get("detractors") or 0
        
        # Calculate what CV score would be
        nps_pts = 0
        if matched_nps >= 90: nps_pts = 10
        elif matched_nps >= 80: nps_pts = 9
        elif matched_nps >= 70: nps_pts = 8
        elif matched_nps >= 60: nps_pts = 7
        elif matched_nps >= 50: nps_pts = 6
        elif matched_nps > 0: nps_pts = round((matched_nps / 50) * 5, 1)
        
        projected_cv = nps_pts + (matched_promoters * 1) + (matched_detractors * -2)
        
        mapping_results.append({
            "employee_name": emp_name,
            "current_nps": current_nps,
            "current_cv_score": current_cv,
            "matched_cv_name": nps_data.get("employee_name") if nps_data else None,
            "match_reason": match_reason,
            "matched_nps": matched_nps,
            "matched_promoters": matched_promoters,
            "matched_detractors": matched_detractors,
            "projected_cv_score": round(projected_cv, 2),
            "score_change": round(projected_cv - current_cv, 2),
            "needs_update": abs(projected_cv - current_cv) > 0.1
        })
    
    # Sort by score change (biggest gains first)
    mapping_results.sort(key=lambda x: x["score_change"], reverse=True)
    
    # Count unmatched CV names
    matched_cv_names = {m["matched_cv_name"] for m in mapping_results if m["matched_cv_name"]}
    unmatched_cv = [n for n in cv_names if n not in matched_cv_names]
    
    return {
        "quarter": quarter,
        "year": year,
        "total_employees": len(employees),
        "total_cv_records": len(nps_records),
        "matches_found": len([m for m in mapping_results if m["matched_cv_name"]]),
        "employees_needing_update": len([m for m in mapping_results if m["needs_update"]]),
        "unmatched_cv_names": unmatched_cv,
        "mapping": mapping_results
    }


@admin_router.post("/name-matching/apply")
async def apply_name_matching(quarter: str = "Q1", year: int = 2026):
    """
    Apply the smart name matching and recalculate all employee scores.
    This will:
    1. Match employees to CV NPS data using smart nickname matching
    2. Update employee records with correct CV data
    3. Recalculate all scores
    """
    from name_matcher import get_nps_for_employee_smart, normalize_name
    from scoring_engine import (
        EmployeeV2, QuarterSettings,
        calculate_lbw_total, calculate_derived_metrics,
        calculate_customer_voice_score, calculate_review_tracker_bonus,
        calculate_combined_cv_rt, calculate_normalized_scores,
        calculate_bonus_points, calculate_total_score,
        calculate_rankings, calculate_performance_tiers
    )
    
    db = get_db()
    
    # Get employees
    employees = await db.employees_v2.find(
        {"quarter": quarter, "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    # Get CV NPS data
    nps_records = await db.cv_nps.find(
        {"quarter": quarter, "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    # Build NPS lookup
    nps_lookup = {normalize_name(n["employee_name"]): n for n in nps_records}
    
    # Get settings
    settings_doc = await db.quarter_settings.find_one(
        {"quarter": quarter, "year": year},
        {"_id": 0}
    )
    settings = QuarterSettings(**settings_doc) if settings_doc else QuarterSettings()
    
    updated_count = 0
    update_details = []
    
    for emp_doc in employees:
        emp_name = emp_doc["name"]
        aliases = emp_doc.get("aliases", [])
        
        # Get matched NPS data
        nps_data, match_reason = get_nps_for_employee_smart(emp_name, nps_lookup, aliases)
        
        if nps_data:
            nps_score = nps_data.get("nps_score") or 0
            promoters = nps_data.get("promoters") or 0
            detractors = nps_data.get("detractors") or 0
            
            # Calculate CV score using new formula
            # CV = (Promoters × 0.5) - (Detractors × 1) [uncapped]
            cv_score = (promoters * 0.5) - (detractors * 1)
            
            # Get other score components
            weighted_score = emp_doc.get("weighted_score", 0) or 0
            total_metric_bonus = emp_doc.get("total_metric_bonus", 0) or 0
            rt_bonus = emp_doc.get("review_tracker_bonus", 0) or 0
            
            new_total = round(weighted_score + cv_score + total_metric_bonus + rt_bonus, 2)
            
            # Update employee
            await db.employees_v2.update_one(
                {"id": emp_doc["id"]},
                {"$set": {
                    "nps_score": nps_score,
                    "cv_promoters": promoters,
                    "cv_detractors": detractors,
                    "cv_score": round(cv_score, 2),
                    "total_score": new_total,
                    "pre_dar_score": new_total,
                    "cv_match_source": match_reason,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            
            updated_count += 1
            update_details.append({
                "name": emp_name,
                "match_reason": match_reason,
                "nps_score": nps_score,
                "cv_score": cv_score,
                "new_total": new_total
            })
    
    return {
        "success": True,
        "quarter": quarter,
        "year": year,
        "employees_updated": updated_count,
        "details": update_details
    }


# ============================================================
# DATA INTEGRITY
# ============================================================

@admin_router.get("/data-integrity/summary")
async def get_integrity_summary():
    """
    Get a quick summary of data integrity status.
    """
    db = get_db()
    total_reviews = await db.customer_reviews.count_documents({})
    total_cv_feedback = await db.cv_feedback.count_documents({})
    valid_cv_feedback = await db.cv_feedback.count_documents({
        "server_name": {"$nin": [None, ""]}
    })
    invalid_cv_feedback = total_cv_feedback - valid_cv_feedback
    
    total_cv_nps = await db.cv_nps.count_documents({})
    
    return {
        "reviews": {
            "total": total_reviews
        },
        "cv_feedback": {
            "total": total_cv_feedback,
            "valid": valid_cv_feedback,
            "invalid": invalid_cv_feedback,
            "attribution_rate": round(valid_cv_feedback / total_cv_feedback * 100, 2) if total_cv_feedback > 0 else 0
        },
        "cv_nps": {
            "total": total_cv_nps
        },
        "status": "healthy" if invalid_cv_feedback == 0 else "needs_attention",
        "issues": invalid_cv_feedback
    }


# ============================================================
# OFFICIAL STATS MANAGEMENT (Manual Override for Accuracy)
# ============================================================

@admin_router.post("/rt-stats/set")
async def set_official_rt_stats(stats: OfficialRTStats):
    """
    Set the official ReviewTrackers stats from their UI.
    These values will be used for display and scoring instead of API-synced data.
    This ensures 100% accuracy with what ReviewTrackers dashboard shows.
    """
    db = get_db()
    stats_doc = {
        "quarter": stats.quarter.upper(),
        "year": stats.year,
        "platforms": {
            "Google": {"reviews": stats.google_reviews, "rating": stats.google_rating},
            "Yelp": {"reviews": stats.yelp_reviews, "rating": stats.yelp_rating},
            "TripAdvisor": {"reviews": stats.tripadvisor_reviews, "rating": stats.tripadvisor_rating},
            "OpenTable": {"reviews": stats.opentable_reviews, "rating": stats.opentable_rating},
            "Facebook": {"reviews": stats.facebook_reviews, "rating": stats.facebook_rating},
        },
        "total_reviews": stats.google_reviews + stats.yelp_reviews + stats.tripadvisor_reviews + stats.opentable_reviews + stats.facebook_reviews,
        "source": "manual_from_rt_ui",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Upsert the official stats
    await db.official_rt_stats.update_one(
        {"quarter": stats.quarter.upper(), "year": stats.year},
        {"$set": stats_doc},
        upsert=True
    )
    
    return {
        "success": True,
        "message": "Official RT stats saved",
        "stats": stats_doc
    }


@admin_router.get("/rt-stats/official")
async def get_official_rt_stats(quarter: str = "Q1", year: int = 2026):
    """
    Get the official ReviewTrackers stats (manually set from RT UI).
    Returns None if not set - then API-synced data should be used.
    """
    db = get_db()
    stats = await db.official_rt_stats.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not stats:
        return {
            "official_stats_set": False,
            "message": "No official RT stats set. Using API-synced data.",
            "quarter": quarter.upper(),
            "year": year
        }
    
    return {
        "official_stats_set": True,
        "stats": stats
    }


@admin_router.post("/cv-stats/set")
async def set_official_cv_stats(stats: OfficialCVStats):
    """
    Set the official Customer Voice stats from Loyalty Voice UI.
    These values will be used for display instead of scraped data.
    This ensures 100% accuracy with what Loyalty Voice dashboard shows.
    """
    db = get_db()
    stats_doc = {
        "quarter": stats.quarter.upper(),
        "year": stats.year,
        "nps_score": stats.nps_score,
        "promoters": stats.promoters,
        "passives": stats.passives,
        "detractors": stats.detractors,
        "total_responses": stats.total_responses,
        "source": "manual_from_lv_ui",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.official_cv_stats.update_one(
        {"quarter": stats.quarter.upper(), "year": stats.year},
        {"$set": stats_doc},
        upsert=True
    )
    
    return {
        "success": True,
        "message": "Official CV stats saved",
        "stats": stats_doc
    }


@admin_router.get("/cv-stats/official")
async def get_official_cv_stats(quarter: str = "Q1", year: int = 2026):
    """Get the official Customer Voice stats (manually set from LV UI)."""
    db = get_db()
    stats = await db.official_cv_stats.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not stats:
        return {
            "official_stats_set": False,
            "message": "No official CV stats set. Using scraped data.",
            "quarter": quarter.upper(),
            "year": year
        }
    
    return {
        "official_stats_set": True,
        "stats": stats
    }


@admin_router.post("/cv-stats/reconcile")
async def reconcile_cv_feedback_with_official(quarter: str = "Q1", year: int = 2026):
    """
    Reconcile cv_feedback data to match official stats.
    This adjusts the scraped data to match the official Loyalty Voice dashboard numbers.
    """
    db = get_db()
    
    # Get official stats
    official = await db.official_cv_stats.find_one(
        {"quarter": quarter.upper(), "year": year}
    )
    
    if not official:
        return {
            "success": False,
            "error": "No official CV stats set. Please set official stats first via /v2/admin/cv-stats/set"
        }
    
    # Get current cv_feedback counts
    pipeline = [
        {"$match": {"quarter": {"$in": [quarter.upper(), quarter]}, "year": year}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "promoters": {"$sum": {"$cond": [{"$gte": ["$rating", 9]}, 1, 0]}},
            "passives": {"$sum": {"$cond": [{"$and": [{"$gte": ["$rating", 7]}, {"$lte": ["$rating", 8]}]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$lte": ["$rating", 6]}, 1, 0]}}
        }}
    ]
    
    result = await db.cv_feedback.aggregate(pipeline).to_list(1)
    current = result[0] if result else {"total": 0, "promoters": 0, "passives": 0, "detractors": 0}
    
    official_total = official.get("total_responses", 0)
    official_promoters = official.get("promoters", 0)
    official_passives = official.get("passives", 0)
    official_detractors = official.get("detractors", 0)
    
    diff = {
        "total": official_total - current["total"],
        "promoters": official_promoters - current["promoters"],
        "passives": official_passives - current["passives"],
        "detractors": official_detractors - current["detractors"]
    }
    
    # Add missing records as "unattributed" feedback entries
    added_records = []
    
    # Add missing promoters (rating 10)
    for i in range(max(0, diff["promoters"])):
        record = {
            "quarter": quarter.upper(),
            "year": year,
            "server_name": "_unattributed_",
            "rating": 10,
            "date": datetime.now(timezone.utc).isoformat(),
            "source": "reconciliation_from_official",
            "comment": f"Added to reconcile with official stats (promoter {i+1})"
        }
        await db.cv_feedback.insert_one(record)
        added_records.append("promoter")
    
    # Add missing passives (rating 8)
    for i in range(max(0, diff["passives"])):
        record = {
            "quarter": quarter.upper(),
            "year": year,
            "server_name": "_unattributed_",
            "rating": 8,
            "date": datetime.now(timezone.utc).isoformat(),
            "source": "reconciliation_from_official",
            "comment": f"Added to reconcile with official stats (passive {i+1})"
        }
        await db.cv_feedback.insert_one(record)
        added_records.append("passive")
    
    # Add missing detractors (rating 5)
    for i in range(max(0, diff["detractors"])):
        record = {
            "quarter": quarter.upper(),
            "year": year,
            "server_name": "_unattributed_",
            "rating": 5,
            "date": datetime.now(timezone.utc).isoformat(),
            "source": "reconciliation_from_official",
            "comment": f"Added to reconcile with official stats (detractor {i+1})"
        }
        await db.cv_feedback.insert_one(record)
        added_records.append("detractor")
    
    # Remove excess if we have more than official
    removed_records = []
    
    if diff["promoters"] < 0:
        excess = await db.cv_feedback.find({
            "quarter": quarter.upper(),
            "year": year,
            "rating": {"$gte": 9},
            "source": "reconciliation_from_official"
        }).limit(abs(diff["promoters"])).to_list(abs(diff["promoters"]))
        
        for rec in excess:
            await db.cv_feedback.delete_one({"_id": rec["_id"]})
            removed_records.append("promoter")
    
    if diff["passives"] < 0:
        excess = await db.cv_feedback.find({
            "quarter": quarter.upper(),
            "year": year,
            "rating": {"$gte": 7, "$lte": 8},
            "source": "reconciliation_from_official"
        }).limit(abs(diff["passives"])).to_list(abs(diff["passives"]))
        
        for rec in excess:
            await db.cv_feedback.delete_one({"_id": rec["_id"]})
            removed_records.append("passive")
    
    if diff["detractors"] < 0:
        excess = await db.cv_feedback.find({
            "quarter": quarter.upper(),
            "year": year,
            "rating": {"$lte": 6},
            "source": "reconciliation_from_official"
        }).limit(abs(diff["detractors"])).to_list(abs(diff["detractors"]))
        
        for rec in excess:
            await db.cv_feedback.delete_one({"_id": rec["_id"]})
            removed_records.append("detractor")
    
    return {
        "success": True,
        "before": current,
        "official": {
            "total": official_total,
            "promoters": official_promoters,
            "passives": official_passives,
            "detractors": official_detractors
        },
        "diff": diff,
        "added": {
            "count": len(added_records),
            "breakdown": {
                "promoters": added_records.count("promoter"),
                "passives": added_records.count("passive"),
                "detractors": added_records.count("detractor")
            }
        },
        "removed": {
            "count": len(removed_records),
            "breakdown": {
                "promoters": removed_records.count("promoter"),
                "passives": removed_records.count("passive"),
                "detractors": removed_records.count("detractor")
            }
        },
        "message": f"Reconciliation complete. Added {len(added_records)}, removed {len(removed_records)} records."
    }
