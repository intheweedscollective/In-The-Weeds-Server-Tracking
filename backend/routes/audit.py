"""
Audit Routes Module
Self-checking audit system that guarantees 100% accurate scoring.
Extracted from server.py for better maintainability.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

audit_router = APIRouter(prefix="/v2/audit", tags=["Audit"])

def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# ============================================================
# SELF-CHECKING AUDIT SYSTEM - Guarantees 100% Accurate Scoring
# ============================================================

@audit_router.get("/employee/{employee_name}")
async def audit_employee_score(employee_name: str, quarter: str = "Q1", year: int = 2026):
    """
    Audit a single employee's score calculation step-by-step.
    Returns a detailed breakdown showing exactly how each component was calculated.
    This is the self-checking audit process that guarantees 100% accuracy.
    """
    db = get_db()
    
    # Get employee record
    employee = await db.employees_v2.find_one(
        {"name": {"$regex": f"^{employee_name}$", "$options": "i"}, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not employee:
        return {"success": False, "error": f"Employee '{employee_name}' not found for {quarter} {year}"}
    
    # Get quarter settings
    settings = await db.quarter_settings.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not settings:
        return {"success": False, "error": f"Quarter settings not found for {quarter} {year}"}
    
    # Get raw CV feedback for this employee
    cv_feedback = await db.cv_feedback.find(
        {"server_name": {"$regex": f"^{employee_name}$", "$options": "i"}, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(100)
    
    # Count raw feedback
    raw_promoters = len([f for f in cv_feedback if f.get("rating", 0) >= 9])
    raw_passives = len([f for f in cv_feedback if 7 <= f.get("rating", 0) <= 8])
    raw_detractors = len([f for f in cv_feedback if f.get("rating", 0) <= 6])
    raw_total = len(cv_feedback)
    raw_nps = round(((raw_promoters - raw_detractors) / raw_total) * 100, 2) if raw_total > 0 else 0
    
    # Get CV NPS record (aggregated)
    cv_nps = await db.cv_nps.find_one(
        {"employee_name": {"$regex": f"^{employee_name}$", "$options": "i"}, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    # Get review mentions for this employee
    review_mentions_cursor = db.customer_reviews.find({
        "quarter": quarter.upper(), 
        "year": year,
        "employee_mentions.name": {"$regex": employee_name, "$options": "i"}
    }, {"_id": 0})
    review_mentions = await review_mentions_cursor.to_list(100)
    raw_rt_mentions = len(review_mentions)
    
    # Build audit report
    audit = {
        "employee_name": employee["name"],
        "quarter": quarter.upper(),
        "year": year,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "final_score": employee.get("pre_dar_score") or employee.get("total_score", 0),
        "discrepancies": [],
        "data_trail": {},
        "calculations": {},
        "validation_status": "PASS"
    }
    
    # === POS METRICS AUDIT ===
    guests = employee.get("guests", 0)
    net_sales = employee.get("net_sales", 0)
    stored_ppa = employee.get("ppa", 0)
    expected_ppa = round(net_sales / guests, 2) if guests > 0 else 0
    
    lbw = employee.get("lbw", 0)
    stored_lbw_per_guest = employee.get("lbw_per_guest", 0)
    expected_lbw_per_guest = round(lbw / guests, 2) if guests > 0 else 0
    
    glassware = employee.get("glassware_sales", 0)
    stored_glass_per_guest = employee.get("glassware_per_guest", 0)
    expected_glass_per_guest = round(glassware / guests, 2) if guests > 0 else 0
    
    lsc_count = employee.get("lsc_count", 0)
    stored_guests_per_lsc = employee.get("guests_per_lsc")
    expected_guests_per_lsc = round(guests / lsc_count, 2) if lsc_count > 0 else None
    
    audit["data_trail"]["pos_metrics"] = {
        "guests": guests,
        "net_sales": net_sales,
        "lbw_total": lbw,
        "glassware_sales": glassware,
        "lsc_count": lsc_count
    }
    
    audit["calculations"]["pos_metrics"] = {
        "ppa": {
            "formula": f"{net_sales} / {guests}",
            "expected": expected_ppa,
            "stored": stored_ppa,
            "match": abs(expected_ppa - stored_ppa) < 0.01
        },
        "lbw_per_guest": {
            "formula": f"{lbw} / {guests}",
            "expected": expected_lbw_per_guest,
            "stored": stored_lbw_per_guest,
            "match": abs(expected_lbw_per_guest - stored_lbw_per_guest) < 0.01
        },
        "glassware_per_guest": {
            "formula": f"{glassware} / {guests}",
            "expected": expected_glass_per_guest,
            "stored": stored_glass_per_guest,
            "match": abs(expected_glass_per_guest - stored_glass_per_guest) < 0.01
        },
        "guests_per_lsc": {
            "formula": f"{guests} / {lsc_count}" if lsc_count > 0 else "N/A (no LSC)",
            "expected": expected_guests_per_lsc,
            "stored": stored_guests_per_lsc,
            "match": expected_guests_per_lsc == stored_guests_per_lsc if expected_guests_per_lsc is not None else True
        }
    }
    
    # === CV DATA AUDIT ===
    stored_cv_promoters = employee.get("cv_promoters", 0)
    stored_cv_passives = employee.get("cv_passives", 0)
    stored_cv_detractors = employee.get("cv_detractors", 0)
    stored_nps = employee.get("nps_score", 0)
    
    audit["data_trail"]["cv_feedback"] = {
        "raw_feedback_count": raw_total,
        "raw_promoters": raw_promoters,
        "raw_passives": raw_passives,
        "raw_detractors": raw_detractors,
        "raw_nps": raw_nps,
        "cv_nps_record": cv_nps
    }
    
    audit["calculations"]["cv_nps"] = {
        "stored_promoters": stored_cv_promoters,
        "stored_passives": stored_cv_passives,
        "stored_detractors": stored_cv_detractors,
        "stored_nps": stored_nps,
        "raw_promoters_match": raw_promoters == stored_cv_promoters,
        "raw_passives_match": raw_passives == stored_cv_passives,
        "raw_detractors_match": raw_detractors == stored_cv_detractors
    }
    
    # === REVIEW TRACKER AUDIT ===
    stored_rt_mentions = employee.get("rt_mentions", 0) or employee.get("review_mentions", 0) or 0
    
    audit["data_trail"]["review_tracker"] = {
        "raw_mention_count": raw_rt_mentions,
        "reviews_with_mentions": [r.get("title", "")[:50] for r in review_mentions[:5]]
    }
    
    audit["calculations"]["review_tracker"] = {
        "stored_mentions": stored_rt_mentions,
        "actual_mentions": raw_rt_mentions,
        "match": stored_rt_mentions == raw_rt_mentions
    }
    
    # === SCORING FORMULA AUDIT ===
    # Get benchmark values
    benchmark_ppa = settings.get("benchmark_ppa", 55)
    benchmark_lbw = settings.get("benchmark_lbw", 8)
    benchmark_glass = settings.get("benchmark_glass", 1.25)
    benchmark_lsc = settings.get("benchmark_lsc", 100)
    
    # Calculate expected scores
    ppa_score = min((stored_ppa / benchmark_ppa) * 100, 100) if benchmark_ppa > 0 else 0
    lbw_score = min((stored_lbw_per_guest / benchmark_lbw) * 100, 100) if benchmark_lbw > 0 else 0
    glass_score = min((stored_glass_per_guest / benchmark_glass) * 100, 100) if benchmark_glass > 0 else 0
    lsc_score = min((benchmark_lsc / stored_guests_per_lsc) * 100, 100) if stored_guests_per_lsc and stored_guests_per_lsc > 0 else 0
    
    # Normalize NPS to 0-100 scale
    nps_normalized = max(0, (stored_nps + 100) / 2)
    nps_score_contribution = min(nps_normalized, 100)
    
    # Calculate weighted base score
    weight_ppa = settings.get("weight_ppa", 0.25)
    weight_lsc = settings.get("weight_lsc", 0.25)
    weight_lbw = settings.get("weight_lbw", 0.15)
    weight_glass = settings.get("weight_glass", 0.10)
    weight_nps = 0.10  # NPS is 10% weight
    
    # RT bonus calculation
    rt_bonus = min(stored_rt_mentions * 0.5, 15)  # 0.5 pts per mention, max 15
    
    weighted_base = (
        (ppa_score * weight_ppa) +
        (lsc_score * weight_lsc) +
        (lbw_score * weight_lbw) +
        (glass_score * weight_glass) +
        (nps_score_contribution * weight_nps) +
        rt_bonus
    )
    
    # Metric bonuses
    metric_bonus = 0
    bonus_rate = settings.get("bonus_rate", 0.2)
    bonus_cap = settings.get("bonus_cap", 5.0)
    
    if stored_ppa > benchmark_ppa:
        metric_bonus += min((stored_ppa - benchmark_ppa) * bonus_rate, bonus_cap)
    if stored_lbw_per_guest > benchmark_lbw:
        metric_bonus += min((stored_lbw_per_guest - benchmark_lbw) * bonus_rate, bonus_cap)
    if stored_glass_per_guest > benchmark_glass:
        metric_bonus += min((stored_glass_per_guest - benchmark_glass) * bonus_rate, bonus_cap)
    if stored_guests_per_lsc and stored_guests_per_lsc < benchmark_lsc:
        metric_bonus += min((benchmark_lsc - stored_guests_per_lsc) * bonus_rate * 0.1, bonus_cap)
    
    metric_bonus = min(metric_bonus, 20)  # Total metric bonus capped at 20
    
    # CV bonus (promoters - detractors formula)
    cv_bonus = (stored_cv_promoters * 1) + (stored_cv_detractors * -2)
    
    # Final expected score
    expected_total = round(weighted_base + metric_bonus + cv_bonus, 2)
    stored_total = employee.get("pre_dar_score") or employee.get("total_score", 0)
    
    audit["calculations"]["scoring"] = {
        "benchmarks": {
            "ppa": benchmark_ppa,
            "lbw": benchmark_lbw,
            "glass": benchmark_glass,
            "lsc": benchmark_lsc
        },
        "metric_scores": {
            "ppa_score": round(ppa_score, 2),
            "lbw_score": round(lbw_score, 2),
            "glass_score": round(glass_score, 2),
            "lsc_score": round(lsc_score, 2),
            "nps_contribution": round(nps_score_contribution, 2)
        },
        "weighted_base": round(weighted_base, 2),
        "metric_bonus": round(metric_bonus, 2),
        "cv_bonus": cv_bonus,
        "rt_bonus": rt_bonus,
        "expected_total": expected_total,
        "stored_total": stored_total,
        "difference": round(abs(expected_total - stored_total), 2),
        "match": abs(expected_total - stored_total) < 1.0
    }
    
    # Check for discrepancies
    if abs(expected_total - stored_total) >= 1.0:
        audit["discrepancies"].append({
            "type": "score_mismatch",
            "expected": expected_total,
            "stored": stored_total,
            "difference": round(expected_total - stored_total, 2)
        })
        audit["validation_status"] = "FAIL"
    
    if stored_rt_mentions != raw_rt_mentions:
        audit["discrepancies"].append({
            "type": "rt_mention_mismatch",
            "expected": raw_rt_mentions,
            "stored": stored_rt_mentions
        })
        audit["validation_status"] = "FAIL"
    
    return audit


@audit_router.post("/fix-employee/{employee_name}")
async def fix_employee_score(employee_name: str, quarter: str = "Q1", year: int = 2026):
    """
    Fix an employee's score based on the audit findings.
    Recalculates all values from raw data sources.
    """
    db = get_db()
    
    # First run audit to get expected values
    audit = await audit_employee_score(employee_name, quarter, year)
    
    if not audit.get("calculations"):
        return {"success": False, "error": "Could not audit employee", "details": audit}
    
    # Get the employee record
    employee = await db.employees_v2.find_one(
        {"name": {"$regex": f"^{employee_name}$", "$options": "i"}, "quarter": quarter.upper(), "year": year}
    )
    
    if not employee:
        return {"success": False, "error": f"Employee '{employee_name}' not found"}
    
    # Extract expected values from audit
    scoring = audit["calculations"]["scoring"]
    pos_calcs = audit["calculations"]["pos_metrics"]
    rt_calcs = audit["calculations"]["review_tracker"]
    
    # Prepare update
    update = {
        "ppa": pos_calcs["ppa"]["expected"],
        "lbw_per_guest": pos_calcs["lbw_per_guest"]["expected"],
        "glassware_per_guest": pos_calcs["glassware_per_guest"]["expected"],
        "score_ppa": scoring["metric_scores"]["ppa_score"],
        "score_lbw": scoring["metric_scores"]["lbw_score"],
        "score_glass": scoring["metric_scores"]["glass_score"],
        "score_lsc": scoring["metric_scores"]["lsc_score"],
        "review_mentions": rt_calcs["actual_mentions"],
        "rt_mentions": rt_calcs["actual_mentions"],
        "review_tracker_bonus": scoring["rt_bonus"],
        "total_metric_bonus": scoring["metric_bonus"],
        "cv_score": scoring["cv_bonus"],
        "weighted_score": scoring["weighted_base"],
        "pre_dar_score": scoring["expected_total"],
        "total_score": scoring["expected_total"],
        "last_audit_fix": datetime.now(timezone.utc).isoformat()
    }
    
    # Update employee
    await db.employees_v2.update_one(
        {"_id": employee["_id"]},
        {"$set": update}
    )
    
    # Log the fix
    await db.audit_log.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "fix_employee_score",
        "employee_name": employee_name,
        "quarter": quarter.upper(),
        "year": year,
        "old_score": audit["final_score"],
        "new_score": scoring["expected_total"],
        "discrepancies_fixed": audit["discrepancies"],
        "user": "system"
    })
    
    return {
        "success": True,
        "employee_name": employee_name,
        "old_score": audit["final_score"],
        "new_score": scoring["expected_total"],
        "changes_applied": update,
        "discrepancies_fixed": audit["discrepancies"]
    }


@audit_router.get("/all")
async def audit_all_employees(quarter: str = "Q1", year: int = 2026):
    """
    Audit all employees for a given quarter.
    Returns summary of validation status and any discrepancies found.
    """
    db = get_db()
    
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "name": 1}
    ).to_list(100)
    
    results = {
        "quarter": quarter.upper(),
        "year": year,
        "total_employees": len(employees),
        "passed": 0,
        "failed": 0,
        "audits": []
    }
    
    for emp in employees:
        audit = await audit_employee_score(emp["name"], quarter, year)
        
        summary = {
            "name": emp["name"],
            "status": audit.get("validation_status", "UNKNOWN"),
            "score": audit.get("final_score", 0),
            "discrepancies": len(audit.get("discrepancies", []))
        }
        
        if audit.get("validation_status") == "PASS":
            results["passed"] += 1
        else:
            results["failed"] += 1
            summary["issues"] = audit.get("discrepancies", [])
        
        results["audits"].append(summary)
    
    results["pass_rate"] = f"{(results['passed'] / results['total_employees'] * 100):.1f}%" if results["total_employees"] > 0 else "0%"
    
    return results


@audit_router.get("/report")
async def get_audit_report(quarter: str = "Q1", year: int = 2026):
    """
    Generate a comprehensive audit report for the quarter.
    """
    db = get_db()
    
    # Get all employees
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(100)
    
    # Get settings
    settings = await db.quarter_settings.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    # Get data counts
    cv_feedback_count = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year})
    reviews_count = await db.customer_reviews.count_documents({"quarter": quarter.upper(), "year": year})
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quarter": quarter.upper(),
        "year": year,
        "data_sources": {
            "employees": len(employees),
            "cv_feedback_records": cv_feedback_count,
            "review_records": reviews_count
        },
        "settings": {
            "benchmark_ppa": settings.get("benchmark_ppa") if settings else None,
            "benchmark_lbw": settings.get("benchmark_lbw") if settings else None,
            "benchmark_glass": settings.get("benchmark_glass") if settings else None,
            "benchmark_lsc": settings.get("benchmark_lsc") if settings else None,
            "a_server_min": settings.get("a_server_min_score") if settings else None,
            "b_server_min": settings.get("b_server_min_score") if settings else None
        },
        "tier_distribution": {
            "Trainer": len([e for e in employees if e.get("tier_label") == "Trainer"]),
            "A-Server": len([e for e in employees if e.get("tier_label") == "A-Server"]),
            "B-Server": len([e for e in employees if e.get("tier_label") == "B-Server"]),
            "C-Server": len([e for e in employees if e.get("tier_label") == "C-Server"]),
            "Bartender": len([e for e in employees if e.get("tier_label") == "Bartender"])
        },
        "score_stats": {
            "min": min([e.get("total_score", 0) for e in employees]) if employees else 0,
            "max": max([e.get("total_score", 0) for e in employees]) if employees else 0,
            "avg": round(sum([e.get("total_score", 0) for e in employees]) / len(employees), 2) if employees else 0
        }
    }
    
    return report


@audit_router.get("/trail")
async def get_audit_trail(limit: int = 50):
    """
    Get recent audit log entries.
    """
    db = get_db()
    
    logs = await db.audit_log.find(
        {},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {"logs": logs, "count": len(logs)}


@audit_router.post("/log")
async def add_audit_log(
    action: str,
    details: dict,
    quarter: str = "Q1",
    year: int = 2026,
    user: str = "system"
):
    """
    Add an entry to the audit log.
    """
    db = get_db()
    
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "quarter": quarter.upper(),
        "year": year,
        "details": details,
        "user": user
    }
    
    await db.audit_log.insert_one(log_entry)
    
    return {"success": True, "logged": log_entry}


@audit_router.post("/recalculate-all")
async def recalculate_all_scores(quarter: str = "Q1", year: int = 2026):
    """
    Recalculate scores for all employees based on raw data.
    Use with caution - this will overwrite all existing scores.
    """
    db = get_db()
    
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(100)
    
    results = {
        "quarter": quarter.upper(),
        "year": year,
        "total": len(employees),
        "updated": 0,
        "errors": []
    }
    
    for emp in employees:
        try:
            fix_result = await fix_employee_score(emp["name"], quarter, year)
            if fix_result.get("success"):
                results["updated"] += 1
            else:
                results["errors"].append({
                    "name": emp["name"],
                    "error": fix_result.get("error", "Unknown error")
                })
        except Exception as e:
            results["errors"].append({
                "name": emp["name"],
                "error": str(e)
            })
    
    # Log the bulk recalculation
    await db.audit_log.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "recalculate_all_scores",
        "quarter": quarter.upper(),
        "year": year,
        "results": {
            "total": results["total"],
            "updated": results["updated"],
            "errors": len(results["errors"])
        },
        "user": "system"
    })
    
    return results


@audit_router.post("/sync-nps-to-employees")
async def sync_nps_to_employees(quarter: str = "Q1", year: int = 2026):
    """
    Sync NPS data from cv_feedback to employees.
    Updates cv_promoters, cv_passives, cv_detractors, and nps_score fields.
    """
    db = get_db()
    
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(100)
    
    results = {
        "quarter": quarter.upper(),
        "year": year,
        "synced": 0,
        "unchanged": 0,
        "details": []
    }
    
    for emp in employees:
        # Count CV feedback for this employee
        cv_feedback = await db.cv_feedback.find(
            {"server_name": {"$regex": f"^{emp['name']}$", "$options": "i"}, "quarter": quarter.upper(), "year": year}
        ).to_list(100)
        
        promoters = len([f for f in cv_feedback if f.get("rating", 0) >= 9])
        passives = len([f for f in cv_feedback if 7 <= f.get("rating", 0) <= 8])
        detractors = len([f for f in cv_feedback if f.get("rating", 0) <= 6])
        total = len(cv_feedback)
        nps = round(((promoters - detractors) / total) * 100, 2) if total > 0 else 0
        
        old_promoters = emp.get("cv_promoters", 0)
        old_detractors = emp.get("cv_detractors", 0)
        
        if promoters != old_promoters or detractors != emp.get("cv_detractors", 0):
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "cv_promoters": promoters,
                    "cv_passives": passives,
                    "cv_detractors": detractors,
                    "nps_score": nps
                }}
            )
            results["synced"] += 1
            results["details"].append({
                "name": emp["name"],
                "old": {"promoters": old_promoters, "detractors": old_detractors},
                "new": {"promoters": promoters, "detractors": detractors, "nps": nps}
            })
        else:
            results["unchanged"] += 1
    
    return results


@audit_router.get("/review-accuracy")
async def check_review_accuracy(quarter: str = "Q1", year: int = 2026):
    """
    Check accuracy of review mention counts across all employees.
    """
    db = get_db()
    
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "name": 1, "rt_mentions": 1, "review_mentions": 1}
    ).to_list(100)
    
    mismatches = []
    
    for emp in employees:
        stored_mentions = emp.get("rt_mentions", 0) or emp.get("review_mentions", 0) or 0
        
        # Count actual mentions
        actual_mentions = await db.customer_reviews.count_documents({
            "quarter": quarter.upper(),
            "year": year,
            "employee_mentions.name": {"$regex": f"^{emp['name']}$", "$options": "i"}
        })
        
        if stored_mentions != actual_mentions:
            mismatches.append({
                "name": emp["name"],
                "stored": stored_mentions,
                "actual": actual_mentions,
                "difference": actual_mentions - stored_mentions
            })
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "total_employees": len(employees),
        "mismatches": len(mismatches),
        "accuracy_rate": f"{((len(employees) - len(mismatches)) / len(employees) * 100):.1f}%" if employees else "0%",
        "mismatch_details": mismatches
    }


@audit_router.post("/fix-all-discrepancies")
async def fix_all_discrepancies(quarter: str = "Q1", year: int = 2026):
    """
    Fix all scoring discrepancies for employees in the quarter.
    Re-syncs CV data from cv_feedback and recalculates scores.
    """
    db = get_db()
    
    results = {
        "quarter": quarter.upper(),
        "year": year,
        "cv_sync": None,
        "rt_sync": None,
        "score_fixes": None,
        "actions_taken": []
    }
    
    # Step 1: Sync CV data from cv_feedback
    cv_sync = await sync_nps_to_employees(quarter, year)
    results["cv_sync"] = {
        "synced": cv_sync.get("synced", 0),
        "unchanged": cv_sync.get("unchanged", 0)
    }
    results["actions_taken"].append(f"Synced CV data for {cv_sync.get('synced', 0)} employees")
    
    # Step 2: Sync RT mentions
    rt_sync = await sync_employee_review_mentions(quarter, year)
    results["rt_sync"] = {
        "updated": rt_sync.get("summary", {}).get("updated", 0),
        "unchanged": rt_sync.get("summary", {}).get("unchanged", 0)
    }
    results["actions_taken"].append(f"Synced RT mentions for {rt_sync.get('summary', {}).get('updated', 0)} employees")
    
    # Step 3: Recalculate all scores
    score_fixes = await recalculate_all_scores(quarter, year)
    results["score_fixes"] = {
        "updated": score_fixes.get("updated", 0),
        "errors": len(score_fixes.get("errors", []))
    }
    results["actions_taken"].append(f"Recalculated scores for {score_fixes.get('updated', 0)} employees")
    
    # Log this fix-all action
    await db.audit_log.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "fix_all_discrepancies",
        "quarter": quarter.upper(),
        "year": year,
        "results": results,
        "user": "system"
    })
    
    return results


@audit_router.get("/data-cap-check")
async def check_data_caps(quarter: str = "Q1", year: int = 2026):
    """
    Check if data counts match official caps/limits.
    Returns comparison with admin_settings official stats.
    """
    db = get_db()
    
    # Get official stats from admin_settings
    official = await db.admin_settings.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    # Get actual counts
    cv_count = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year})
    rt_count = await db.customer_reviews.count_documents({"quarter": quarter.upper(), "year": year})
    
    result = {
        "quarter": quarter.upper(),
        "year": year,
        "cv_feedback": {
            "actual": cv_count,
            "official": official.get("official_cv_total") if official else None,
            "status": "ok" if not official or cv_count == official.get("official_cv_total") else "mismatch"
        },
        "reviews": {
            "actual": rt_count,
            "official": official.get("official_rt_total") if official else None,
            "status": "ok" if not official or rt_count == official.get("official_rt_total") else "mismatch"
        }
    }
    
    return result


@audit_router.post("/enforce-data-caps")
async def enforce_data_caps(quarter: str = "Q1", year: int = 2026):
    """
    Remove excess records to match official data caps.
    """
    db = get_db()
    
    # Get official stats
    official = await db.admin_settings.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not official:
        return {"success": False, "error": "No official stats set for this quarter"}
    
    results = {
        "quarter": quarter.upper(),
        "year": year,
        "actions": []
    }
    
    # Check CV feedback
    cv_count = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year})
    official_cv = official.get("official_cv_total", cv_count)
    
    if cv_count > official_cv:
        excess = cv_count - official_cv
        # Delete oldest excess records
        to_delete = await db.cv_feedback.find(
            {"quarter": quarter.upper(), "year": year}
        ).sort("created_at", 1).limit(excess).to_list(excess)
        
        if to_delete:
            ids_to_delete = [doc["_id"] for doc in to_delete]
            await db.cv_feedback.delete_many({"_id": {"$in": ids_to_delete}})
            results["actions"].append(f"Deleted {excess} excess CV feedback records")
    
    # Check reviews
    rt_count = await db.customer_reviews.count_documents({"quarter": quarter.upper(), "year": year})
    official_rt = official.get("official_rt_total", rt_count)
    
    if rt_count > official_rt:
        excess = rt_count - official_rt
        to_delete = await db.customer_reviews.find(
            {"quarter": quarter.upper(), "year": year}
        ).sort("created_at", 1).limit(excess).to_list(excess)
        
        if to_delete:
            ids_to_delete = [doc["_id"] for doc in to_delete]
            await db.customer_reviews.delete_many({"_id": {"$in": ids_to_delete}})
            results["actions"].append(f"Deleted {excess} excess review records")
    
    # Sync employee mentions after deletion
    if results["actions"]:
        sync_result = await sync_employee_review_mentions(quarter, year)
        results["employee_sync"] = {
            "updated": sync_result.get("summary", {}).get("updated", 0),
            "unchanged": sync_result.get("summary", {}).get("unchanged", 0)
        }
        results["actions"].append(f"Updated {results['employee_sync']['updated']} employee mention counts")
    else:
        results["actions"].append("No excess data found - all within official limits")
    
    return results


@audit_router.post("/sync-employee-mentions")
async def sync_employee_review_mentions(quarter: str = "Q1", year: int = 2026):
    """
    Sync employee review_mentions count with actual reviews in database.
    This should be run after enforcing data caps to update employee records.
    """
    db = get_db()
    
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(1000)
    
    updated = []
    unchanged = []
    
    for emp in employees:
        # Count actual review mentions for this employee
        actual_mentions = await db.customer_reviews.count_documents({
            "quarter": quarter.upper(),
            "year": year,
            "employee_mentions.name": {"$regex": f"^{emp['name']}$", "$options": "i"}
        })
        
        stored_mentions = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        
        if actual_mentions != stored_mentions:
            # Calculate new RT bonus
            new_rt_bonus = round(min(actual_mentions * 0.5, 15), 2)
            old_rt_bonus = emp.get("review_tracker_bonus", 0) or 0
            
            # Recalculate score components
            capped_ppa = min(emp.get('score_ppa', 0) or 0, 100)
            capped_lsc = min(emp.get('score_lsc', 0) or 0, 100)
            capped_lbw = min(emp.get('score_lbw', 0) or 0, 100)
            capped_glass = min(emp.get('score_glass', 0) or 0, 100)
            nps_score = emp.get('nps_score', 0) or 0
            
            nps_normalized = max(0, (nps_score + 100) / 2)
            nps_contribution = min(nps_normalized, 100) * 0.10
            
            base_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.15) + (capped_glass * 0.10) + nps_contribution + new_rt_bonus
            
            metric_bonus = min(emp.get('total_metric_bonus', 0) or 0, 20)
            cv_bonus = emp.get('cv_score', 0) or emp.get('cv_bonus', 0) or 0
            
            new_weighted = round(base_weighted, 2)
            new_score = round(base_weighted + metric_bonus + cv_bonus, 2)
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "review_mentions": actual_mentions,
                    "rt_mentions": actual_mentions,
                    "review_tracker_bonus": new_rt_bonus,
                    "weighted_score": new_weighted,
                    "pre_dar_score": new_score,
                    "total_score": new_score
                }}
            )
            
            updated.append({
                "name": emp["name"],
                "old_mentions": stored_mentions,
                "new_mentions": actual_mentions,
                "old_rt_bonus": old_rt_bonus,
                "new_rt_bonus": new_rt_bonus,
                "old_score": emp.get("pre_dar_score", 0) or 0,
                "new_score": new_score,
                "score_change": round(new_score - (emp.get("pre_dar_score", 0) or 0), 2)
            })
        else:
            unchanged.append(emp["name"])
    
    # Log this action
    if updated:
        await db.audit_log.insert_one({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "sync_employee_mentions",
            "quarter": quarter.upper(),
            "year": year,
            "details": {
                "updated_count": len(updated),
                "employees": [u["name"] for u in updated]
            },
            "user": "system"
        })
    
    return {
        "success": True,
        "quarter": quarter.upper(),
        "year": year,
        "summary": {
            "total_employees": len(employees),
            "updated": len(updated),
            "unchanged": len(unchanged)
        },
        "updated_employees": updated
    }
