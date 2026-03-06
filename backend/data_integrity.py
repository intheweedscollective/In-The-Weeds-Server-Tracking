"""
Data Integrity Module for Restaurant Performance System

This module provides:
1. Duplicate detection and removal
2. Data validation against source
3. Server name verification for CV feedback
4. Reconciliation reports
5. Audit logging
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class DataIntegrityChecker:
    """
    Validates and ensures data accuracy across Review Tracker and Customer Voice.
    """
    
    def __init__(self, db):
        self.db = db
        self.audit_log = []
    
    async def run_full_integrity_check(self) -> Dict[str, Any]:
        """
        Run complete data integrity check across all data sources.
        Returns a comprehensive report.
        """
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "complete",
            "issues_found": 0,
            "issues_fixed": 0,
            "checks": {}
        }
        
        # 1. Check customer_reviews for duplicates
        review_check = await self.check_review_duplicates()
        report["checks"]["review_duplicates"] = review_check
        report["issues_found"] += review_check.get("duplicates_found", 0)
        
        # 2. Check CV feedback for missing server names
        cv_check = await self.check_cv_server_names()
        report["checks"]["cv_server_names"] = cv_check
        report["issues_found"] += cv_check.get("missing_server_names", 0)
        
        # 3. Validate CV NPS calculations
        nps_check = await self.validate_cv_nps_calculations()
        report["checks"]["cv_nps_validation"] = nps_check
        report["issues_found"] += nps_check.get("mismatches", 0)
        
        # 4. Check review counts by source
        counts_check = await self.check_review_counts()
        report["checks"]["review_counts"] = counts_check
        
        # 5. Check for orphaned records
        orphan_check = await self.check_orphaned_records()
        report["checks"]["orphaned_records"] = orphan_check
        report["issues_found"] += orphan_check.get("orphaned_count", 0)
        
        return report
    
    async def check_review_duplicates(self) -> Dict[str, Any]:
        """
        Check for duplicate reviews in customer_reviews collection.
        Duplicates are identified by:
        - Same review_id or id
        - Same content hash (reviewer + date + text + source)
        """
        result = {
            "total_reviews": 0,
            "unique_reviews": 0,
            "duplicates_found": 0,
            "duplicate_details": []
        }
        
        reviews = await self.db.customer_reviews.find({}, {"_id": 0}).to_list(10000)
        result["total_reviews"] = len(reviews)
        
        # Track by multiple keys
        seen_ids = set()
        seen_hashes = set()
        duplicates = []
        
        for review in reviews:
            review_id = review.get("review_id") or review.get("id")
            
            # Create content hash using the actual field names
            reviewer = review.get('reviewer_name') or review.get('author', '')
            date = review.get('review_date') or review.get('date', '')
            text = review.get('review_text') or review.get('text', '')
            source = review.get('platform') or review.get('source', '')
            
            content = f"{reviewer}{date}{text}{source}"
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            is_duplicate = False
            reason = []
            
            if review_id and review_id in seen_ids:
                is_duplicate = True
                reason.append("duplicate_id")
            
            # Only check content hash if we have actual content
            if text and content_hash in seen_hashes:
                is_duplicate = True
                reason.append("duplicate_content")
            
            if is_duplicate:
                duplicates.append({
                    "id": review_id,
                    "author": reviewer,
                    "date": date,
                    "reason": reason
                })
            else:
                if review_id:
                    seen_ids.add(review_id)
                if text:
                    seen_hashes.add(content_hash)
        
        result["unique_reviews"] = len(seen_ids)
        result["duplicates_found"] = len(duplicates)
        result["duplicate_details"] = duplicates[:20]  # Limit details
        
        return result
    
    async def check_cv_server_names(self) -> Dict[str, Any]:
        """
        Check CV feedback for missing server names.
        All CV feedback MUST have a server_name - this is non-negotiable.
        """
        result = {
            "total_feedback": 0,
            "with_server_name": 0,
            "missing_server_names": 0,
            "missing_details": []
        }
        
        feedback = await self.db.cv_feedback.find({}, {"_id": 0}).to_list(10000)
        result["total_feedback"] = len(feedback)
        
        missing = []
        for f in feedback:
            server_name = f.get("server_name", "").strip()
            if not server_name:
                missing.append({
                    "id": f.get("id"),
                    "date": f.get("date"),
                    "rating": f.get("rating"),
                    "comment_preview": str(f.get("comment", ""))[:100]
                })
            else:
                result["with_server_name"] += 1
        
        result["missing_server_names"] = len(missing)
        result["missing_details"] = missing[:20]
        result["attribution_rate"] = round(
            (result["with_server_name"] / result["total_feedback"] * 100) 
            if result["total_feedback"] > 0 else 0, 2
        )
        
        return result
    
    async def validate_cv_nps_calculations(self) -> Dict[str, Any]:
        """
        Validate that cv_nps records match the actual cv_feedback data.
        """
        result = {
            "total_nps_records": 0,
            "validated": 0,
            "mismatches": 0,
            "mismatch_details": []
        }
        
        nps_records = await self.db.cv_nps.find({}, {"_id": 0}).to_list(1000)
        result["total_nps_records"] = len(nps_records)
        
        for nps in nps_records:
            employee_name = nps.get("employee_name")
            quarter = nps.get("quarter")
            year = nps.get("year")
            
            # Get actual feedback for this employee
            feedback = await self.db.cv_feedback.find({
                "server_name": employee_name,
                "quarter": quarter,
                "year": year
            }, {"_id": 0, "rating": 1}).to_list(1000)
            
            # Calculate actual promoters/detractors
            actual_promoters = sum(1 for f in feedback if (f.get("rating") or 0) >= 9)
            actual_detractors = sum(1 for f in feedback if (f.get("rating") or 0) <= 6 and f.get("rating") is not None)
            actual_total = len([f for f in feedback if f.get("rating") is not None])
            
            if actual_total > 0:
                actual_nps = round(((actual_promoters - actual_detractors) / actual_total) * 100)
            else:
                actual_nps = 0
            
            # Compare with stored values
            stored_promoters = nps.get("promoters", 0)
            stored_detractors = nps.get("detractors", 0)
            stored_nps = nps.get("nps_score", 0)
            
            if (stored_promoters != actual_promoters or 
                stored_detractors != actual_detractors or 
                abs(stored_nps - actual_nps) > 1):
                result["mismatches"] += 1
                result["mismatch_details"].append({
                    "employee": employee_name,
                    "quarter": quarter,
                    "year": year,
                    "stored": {
                        "promoters": stored_promoters,
                        "detractors": stored_detractors,
                        "nps": stored_nps
                    },
                    "actual": {
                        "promoters": actual_promoters,
                        "detractors": actual_detractors,
                        "nps": actual_nps
                    }
                })
            else:
                result["validated"] += 1
        
        return result
    
    async def check_review_counts(self) -> Dict[str, Any]:
        """
        Check review counts by source and quarter.
        """
        result = {
            "by_source": {},
            "by_quarter": {},
            "total": 0
        }
        
        reviews = await self.db.customer_reviews.find({}, {"_id": 0, "source": 1, "quarter": 1, "year": 1}).to_list(10000)
        result["total"] = len(reviews)
        
        for review in reviews:
            source = review.get("source", "unknown")
            quarter = f"{review.get('year', 'unknown')}-{review.get('quarter', 'unknown')}"
            
            result["by_source"][source] = result["by_source"].get(source, 0) + 1
            result["by_quarter"][quarter] = result["by_quarter"].get(quarter, 0) + 1
        
        return result
    
    async def check_orphaned_records(self) -> Dict[str, Any]:
        """
        Check for orphaned records (CV feedback not linked to any employee).
        """
        result = {
            "orphaned_count": 0,
            "orphaned_details": []
        }
        
        # Get all employee names
        employees = await self.db.employees_v2.find({}, {"_id": 0, "name": 1}).to_list(1000)
        employee_names = set(e.get("name", "").lower().strip() for e in employees)
        
        # Get all CV NPS records
        nps_records = await self.db.cv_nps.find({}, {"_id": 0, "employee_name": 1}).to_list(1000)
        
        for nps in nps_records:
            emp_name = nps.get("employee_name", "").lower().strip()
            if emp_name and emp_name not in employee_names:
                result["orphaned_count"] += 1
                result["orphaned_details"].append(nps.get("employee_name"))
        
        return result
    
    async def remove_duplicate_reviews(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Remove duplicate reviews from customer_reviews collection.
        Uses the actual field names in the collection.
        """
        result = {
            "duplicates_found": 0,
            "duplicates_removed": 0,
            "dry_run": dry_run
        }
        
        reviews = await self.db.customer_reviews.find({}).to_list(10000)
        
        seen_hashes = {}
        to_delete = []
        
        for review in reviews:
            # Use actual field names
            reviewer = review.get('reviewer_name') or review.get('author', '')
            date = review.get('review_date') or review.get('date', '')
            text = review.get('review_text') or review.get('text', '')
            source = review.get('platform') or review.get('source', '')
            
            # Only hash if we have meaningful content
            if not text:
                continue
                
            content = f"{reviewer}{date}{text}{source}"
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            if content_hash in seen_hashes:
                to_delete.append(review["_id"])
            else:
                seen_hashes[content_hash] = review["_id"]
        
        result["duplicates_found"] = len(to_delete)
        
        if not dry_run and to_delete:
            delete_result = await self.db.customer_reviews.delete_many({"_id": {"$in": to_delete}})
            result["duplicates_removed"] = delete_result.deleted_count
        
        return result
    
    async def fix_cv_server_names(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Attempt to fix CV feedback entries missing server names.
        This marks them for manual review or deletion.
        """
        result = {
            "missing_found": 0,
            "action_taken": "marked_for_review" if dry_run else "flagged",
            "dry_run": dry_run
        }
        
        missing = await self.db.cv_feedback.find({
            "$or": [
                {"server_name": None},
                {"server_name": ""},
                {"server_name": {"$exists": False}}
            ]
        }).to_list(10000)
        
        result["missing_found"] = len(missing)
        
        if not dry_run:
            # Mark these records as invalid/needs_review
            for record in missing:
                await self.db.cv_feedback.update_one(
                    {"_id": record["_id"]},
                    {"$set": {
                        "is_valid": False,
                        "needs_review": True,
                        "integrity_flag": "missing_server_name",
                        "flagged_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            result["flagged_count"] = len(missing)
        
        return result
    
    async def recalculate_all_cv_nps(self) -> Dict[str, Any]:
        """
        Recalculate all CV NPS records from raw feedback data.
        This ensures 100% accuracy.
        """
        result = {
            "records_updated": 0,
            "records_created": 0,
            "employees_processed": 0
        }
        
        # Get all valid CV feedback (with server names)
        feedback = await self.db.cv_feedback.find({
            "server_name": {"$nin": [None, ""]},
            "$or": [{"is_valid": {"$ne": False}}, {"is_valid": {"$exists": False}}]
        }, {"_id": 0}).to_list(10000)
        
        # Group by server + quarter + year
        grouped = defaultdict(list)
        for f in feedback:
            key = (f.get("server_name"), f.get("quarter"), f.get("year"))
            grouped[key].append(f)
        
        for (server_name, quarter, year), server_feedback in grouped.items():
            if not server_name or not quarter or not year:
                continue
            
            promoters = sum(1 for f in server_feedback if (f.get("rating") or 0) >= 9)
            passives = sum(1 for f in server_feedback if 7 <= (f.get("rating") or 0) <= 8)
            detractors = sum(1 for f in server_feedback if (f.get("rating") or 0) <= 6 and f.get("rating") is not None)
            total = promoters + passives + detractors
            
            if total > 0:
                nps = round(((promoters - detractors) / total) * 100)
            else:
                nps = 0
            
            # Update or create cv_nps record
            update_result = await self.db.cv_nps.update_one(
                {"employee_name": server_name, "quarter": quarter, "year": year},
                {"$set": {
                    "promoters": promoters,
                    "passives": passives,
                    "detractors": detractors,
                    "total_surveys": total,
                    "nps_score": nps,
                    "recalculated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "recalculated"
                }},
                upsert=True
            )
            
            if update_result.modified_count > 0:
                result["records_updated"] += 1
            elif update_result.upserted_id:
                result["records_created"] += 1
            
            result["employees_processed"] += 1
        
        return result


class VerificationMode:
    """
    Verification mode compares stored data against fresh scrape.
    """
    
    def __init__(self, db):
        self.db = db
    
    async def compare_cv_data(self, fresh_data: List[Dict], quarter: str, year: int) -> Dict[str, Any]:
        """
        Compare fresh CV data against stored data.
        """
        result = {
            "fresh_count": len(fresh_data),
            "stored_count": 0,
            "matches": 0,
            "missing_in_db": 0,
            "extra_in_db": 0,
            "discrepancies": []
        }
        
        # Get stored data
        stored = await self.db.cv_feedback.find({
            "quarter": quarter,
            "year": year
        }, {"_id": 0}).to_list(10000)
        
        result["stored_count"] = len(stored)
        
        # Create lookup by unique identifier (date + rating + server)
        stored_lookup = {}
        for s in stored:
            key = f"{s.get('date', '')}{s.get('rating', '')}{s.get('server_name', '')}"
            stored_lookup[key] = s
        
        fresh_keys = set()
        for f in fresh_data:
            key = f"{f.get('date', '')}{f.get('rating', '')}{f.get('server_name', '')}"
            fresh_keys.add(key)
            
            if key in stored_lookup:
                result["matches"] += 1
            else:
                result["missing_in_db"] += 1
                result["discrepancies"].append({
                    "type": "missing_in_db",
                    "data": f
                })
        
        # Check for extra in DB
        for key in stored_lookup:
            if key not in fresh_keys:
                result["extra_in_db"] += 1
                result["discrepancies"].append({
                    "type": "extra_in_db",
                    "data": stored_lookup[key]
                })
        
        result["match_rate"] = round(
            (result["matches"] / result["fresh_count"] * 100) 
            if result["fresh_count"] > 0 else 0, 2
        )
        
        return result
    
    async def compare_review_data(self, fresh_data: List[Dict], quarter: str, year: int) -> Dict[str, Any]:
        """
        Compare fresh review data against stored data.
        """
        result = {
            "fresh_count": len(fresh_data),
            "stored_count": 0,
            "matches": 0,
            "missing_in_db": 0,
            "extra_in_db": 0,
            "discrepancies": []
        }
        
        stored = await self.db.customer_reviews.find({
            "quarter": quarter,
            "year": year
        }, {"_id": 0}).to_list(10000)
        
        result["stored_count"] = len(stored)
        
        # Create lookup by review_id or content hash
        stored_lookup = {}
        for s in stored:
            review_id = s.get("review_id") or s.get("id")
            if review_id:
                stored_lookup[review_id] = s
        
        for f in fresh_data:
            review_id = f.get("review_id") or f.get("id")
            if review_id and review_id in stored_lookup:
                result["matches"] += 1
            else:
                result["missing_in_db"] += 1
        
        result["match_rate"] = round(
            (result["matches"] / result["fresh_count"] * 100) 
            if result["fresh_count"] > 0 else 0, 2
        )
        
        return result
