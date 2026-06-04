"""
Data Integrity & Audit System for Restaurant Performance Scoring

This module provides:
1. Official stats management with audit trails
2. Score calculation verification
3. Data consistency checks
4. Detailed audit reports for accountability

Every number must be traceable and verifiable.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib
import json


class DataSource(Enum):
    """Tracks where each piece of data originated."""
    OFFICIAL_RT_UI = "official_reviewtrackers_ui"  # Manually entered from RT dashboard
    OFFICIAL_LV_UI = "official_loyalty_voice_ui"   # Manually entered from LV dashboard
    POS_UPLOAD = "pos_xlsx_upload"                  # From POS data upload
    API_SYNC = "api_sync"                           # From API (may differ from UI)
    CALCULATED = "calculated"                       # Derived from other data
    MANUAL_OVERRIDE = "manual_override"            # Admin override


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: str
    action: str
    data_source: str
    field: str
    old_value: Any
    new_value: Any
    user: str
    reason: str
    checksum: str


class ScoringAuditSystem:
    """
    Comprehensive audit system for employee scoring.
    Ensures 100% accuracy and accountability.
    """
    
    def __init__(self, db):
        self.db = db
    
    # =========================================================================
    # OFFICIAL STATS MANAGEMENT
    # =========================================================================
    
    async def set_official_cv_stats(
        self,
        quarter: str,
        year: int,
        nps_score: float,
        promoters: int,
        passives: int,
        detractors: int,
        total_responses: int,
        entered_by: str = "admin",
        source_screenshot_url: str = None,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Set official Customer Voice stats with full audit trail.
        These are the EXACT numbers from the Loyalty Voice UI.
        """
        # Validate the math
        expected_total = promoters + passives + detractors
        if total_responses != expected_total:
            return {
                "success": False,
                "error": f"Total responses ({total_responses}) doesn't match P+Pa+D ({expected_total})"
            }
        
        # Calculate expected NPS
        if total_responses > 0:
            expected_nps = round(((promoters - detractors) / total_responses) * 100, 2)
            if abs(expected_nps - nps_score) > 0.5:
                return {
                    "success": False,
                    "error": f"NPS ({nps_score}%) doesn't match calculation ({expected_nps}%). Expected: (({promoters}-{detractors})/{total_responses})*100"
                }
        
        # Get previous values for audit
        previous = await self.db.official_cv_stats.find_one(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        )
        
        # Create new record
        stats_doc = {
            "quarter": quarter.upper(),
            "year": year,
            "nps_score": nps_score,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "total_responses": total_responses,
            "data_source": DataSource.OFFICIAL_LV_UI.value,
            "entered_by": entered_by,
            "entered_at": datetime.now(timezone.utc).isoformat(),
            "source_screenshot_url": source_screenshot_url,
            "notes": notes,
            "checksum": self._generate_checksum({
                "nps": nps_score, "p": promoters, "pa": passives, "d": detractors, "t": total_responses
            })
        }
        
        # Save
        await self.db.official_cv_stats.update_one(
            {"quarter": quarter.upper(), "year": year},
            {"$set": stats_doc},
            upsert=True
        )
        
        # Create audit entry
        await self._log_audit(
            action="SET_OFFICIAL_CV_STATS",
            quarter=quarter,
            year=year,
            old_value=previous,
            new_value=stats_doc,
            user=entered_by,
            reason=notes or "Official stats update from Loyalty Voice UI"
        )
        
        return {"success": True, "stats": stats_doc, "validated": True}
    
    async def set_official_rt_stats(
        self,
        quarter: str,
        year: int,
        google_reviews: int,
        google_rating: float,
        yelp_reviews: int,
        yelp_rating: float,
        tripadvisor_reviews: int,
        tripadvisor_rating: float,
        opentable_reviews: int,
        opentable_rating: float,
        facebook_reviews: int = 0,
        facebook_rating: float = 0.0,
        entered_by: str = "admin",
        source_screenshot_url: str = None,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Set official ReviewTrackers stats with full audit trail.
        These are the EXACT numbers from the ReviewTrackers UI.
        """
        # Validate ratings are in valid range
        for platform, rating in [("Google", google_rating), ("Yelp", yelp_rating), 
                                  ("TripAdvisor", tripadvisor_rating), ("OpenTable", opentable_rating)]:
            if rating < 0 or rating > 5:
                return {"success": False, "error": f"{platform} rating ({rating}) must be between 0-5"}
        
        # Get previous values for audit
        previous = await self.db.official_rt_stats.find_one(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        )
        
        total_reviews = google_reviews + yelp_reviews + tripadvisor_reviews + opentable_reviews + facebook_reviews
        
        # Create new record
        stats_doc = {
            "quarter": quarter.upper(),
            "year": year,
            "platforms": {
                "Google": {"reviews": google_reviews, "rating": google_rating},
                "Yelp": {"reviews": yelp_reviews, "rating": yelp_rating},
                "TripAdvisor": {"reviews": tripadvisor_reviews, "rating": tripadvisor_rating},
                "OpenTable": {"reviews": opentable_reviews, "rating": opentable_rating},
                "Facebook": {"reviews": facebook_reviews, "rating": facebook_rating},
            },
            "total_reviews": total_reviews,
            "data_source": DataSource.OFFICIAL_RT_UI.value,
            "entered_by": entered_by,
            "entered_at": datetime.now(timezone.utc).isoformat(),
            "source_screenshot_url": source_screenshot_url,
            "notes": notes,
            "checksum": self._generate_checksum({
                "g": google_reviews, "y": yelp_reviews, "ta": tripadvisor_reviews, 
                "ot": opentable_reviews, "fb": facebook_reviews
            })
        }
        
        # Save
        await self.db.official_rt_stats.update_one(
            {"quarter": quarter.upper(), "year": year},
            {"$set": stats_doc},
            upsert=True
        )
        
        # Create audit entry
        await self._log_audit(
            action="SET_OFFICIAL_RT_STATS",
            quarter=quarter,
            year=year,
            old_value=previous,
            new_value=stats_doc,
            user=entered_by,
            reason=notes or "Official stats update from ReviewTrackers UI"
        )
        
        return {"success": True, "stats": stats_doc, "validated": True}
    
    # =========================================================================
    # SCORE VERIFICATION
    # =========================================================================
    
    async def verify_employee_score(self, employee_name: str, quarter: str, year: int) -> Dict[str, Any]:
        """
        Verify an employee's score calculation step-by-step.
        Returns detailed breakdown showing exactly how score was calculated.
        """
        # Get employee record
        employee = await self.db.employees_v2.find_one(
            {"name": employee_name, "quarter": quarter.upper(), "year": year},
            {"_id": 0}
        )
        
        if not employee:
            return {"success": False, "error": f"Employee '{employee_name}' not found"}
        
        # Get official stats
        official_cv = await self.db.official_cv_stats.find_one(
            {"quarter": quarter.upper(), "year": year}, {"_id": 0}
        )
        official_rt = await self.db.official_rt_stats.find_one(
            {"quarter": quarter.upper(), "year": year}, {"_id": 0}
        )
        
        # Get quarter settings
        settings = await self.db.quarter_settings.find_one(
            {"quarter": quarter.upper(), "year": year}, {"_id": 0}
        )
        
        # Build verification report
        verification = {
            "employee_name": employee_name,
            "quarter": quarter.upper(),
            "year": year,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "final_score": employee.get("pre_dar_score") or employee.get("total_score"),
            "data_sources": {
                "cv_stats": "OFFICIAL" if official_cv else "API_SYNCED",
                "rt_stats": "OFFICIAL" if official_rt else "API_SYNCED",
            },
            "breakdown": {},
            "validation_checks": [],
            "issues": []
        }
        
        # POS Metrics Breakdown
        verification["breakdown"]["pos_metrics"] = {
            "guests": employee.get("guests", 0),
            "net_sales": employee.get("net_sales", 0),
            "ppa": {
                "value": employee.get("ppa", 0),
                "calculation": f"net_sales / guests = {employee.get('net_sales', 0)} / {employee.get('guests', 0)}",
                "normalized_score": employee.get("score_ppa", 0)
            },
            "lbw_per_guest": {
                "value": employee.get("lbw_per_guest", 0),
                "normalized_score": employee.get("score_lbw", 0)
            },
            "glassware_per_guest": {
                "value": employee.get("glassware_per_guest", 0),
                "normalized_score": employee.get("score_glass", 0)
            },
            "guests_per_lsc": {
                "value": employee.get("guests_per_lsc", 0),
                "normalized_score": employee.get("score_lsc", 0)
            }
        }
        
        # Customer Voice Breakdown
        cv_promoters = employee.get("cv_promoters", 0)
        cv_detractors = employee.get("cv_detractors", 0)
        nps_score = employee.get("nps_score", 0)
        cv_score = employee.get("cv_score", 0)
        
        # Calculate expected CV score
        nps_pts = 0
        if nps_score >= 90: nps_pts = 10
        elif nps_score >= 80: nps_pts = 9
        elif nps_score >= 70: nps_pts = 8
        elif nps_score >= 60: nps_pts = 7
        elif nps_score >= 50: nps_pts = 6
        elif nps_score > 0: nps_pts = round((nps_score / 50) * 5, 1)
        
        expected_cv_score = nps_pts + (cv_promoters * 1) + (cv_detractors * -2)
        
        verification["breakdown"]["customer_voice"] = {
            "nps_score": nps_score,
            "nps_points": nps_pts,
            "nps_calculation": f"NPS {nps_score}% → {nps_pts} pts (90%=10, 80%=9, 70%=8, 60%=7, 50%=6)",
            "promoters": cv_promoters,
            "promoter_points": cv_promoters * 1,
            "promoter_calculation": f"{cv_promoters} promoters × 1 pt = {cv_promoters} pts",
            "detractors": cv_detractors,
            "detractor_points": cv_detractors * -2,
            "detractor_calculation": f"{cv_detractors} detractors × -2 pts = {cv_detractors * -2} pts",
            "cv_score": cv_score,
            "expected_cv_score": expected_cv_score,
            "cv_calculation": f"{nps_pts} (NPS) + {cv_promoters} (promoters) + {cv_detractors * -2} (detractors) = {expected_cv_score}"
        }
        
        # Check CV score matches calculation
        if abs(cv_score - expected_cv_score) > 0.1:
            verification["issues"].append({
                "field": "cv_score",
                "expected": expected_cv_score,
                "actual": cv_score,
                "message": f"CV score mismatch: expected {expected_cv_score}, got {cv_score}"
            })
        
        # Review Tracker Breakdown
        rt_mentions = employee.get("review_mentions", 0)
        rt_bonus = employee.get("review_tracker_bonus", 0)
        expected_rt_bonus = min(rt_mentions * 0.33, 20)  # Q2+ rule: 0.33 pts/mention, capped at 20

        verification["breakdown"]["review_tracker"] = {
            "mentions": rt_mentions,
            "points_per_mention": 0.33,
            "rt_bonus": rt_bonus,
            "expected_rt_bonus": expected_rt_bonus,
            "calculation": f"{rt_mentions} mentions × 0.33 pts = {expected_rt_bonus} pts (capped at 20)"
        }
        
        if abs(rt_bonus - expected_rt_bonus) > 0.01:
            verification["issues"].append({
                "field": "review_tracker_bonus",
                "expected": expected_rt_bonus,
                "actual": rt_bonus,
                "message": f"RT bonus mismatch: expected {expected_rt_bonus}, got {rt_bonus}"
            })
        
        # Total Score Breakdown
        base_score = employee.get("base_score", 0)
        metric_bonus = employee.get("total_metric_bonus", 0)
        
        verification["breakdown"]["total_score"] = {
            "base_score": base_score,
            "metric_bonus": metric_bonus,
            "cv_score": cv_score,
            "rt_bonus": rt_bonus,
            "pre_dar_score": employee.get("pre_dar_score", 0),
            "calculation": f"base({base_score}) + metric_bonus({metric_bonus}) + cv({cv_score}) + rt({rt_bonus})"
        }
        
        # Add validation summary
        verification["validation_checks"] = [
            {"check": "CV score calculation", "passed": abs(cv_score - expected_cv_score) <= 0.1},
            {"check": "RT bonus calculation", "passed": abs(rt_bonus - expected_rt_bonus) <= 0.01},
            {"check": "Data sources verified", "passed": official_cv is not None and official_rt is not None}
        ]
        
        verification["all_checks_passed"] = len(verification["issues"]) == 0
        
        return {"success": True, "verification": verification}
    
    async def verify_all_employees(self, quarter: str, year: int) -> Dict[str, Any]:
        """Verify scores for all employees in a quarter."""
        employees = await self.db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0, "name": 1}
        ).to_list(100)
        
        results = {
            "quarter": quarter.upper(),
            "year": year,
            "total_employees": len(employees),
            "passed": 0,
            "failed": 0,
            "issues": []
        }
        
        for emp in employees:
            verification = await self.verify_employee_score(emp["name"], quarter, year)
            if verification.get("success") and verification.get("verification", {}).get("all_checks_passed"):
                results["passed"] += 1
            else:
                results["failed"] += 1
                results["issues"].append({
                    "employee": emp["name"],
                    "issues": verification.get("verification", {}).get("issues", [])
                })
        
        return results
    
    # =========================================================================
    # DATA CONSISTENCY CHECKS
    # =========================================================================
    
    async def run_consistency_checks(self, quarter: str, year: int) -> Dict[str, Any]:
        """
        Run all data consistency checks for a quarter.
        Returns detailed report of any issues found.
        """
        checks = {
            "quarter": quarter.upper(),
            "year": year,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": [],
            "issues": [],
            "passed": True
        }
        
        # Check 1: Official CV stats exist
        official_cv = await self.db.official_cv_stats.find_one(
            {"quarter": quarter.upper(), "year": year}
        )
        checks["checks"].append({
            "name": "Official CV Stats Set",
            "passed": official_cv is not None,
            "message": "Official CV stats are set" if official_cv else "WARNING: No official CV stats - using synced data"
        })
        if not official_cv:
            checks["issues"].append("No official CV stats set - numbers may not match Loyalty Voice UI")
            checks["passed"] = False
        
        # Check 2: Official RT stats exist
        official_rt = await self.db.official_rt_stats.find_one(
            {"quarter": quarter.upper(), "year": year}
        )
        checks["checks"].append({
            "name": "Official RT Stats Set",
            "passed": official_rt is not None,
            "message": "Official RT stats are set" if official_rt else "WARNING: No official RT stats - using synced data"
        })
        if not official_rt:
            checks["issues"].append("No official RT stats set - numbers may not match ReviewTrackers UI")
            checks["passed"] = False
        
        # Check 3: CV feedback matches official totals
        if official_cv:
            cv_feedback_count = await self.db.cv_feedback.count_documents(
                {"quarter": quarter.upper(), "year": year}
            )
            official_total = official_cv.get("total_responses", 0)
            cv_match = cv_feedback_count == official_total
            checks["checks"].append({
                "name": "CV Feedback Count Match",
                "passed": cv_match,
                "message": f"CV feedback ({cv_feedback_count}) {'matches' if cv_match else 'DOES NOT MATCH'} official ({official_total})"
            })
            if not cv_match:
                checks["issues"].append(f"CV feedback count ({cv_feedback_count}) doesn't match official total ({official_total})")
        
        # Check 4: All employees have scores calculated
        employees = await self.db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0, "name": 1, "pre_dar_score": 1}
        ).to_list(100)
        
        missing_scores = [e["name"] for e in employees if not e.get("pre_dar_score")]
        checks["checks"].append({
            "name": "All Employees Scored",
            "passed": len(missing_scores) == 0,
            "message": f"All {len(employees)} employees have scores" if not missing_scores else f"{len(missing_scores)} employees missing scores"
        })
        if missing_scores:
            checks["issues"].append(f"Employees missing scores: {', '.join(missing_scores[:5])}")
            checks["passed"] = False
        
        # Check 5: No duplicate employees
        employee_names = [e["name"] for e in employees]
        duplicates = [n for n in employee_names if employee_names.count(n) > 1]
        checks["checks"].append({
            "name": "No Duplicate Employees",
            "passed": len(duplicates) == 0,
            "message": "No duplicate employees" if not duplicates else f"Found duplicates: {list(set(duplicates))}"
        })
        if duplicates:
            checks["issues"].append(f"Duplicate employees found: {list(set(duplicates))}")
            checks["passed"] = False
        
        return checks
    
    # =========================================================================
    # AUDIT TRAIL
    # =========================================================================
    
    async def _log_audit(
        self,
        action: str,
        quarter: str,
        year: int,
        old_value: Any,
        new_value: Any,
        user: str,
        reason: str
    ):
        """Log an audit entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "quarter": quarter.upper(),
            "year": year,
            "old_value": old_value,
            "new_value": new_value,
            "user": user,
            "reason": reason,
            "checksum": self._generate_checksum({"action": action, "new": new_value})
        }
        await self.db.audit_log.insert_one(entry)
    
    async def get_audit_trail(self, quarter: str, year: int, limit: int = 50) -> List[Dict]:
        """Get audit trail for a quarter."""
        entries = await self.db.audit_log.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return entries
    
    def _generate_checksum(self, data: Dict) -> str:
        """Generate checksum for data integrity verification."""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]
    
    # =========================================================================
    # AUDIT REPORT GENERATION
    # =========================================================================
    
    async def generate_audit_report(self, quarter: str, year: int) -> Dict[str, Any]:
        """
        Generate comprehensive audit report for a quarter.
        This report can be used to verify all scoring is accurate.
        """
        report = {
            "title": f"Scoring Audit Report - {quarter.upper()} {year}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "quarter": quarter.upper(),
            "year": year,
            "sections": {}
        }
        
        # Section 1: Official Stats Summary
        official_cv = await self.db.official_cv_stats.find_one(
            {"quarter": quarter.upper(), "year": year}, {"_id": 0}
        )
        official_rt = await self.db.official_rt_stats.find_one(
            {"quarter": quarter.upper(), "year": year}, {"_id": 0}
        )
        
        report["sections"]["official_stats"] = {
            "customer_voice": official_cv,
            "review_tracker": official_rt,
            "cv_source": official_cv.get("data_source") if official_cv else "NOT SET",
            "rt_source": official_rt.get("data_source") if official_rt else "NOT SET",
        }
        
        # Section 2: Consistency Checks
        consistency = await self.run_consistency_checks(quarter, year)
        report["sections"]["consistency_checks"] = consistency
        
        # Section 3: Employee Score Summary
        employees = await self.db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(100)
        
        report["sections"]["employee_summary"] = {
            "total_employees": len(employees),
            "rankings": sorted(
                [{"name": e["name"], "score": e.get("pre_dar_score", 0), "rank": e.get("rank", 0)} 
                 for e in employees],
                key=lambda x: x["score"],
                reverse=True
            )
        }
        
        # Section 4: Verification Summary
        verification = await self.verify_all_employees(quarter, year)
        report["sections"]["verification"] = verification
        
        # Section 5: Recent Audit Trail
        audit_trail = await self.get_audit_trail(quarter, year, limit=20)
        report["sections"]["recent_changes"] = audit_trail
        
        # Overall Status
        report["overall_status"] = "VERIFIED" if (
            consistency.get("passed") and 
            verification.get("failed", 1) == 0
        ) else "ISSUES_FOUND"
        
        return report
