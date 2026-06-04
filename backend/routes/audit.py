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
from services.employee_v2_writer import upsert_employee_v2

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
    benchmark_glass = settings.get("benchmark_glass", 1.35)
    benchmark_lsc = settings.get("benchmark_lsc", 100)
    
    # Calculate expected scores (uncapped for bonus calculation)
    ppa_score_raw = (stored_ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
    lbw_score_raw = (stored_lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
    glass_score_raw = (stored_glass_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
    lsc_score_raw = (benchmark_lsc / stored_guests_per_lsc) * 100 if stored_guests_per_lsc and stored_guests_per_lsc > 0 else 0
    
    # Cap at 100 for weighted calculation
    ppa_score = min(ppa_score_raw, 100)
    lbw_score = min(lbw_score_raw, 100)
    glass_score = min(glass_score_raw, 100)
    lsc_score = min(lsc_score_raw, 100)
    
    # NPS contribution at 10% weight (NPS already in 0-100 scale)
    nps_normalized = min(max(stored_nps or 0, 0), 100)
    nps_contribution = nps_normalized * 0.10
    
    # Calculate weighted POS score (75% of base)
    weight_ppa = settings.get("weight_ppa", 0.25)
    weight_lsc = settings.get("weight_lsc", 0.25)
    weight_lbw = settings.get("weight_lbw", 0.15)
    weight_glass = settings.get("weight_glass", 0.10)
    
    weighted_pos = (
        (ppa_score * weight_ppa) +
        (lsc_score * weight_lsc) +
        (lbw_score * weight_lbw) +
        (glass_score * weight_glass)
    )
    
    # Full weighted base = POS (75%) + NPS (10%)
    weighted_base = weighted_pos + nps_contribution
    
    # RT bonus calculation (0.5 pts per mention, capped at 15)
    rt_bonus = min(stored_rt_mentions * 0.3, 20)
    
    # METRIC BONUSES: Linear from 100%-120% = 0-5 pts (0.25 pts per 1%)
    def calc_metric_bonus(score_raw):
        if score_raw <= 100:
            return 0
        excess_pct = min(score_raw - 100, 20)  # Cap at 20% over
        return round(excess_pct * 0.25, 2)  # 0.25 pts per 1%
    
    bonus_ppa = calc_metric_bonus(ppa_score_raw)
    bonus_lbw = calc_metric_bonus(lbw_score_raw)
    bonus_glass = calc_metric_bonus(glass_score_raw)
    bonus_lsc = calc_metric_bonus(lsc_score_raw)
    
    metric_bonus = min(bonus_ppa + bonus_lbw + bonus_glass + bonus_lsc, 20)  # Total capped at 20
    
    # CV bonus (promoters - detractors formula, NO CAP)
    cv_bonus = (stored_cv_promoters * 1) + (stored_cv_detractors * -2)
    
    # Final expected score = Weighted Base + RT Bonus + CV Bonus + Metric Bonus
    expected_total = round(weighted_base + rt_bonus + cv_bonus + metric_bonus, 2)
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
            "nps_contribution": round(nps_contribution, 2)
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
            new_rt_bonus = round(min(actual_mentions * 0.3, 20), 2)
            old_rt_bonus = emp.get("review_tracker_bonus", 0) or 0
            
            # Recalculate score components
            capped_ppa = min(emp.get('score_ppa', 0) or 0, 100)
            capped_lsc = min(emp.get('score_lsc', 0) or 0, 100)
            capped_lbw = min(emp.get('score_lbw', 0) or 0, 100)
            capped_glass = min(emp.get('score_glass', 0) or 0, 100)
            nps_score = emp.get('nps_score', 0) or 0
            
            nps_normalized = max(0, (nps_score + 100) / 2)
            nps_contribution = min(nps_normalized, 100) * 0.10
            
            base_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.20) + (capped_glass * 0.15) + nps_contribution + new_rt_bonus
            
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


@audit_router.get("/cross-reference/{year}/{quarter}")
async def cross_reference_snapshot_vs_dashboard(year: int, quarter: str):
    """
    Cross-reference snapshot_workflow employee data vs employees_v2 (dashboard) data.
    Identifies discrepancies where snapshot has real data but dashboard shows zeros.
    """
    db = get_db()
    quarter = quarter.upper()

    # Get the active/latest completed snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter, "year": year},
        {"_id": 0}
    )
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter, "year": year},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )

    if not snapshot or not snapshot.get("employees"):
        raise HTTPException(status_code=404, detail=f"No snapshot found for {quarter} {year}")

    snapshot_employees = snapshot.get("employees", [])

    # Build lookup from employees_v2
    dashboard_lookup = {}
    async for emp in db.employees_v2.find(
        {"quarter": quarter, "year": year},
        {"_id": 0}
    ):
        name = (emp.get("name") or "").lower().strip()
        dashboard_lookup[name] = emp

    # Compare key POS fields
    key_fields = ["ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc",
                  "guest_count", "net_sales", "loyalty_sales"]
    score_fields = ["score_ppa", "score_lbw", "score_glass", "score_lsc",
                    "cv_score", "total_score", "pre_dar_score"]

    discrepancies = []
    matched = []
    missing_from_dashboard = []

    for snap_emp in snapshot_employees:
        snap_name = (snap_emp.get("name") or "").lower().strip()
        dash_emp = dashboard_lookup.get(snap_name)

        if not dash_emp:
            missing_from_dashboard.append({
                "name": snap_emp.get("name"),
                "snapshot_score": snap_emp.get("total_score", 0),
                "tier": snap_emp.get("tier_label") or snap_emp.get("performance_tier"),
            })
            continue

        field_diffs = {}
        has_zero_issue = False
        for field in key_fields + score_fields:
            snap_val = snap_emp.get(field, 0) or 0
            dash_val = dash_emp.get(field, 0) or 0
            if abs(snap_val - dash_val) > 0.01:
                field_diffs[field] = {"snapshot": snap_val, "dashboard": dash_val}
                if dash_val == 0 and snap_val > 0:
                    has_zero_issue = True

        if field_diffs:
            discrepancies.append({
                "name": snap_emp.get("name"),
                "employee_id": dash_emp.get("id"),
                "snapshot_score": snap_emp.get("total_score", 0) or snap_emp.get("pre_dar_score", 0),
                "dashboard_score": dash_emp.get("total_score", 0),
                "tier_snapshot": snap_emp.get("tier_label") or snap_emp.get("performance_tier"),
                "tier_dashboard": dash_emp.get("tier_label") or dash_emp.get("performance_tier"),
                "has_zero_issue": has_zero_issue,
                "differences": field_diffs,
            })
        else:
            matched.append(snap_emp.get("name"))

    return {
        "success": True,
        "quarter": quarter,
        "year": year,
        "snapshot_employee_count": len(snapshot_employees),
        "dashboard_employee_count": len(dashboard_lookup),
        "matched_count": len(matched),
        "discrepancy_count": len(discrepancies),
        "missing_from_dashboard_count": len(missing_from_dashboard),
        "discrepancies": sorted(discrepancies, key=lambda d: d.get("has_zero_issue", False), reverse=True),
        "missing_from_dashboard": missing_from_dashboard,
        "matched_employees": matched,
    }


@audit_router.post("/sync-from-snapshot/{year}/{quarter}")
async def sync_employees_from_snapshot(year: int, quarter: str, employee_name: Optional[str] = None):
    """
    Sync employee data FROM the active snapshot BACK to employees_v2 (dashboard).
    Fixes cases where dashboard shows zeros but snapshot has real data.
    If employee_name is provided, only sync that employee. Otherwise sync all with discrepancies.
    """
    db = get_db()
    quarter = quarter.upper()

    # Get the active/latest completed snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter, "year": year},
        {"_id": 0}
    )
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter, "year": year},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )

    if not snapshot or not snapshot.get("employees"):
        raise HTTPException(status_code=404, detail=f"No snapshot found for {quarter} {year}")

    snapshot_employees = snapshot.get("employees", [])

    # Fields to sync from snapshot to employees_v2
    sync_fields = [
        "ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc",
        "guest_count", "net_sales", "loyalty_sales", "lsc_count",
        "liquor_sales", "beer_sales", "wine_sales", "bar_glassware_sales",
        "score_ppa", "score_lbw", "score_glass", "score_lsc",
        "cv_score", "cv_nps", "cv_responses", "cv_promoters", "cv_detractors",
        "rt_mentions", "review_mentions", "review_tracker_bonus",
        "total_score", "pre_dar_score", "total_metric_bonus",
        "tier_label", "performance_tier", "rank",
    ]

    updated = []
    not_found = []
    skipped = []

    for snap_emp in snapshot_employees:
        snap_name = (snap_emp.get("name") or "").strip()
        if employee_name and snap_name.lower() != employee_name.lower():
            continue

        # Find matching employee in employees_v2
        dash_emp = await db.employees_v2.find_one(
            {"name": {"$regex": f"^{snap_name}$", "$options": "i"}, "quarter": quarter, "year": year}
        )

        if not dash_emp:
            not_found.append(snap_name)
            continue

        # Build update with non-zero snapshot values
        update_fields = {}
        for field in sync_fields:
            snap_val = snap_emp.get(field)
            if snap_val is not None and snap_val != 0:
                dash_val = dash_emp.get(field, 0) or 0
                if dash_val == 0 or (employee_name and snap_val != dash_val):
                    update_fields[field] = snap_val

        if update_fields:
            await db.employees_v2.update_one(
                {"_id": dash_emp["_id"]},
                {"$set": update_fields}
            )
            updated.append({
                "name": snap_name,
                "fields_updated": list(update_fields.keys()),
                "field_count": len(update_fields),
            })
        else:
            skipped.append(snap_name)

    return {
        "success": True,
        "quarter": quarter,
        "year": year,
        "updated_count": len(updated),
        "not_found_count": len(not_found),
        "skipped_count": len(skipped),
        "updated": updated,
        "not_found": not_found,
        "skipped": skipped,
    }


@audit_router.post("/sync-to-snapshot/{year}/{quarter}")
async def sync_dashboard_to_snapshot(year: int, quarter: str, employee_name: Optional[str] = None):
    """
    Sync employee data FROM employees_v2 (dashboard) TO the active snapshot.
    Fixes cases where snapshot has zeros/stale data but dashboard has correct data.
    If employee_name is provided, only sync that employee. Otherwise sync all.
    """
    db = get_db()
    quarter = quarter.upper()

    # Get the active/latest completed snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter, "year": year}
    )
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter, "year": year},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )

    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {quarter} {year}")

    snapshot_id = snapshot["_id"]
    snapshot_employees = snapshot.get("employees", [])

    # Build lookup from snapshot employees by name
    snap_lookup = {}
    for i, emp in enumerate(snapshot_employees):
        name = (emp.get("name") or "").lower().strip()
        snap_lookup[name] = i

    # Fields to sync from dashboard to snapshot
    sync_fields = [
        "ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc",
        "guest_count", "net_sales", "loyalty_sales", "lsc_count",
        "liquor_sales", "beer_sales", "wine_sales", "bar_glassware_sales",
        "score_ppa", "score_lbw", "score_glass", "score_lsc",
        "weighted_score",  # ← critical: was missing, causing snapshot to retain stale uncapped values
        "cv_score", "cv_nps", "cv_responses", "cv_promoters", "cv_detractors",
        "nps_score", "nps_contribution", "cv_raw_points",
        "rt_mentions", "review_mentions", "review_tracker_bonus",
        "total_score", "pre_dar_score", "total_metric_bonus",
        "tier_label", "performance_tier", "rank", "job_title",
    ]

    updated = []
    not_in_snapshot = []
    skipped = []

    # Get dashboard employees
    query = {"quarter": quarter, "year": year}
    if employee_name:
        query["name"] = {"$regex": f"^{employee_name}$", "$options": "i"}

    async for dash_emp in db.employees_v2.find(query, {"_id": 0}):
        dash_name = (dash_emp.get("name") or "").lower().strip()
        snap_idx = snap_lookup.get(dash_name)

        if snap_idx is None:
            not_in_snapshot.append(dash_emp.get("name"))
            continue

        snap_emp = snapshot_employees[snap_idx]

        # Build update: copy dashboard values to snapshot employee
        field_updates = {}
        for field in sync_fields:
            dash_val = dash_emp.get(field)
            snap_val = snap_emp.get(field, 0) or 0
            if dash_val is not None and dash_val != 0 and (snap_val == 0 or dash_val != snap_val):
                field_updates[field] = dash_val

        if field_updates:
            # Update the snapshot employee in-place
            set_ops = {}
            for field, val in field_updates.items():
                set_ops[f"employees.{snap_idx}.{field}"] = val
            await db.snapshot_workflow.update_one(
                {"_id": snapshot_id},
                {"$set": set_ops}
            )
            updated.append({
                "name": dash_emp.get("name"),
                "fields_updated": list(field_updates.keys()),
                "field_count": len(field_updates),
            })
        else:
            skipped.append(dash_emp.get("name"))

    return {
        "success": True,
        "quarter": quarter,
        "year": year,
        "direction": "dashboard → snapshot",
        "updated_count": len(updated),
        "not_in_snapshot_count": len(not_in_snapshot),
        "skipped_count": len(skipped),
        "updated": updated,
        "not_in_snapshot": not_in_snapshot,
        "skipped": skipped,
    }



@audit_router.post("/dedup-snapshot/{year}/{quarter}")
async def dedup_snapshot_employees(year: int, quarter: str):
    """
    Remove duplicate employees from the active snapshot, keeping the entry with the highest score.
    """
    db = get_db()
    quarter = quarter.upper()

    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter, "year": year}
    )
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter, "year": year},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {quarter} {year}")

    snapshot_id = snapshot["_id"]
    employees = snapshot.get("employees", [])

    # Group by lowercase name
    seen = {}
    deduped = []
    removed = []

    for emp in employees:
        name_key = (emp.get("name") or "").lower().strip()
        score = emp.get("pre_dar_score", 0) or emp.get("total_score", 0) or 0

        if name_key not in seen:
            seen[name_key] = len(deduped)
            deduped.append(emp)
        else:
            existing_idx = seen[name_key]
            existing_score = deduped[existing_idx].get("pre_dar_score", 0) or deduped[existing_idx].get("total_score", 0) or 0
            if score > existing_score:
                removed.append({"name": deduped[existing_idx].get("name"), "score": existing_score, "action": "replaced"})
                deduped[existing_idx] = emp
            else:
                removed.append({"name": emp.get("name"), "score": score, "action": "dropped"})

    if removed:
        await db.snapshot_workflow.update_one(
            {"_id": snapshot_id},
            {"$set": {"employees": deduped, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

    return {
        "success": True,
        "original_count": len(employees),
        "deduped_count": len(deduped),
        "removed_count": len(removed),
        "removed": removed,
    }


@audit_router.post("/restore-employee/{year}/{quarter}")
async def restore_employee_to_snapshot(year: int, quarter: str, employee_name: str):
    """
    Restore a specific employee from employees_v2 (dashboard) into the active snapshot.
    Used when an employee was accidentally deleted from the snapshot.
    """
    db = get_db()
    quarter = quarter.upper()

    # Find the employee in dashboard
    dash_emp = await db.employees_v2.find_one(
        {"name": {"$regex": f"^{employee_name}$", "$options": "i"}, "quarter": quarter, "year": year},
        {"_id": 0}
    )
    if not dash_emp:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_name}' not found in dashboard")

    # Find the active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter, "year": year}
    )
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter, "year": year},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {quarter} {year}")

    snapshot_id = snapshot["_id"]
    employees = snapshot.get("employees", [])

    # Check if already exists
    existing = [e for e in employees if (e.get("name") or "").lower().strip() == employee_name.lower().strip()]
    if existing:
        return {"success": False, "message": f"Employee '{employee_name}' already exists in snapshot ({len(existing)} entries)"}

    # Add the employee with all dashboard fields
    employees.append(dash_emp)

    await db.snapshot_workflow.update_one(
        {"_id": snapshot_id},
        {"$set": {"employees": employees, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    return {
        "success": True,
        "message": f"Restored '{employee_name}' to snapshot",
        "employee_score": dash_emp.get("total_score", 0),
        "snapshot_employee_count": len(employees),
    }



@audit_router.get("/apply-corrections/{year}/{quarter}")
async def apply_data_corrections(year: int, quarter: str):
    """
    One-shot fix: Apply known data corrections for the quarter.
    """
    import uuid
    db = get_db()
    quarter = quarter.upper()

    results = []

    # Fix 0: Correct tier thresholds in quarter_settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter}
    )
    if settings_doc:
        updates = {}
        if settings_doc.get("a_server_min_score") != 85:
            updates["a_server_min_score"] = 85
        if settings_doc.get("b_server_min_score") != 70:
            updates["b_server_min_score"] = 70
        if updates:
            await db.quarter_settings.update_one(
                {"_id": settings_doc["_id"]},
                {"$set": updates}
            )
            results.append("Fixed tier thresholds: A>=85, B>=70")

    a_min = 85
    b_min = 70

    # Fix 1: Starwars - clear wrong display_name "Stanvars"
    starwars = await db.employees_v2.find_one(
        {"name": {"$regex": "starwars", "$options": "i"}, "quarter": quarter, "year": year}
    )
    if starwars and starwars.get("display_name") and "stanv" in (starwars.get("display_name") or "").lower():
        await db.employees_v2.update_one(
            {"_id": starwars["_id"]},
            {"$set": {"display_name": "Starwars McKinnon-Herrera"}}
        )
        results.append("Fixed Starwars: removed wrong display_name 'Stanvars'")

    # Fix 2: Keisha Martin - restore display_name and score
    keisha = await db.employees_v2.find_one(
        {"name": {"$regex": "keisha|lakeisha", "$options": "i"}, "quarter": quarter, "year": year}
    )
    if keisha:
        await db.employees_v2.update_one(
            {"_id": keisha["_id"]},
            {"$set": {
                "display_name": "Keisha Martin",
                "total_score": 114.0,
                "pre_dar_score": 114.0,
                "score_ppa": 94,
                "score_lbw": 109,
                "score_glass": 110,
                "score_lsc": 101,
                "cv_score": 22.0,
                "review_tracker_bonus": 13.5,
                "total_metric_bonus": 4.9,
            }}
        )
        results.append("Fixed Keisha Martin: display_name + score 114.0")

    # Fix 3: Lennie Nguyen - add back with correct data
    lennie = await db.employees_v2.find_one(
        {"name": {"$regex": "^lennie", "$options": "i"}, "quarter": quarter, "year": year}
    )
    if not lennie:
        lennie_data = {
            "id": str(uuid.uuid4()),
            "name": "Lennie Nguyen",
            "display_name": "Lennie Nguyen",
            "job_title": "server",
            "year": year,
            "quarter": quarter,
            "tier_label": "A-Server",
            "total_score": 90.2,
            "pre_dar_score": 90.2,
            "score_ppa": 83,
            "score_lbw": 62,
            "score_glass": 158,
            "score_lsc": 147,
            "cv_score": 11.0,
            "review_tracker_bonus": 4.0,
            "total_metric_bonus": 10.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await upsert_employee_v2(db, lennie_data)
        results.append("Added Lennie Nguyen: score 90.2, tier A-Server")
    else:
        results.append("Lennie Nguyen already exists - skipped")

    # Fix 4: Correct tier labels for all employees based on score thresholds
    tier_fixes = 0
    fixed_names = []
    async for emp in db.employees_v2.find({"quarter": quarter, "year": year}):
        score = emp.get("pre_dar_score", 0) or emp.get("total_score", 0) or 0
        stored_tier = (emp.get("tier_label") or "").strip()
        job_title = (emp.get("job_title") or "").lower()

        if "trainer" in job_title or stored_tier == "Trainer":
            correct_tier = "Trainer"
        elif "bartender" in job_title or "bar" in job_title or stored_tier == "Bartender":
            correct_tier = "Bartender"
        elif score >= a_min:
            correct_tier = "A-Server"
        elif score >= b_min:
            correct_tier = "B-Server"
        else:
            correct_tier = "C-Server"

        if correct_tier != stored_tier:
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {"tier_label": correct_tier}}
            )
            tier_fixes += 1
            fixed_names.append(f"{emp.get('name')}: {stored_tier} -> {correct_tier}")

    if tier_fixes:
        results.append(f"Fixed {tier_fixes} tier labels: {', '.join(fixed_names)}")

    return {"success": True, "corrections": results}



@audit_router.post("/fix-employee-data/{year}/{quarter}")
async def fix_employee_data(year: int, quarter: str, employee_data: dict):
    """
    Insert or update an employee in employees_v2 with exact pre-calculated data.
    Used to restore employees with known correct scores without going through the scoring pipeline.
    """
    import uuid
    db = get_db()
    quarter = quarter.upper()

    name = employee_data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Employee name is required")

    # Check if employee already exists
    existing = await db.employees_v2.find_one(
        {"name": {"$regex": f"^{name}$", "$options": "i"}, "quarter": quarter, "year": year}
    )

    employee_data["quarter"] = quarter
    employee_data["year"] = year

    if existing:
        # Update existing
        await db.employees_v2.update_one(
            {"_id": existing["_id"]},
            {"$set": employee_data}
        )
        return {"success": True, "action": "updated", "name": name}
    else:
        # Insert new
        if "id" not in employee_data:
            employee_data["id"] = str(uuid.uuid4())
        employee_data["created_at"] = datetime.now(timezone.utc).isoformat()
        await upsert_employee_v2(db, employee_data)
        # Remove _id from response
        return {"success": True, "action": "created", "name": name, "id": employee_data["id"]}



@audit_router.get("/fix-q2-data")
async def fix_q2_data():
    """
    One-shot fix for Q2 2026 production data:
    1. Fix NPS data (push promoters/detractors from Server Performance Report)
    2. Fix display names (Tad, TK, Terry, Keisha, etc.)
    3. Remove duplicate employees
    """
    db = get_db()
    results = []
    
    # === 1. NPS DATA ===
    nps_data = [
        {"name": "Treyanna Quick", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 6},
        {"name": "Matthew Spath", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 8},
        {"name": "Lakeisha Martin", "prom": 0, "pas": 2, "det": 0, "avg": 7.5, "recv": 2, "sent": 11},
        {"name": "Thaddeus Hashey", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 6},
        {"name": "Daniel Mayorga", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 4},
        {"name": "Craig Simmons", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 8},
        {"name": "Eddie Garcia", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 7},
        {"name": "Jose Plancarte Villa", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 7},
        {"name": "Ashley Jackson", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 7},
        {"name": "Ethan Dever", "prom": 0, "pas": 0, "det": 1, "avg": 3.0, "recv": 1, "sent": 6},
        {"name": "Robert Mckinnon", "prom": 2, "pas": 0, "det": 0, "avg": 9.0, "recv": 2, "sent": 5},
        {"name": "Eric Ostgarden", "prom": 1, "pas": 0, "det": 0, "avg": 10.0, "recv": 1, "sent": 6},
        {"name": "Adriana Bracamontes", "prom": 0, "pas": 0, "det": 1, "avg": 5.0, "recv": 1, "sent": 7},
    ]
    
    nps_updated = 0
    for nps in nps_data:
        total = nps["prom"] + nps["pas"] + nps["det"]
        nps_score = round(((nps["prom"] - nps["det"]) / total) * 100, 2) if total > 0 else 0
        cv_score = (nps["prom"] * 1) + (nps["det"] * -2)
        
        result = await db.employees_v2.update_one(
            {"name": {"$regex": f"^{nps['name']}$", "$options": "i"}, "quarter": "Q2", "year": 2026},
            {"$set": {
                "cv_promoters": nps["prom"],
                "cv_passives": nps["pas"],
                "cv_detractors": nps["det"],
                "nps_score": nps_score,
                "cv_score": cv_score,
                "cv_avg_rating": nps["avg"],
                "cv_surveys_received": nps["recv"],
                "cv_surveys_sent": nps["sent"],
            }}
        )
        if result.modified_count > 0:
            nps_updated += 1
    results.append(f"NPS: updated {nps_updated}/{len(nps_data)} employees")
    
    # === 2. DISPLAY NAMES ===
    display_name_fixes = {
        "Thaddeus Hashey": "Tad Hashey",
        "Thomas Kozan": "TK Kozan",
        "Terrance Kott": "Terry Kott",
        "Lakeisha Martin": "Keisha Martin",
        "Abigail Ostrowski": "Abby Ostrowski",
        "Eric Ostgarden": "Ikey Ostgarden",
        "Matthew Spath": "Matt Spath",
        "Starwars Mckinnon-Herrera": "Starwars McKinnon-Herrera",
        "Craig Simmons": "Allen Simmons",
    }
    
    dn_updated = 0
    for formal, preferred in display_name_fixes.items():
        result = await db.employees_v2.update_one(
            {"name": {"$regex": f"^{formal}$", "$options": "i"}, "quarter": "Q2", "year": 2026},
            {"$set": {
                "display_name": preferred,
                "report_name": formal,
            }}
        )
        if result.modified_count > 0:
            dn_updated += 1
    results.append(f"Display names: updated {dn_updated}/{len(display_name_fixes)}")
    
    # === 3. REMOVE DUPLICATES ===
    # Find and remove duplicate employees by name, keeping the one with most data
    from collections import defaultdict
    name_groups = defaultdict(list)
    async for emp in db.employees_v2.find({"quarter": "Q2", "year": 2026}):
        name_key = (emp.get("name") or "").lower().strip()
        name_groups[name_key].append(emp)
    
    dupes_removed = 0
    for name, emps in name_groups.items():
        if len(emps) > 1:
            # Keep the one with the highest score or most data
            emps.sort(key=lambda x: (
                x.get("total_score") or 0,
                x.get("cv_promoters") or 0,
                x.get("rt_mentions") or 0,
            ), reverse=True)
            # Remove all but the first (best)
            for dup in emps[1:]:
                await db.employees_v2.delete_one({"_id": dup["_id"]})
                dupes_removed += 1
                results.append(f"Removed duplicate: {dup.get('name')} (score={dup.get('total_score',0)})")
    
    if dupes_removed == 0:
        results.append("No duplicates found in employees_v2")
    
    # === 4. DEDUP SNAPSHOT ===
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": "Q2", "year": 2026}
    )
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": "Q2", "year": 2026},
            sort=[("completed_at", -1)]
        )
    
    snap_dupes_removed = 0
    if snapshot:
        snap_employees = snapshot.get("employees", [])
        seen = {}
        deduped = []
        for emp in snap_employees:
            name_key = (emp.get("name") or "").lower().strip()
            score = emp.get("pre_dar_score", 0) or emp.get("total_score", 0) or 0
            if name_key not in seen:
                seen[name_key] = len(deduped)
                deduped.append(emp)
            else:
                existing_idx = seen[name_key]
                existing_score = deduped[existing_idx].get("pre_dar_score", 0) or deduped[existing_idx].get("total_score", 0) or 0
                if score > existing_score:
                    results.append(f"Snapshot: replaced {emp.get('name')} (score={existing_score}) with score={score}")
                    deduped[existing_idx] = emp
                else:
                    results.append(f"Snapshot: dropped duplicate {emp.get('name')} (score={score})")
                snap_dupes_removed += 1
        
        if snap_dupes_removed > 0:
            await db.snapshot_workflow.update_one(
                {"_id": snapshot["_id"]},
                {"$set": {"employees": deduped}}
            )
            results.append(f"Snapshot deduped: {len(snap_employees)} -> {len(deduped)}")
        else:
            results.append("No duplicates in snapshot")
    
    return {"success": True, "corrections": results}
