"""
Admin Routes Module
Administrative endpoints for data management, sync, integrity, and fixes.
Extracted from server.py for better maintainability.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
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


@admin_router.post("/snapshots/{snapshot_id}/backfill-lsc")
async def backfill_snapshot_lsc(snapshot_id: str, apply: bool = False):
    """
    Backfill missing POS / CV / RT fields on a non-finalized snapshot
    from the live `employees_v2` collection (alias-aware) and recompute
    `total_score` / `pre_dar_score` / `weighted_score` through the
    canonical scoring engine.

    Default mode is dry-run. Pass `?apply=true` to persist.

    Refuses to run on finalized snapshots — finalized snapshots are
    intentionally immutable history.
    """
    import sys, importlib
    sys.path.insert(0, "/app/backend")
    # Reuse the script's `backfill` function directly so the HTTP endpoint
    # and the CLI share one implementation. No copy-paste, no drift.
    mod = importlib.import_module("scripts.backfill_snapshot_lsc")

    db = get_db()
    snap = await db.snapshot_workflow.find_one(
        {"id": snapshot_id}, {"_id": 0, "name": 1, "status": 1},
    )
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    if snap.get("status") == "finalized":
        raise HTTPException(
            status_code=400,
            detail="Refusing to backfill a finalized snapshot. "
                   "Finalized snapshots are immutable history.",
        )
    summary = await mod.backfill(db, snap["name"], apply=apply)
    return summary


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
    nps_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    promoters: int = Field(default=0, ge=0)
    passives: int = Field(default=0, ge=0)
    detractors: int = Field(default=0, ge=0)
    total_responses: int = Field(default=0, ge=0)
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
    Zero out cv_detractors for every employee in the target quarter and
    re-run the canonical scoring engine. The engine — not this endpoint —
    owns the CV / total-score formula, so there is no chance of drift.

    Steps:
    1. Set cv_detractors=0 on every active v2 row for the quarter.
    2. Replay `run_full_scoring` so cv_score, weighted_score, bonuses,
       and total_score all reconverge through one canonical path.
    """
    from scoring_engine import EmployeeV2, QuarterSettings, run_full_scoring

    db = get_db()
    quarter = quarter.upper()

    employees_with_detractors = await db.employees_v2.find({
        "quarter": quarter,
        "year": year,
        "cv_detractors": {"$gt": 0},
    }).to_list(2000)

    if not employees_with_detractors:
        return {
            "success": True,
            "message": "No employees with detractors found",
            "employees_updated": [],
        }

    # Zero detractors in the DB and in our working list so the rescore
    # operates on the post-clear state.
    ids = [e["_id"] for e in employees_with_detractors]
    await db.employees_v2.update_many(
        {"_id": {"$in": ids}},
        {"$set": {"cv_detractors": 0,
                  "updated_at": datetime.now(timezone.utc)}},
    )

    # Reload through the engine.
    settings_doc = await db.quarter_settings.find_one(
        {"quarter": quarter, "year": year}, {"_id": 0}
    )
    settings_doc = settings_doc or {}
    settings_doc.pop("id", None)
    try:
        settings = QuarterSettings(**settings_doc)
    except Exception:
        settings = QuarterSettings(quarter=quarter, year=year)

    fresh = await db.employees_v2.find(
        {"_id": {"$in": ids}}, {"_id": 0}
    ).to_list(2000)

    # Legacy field bridges so the engine sees its expected inputs.
    for r in fresh:
        if (not (r.get("review_mentions") or 0)) and (r.get("rt_mentions") or 0):
            r["review_mentions"] = int(r["rt_mentions"])
        if (not (r.get("guests") or 0)) and (r.get("guest_count") or 0):
            r["guests"] = float(r["guest_count"])

    emp_models = []
    for r in fresh:
        try:
            emp_models.append(EmployeeV2(**{
                k: v for k, v in r.items()
                if k in EmployeeV2.model_fields
            }))
        except Exception as e:
            logger.warning(f"clear-detractors: rescore skipped {r.get('name')}: {e}")

    scored = run_full_scoring(emp_models, settings)
    updated_employees = []
    for emp in scored:
        await db.employees_v2.update_one(
            {"id": emp.id, "quarter": quarter, "year": year},
            {"$set": emp.model_dump(exclude_none=True)},
        )
        updated_employees.append({
            "name": emp.name,
            "new_cv_score": emp.cv_score,
            "new_total": emp.total_score,
        })

    return {
        "success": True,
        "message": f"Cleared detractors for {len(updated_employees)} employees (re-scored through canonical engine)",
        "employees_updated": updated_employees,
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
    EMERGENCY FIX: Recalculate ALL employee rankings and sync to ALL snapshots
    for this quarter. Historical snapshots are fixed too so stale scores don't
    linger. Also backfills `review_mentions` from `rt_mentions` so the RT
    column renders correctly.
    """
    from scoring_engine import EmployeeV2, QuarterSettings, run_full_scoring

    db = get_db()
    logger.info(f"=== FIXING ALL RANKINGS for {quarter} {year} ===")

    # 1. Fix PPA values
    ppa_fixed = await _fix_ppa_values(quarter, year)
    logger.info(f"Fixed PPA for {ppa_fixed} employees")

    # 2. Backfill review_mentions from rt_mentions (EmployeeV2 model only has
    #    review_mentions — rt_mentions gets dropped on deserialization, so
    #    the RT column would render as 0 without this step).
    rt_backfill = await db.employees_v2.update_many(
        {
            "year": year,
            "quarter": quarter.upper(),
            "$or": [
                {"review_mentions": None},
                {"review_mentions": {"$exists": False}},
            ],
        },
        [{"$set": {"review_mentions": {"$ifNull": ["$rt_mentions", 0]}}}],
    )
    logger.info(f"Backfilled review_mentions on {rt_backfill.modified_count} employees")

    # 3. Get settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")

    settings = QuarterSettings(**settings_doc)

    # 4. Load all employees (re-fetch after backfill)
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(500)

    if not employees_docs:
        return {"error": "No employees found", "fixed": 0}

    # Normalize legacy/alternate field names so EmployeeV2 picks them up
    # (EmployeeV2 only has `review_mentions` and `glassware_sales`; the POS
    # parser writes `rt_mentions` and `bar_glassware_sales`). Without this,
    # RT column renders as 0 and glassware_per_guest gets wiped by
    # calculate_derived_metrics (glassware_sales / guests = 0 / guests = 0).
    for d in employees_docs:
        if not d.get("review_mentions") and d.get("rt_mentions"):
            d["review_mentions"] = d["rt_mentions"]
        if not d.get("glassware_sales") and d.get("bar_glassware_sales"):
            d["glassware_sales"] = d["bar_glassware_sales"]

    employees = [EmployeeV2(**doc) for doc in employees_docs]

    # 5. Run full scoring pipeline (caps each POS metric at 100, applies
    #    weights, adds CV + RT + metric bonuses).
    employees = run_full_scoring(employees, settings)

    # 6. Persist each recomputed employee
    updated_count = 0
    for emp in employees:
        await db.employees_v2.update_one(
            {"id": emp.id},
            {"$set": emp.model_dump()}
        )
        updated_count += 1

    logger.info(f"Updated {updated_count} employees")

    # 7. Sync fresh scores into every snapshot for this quarter (not just
    #    the most recent — historical snapshots had stale weighted_score
    #    values from the old formula). Also overlay the freshly computed
    #    tier_label / position_label so the leaderboard endpoint (which
    #    reads `tier_label` directly from the snapshot) matches the
    #    snapshot view (which recomputes tiers live).
    fresh_employees = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(500)

    # Build the hierarchy rankings (same logic the snapshot view uses) so
    # we can stamp tier_label / position_label onto each fresh employee.
    from scoring_engine import generate_hierarchy_rankings
    fresh_emp_objs = []
    for d in fresh_employees:
        d2 = dict(d)
        if not d2.get("review_mentions") and d2.get("rt_mentions"):
            d2["review_mentions"] = d2["rt_mentions"]
        if not d2.get("glassware_sales") and d2.get("bar_glassware_sales"):
            d2["glassware_sales"] = d2["bar_glassware_sales"]
        try:
            fresh_emp_objs.append(EmployeeV2(**d2))
        except Exception:
            continue
    rankings = generate_hierarchy_rankings(fresh_emp_objs, settings)
    rank_by_id = {r.get("employee_id"): r for r in rankings if r.get("employee_id")}

    # Overlay tier_label, position_label, peer_rank onto fresh_employees.
    for emp in fresh_employees:
        ranked = rank_by_id.get(emp.get("id"))
        if not ranked:
            continue
        emp["tier_label"] = ranked.get("tier_label")
        emp["position_label"] = ranked.get("position_label")
        emp["peer_rank"] = ranked.get("peer_rank")
        emp["performance_tier"] = ranked.get("performance_tier")

    snaps = await db.snapshot_workflow.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 1, "is_current": 1, "status": 1, "employees": 1}
    ).to_list(200)

    now_iso = datetime.now(timezone.utc).isoformat()
    snapshots_synced = 0
    for snap in snaps:
        existing = snap.get("employees") or []
        # snapshot.employees can be a dict keyed by name, or a list.
        if isinstance(existing, dict):
            fresh_by_id = {e.get("id"): e for e in fresh_employees if e.get("id")}
            rebuilt = {}
            for k, v in existing.items():
                if isinstance(v, dict) and v.get("id") in fresh_by_id:
                    rebuilt[k] = fresh_by_id[v["id"]]
                else:
                    rebuilt[k] = v
            employees_update = rebuilt
        else:
            employees_update = fresh_employees

        await db.snapshot_workflow.update_one(
            {"_id": snap["_id"]},
            {"$set": {"employees": employees_update, "synced_at": now_iso}},
        )
        snapshots_synced += 1

    logger.info(f"Synced {snapshots_synced} snapshots")

    # Persist tier_label updates back to employees_v2 too, so any other
    # endpoint reading from the v2 collection sees consistent tiers.
    for emp in fresh_employees:
        await db.employees_v2.update_one(
            {"id": emp.get("id")},
            {"$set": {
                "tier_label": emp.get("tier_label"),
                "position_label": emp.get("position_label"),
                "peer_rank": emp.get("peer_rank"),
                "performance_tier": emp.get("performance_tier"),
            }}
        )

    return {
        "success": True,
        "ppa_fixed": ppa_fixed,
        "rt_backfill": rt_backfill.modified_count,
        "employees_fixed": updated_count,
        "snapshots_fixed": snapshots_synced,
        "message": (
            f"Fixed rankings for {updated_count} employees, synced "
            f"{snapshots_synced} snapshots"
        ),
    }


# ============================================================
# DATA CLEARING UTILITIES
# ============================================================

@admin_router.delete("/clear-cv-data")
async def clear_cv_data(quarter: str = "Q1", year: int = 2026):
    """
    Clear all Customer Voice data and reset employee CV scores.
    """
    from scoring_engine import compute_total_score_dict, QuarterSettings

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

        # Recalculate total scores via the canonical scoring engine so
        # that any per-quarter weight or formula tweak applies here too.
        settings_doc = await db.quarter_settings.find_one(
            {"year": year, "quarter": quarter.upper()}, {"_id": 0}
        )
        settings = QuarterSettings(**settings_doc) if settings_doc else QuarterSettings(
            year=year, quarter=quarter.upper()
        )
        employees = await db.employees_v2.find({
            "quarter": quarter,
            "year": year
        }).to_list(200)

        for emp in employees:
            scored = compute_total_score_dict({**emp, "cv_score": 0}, settings)
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "weighted_score": scored["weighted_score"],
                    "pre_dar_score": scored["pre_dar_score"],
                    "total_score": scored["total_score"],
                }},
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
    from scoring_engine import compute_total_score_dict, QuarterSettings

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

        # Recalculate total scores through the canonical engine.
        settings_doc = await db.quarter_settings.find_one(
            {"year": year, "quarter": quarter.upper()}, {"_id": 0}
        )
        settings = QuarterSettings(**settings_doc) if settings_doc else QuarterSettings(
            year=year, quarter=quarter.upper()
        )
        employees = await db.employees_v2.find({
            "quarter": quarter,
            "year": year
        }).to_list(200)

        for emp in employees:
            scored = compute_total_score_dict({**emp, "review_tracker_bonus": 0}, settings)
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "weighted_score": scored["weighted_score"],
                    "pre_dar_score": scored["pre_dar_score"],
                    "total_score": scored["total_score"],
                }},
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
    from scoring_engine import EmployeeV2, calculate_customer_voice_score

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

        # Project the new CV score by replaying the canonical engine on a
        # throwaway employee with the matched CV inputs. Guarantees the
        # preview matches what apply_name_matching will actually write.
        projected_emp = EmployeeV2(
            name=emp_name,
            nps_score=matched_nps,
            cv_promoters=matched_promoters,
            cv_detractors=matched_detractors,
        )
        calculate_customer_voice_score(projected_emp)
        projected_cv = projected_emp.cv_score or 0

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
    Apply smart-name-matching to attach the right CV NPS rows to each
    employee, then re-run the canonical scoring engine. Engine — not
    inline math — owns the CV formula and the total-score formula so
    this endpoint can never drift.

    Pipeline:
    1. For every active v2 row in the quarter, look up the best NPS
       match by canonical name + aliases.
    2. Stamp `nps_score`, `cv_promoters`, `cv_detractors`,
       `cv_match_source` onto the row (preserve everything else).
    3. Reload the touched rows and replay `run_full_scoring` so cv_score
       and total_score are recomputed by the engine.
    """
    from name_matcher import get_nps_for_employee_smart, normalize_name
    from scoring_engine import EmployeeV2, QuarterSettings, run_full_scoring

    db = get_db()

    employees = await db.employees_v2.find(
        {"quarter": quarter, "year": year},
        {"_id": 0},
    ).to_list(2000)

    nps_records = await db.cv_nps.find(
        {"quarter": quarter, "year": year},
        {"_id": 0},
    ).to_list(2000)
    nps_lookup = {normalize_name(n["employee_name"]): n for n in nps_records}

    settings_doc = await db.quarter_settings.find_one(
        {"quarter": quarter, "year": year}, {"_id": 0}
    )
    settings_doc = settings_doc or {}
    settings_doc.pop("id", None)
    try:
        settings = QuarterSettings(**settings_doc)
    except Exception:
        settings = QuarterSettings(quarter=quarter, year=year)

    touched_ids: List[str] = []
    update_details: List[Dict[str, Any]] = []

    for emp_doc in employees:
        emp_name = emp_doc["name"]
        aliases = emp_doc.get("aliases", [])
        nps_data, match_reason = get_nps_for_employee_smart(
            emp_name, nps_lookup, aliases,
        )
        if not nps_data:
            continue

        nps_score = nps_data.get("nps_score") or 0
        promoters = nps_data.get("promoters") or 0
        detractors = nps_data.get("detractors") or 0

        await db.employees_v2.update_one(
            {"id": emp_doc["id"], "quarter": quarter, "year": year},
            {"$set": {
                "nps_score": nps_score,
                "cv_promoters": promoters,
                "cv_detractors": detractors,
                "cv_match_source": match_reason,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        touched_ids.append(emp_doc["id"])
        update_details.append({
            "name": emp_name,
            "match_reason": match_reason,
            "nps_score": nps_score,
            "promoters": promoters,
            "detractors": detractors,
        })

    # Re-run canonical scoring on every touched row.
    if touched_ids:
        fresh = await db.employees_v2.find(
            {"id": {"$in": touched_ids}, "quarter": quarter, "year": year},
            {"_id": 0},
        ).to_list(2000)
        # Legacy bridges so the engine sees its expected inputs.
        for r in fresh:
            if (not (r.get("review_mentions") or 0)) and (r.get("rt_mentions") or 0):
                r["review_mentions"] = int(r["rt_mentions"])
            if (not (r.get("guests") or 0)) and (r.get("guest_count") or 0):
                r["guests"] = float(r["guest_count"])
        emp_models = []
        for r in fresh:
            try:
                emp_models.append(EmployeeV2(**{
                    k: v for k, v in r.items()
                    if k in EmployeeV2.model_fields
                }))
            except Exception as e:
                logger.warning(f"name-matching: rescore skipped {r.get('name')}: {e}")
        scored = run_full_scoring(emp_models, settings)
        for emp in scored:
            await db.employees_v2.update_one(
                {"id": emp.id, "quarter": quarter, "year": year},
                {"$set": emp.model_dump(exclude_none=True)},
            )
            # Mirror the freshly scored cv_score/total_score into the
            # detail payload for the admin to sanity-check.
            for d in update_details:
                if d["name"] == emp.name:
                    d["cv_score"] = emp.cv_score
                    d["new_total"] = emp.total_score
                    break

    return {
        "success": True,
        "quarter": quarter,
        "year": year,
        "employees_updated": len(touched_ids),
        "details": update_details,
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



# ---------------------------------------------------------------------------
# Canonical Quarter Settings Normalizer
# ---------------------------------------------------------------------------
# Per the May 2026 Scoring Engine Audit, every quarter's stored settings
# must match ONE canonical model before the company-wide demo. This
# endpoint walks `quarter_settings` and rewrites:
#   • weight_ppa / weight_lsc / weight_lbw / weight_glass → 0.25/0.25/0.20/0.15
#   • benchmark_ppa = 55, benchmark_lbw = 8, benchmark_glass = 1.35, benchmark_lsc = 100
#   • rt_points_per_mention = 0.33, rt_max_points = 20
#   • cv_promoter_points = 1, cv_detractor_points = 2
# Quarters whose `locked == true` are reported but skipped (history is
# frozen — admin must explicitly unlock via Quarter Settings UI first).
# ---------------------------------------------------------------------------

CANONICAL_ENGINE_CONSTANTS = {
    "weight_ppa": 0.25,
    "weight_lsc": 0.25,
    "weight_lbw": 0.20,
    "weight_glass": 0.15,
    "rt_points_per_mention": 0.33,
    "rt_max_points": 20.0,
    "cv_promoter_points": 1.0,
    "cv_detractor_points": 2.0,
    "bonus_rate": 0.25,
    "bonus_cap": 5.0,
}

CANONICAL_BENCHMARKS = {
    "benchmark_ppa": 55.0,
    "benchmark_lbw": 8.0,
    "benchmark_glass": 1.35,
    "benchmark_lsc": 100.0,
}


@admin_router.post("/normalize-quarter-settings")
async def normalize_quarter_settings(
    apply: bool = False,
    include_locked: bool = False,
    lock_after: bool = False,
    normalize_benchmarks: bool = False,
):
    """
    Audit (and optionally repair) every quarter_settings doc to the
    canonical scoring model. Default is DRY-RUN — pass `?apply=true` to
    persist changes.

    Engine constants normalized by default (weights, RT rate/cap, CV
    promoter/detractor points, bonus rate/cap). Benchmarks (PPA $55,
    LBW $8, Glass $1.35, LSC 100) are NOT touched unless
    `?normalize_benchmarks=true` is passed — historical quarters may
    have intentional benchmark overrides.

    Query params:
      • apply=true                → actually write the changes (default false = preview)
      • include_locked=true       → also rewrite quarters where locked=true
      • lock_after=true           → set locked=true on every quarter touched
      • normalize_benchmarks=true → also rewrite benchmarks to canonical

    Returns a per-quarter diff so the admin can sanity-check before
    re-running with apply=true.
    """
    db = get_db()
    docs = await db.quarter_settings.find({}, {"_id": 0}).to_list(500)
    docs.sort(key=lambda d: (d.get("year", 0), d.get("quarter", "")))

    canonical_spec = dict(CANONICAL_ENGINE_CONSTANTS)
    if normalize_benchmarks:
        canonical_spec.update(CANONICAL_BENCHMARKS)

    report = []
    changes_total = 0

    for doc in docs:
        year = doc.get("year")
        quarter = doc.get("quarter")
        is_locked = bool(doc.get("locked"))

        diff = {}
        for key, canonical_val in canonical_spec.items():
            current = doc.get(key)
            if current is None or abs(float(current) - float(canonical_val)) > 0.0001:
                diff[key] = {"from": current, "to": canonical_val}

        entry = {
            "year": year,
            "quarter": quarter,
            "locked": is_locked,
            "needs_change": bool(diff),
            "diff": diff,
            "applied": False,
            "skipped_reason": None,
        }

        if not diff:
            report.append(entry)
            continue

        if is_locked and not include_locked:
            entry["skipped_reason"] = "locked (pass include_locked=true to override)"
            report.append(entry)
            continue

        if apply:
            update_set = {k: v["to"] for k, v in diff.items()}
            update_set["normalized_at"] = datetime.now(timezone.utc).isoformat()
            if lock_after:
                update_set["locked"] = True
                update_set["locked_at"] = datetime.now(timezone.utc).isoformat()
            await db.quarter_settings.update_one(
                {"year": year, "quarter": quarter},
                {"$set": update_set},
            )
            entry["applied"] = True
            changes_total += len(diff)

        report.append(entry)

    return {
        "success": True,
        "dry_run": not apply,
        "include_locked": include_locked,
        "lock_after": lock_after,
        "normalize_benchmarks": normalize_benchmarks,
        "canonical_spec": canonical_spec,
        "quarters_total": len(docs),
        "quarters_needing_change": sum(1 for r in report if r["needs_change"]),
        "quarters_applied": sum(1 for r in report if r["applied"]),
        "field_writes_total": changes_total,
        "report": report,
    }



# ---------------------------------------------------------------------------
# Scoring Trust Score (Dashboard widget)
# ---------------------------------------------------------------------------
# Single endpoint that rolls up three audit signals so the RD can see at a
# glance that the math is bulletproof before a demo:
#   1. Quarter settings drift  — any stored quarter that diverges from the
#      canonical engine constants (weights, RT rate/cap, CV +1/-2, bonus).
#   2. Data integrity           — P0/P1/P2 issue counts from the validation
#      suite (mirrors GET /api/v2/admin/integrity but condensed).
#   3. Alias collisions         — active canonical records whose names
#      collide with another active record's aliases.
# Returns a tri-state "status": green / amber / red.
# ---------------------------------------------------------------------------

@admin_router.get("/scoring-trust")
async def scoring_trust_score():
    """Aggregate scoring-health signal for the Dashboard trust widget."""
    db = get_db()

    # --- 1. Quarter settings drift -----------------------------------------
    qs_docs = await db.quarter_settings.find({}, {"_id": 0}).to_list(500)
    drift_quarters = []
    for doc in qs_docs:
        diff_keys = []
        for key, canonical_val in CANONICAL_ENGINE_CONSTANTS.items():
            current = doc.get(key)
            if current is None or abs(float(current) - float(canonical_val)) > 0.0001:
                diff_keys.append(key)
        if diff_keys:
            drift_quarters.append({
                "year": doc.get("year"),
                "quarter": doc.get("quarter"),
                "locked": bool(doc.get("locked")),
                "drift_fields": diff_keys,
            })

    # --- 2. Data integrity -------------------------------------------------
    from services.validation_service import EmployeeValidator
    try:
        integrity = await EmployeeValidator(db).run_all()
        integrity_summary = integrity.get("summary", {})
        p0 = int(integrity_summary.get("p0_issues", 0))
        p1 = int(integrity_summary.get("p1_issues", 0))
        p2 = int(integrity_summary.get("p2_issues", 0))
        deploy_gate = integrity_summary.get("deploy_gate", "UNKNOWN")
    except Exception as e:
        logger.warning(f"scoring_trust: integrity check failed: {e}")
        p0 = p1 = p2 = -1
        deploy_gate = "ERROR"

    # --- 3. Alias collisions ----------------------------------------------
    collisions = []
    all_emps = await db.employees.find(
        {}, {"_id": 0, "id": 1, "name": 1, "aliases": 1, "status": 1,
             "current_metrics": 1}
    ).to_list(2000)
    name_to_emp = {(e.get("name") or "").lower(): e for e in all_emps}
    for e in all_emps:
        if (e.get("status") or "").lower() != "active":
            continue
        for a in (e.get("aliases") or []):
            al = (a or "").strip().lower()
            other = name_to_emp.get(al)
            if not other or other.get("id") == e.get("id"):
                continue
            if (other.get("status") or "").lower() != "active":
                continue
            collisions.append({
                "primary_id": e.get("id"),
                "primary_name": e.get("name"),
                "duplicate_id": other.get("id"),
                "duplicate_name": other.get("name"),
            })

    # --- 4. Metric integrity (passive corruption detection) --------------
    # For every active employee with snapshot-mirrored metrics, verify the
    # stored derived ratios match their inputs. A mismatch indicates either
    # raw-data corruption (e.g. Kahi's $20B net_sales typo) or a stale
    # ratio that never got recomputed after an edit. The Dashboard Trust
    # badge surfaces a "Metric Integrity" tile so the owner sees the
    # problem the moment it appears — not after a coaching meeting.
    METRIC_TOLERANCE = 0.02   # 2% relative
    METRIC_MIN_ABS   = 0.05   # ignore sub-5¢ rounding noise
    metric_mismatches: List[Dict[str, Any]] = []
    for e in all_emps:
        if (e.get("status") or "").lower() != "active":
            continue
        cm = e.get("current_metrics") or {}
        guests = cm.get("guests") or cm.get("guest_count") or 0
        if not guests or guests <= 0:
            continue

        def _check(label: str, numerator: float, denom: float, stored):
            if denom is None or denom <= 0:
                return
            if stored is None:
                return
            expected = round(numerator / denom, 2)
            diff = abs(expected - stored)
            if diff < METRIC_MIN_ABS:
                return
            # Use the larger of expected/stored as denominator so a
            # 0 stored value triggers the check (relative-to-stored
            # would dodge the corruption).
            rel = diff / max(abs(expected), abs(stored), 1e-9)
            if rel > METRIC_TOLERANCE:
                metric_mismatches.append({
                    "employee_id": e.get("id"),
                    "name": e.get("name"),
                    "metric": label,
                    "stored": stored,
                    "expected": expected,
                    "diff": round(diff, 4),
                    "rel_diff_pct": round(rel * 100, 2),
                })

        net_sales = cm.get("net_sales")
        ppa = cm.get("ppa")
        if net_sales is not None and ppa is not None:
            _check("ppa", float(net_sales), float(guests), float(ppa))

        lsc_count = cm.get("lsc_count") or 0
        gpl = cm.get("guests_per_lsc")
        if lsc_count and gpl is not None:
            _check("guests_per_lsc", float(guests), float(lsc_count), float(gpl))

        lbw = cm.get("lbw") or cm.get("lbw_total")
        lbw_per_guest = cm.get("lbw_per_guest")
        if lbw is not None and lbw_per_guest is not None:
            _check("lbw_per_guest", float(lbw), float(guests), float(lbw_per_guest))

    # --- Tri-state rollup --------------------------------------------------
    # RED   = any P0 issue OR alias collision present OR ≥1 unlocked
    #         current-or-future-quarter has drift
    # AMBER = drift on a locked/historical quarter only, P1 issues, OR
    #         legacy benchmark stragglers
    # GREEN = no drift, no integrity issues, no collisions
    now = datetime.now(timezone.utc)
    current_year = now.year
    current_quarter_idx = (now.month - 1) // 3 + 1
    current_quarter = f"Q{current_quarter_idx}"

    def is_current_or_future(q):
        try:
            y = int(q.get("year"))
        except (TypeError, ValueError):
            return False
        if y > current_year:
            return True
        if y == current_year:
            qn = q.get("quarter") or ""
            try:
                return int(qn.replace("Q", "")) >= current_quarter_idx
            except ValueError:
                return False
        return False

    unlocked_active_drift = [
        q for q in drift_quarters
        if (not q["locked"]) and is_current_or_future(q)
    ]
    historical_or_locked_drift = [
        q for q in drift_quarters
        if q not in unlocked_active_drift
    ]

    issues = []
    if p0 > 0:
        issues.append(f"{p0} P0 integrity issue(s)")
    if collisions:
        issues.append(f"{len(collisions)} alias collision(s)")
    if unlocked_active_drift:
        issues.append(
            f"{len(unlocked_active_drift)} current/future quarter(s) "
            f"with scoring-constant drift"
        )
    # Metric corruption: 5+ mismatches = blocker (data is silently lying
    # to coaches), 1-4 = advisory.
    if len(metric_mismatches) >= 5:
        issues.append(
            f"{len(metric_mismatches)} employee metric(s) drift from raw inputs"
        )

    warnings = []
    if p1 > 0:
        warnings.append(f"{p1} P1 integrity issue(s)")
    if historical_or_locked_drift:
        warnings.append(
            f"{len(historical_or_locked_drift)} historical quarter(s) "
            f"with scoring-constant drift"
        )
    if p2 > 0:
        warnings.append(f"{p2} P2 integrity issue(s)")
    if 0 < len(metric_mismatches) < 5:
        warnings.append(
            f"{len(metric_mismatches)} employee metric(s) drift from raw inputs"
        )

    if issues:
        status = "red"
    elif warnings:
        status = "amber"
    else:
        status = "green"

    return {
        "status": status,                  # "green" | "amber" | "red"
        "headline": {
            "green": "Scoring engine verified canonical.",
            "amber": "Minor drift — review before demo.",
            "red":   "Action required before demo.",
        }[status],
        "issues": issues,                  # blocker-level
        "warnings": warnings,              # advisory
        "checked_at": now.isoformat(),
        "details": {
            "quarter_settings": {
                "total": len(qs_docs),
                "drift_count": len(drift_quarters),
                "unlocked_active_drift": unlocked_active_drift,
                "historical_or_locked_drift": historical_or_locked_drift,
                "current_quarter": f"{current_year} {current_quarter}",
            },
            "integrity": {
                "p0_issues": p0,
                "p1_issues": p1,
                "p2_issues": p2,
                "deploy_gate": deploy_gate,
            },
            "alias_collisions": {
                "count": len(collisions),
                "pairs": collisions[:10],   # cap response size
            },
            "metric_integrity": {
                "count": len(metric_mismatches),
                "tolerance_pct": round(METRIC_TOLERANCE * 100, 2),
                "mismatches": metric_mismatches[:20],
            },
        },
        "remediation": {
            "scoring_drift": "POST /api/v2/admin/normalize-quarter-settings?apply=true",
            "alias_collisions": "Open Nickname Manager and merge the collision pairs.",
            "integrity": "GET /api/v2/admin/integrity for the full validation report.",
            "metric_integrity": (
                "Open the affected employee in Data Uploads or POS Review "
                "and correct the raw input (guests / net_sales / lsc_count / lbw) — "
                "the engine recomputes derived ratios on save."
            ),
        },
    }



# ---------------------------------------------------------------------------
# Demo Prep — Consolidate v2 alias-named rows + backfill display names
# ---------------------------------------------------------------------------
# Fixes three categories of demo-blocking drift in a single transaction:
#
#   1. employees_v2 contains multiple rows for the same canonical employee
#      because a POS upload landed under both the canonical name AND an
#      alias (e.g. "Trey Quick" + "Treyanna Quick"). The merge endpoint
#      deletes by *id*, so any later POS upload re-creates an alias row
#      with a fresh id and the drift returns. This endpoint hard-resolves
#      every alias-named v2 row in the target quarter:
#        - If a canonical-named row also exists: merge POS/CV/RT inputs
#          (sum guests, sales, mentions, promoters/passives/detractors),
#          drop the alias row, rerun scoring.
#        - If only the alias row exists: rename it to the canonical name,
#          rerun scoring.
#
#   2. Backfill display_name on any canonical (and per-quarter v2) record
#      whose display_name is a single word but whose `name` or
#      `report_name` carries the full name.
#
#   3. Resync the current snapshot's employees[] from employees_v2 so
#      the dashboard immediately reflects all post-cleanup rows.
#
# Default mode is dry-run. Pass `?apply=true` to persist.
# ---------------------------------------------------------------------------

# Fields that should be SUMMED when merging two POS-only / CV / RT rows
# for the same canonical person. These are the raw inputs that flow into
# the scoring engine — derived metrics (PPA / LBW per guest / etc.) are
# recomputed downstream by run_full_scoring.
_MERGE_SUM_FIELDS = (
    "guests", "guest_count",
    "net_sales", "food_sales", "liquor_sales", "beer_sales", "wine_sales",
    "bar_glassware_sales", "lbw", "loyalty_sales", "lsc_count",
    "cv_promoters", "cv_passives", "cv_detractors",
    "rt_mentions", "review_mentions",
)

# Fields that should be taken from whichever row has a non-empty value
# (e.g. job_title, store_id) — never summed.
_MERGE_PICK_FIELDS = ("job_title", "store_id", "tier_label", "display_name")


def _full_name_candidates(canonical_doc: dict) -> Optional[str]:
    """Return the longest single-line full-name candidate from a canonical
    employee doc (looking at name / display_name / report_name). Returns
    None if every candidate is single-token."""
    cands = [
        canonical_doc.get("report_name"),
        canonical_doc.get("name"),
        canonical_doc.get("display_name"),
    ]
    multi = [c.strip() for c in cands if c and " " in str(c).strip()]
    if not multi:
        return None
    # Pick the longest non-empty multi-token candidate.
    return max(multi, key=len)


@admin_router.post("/demo-prep")
async def demo_prep(
    quarter: str,
    year: int,
    apply: bool = False,
    resync_snapshot: bool = True,
    force_rescore: bool = True,
):
    """
    One-shot consolidation for the live-demo quarter.

    Query params:
      • quarter           — "Q1", "Q2", "Q3", "Q4"
      • year              — e.g. 2026
      • apply=true        — actually write changes (default dry-run)
      • resync_snapshot   — after dedup, repull snapshot.employees from
                            employees_v2 so the dashboard catches up
                            (default true)
      • force_rescore     — rerun run_full_scoring on every active v2 row
                            in the quarter so summed metrics reflect in
                            scores (default true)

    Returns a per-action diff for sanity-check.
    """
    db = get_db()
    quarter = quarter.upper()

    # ----- 0. Index canonical employees ---------------------------------
    canonical = await db.employees.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "name": 1, "display_name": 1,
         "report_name": 1, "aliases": 1},
    ).to_list(5000)

    canonical_by_name: Dict[str, dict] = {}
    alias_to_canonical_name: Dict[str, str] = {}
    for c in canonical:
        cn = (c.get("name") or "").strip()
        if cn:
            canonical_by_name[cn.lower()] = c
        for a in (c.get("aliases") or []):
            akey = (a or "").strip().lower()
            if akey and akey != cn.lower():
                alias_to_canonical_name[akey] = cn

    # ----- 1. Display-name backfill -------------------------------------
    display_fixes: List[Dict[str, Any]] = []
    for c in canonical:
        dn = (c.get("display_name") or "").strip()
        nm = (c.get("name") or "").strip()
        # If display_name is single-word but a fuller name exists elsewhere
        # on the doc, prefer the fuller name. We only repair docs where the
        # canonical record itself has a fuller candidate (report_name etc).
        full = _full_name_candidates(c)
        needs = False
        new_dn = dn
        new_nm = nm
        if dn and " " not in dn and full and full != dn:
            new_dn = full
            needs = True
        if nm and " " not in nm and full and full != nm:
            new_nm = full
            needs = True
        if not needs:
            continue
        display_fixes.append({
            "id": c["id"],
            "from": {"name": nm, "display_name": dn},
            "to":   {"name": new_nm, "display_name": new_dn},
        })
        if apply:
            await db.employees.update_one(
                {"id": c["id"]},
                {"$set": {"name": new_nm, "display_name": new_dn}},
            )
            await db.employees_v2.update_many(
                {"id": c["id"]},
                {"$set": {"name": new_nm, "display_name": new_dn}},
            )

    # ----- 2. employees_v2 alias-row consolidation ----------------------
    # Refresh canonical state — we may have just rewritten name/display_name
    # in section 1, and the alias index needs to use the new canonical name
    # as the merge target.
    if display_fixes:
        canonical = await db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "display_name": 1,
             "report_name": 1, "aliases": 1},
        ).to_list(5000)
        canonical_by_name = {}
        alias_to_canonical_name = {}
        for c in canonical:
            cn = (c.get("name") or "").strip()
            if cn:
                canonical_by_name[cn.lower()] = c
            for a in (c.get("aliases") or []):
                akey = (a or "").strip().lower()
                if akey and akey != cn.lower():
                    alias_to_canonical_name[akey] = cn

    # Index v2 rows for the target quarter by lowercased name.
    v2_rows = await db.employees_v2.find(
        {"quarter": quarter, "year": year},
        {"_id": 0},
    ).to_list(2000)
    by_name: Dict[str, dict] = {}
    for r in v2_rows:
        key = (r.get("name") or "").strip().lower()
        if not key:
            continue
        # If we already saw the name (rare exact dup), keep the higher
        # total_score row as the "winner" and treat the other as a
        # secondary that gets merged in too.
        if key in by_name:
            existing = by_name[key]
            if (r.get("total_score") or 0) > (existing.get("total_score") or 0):
                by_name[key] = r
        else:
            by_name[key] = r

    dedup_actions: List[Dict[str, Any]] = []
    rows_to_rescore: List[dict] = []

    for alias_key, canonical_name in alias_to_canonical_name.items():
        alias_row = by_name.get(alias_key)
        if not alias_row:
            continue
        canonical_row = by_name.get(canonical_name.lower())

        if canonical_row is None:
            # Rename only — no metric merge required.
            dedup_actions.append({
                "kind": "rename",
                "from": alias_row.get("name"),
                "to": canonical_name,
                "alias_id": alias_row.get("id"),
            })
            if apply:
                await db.employees_v2.update_one(
                    {"id": alias_row["id"]},
                    {"$set": {
                        "name": canonical_name,
                        "display_name": canonical_name,
                    }},
                )
                alias_row["name"] = canonical_name
                alias_row["display_name"] = canonical_name
                rows_to_rescore.append(alias_row)
            continue

        # Both rows exist — merge metrics into canonical_row, drop alias_row.
        merged_fields = {}
        for k in _MERGE_SUM_FIELDS:
            a = float(alias_row.get(k) or 0)
            b = float(canonical_row.get(k) or 0)
            merged_fields[k] = a + b
        for k in _MERGE_PICK_FIELDS:
            cur = canonical_row.get(k)
            if cur in (None, "", 0):
                v = alias_row.get(k)
                if v not in (None, "", 0):
                    merged_fields[k] = v

        dedup_actions.append({
            "kind": "merge_and_drop",
            "kept": canonical_name,
            "kept_id": canonical_row.get("id"),
            "dropped": alias_row.get("name"),
            "dropped_id": alias_row.get("id"),
            "merged_fields": merged_fields,
        })
        if apply:
            await db.employees_v2.update_one(
                {"id": canonical_row["id"]},
                {"$set": {**merged_fields, "name": canonical_name,
                          "display_name": canonical_name}},
            )
            await db.employees_v2.delete_one({"id": alias_row["id"]})
            # Pull the freshly merged row for rescore
            refreshed = await db.employees_v2.find_one(
                {"id": canonical_row["id"]}, {"_id": 0}
            )
            if refreshed:
                rows_to_rescore.append(refreshed)
        # Remove the alias entry from our local index so we don't double-process
        by_name.pop(alias_key, None)

    # ----- 2b. Same-name v2 duplicate dedup ------------------------------
    # After the alias-aware rename/merge above, multiple v2 rows can still
    # share the same canonical name (e.g. two different upload batches
    # both landed under "Lennie Nguyen"), and in pathological cases two
    # rows can even share the SAME `id` field (legacy upload bug where
    # the merge dropped one row but another upload re-created it with
    # the same canonical id). Group by name and consolidate, using
    # Mongo's `_id` for deletion so duplicate-`id` rows are still
    # individually addressable.
    name_groups: Dict[str, List[dict]] = {}
    fresh = await db.employees_v2.find(
        {"quarter": quarter, "year": year},
    ).to_list(2000)  # keep _id so we can delete by ObjectId
    for r in fresh:
        key = (r.get("name") or "").strip().lower()
        if key:
            name_groups.setdefault(key, []).append(r)

    same_name_dedup_actions: List[Dict[str, Any]] = []
    for key, rows in name_groups.items():
        if len(rows) < 2:
            continue
        # Pick survivor = row with highest total_score so the higher-confidence
        # POS+CV+RT row wins job_title/store_id, then sum the rest.
        rows.sort(key=lambda r: r.get("total_score") or 0, reverse=True)
        survivor = rows[0]
        merged_fields = {}
        dropped_object_ids: List[Any] = []
        for r in rows[1:]:
            for f in _MERGE_SUM_FIELDS:
                a = float(survivor.get(f) or 0)
                b = float(r.get(f) or 0)
                merged_fields[f] = a + b
                survivor[f] = a + b
            dropped_object_ids.append(r.get("_id"))

        same_name_dedup_actions.append({
            "kind": "same_name_merge",
            "name": survivor.get("name"),
            "kept_id": survivor.get("id"),
            "dropped_count": len(dropped_object_ids),
            "merged_fields": merged_fields,
        })
        if apply:
            await db.employees_v2.update_one(
                {"_id": survivor["_id"]},
                {"$set": merged_fields},
            )
            await db.employees_v2.delete_many(
                {"_id": {"$in": dropped_object_ids}}
            )
            refreshed = await db.employees_v2.find_one(
                {"_id": survivor["_id"]}, {"_id": 0}
            )
            if refreshed:
                rows_to_rescore = [r for r in rows_to_rescore
                                   if r.get("id") != survivor["id"]]
                rows_to_rescore.append(refreshed)

    # ----- 3. Rescore touched rows --------------------------------------
    rescore_summary = {"rescored": 0, "skipped": 0}
    if apply and (rows_to_rescore or force_rescore):
        from scoring_engine import EmployeeV2, run_full_scoring, QuarterSettings as QSModel
        qs_doc = await db.quarter_settings.find_one(
            {"quarter": quarter, "year": year}, {"_id": 0}
        )
        if qs_doc:
            try:
                qs_doc.pop("id", None)
                settings = QSModel(**qs_doc)
            except Exception:
                settings = QSModel(quarter=quarter, year=year)
        else:
            settings = QSModel(quarter=quarter, year=year)

        # If force_rescore, replace the queue with EVERY active v2 row in
        # the quarter — guarantees summed metrics flow into scores even
        # if a previous demo-prep run already consolidated rows but
        # skipped rescoring.
        if force_rescore:
            rows_to_rescore = await db.employees_v2.find(
                {"quarter": quarter, "year": year},
                {"_id": 0},
            ).to_list(2000)

        # Legacy field bridge — `rt_mentions` is the historical column
        # populated by the Review Tracker upload pipeline, but the scoring
        # engine reads `review_mentions`. When `review_mentions` is empty
        # and `rt_mentions` carries a value, copy across so RT bonus
        # computes correctly. Same idea for guest_count → guests.
        for r in rows_to_rescore:
            rm = r.get("review_mentions") or 0
            rt = r.get("rt_mentions") or 0
            if (not rm) and rt:
                r["review_mentions"] = int(rt)
            g = r.get("guests") or 0
            gc = r.get("guest_count") or 0
            if (not g) and gc:
                r["guests"] = float(gc)

        emp_models: List[EmployeeV2] = []
        for r in rows_to_rescore:
            try:
                emp_models.append(EmployeeV2(**{
                    k: v for k, v in r.items()
                    if k in EmployeeV2.model_fields
                }))
            except Exception as e:
                logger.warning(f"demo-prep: rescore skipped {r.get('name')}: {e}")
                rescore_summary["skipped"] += 1
        scored = run_full_scoring(emp_models, settings)
        for emp in scored:
            await db.employees_v2.update_one(
                {"id": emp.id},
                {"$set": emp.model_dump(exclude_none=True)},
            )
            rescore_summary["rescored"] += 1

    # ----- 4. Resync current snapshot -----------------------------------
    snapshot_synced = {"attempted": False, "ok": False, "snapshot_id": None}
    if apply and resync_snapshot:
        snap = await db.snapshot_workflow.find_one(
            {"quarter": quarter, "year": year, "is_current": True},
            {"_id": 0, "id": 1, "status": 1},
        )
        if snap and snap.get("status") != "finalized":
            snapshot_synced["attempted"] = True
            snapshot_synced["snapshot_id"] = snap["id"]
            try:
                # Re-import here to avoid circular import at module load.
                from services.employee_service import EmployeeService
                # Pull every active v2 row for the quarter and overwrite
                # the snapshot's employees[] array. Keep the existing rows[]
                # frame structure untouched (it's the FK ledger), but
                # immediately resync its frozen_metrics from the freshly
                # updated employees[] so the dashboard's FK-hydrated
                # reads don't drift.
                v2_active = await db.employees_v2.find(
                    {"quarter": quarter, "year": year},
                    {"_id": 0},
                ).to_list(2000)
                await db.snapshot_workflow.update_one(
                    {"id": snap["id"]},
                    {"$set": {
                        "employees": v2_active,
                        "employee_count": len(v2_active),
                        "last_save_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                # Resync rows[].frozen_metrics from the new employees[]
                # — `_sync_snapshot_rows_from_employees` lives further
                # down in this file and is the same helper used by the
                # `/sync-snapshot-rows` endpoint.
                refreshed_snap = await db.snapshot_workflow.find_one(
                    {"id": snap["id"]}
                )
                if refreshed_snap and refreshed_snap.get("status") != "finalized":
                    sync_summary = await _sync_snapshot_rows_from_employees(
                        db, refreshed_snap
                    )
                    if sync_summary["rows_changed"] > 0:
                        await db.snapshot_workflow.update_one(
                            {"_id": refreshed_snap["_id"]},
                            {"$set": {
                                "rows": sync_summary["new_rows"],
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }},
                        )
                        snapshot_synced["rows_resynced"] = sync_summary["rows_changed"]
                snapshot_synced["ok"] = True
                snapshot_synced["employee_count"] = len(v2_active)
            except Exception as e:
                logger.warning(f"demo-prep: snapshot resync failed: {e}")
                snapshot_synced["error"] = str(e)

    return {
        "success": True,
        "dry_run": not apply,
        "quarter": quarter,
        "year": year,
        "display_name_fixes": display_fixes,
        "v2_dedup_actions": dedup_actions,
        "same_name_dedup_actions": same_name_dedup_actions,
        "rescore": rescore_summary,
        "snapshot": snapshot_synced,
    }



# ---------------------------------------------------------------------------
# Scoring Example — server-side worked example for /scoring-guide
# ---------------------------------------------------------------------------
# Runs a synthetic EmployeeV2 through the canonical scoring engine and
# returns the line-by-line breakdown. The /scoring-guide page renders
# this response with zero math — guaranteeing the doc cannot drift from
# the code, since the code IS the doc.
# ---------------------------------------------------------------------------


@admin_router.get("/scoring-example")
async def scoring_example(
    quarter: str = "Q2",
    year: int = 2026,
    ppa_pct: float = 115.0,
    lsc_pct: float = 110.0,
    lbw_pct: float = 95.0,
    glass_pct: float = 104.0,
    nps: float = 80.0,
    promoters: int = 20,
    detractors: int = 2,
    mentions: int = 25,
):
    """
    Compute a worked example through the canonical scoring engine.

    Accepts per-metric percentage scores (0-120+), NPS, promoter/
    detractor counts, and RT mention count. Returns the live breakdown
    and grand total — every number produced by the same building-block
    functions the production scorer uses (`calculate_customer_voice_score`,
    `calculate_review_tracker_bonus`, `calculate_bonus_points`,
    `calculate_total_score`).
    """
    from scoring_engine import (
        EmployeeV2,
        QuarterSettings,
        calculate_customer_voice_score,
        calculate_review_tracker_bonus,
        calculate_bonus_points,
        calculate_total_score,
        CV_PROMOTER_POINTS,
        CV_DETRACTOR_POINTS,
    )

    db = get_db()
    qs_doc = await db.quarter_settings.find_one(
        {"quarter": quarter.upper(), "year": year}, {"_id": 0}
    )
    qs_doc = qs_doc or {}
    qs_doc.pop("id", None)
    try:
        settings = QuarterSettings(**qs_doc)
    except Exception:
        settings = QuarterSettings(quarter=quarter.upper(), year=year)

    emp = EmployeeV2(
        name="Worked Example",
        score_ppa=ppa_pct,
        score_lsc=lsc_pct,
        score_lbw=lbw_pct,
        score_glass=glass_pct,
        nps_score=nps,
        cv_promoters=promoters,
        cv_detractors=detractors,
        review_mentions=mentions,
    )

    # Engine pipeline — same building blocks the production scorer
    # invokes inside run_full_scoring().
    calculate_customer_voice_score(emp)
    calculate_review_tracker_bonus(emp, settings)
    calculate_bonus_points(emp, settings)
    calculate_total_score(emp, settings)

    # Per-metric weighted contributions (post-cap) so the doc can show
    # each line with its actual point value.
    cap = lambda v: min(v, 100)  # noqa: E731 — local lambda for clarity
    contributions = {
        "ppa":   round(cap(ppa_pct)   * settings.weight_ppa,   2),
        "lsc":   round(cap(lsc_pct)   * settings.weight_lsc,   2),
        "lbw":   round(cap(lbw_pct)   * settings.weight_lbw,   2),
        "glass": round(cap(glass_pct) * settings.weight_glass, 2),
    }

    return {
        "inputs": {
            "ppa_pct": ppa_pct,
            "lsc_pct": lsc_pct,
            "lbw_pct": lbw_pct,
            "glass_pct": glass_pct,
            "nps": nps,
            "promoters": promoters,
            "detractors": detractors,
            "mentions": mentions,
        },
        "settings": {
            "quarter": settings.quarter,
            "year": settings.year,
            "weight_ppa": settings.weight_ppa,
            "weight_lsc": settings.weight_lsc,
            "weight_lbw": settings.weight_lbw,
            "weight_glass": settings.weight_glass,
            "rt_points_per_mention": settings.rt_points_per_mention,
            "rt_max_points": settings.rt_max_points,
            "cv_promoter_points": CV_PROMOTER_POINTS,
            "cv_detractor_points": abs(CV_DETRACTOR_POINTS),
            "bonus_rate": settings.bonus_rate,
            "bonus_cap": settings.bonus_cap,
        },
        "breakdown": {
            "weighted_pos_contributions": contributions,
            "weighted_pos_subtotal": emp.weighted_score,
            "metric_bonuses": {
                "ppa":   emp.bonus_ppa or 0,
                "lsc":   emp.bonus_lsc or 0,
                "lbw":   emp.bonus_lbw or 0,
                "glass": emp.bonus_glass or 0,
                "total": emp.total_metric_bonus or 0,
            },
            "customer_voice": {
                "nps_contribution": emp.nps_contribution or 0,
                "promoter_detractor_net": emp.cv_raw_points or 0,
                "total": emp.cv_score or 0,
            },
            "review_tracker": {
                "mentions": mentions,
                "raw": round(mentions * settings.rt_points_per_mention, 2),
                "capped": emp.review_tracker_bonus or 0,
                "cap": settings.rt_max_points,
            },
        },
        "total_score": emp.total_score,
        "pre_dar_score": emp.pre_dar_score,
    }



# ---------------------------------------------------------------------------
# Sync snapshot.rows[] from snapshot.employees[]
# ---------------------------------------------------------------------------
# The snapshot stores two views of the same employees: `rows[]` (the FK
# ledger with `frozen_metrics`) and `employees[]` (the legacy blob).
# Hydration prefers `rows[]`. Several write paths (demo-prep,
# bulk-merge, manual employee delete) update only `employees[]` and
# leave `rows[]` stale — that drift surfaces on the dashboard as
# silently wrong PPA/LSC/total numbers.
#
# This endpoint rebuilds `rows[].frozen_metrics` (+ frozen_score/tier/
# rank) from the current `employees[]` content for every active
# non-finalized snapshot. Finalized snapshots are intentionally
# skipped — they are immutable history.
# ---------------------------------------------------------------------------


async def _sync_snapshot_rows_from_employees(db, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rewrite `rows[].frozen_metrics` to match the corresponding
    employees[] entry by canonical id. Returns a per-row diff summary.

    Caller is responsible for status/finalized guard — this helper
    assumes the snapshot is editable.
    """
    emps = snapshot.get("employees") or []
    rows = snapshot.get("rows") or []

    # Index employees[] by every key the FK ledger might use.
    emps_by_id: Dict[str, Dict[str, Any]] = {}
    emps_by_name: Dict[str, Dict[str, Any]] = {}
    for e in emps:
        eid = e.get("id")
        if eid:
            emps_by_id[eid] = e
        for n in (e.get("name"), e.get("display_name"), e.get("report_name")):
            if n:
                emps_by_name.setdefault(n.strip().lower(), e)

    # Build canonical id resolver so a row whose `employee_id` is a
    # canonical id can still locate an `employees[]` blob stored under
    # a legacy_id (or vice versa).
    canonical_resolver: Dict[str, str] = {}
    async for c in db.employees.find({}, {"_id": 0, "id": 1, "legacy_ids": 1}):
        cid = c.get("id")
        if not cid:
            continue
        canonical_resolver[cid] = cid
        for lid in (c.get("legacy_ids") or []):
            canonical_resolver[lid] = cid

    diffs: List[Dict[str, Any]] = []
    new_rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        eid = row.get("employee_id") or ""
        # Find matching employees[] blob — try id, canonical id, then names.
        emp = (
            emps_by_id.get(eid)
            or emps_by_id.get(canonical_resolver.get(eid, ""))
            or emps_by_name.get((row.get("frozen_display_name") or "").strip().lower())
            or emps_by_name.get((row.get("frozen_report_name")  or "").strip().lower())
        )
        if not emp:
            # No match — leave the row untouched so we don't accidentally
            # wipe an active server who only exists in rows[].
            new_rows.append(row)
            continue

        before_fm = row.get("frozen_metrics") or {}
        new_fm = {k: v for k, v in emp.items()
                  if k not in ("id", "name", "display_name", "report_name",
                               "aliases")}

        # Track which keys actually changed to surface in diff.
        changed = []
        for k in (
            "ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc",
            "lsc_count", "guests", "guest_count", "net_sales", "lbw",
            "loyalty_sales", "score_ppa", "score_lbw", "score_glass",
            "score_lsc", "total_score", "weighted_score", "pre_dar_score",
            "tier_label",
        ):
            a = before_fm.get(k)
            b = new_fm.get(k)
            if a != b:
                changed.append({"field": k, "from": a, "to": b})
        if changed:
            diffs.append({
                "employee_id": eid,
                "name": row.get("frozen_display_name"),
                "changes": changed,
            })

        new_rows.append({
            **row,
            "employee_id": emp.get("id") or eid,
            "frozen_display_name": emp.get("display_name") or emp.get("name") or row.get("frozen_display_name"),
            "frozen_report_name":  emp.get("report_name")  or emp.get("name") or row.get("frozen_report_name"),
            "frozen_metrics": new_fm,
            "frozen_score":   emp.get("total_score", row.get("frozen_score")),
            "frozen_tier":    emp.get("tier_label") or emp.get("performance_tier") or row.get("frozen_tier"),
            "frozen_rank":    emp.get("tier_rank") or emp.get("peer_rank") or row.get("frozen_rank"),
            "recorded_at":    now if changed else row.get("recorded_at"),
        })

    return {
        "row_count": len(rows),
        "rows_changed": len(diffs),
        "diffs": diffs,
        "new_rows": new_rows,
    }


@admin_router.post("/sync-snapshot-rows")
async def sync_snapshot_rows(
    apply: bool = False,
    snapshot_id: Optional[str] = None,
    include_completed: bool = False,
):
    """
    Resync `snapshot.rows[].frozen_metrics` from `snapshot.employees[]`
    for non-finalized snapshots. Default scope is `in_progress` ONLY —
    pass `include_completed=true` to also touch `completed`/`reviewed`
    snapshots (intentionally opt-in because the direction of truth on
    historical snapshots is ambiguous: a corrupted employees[] blob can
    legitimately disagree with a correct rows[] ledger).

    Finalized snapshots are always skipped.

    Returns a per-snapshot diff so the caller can sanity-check what
    would change. Default is dry-run; pass `?apply=true` to persist.
    """
    db = get_db()

    if snapshot_id:
        query: Dict[str, Any] = {"id": snapshot_id}
    elif include_completed:
        query = {"status": {"$nin": ["finalized"]}}
    else:
        query = {"status": "in_progress"}

    snapshots = await db.snapshot_workflow.find(query).to_list(200)
    if snapshot_id and not snapshots:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    results: List[Dict[str, Any]] = []
    total_rows_changed = 0
    snapshots_touched = 0

    for snap in snapshots:
        if snap.get("status") == "finalized":
            continue
        summary = await _sync_snapshot_rows_from_employees(db, snap)
        snap_result = {
            "snapshot_id": snap.get("id"),
            "name": snap.get("name"),
            "quarter": snap.get("quarter"),
            "year": snap.get("year"),
            "status": snap.get("status"),
            "row_count": summary["row_count"],
            "rows_changed": summary["rows_changed"],
            "diffs": summary["diffs"],
        }
        results.append(snap_result)

        if summary["rows_changed"] > 0:
            snapshots_touched += 1
            total_rows_changed += summary["rows_changed"]
            if apply:
                await db.snapshot_workflow.update_one(
                    {"_id": snap["_id"]},
                    {"$set": {
                        "rows": summary["new_rows"],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                logger.info(
                    f"sync-snapshot-rows: synced {summary['rows_changed']} rows on {snap.get('name')}"
                )

    return {
        "success": True,
        "dry_run": not apply,
        "snapshots_scanned": len(results),
        "snapshots_touched": snapshots_touched,
        "total_rows_changed": total_rows_changed,
        "results": results,
    }



# ---------------------------------------------------------------------------
# Data Reconciliation — Manual override queue for canonical-vs-snapshot drift
# ---------------------------------------------------------------------------
# Surfaces every conflict that `/scoring-trust` flags as a card the
# operator must individually adjudicate. ZERO auto-resolution. ZERO
# batch endpoint. Every resolution writes to an append-only audit log.
# ---------------------------------------------------------------------------

from fastapi import Depends  # noqa: E402 — appended after admin_router exists
from routes.auth import require_admin  # noqa: E402


class ReconcilePayload(BaseModel):
    """Single-card resolution payload. The frontend must POST one of
    these per card — there is no bulk endpoint."""
    conflict_id: str = Field(..., min_length=1)
    action: str = Field(
        ...,
        description="keep_stored | accept_snapshot | manual_override | defer | revoke_alias",
    )
    value_override: Optional[float] = Field(
        default=None,
        description="Required when action == 'manual_override'. Operator-typed value.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Optional free-text note saved to the audit log.",
    )


@admin_router.get("/reconciliation/queue")
async def reconciliation_queue():
    """Return the active + deferred reconciliation queue, sorted so
    the worst drift sits at the top."""
    from services.reconciliation_service import ReconciliationService
    svc = ReconciliationService(get_db())
    return await svc.queue()


@admin_router.post("/reconciliation/resolve")
async def reconciliation_resolve(
    payload: ReconcilePayload,
    user=Depends(require_admin),
):
    """Apply one resolution. Logs the before/after to the audit
    collection. Never auto-resolves anything else, never batches."""
    from services.reconciliation_service import ReconciliationService
    svc = ReconciliationService(get_db())
    try:
        return await svc.resolve(
            conflict_id=payload.conflict_id,
            action=payload.action,
            actor=getattr(user, "email", None) or "unknown",
            value_override=payload.value_override,
            reason=payload.reason,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.get("/reconciliation/audit")
async def reconciliation_audit(limit: int = 100):
    """Tail of the append-only resolution log."""
    from services.reconciliation_service import ReconciliationService
    svc = ReconciliationService(get_db())
    return {"entries": await svc.audit_log(limit=limit)}
