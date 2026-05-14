"""
Legacy Snapshots Router

This module handles the legacy /v2/snapshots/* endpoints that use the `db.snapshots` collection.
These are used by the /snapshots page in the frontend for a simpler snapshot management workflow.

Note: This is distinct from the main SnapshotWorkflow system (in snapshot_routes.py) 
which uses `db.snapshot_workflow` and powers the more sophisticated /snapshot-workflow pages.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid
import logging
import pandas as pd
import io
import os
import tempfile

# Import scoring engine
from scoring_engine import (
    EmployeeV2, QuarterSettings,
    validate_upload_columns,
    calculate_lbw_total, calculate_derived_metrics, calculate_normalized_scores,
    calculate_bonus_points, calculate_total_score, compute_total_score_dict,
    calculate_customer_voice_score, calculate_review_tracker_bonus, calculate_combined_cv_rt
)
from snapshot_slides import get_available_backgrounds

# Create router
snapshots_legacy_router = APIRouter(tags=["snapshots-legacy"])


# Pydantic model for snapshot creation
class SnapshotCreate(BaseModel):
    snapshot_date: str
    title: Optional[str] = ""
    year: int = 2026
    quarter: str = "Q1"


def register_snapshots_legacy_routes(router: APIRouter, db):
    """Register all legacy snapshot routes with the provided router and database."""
    
    async def recalculate_peer_ranks(quarter: str, year: int):
        """Recalculate peer ranks for all employees in a quarter."""
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(500)
        
        if not employees:
            return
        
        # Sort by total_score descending
        employees.sort(key=lambda x: -(x.get('total_score') or 0))
        
        # Assign peer ranks
        for i, emp in enumerate(employees):
            await db.employees_v2.update_one(
                {"id": emp["id"]},
                {"$set": {"peer_rank": i + 1}}
            )
    
    async def _sync_snapshot_to_employees_v2(snapshot_id: str, quarter: str, year: int):
        """
        Sync snapshot employee data BACK to employees_v2 collection.
        
        This is the reverse of sync_employees_to_most_recent_snapshot.
        Use after uploading data to a snapshot to update the main employee records.
        """
        # Get the snapshot
        snapshot = await db.snapshots.find_one({"id": snapshot_id})
        if not snapshot or not snapshot.get("employees"):
            logging.info(f"No employees in snapshot {snapshot_id} - skipping reverse sync")
            return 0
        
        snapshot_employees = snapshot.get("employees", [])
        updated_count = 0
        
        for snap_emp in snapshot_employees:
            emp_name = snap_emp.get("name")
            if not emp_name:
                continue
            
            # Find matching employee in employees_v2
            existing = await db.employees_v2.find_one({
                "name": {"$regex": f"^{emp_name}$", "$options": "i"},
                "quarter": quarter.upper(),
                "year": year
            })
            
            if existing:
                # Update existing employee with snapshot data (POS metrics)
                def get_val(snap_key, exist_key=None):
                    exist_key = exist_key or snap_key
                    snap_val = snap_emp.get(snap_key)
                    if snap_val is not None:
                        return snap_val
                    return existing.get(exist_key)
                
                update_fields = {
                    "guests": get_val("guests"),
                    "net_sales": get_val("net_sales"),
                    "ppa": get_val("ppa"),
                    "lbw": get_val("lbw"),
                    "lbw_per_guest": get_val("lbw_per_guest"),
                    "glassware_sales": get_val("glassware_sales"),
                    "glassware_per_guest": get_val("glassware_per_guest"),
                    "lsc_count": get_val("lsc_count"),
                    "score_ppa": get_val("score_ppa"),
                    "score_lbw": get_val("score_lbw"),
                    "score_glass": get_val("score_glass"),
                    "score_lsc": get_val("score_lsc"),
                    "updated_at": datetime.now(timezone.utc)
                }

                # Recompute weighted/pre_dar/total through the canonical
                # scoring engine — picks up per-quarter weights, RT/CV
                # rules, DAR penalty config automatically.
                settings_doc = await db.quarter_settings.find_one(
                    {"year": year, "quarter": quarter.upper()}, {"_id": 0}
                )
                settings = QuarterSettings(**settings_doc) if settings_doc else QuarterSettings(
                    year=year, quarter=quarter.upper()
                )
                scored = compute_total_score_dict({
                    "score_ppa": update_fields.get("score_ppa") or 0,
                    "score_lbw": update_fields.get("score_lbw") or 0,
                    "score_glass": update_fields.get("score_glass") or 0,
                    "score_lsc": update_fields.get("score_lsc") or 0,
                    "cv_score": existing.get("cv_score") or 0,
                    "review_tracker_bonus": existing.get("review_tracker_bonus") or 0,
                    "total_metric_bonus": existing.get("total_metric_bonus") or 0,
                    "dar_penalty": existing.get("dar_penalty") or 0,
                }, settings)
                update_fields["weighted_score"] = scored["weighted_score"]
                update_fields["pre_dar_score"] = scored["pre_dar_score"]
                update_fields["total_score"] = scored["total_score"]

                await db.employees_v2.update_one(
                    {"_id": existing["_id"]},
                    {"$set": update_fields}
                )
                updated_count += 1
            else:
                # Create new employee from snapshot data
                new_emp = {
                    "id": str(uuid.uuid4()),
                    "name": emp_name,
                    "quarter": quarter.upper(),
                    "year": year,
                    "guests": snap_emp.get("guests", 0),
                    "net_sales": snap_emp.get("net_sales", 0),
                    "ppa": snap_emp.get("ppa", 0),
                    "lbw": snap_emp.get("lbw", 0),
                    "lbw_per_guest": snap_emp.get("lbw_per_guest", 0),
                    "glassware_sales": snap_emp.get("glassware_sales", 0),
                    "glassware_per_guest": snap_emp.get("glassware_per_guest", 0),
                    "lsc_count": snap_emp.get("lsc_count", 0),
                    "score_ppa": snap_emp.get("score_ppa", 0),
                    "score_lbw": snap_emp.get("score_lbw", 0),
                    "score_glass": snap_emp.get("score_glass", 0),
                    "score_lsc": snap_emp.get("score_lsc", 0),
                    "weighted_score": snap_emp.get("total_score", 0),
                    "total_score": snap_emp.get("total_score", 0),
                    "pre_dar_score": snap_emp.get("total_score", 0),
                    "nps_score": 0,
                    "cv_score": 0,
                    "cv_promoters": 0,
                    "cv_detractors": 0,
                    "rt_mentions": 0,
                    "review_tracker_bonus": 0,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                await db.employees_v2.insert_one(new_emp)
                updated_count += 1
        
        # Recalculate ranks after update
        await recalculate_peer_ranks(quarter.upper(), year)
        
        logging.info(f"Reverse-synced {updated_count} employees from snapshot to employees_v2")
        return updated_count

    @router.post("/v2/snapshots/{snapshot_id}/sync-from-employees")
    async def sync_snapshot_from_employees(snapshot_id: str, quarter: str = "Q1", year: int = 2026):
        """
        Re-sync a specific snapshot with fresh data from employees_v2.
        This updates the snapshot with current CV scores, RT data, and recalculates sorting.
        """
        # Get all current employees
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(500)
        
        if not employees:
            raise HTTPException(status_code=404, detail=f"No employees found for {quarter} {year}")
        
        # Sort by tier, then by score
        tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
        employees.sort(key=lambda x: (
            tier_order.get(x.get('tier_label', 'C-Server'), 4),
            -(x.get('total_score') or 0)
        ))
        
        # Serialize dates
        snapshot_employees = []
        for emp in employees:
            emp_copy = emp.copy()
            if isinstance(emp_copy.get('created_at'), datetime):
                emp_copy['created_at'] = emp_copy['created_at'].isoformat()
            snapshot_employees.append(emp_copy)
        
        # Update snapshot
        result = await db.snapshots.update_one(
            {"id": snapshot_id},
            {
                "$set": {
                    "employees": snapshot_employees,
                    "employee_count": len(snapshot_employees),
                    "last_synced_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
        
        return {
            "status": "synced",
            "snapshot_id": snapshot_id,
            "employee_count": len(snapshot_employees),
            "sort_order_preview": [
                {
                    "rank": i+1,
                    "name": emp.get("name"),
                    "tier": emp.get("tier_label"),
                    "score": emp.get("total_score"),
                    "cv_score": emp.get("cv_score", 0)
                }
                for i, emp in enumerate(snapshot_employees[:10])
            ]
        }

    @router.get("/v2/snapshots")
    async def list_snapshots(year: Optional[int] = None):
        """List all snapshots, optionally filtered by year."""
        query = {}
        if year:
            query["year"] = year
        
        snapshots = await db.snapshots.find(query, {"_id": 0}).sort("snapshot_date", -1).to_list(100)
        
        # Sort employees within each snapshot by tier first, then by total_score descending
        tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
        for snapshot in snapshots:
            if "employees" in snapshot and snapshot["employees"]:
                snapshot["employees"].sort(
                    key=lambda x: (
                        tier_order.get(x.get('tier_label', 'C-Server'), 4),
                        -(x.get('total_score') or x.get('pre_dar_score') or 0)
                    )
                )
        
        return snapshots

    @router.get("/v2/snapshots/backgrounds")
    async def get_snapshot_backgrounds():
        """Get available background options for snapshots."""
        return get_available_backgrounds()

    @router.get("/v2/snapshots/{snapshot_id}")
    async def get_snapshot(snapshot_id: str):
        """Get a specific snapshot by ID."""
        snapshot = await db.snapshots.find_one({"id": snapshot_id}, {"_id": 0})
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        # Sort employees by tier first, then by total_score descending
        tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
        if "employees" in snapshot and snapshot["employees"]:
            snapshot["employees"].sort(
                key=lambda x: (
                    tier_order.get(x.get('tier_label', 'C-Server'), 4),
                    -(x.get('total_score') or x.get('pre_dar_score') or 0)
                )
            )
        
        return snapshot

    @router.post("/v2/parse-clean-pos")
    async def parse_clean_pos_preview(file: UploadFile = File(...)):
        """
        Parse a clean POS file and preview the extracted data without creating a snapshot.
        """
        from clean_pos_parser import parse_clean_pos_report
        
        contents = await file.read()
        
        result = parse_clean_pos_report(contents, file.filename)
        
        if not result["success"]:
            return {
                "success": False,
                "message": "Failed to parse file",
                "errors": result.get("errors", [])
            }
        
        return {
            "success": True,
            "message": f"Successfully parsed {len(result['employees'])} employees",
            "employees": result["employees"],
            "stats": result["stats"]
        }

    @router.post("/v2/snapshots")
    async def create_snapshot(data: SnapshotCreate):
        """Create a new snapshot capturing the current state of employee data."""
        snapshot_id = str(uuid.uuid4())
        
        # Get benchmarks from quarter settings
        settings = await db.quarter_settings.find_one(
            {"year": data.year, "quarter": data.quarter.upper()},
            {"_id": 0}
        )
        
        benchmarks = {
            "ppa_benchmark": settings.get("ppa_benchmark", 55) if settings else 55,
            "lbw_benchmark": settings.get("lbw_benchmark", 6.5) if settings else 6.5,
            "glassware_benchmark": settings.get("glassware_benchmark", 1.2) if settings else 1.2,
            "lsc_benchmark": settings.get("lsc_benchmark", 30) if settings else 30,
            "cv_benchmark": settings.get("cv_benchmark", 20) if settings else 20,
            "total_benchmark": settings.get("total_benchmark", 100) if settings else 100,
        }
        
        # Pull current employee data from employees_v2 (point-in-time capture)
        current_employees = await db.employees_v2.find(
            {"quarter": data.quarter.upper(), "year": data.year},
            {"_id": 0}
        ).to_list(500)
        
        # Format employees for snapshot storage
        snapshot_employees = []
        for emp in current_employees:
            snapshot_employees.append({
                "id": emp.get("id"),
                "name": emp.get("display_name") or emp.get("name"),
                "report_name": emp.get("report_name"),
                "job_title": emp.get("job_title", "Server"),
                "guests": emp.get("guests", 0),
                "net_sales": emp.get("net_sales", 0),
                "ppa": emp.get("ppa", 0),
                "lbw": emp.get("lbw", 0),
                "lbw_per_guest": emp.get("lbw_per_guest", 0),
                "glassware_sales": emp.get("glassware_sales", 0),
                "glassware_per_guest": emp.get("glassware_per_guest", 0),
                "lsc_count": emp.get("lsc_count", 0),
                "guests_per_lsc": emp.get("guests_per_lsc"),
                "nps_score": emp.get("nps_score", 0),
                "cv_score": emp.get("cv_score", 0),
                "cv_promoters": emp.get("cv_promoters", 0),
                "cv_detractors": emp.get("cv_detractors", 0),
                "rt_mentions": emp.get("rt_mentions", 0),
                "score_ppa": emp.get("score_ppa", 0),
                "score_lbw": emp.get("score_lbw", 0),
                "score_glass": emp.get("score_glass", 0),
                "score_lsc": emp.get("score_lsc", 0),
                "weighted_score": emp.get("weighted_score", 0),
                "total_score": emp.get("total_score", 0),
                "rank": emp.get("rank"),
                "peer_rank": emp.get("peer_rank"),
            })
        
        snapshot = {
            "id": snapshot_id,
            "snapshot_date": data.snapshot_date,
            "title": data.title,
            "year": data.year,
            "quarter": data.quarter.upper(),
            "employees": snapshot_employees,
            "benchmarks": benchmarks,
            "employee_count": len(snapshot_employees),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data_source": "employees_v2",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        
        await db.snapshots.insert_one(snapshot)
        return {
            "id": snapshot_id, 
            "message": f"Snapshot created with {len(snapshot_employees)} employees",
            "employee_count": len(snapshot_employees)
        }

    @router.post("/v2/snapshots/{snapshot_id}/upload")
    async def upload_snapshot_data(snapshot_id: str, file: UploadFile = File(...)):
        """Upload employee data for a snapshot."""
        # Get the snapshot
        snapshot = await db.snapshots.find_one({"id": snapshot_id})
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        # Read file
        contents = await file.read()
        filename = file.filename.lower()
        
        try:
            # First check for SSD Engine / consolidated format (has Master_Summary sheet)
            from pos_report_parser import is_pos_report_format, is_consolidated_format, parse_pos_report, parse_consolidated_pos_report
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
            
            # Try consolidated format FIRST (SSD Engine with Master_Summary)
            if not filename.endswith('.csv') and is_consolidated_format(tmp_path):
                logging.info("Detected CONSOLIDATED format - using specialized parser (SSD Engine)")
                pos_employees = parse_consolidated_pos_report(tmp_path)
                
                os.unlink(tmp_path)  # Clean up temp file
                
                if pos_employees and len(pos_employees) > 1:
                    logging.info(f"Found {len(pos_employees)} employees from consolidated format")
                    
                    # Get settings for scoring
                    settings_doc = await db.quarter_settings.find_one(
                        {"year": snapshot["year"], "quarter": snapshot["quarter"]},
                        {"_id": 0}
                    )
                    settings = QuarterSettings(**(settings_doc or {}))
                    
                    employees = []
                    for emp_data in pos_employees:
                        name = emp_data['name']
                        guests = emp_data.get('guests', 0) or 0
                        net_sales = emp_data.get('net_sales', 0) or 0
                        lbw = emp_data.get('lbw', 0) or 0
                        glassware_sales = emp_data.get('glassware', 0) or 0
                        lsc_count = emp_data.get('lsc_count', 0) or 0
                        
                        # Skip if no meaningful data
                        if net_sales <= 0 and lbw <= 0:
                            logging.info(f"Skipping {name} - no sales data")
                            continue
                        
                        # Calculate derived values
                        ppa = net_sales / guests if guests > 0 else 0
                        lbw_per_guest = lbw / guests if guests > 0 else 0
                        glassware_per_guest = glassware_sales / guests if guests > 0 else 0
                        guests_per_lsc = guests / lsc_count if lsc_count > 0 else None
                        
                        # Calculate scores using benchmarks
                        benchmark_ppa = settings.benchmark_ppa or 55
                        benchmark_lbw = settings.benchmark_lbw or 8
                        benchmark_glass = settings.benchmark_glass or 1.35
                        benchmark_lsc = settings.benchmark_lsc or 100
                        
                        score_ppa = (ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
                        score_lbw = (lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
                        score_glass = (glassware_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
                        score_lsc = (benchmark_lsc / guests_per_lsc) * 100 if guests_per_lsc and guests_per_lsc > 0 else 0
                        
                        # Compute base/total score through the canonical
                        # scoring engine so per-quarter weights stay in sync.
                        scored = compute_total_score_dict({
                            "score_ppa": score_ppa, "score_lbw": score_lbw,
                            "score_glass": score_glass, "score_lsc": score_lsc,
                        }, settings)
                        total_score = scored["total_score"]
                        
                        emp = {
                            "name": name,
                            "guests": guests,
                            "net_sales": round(net_sales, 2),
                            "lbw": round(lbw, 2),
                            "glassware_sales": round(glassware_sales, 2),
                            "lsc_count": lsc_count,
                            "ppa": round(ppa, 2),
                            "lbw_per_guest": round(lbw_per_guest, 2),
                            "glassware_per_guest": round(glassware_per_guest, 2),
                            "guests_per_lsc": round(guests_per_lsc, 2) if guests_per_lsc else None,
                            "score_ppa": round(score_ppa, 2),
                            "score_lbw": round(score_lbw, 2),
                            "score_glass": round(score_glass, 2),
                            "score_lsc": round(score_lsc, 2),
                            "total_score": total_score
                        }
                        employees.append(emp)
                    
                    # Update snapshot
                    await db.snapshots.update_one(
                        {"id": snapshot_id},
                        {"$set": {
                            "employees": employees,
                            "employee_count": len(employees),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "parse_method": "ssd_engine_consolidated"
                        }}
                    )
                    
                    # Sync snapshot employees to employees_v2 for dashboard metrics
                    await _sync_snapshot_to_employees_v2(snapshot_id, snapshot["quarter"], snapshot["year"])
                    
                    return {
                        "message": f"Parsed {len(employees)} employees using SSD Engine format",
                        "employee_count": len(employees),
                        "parse_method": "ssd_engine_consolidated"
                    }
            
            # Next, try the Clean POS format (simplified single-sheet format)
            from clean_pos_parser import parse_clean_pos_report
            
            # Try clean format (if it's an xlsx)
            if not filename.endswith('.csv'):
                clean_result = parse_clean_pos_report(contents, filename)
                
                if clean_result["success"] and clean_result["employees"]:
                    logging.info(f"Detected clean POS format - found {len(clean_result['employees'])} employees")
                    
                    # Get settings for scoring
                    settings_doc = await db.quarter_settings.find_one(
                        {"year": snapshot["year"], "quarter": snapshot["quarter"]},
                        {"_id": 0}
                    )
                    settings = QuarterSettings(**(settings_doc or {}))
                    
                    employees = []
                    for emp_data in clean_result["employees"]:
                        name = emp_data.get('name', '')
                        guests = emp_data.get('total_guests', 0)
                        net_sales = emp_data.get('totals', 0) or emp_data.get('net_sales', 0)
                        
                        # Calculate LBW from components
                        liquor = emp_data.get('liquor', 0)
                        beer = emp_data.get('beer', 0)
                        wine = emp_data.get('wine', 0)
                        lbw = liquor + beer + wine
                        
                        glassware_sales = emp_data.get('bar_glassware', 0)
                        
                        # Calculate LSC count from Loyalty sales ($25 per LSC card)
                        loyalty_sales = emp_data.get('loyalty', 0)
                        lsc_count = int(loyalty_sales / 25.0) if loyalty_sales > 0 else 0
                        
                        # Calculate PPA
                        ppa = (net_sales / guests) if guests > 0 else 0
                        
                        # Calculate LBW per guest and Guests per LSC
                        lbw_per_guest = (lbw / guests) if guests > 0 else 0
                        guests_per_lsc = (guests / lsc_count) if lsc_count > 0 else None
                        
                        # Calculate component scores
                        ppa_benchmark = getattr(settings, 'ppa_benchmark', None) or getattr(settings, 'benchmark_ppa', 55)
                        lbw_benchmark = getattr(settings, 'lbw_benchmark', None) or getattr(settings, 'benchmark_lbw', 8)
                        glass_benchmark = getattr(settings, 'glassware_benchmark', None) or getattr(settings, 'benchmark_glass', 1)
                        lsc_benchmark = getattr(settings, 'lsc_benchmark', None) or getattr(settings, 'benchmark_lsc', 20)
                        
                        score_ppa = (ppa / ppa_benchmark * 100) if ppa_benchmark > 0 else 0
                        score_lbw = (lbw_per_guest / lbw_benchmark * 100) if lbw_benchmark > 0 else 0
                        score_glass = (glassware_sales / guests / glass_benchmark * 100) if guests > 0 and glass_benchmark > 0 else 0
                        score_lsc = (lsc_benchmark / guests_per_lsc * 100) if guests_per_lsc and guests_per_lsc > 0 else 0
                        
                        emp = EmployeeV2(
                            employee_id=str(uuid.uuid4()),
                            name=name,
                            quarter=snapshot["quarter"],
                            year=snapshot["year"],
                            job_title="Server",
                            guests=guests,
                            net_sales=round(net_sales, 2),
                            ppa=round(ppa, 2),
                            lbw_amount=round(lbw, 2),
                            lbw_per_guest=round(lbw_per_guest, 2),
                            glassware_sales=round(glassware_sales, 2),
                            guests_per_lsc=round(guests_per_lsc, 2) if guests_per_lsc else None,
                            score_ppa=round(score_ppa, 2),
                            score_lbw=round(score_lbw, 2),
                            score_glass=round(score_glass, 2),
                            score_lsc=round(score_lsc, 2),
                            lsc_count=lsc_count,
                            liquor_sales=round(liquor, 2),
                            beer_sales=round(beer, 2),
                            wine_sales=round(wine, 2),
                            created_at=datetime.now(timezone.utc)
                        )
                        
                        emp = calculate_total_score(emp, settings)
                        
                        # Look up employee's actual job_title from employees_v2
                        existing_emp = await db.employees_v2.find_one(
                            {"name": name, "quarter": snapshot["quarter"], "year": snapshot["year"]},
                            {"_id": 0, "job_title": 1}
                        )
                        
                        actual_job_title = "Server"
                        if existing_emp and existing_emp.get("job_title"):
                            actual_job_title = existing_emp["job_title"]
                        
                        # Determine tier label based on job_title first, then score for servers
                        job_lower = actual_job_title.lower()
                        if job_lower == "trainer":
                            tier_label = "Trainer"
                        elif job_lower == "bartender":
                            tier_label = "Bartender"
                        elif emp.total_score >= settings.a_server_min_score:
                            tier_label = "A-Server"
                        elif emp.total_score >= settings.b_server_min_score:
                            tier_label = "B-Server"
                        else:
                            tier_label = "C-Server"
                        
                        emp_dict = emp.model_dump()
                        emp_dict["tier_label"] = tier_label
                        emp_dict["job_title"] = actual_job_title
                        employees.append(emp_dict)
                    
                    # Update snapshot
                    await db.snapshots.update_one(
                        {"id": snapshot_id},
                        {
                            "$set": {
                                "employees": employees,
                                "employee_count": len(employees),
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                                "parse_method": "clean_pos_format"
                            }
                        }
                    )
                    
                    os.unlink(tmp_path)
                    
                    return {
                        "message": f"Parsed {len(employees)} employees using clean POS format",
                        "employee_count": len(employees),
                        "parse_method": "clean_pos_format",
                        "stats": clean_result["stats"]
                    }
            
            # Fall back to original POS report format (multi-sheet)
            tmp_path_exists = 'tmp_path' in dir() and os.path.exists(tmp_path)
            if not tmp_path_exists:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    tmp.write(contents)
                    tmp_path = tmp.name
            
            if not filename.endswith('.csv') and is_pos_report_format(tmp_path):
                logging.info("Detected POS report format")
                
                if is_consolidated_format(tmp_path):
                    logging.info("Using CONSOLIDATED format parser (SSD Engine)")
                    pos_employees = parse_consolidated_pos_report(tmp_path)
                else:
                    logging.info("Using multi-sheet format parser")
                    pos_employees = parse_pos_report(tmp_path)
                
                os.unlink(tmp_path)
                
                if not pos_employees:
                    raise HTTPException(status_code=400, detail="Could not parse any employees from POS report")
                
                # Get settings for scoring
                settings_doc = await db.quarter_settings.find_one(
                    {"year": snapshot["year"], "quarter": snapshot["quarter"]},
                    {"_id": 0}
                )
                settings = QuarterSettings(**(settings_doc or {}))
                
                employees = []
                for emp_data in pos_employees:
                    name = emp_data['name']
                    guests = emp_data.get('guests', 0) or 0
                    net_sales = emp_data.get('net_sales', 0) or 0
                    lbw = emp_data.get('lbw', 0) or 0
                    glassware_sales = emp_data.get('glassware_sales', 0) or emp_data.get('glassware', 0) or 0
                    lsc_count = emp_data.get('lsc_count', 0) or 0
                    
                    if net_sales <= 0 and lbw <= 0:
                        logging.info(f"Skipping {name} - no sales data")
                        continue
                    
                    ppa = net_sales / guests if guests > 0 else 0
                    lbw_per_guest = lbw / guests if guests > 0 else 0
                    glassware_per_guest = glassware_sales / guests if guests > 0 else 0
                    guests_per_lsc = guests / lsc_count if lsc_count > 0 else None
                    
                    benchmark_ppa = settings.benchmark_ppa or 55
                    benchmark_lbw = settings.benchmark_lbw or 8
                    benchmark_glass = settings.benchmark_glass or 1.35
                    benchmark_lsc = settings.benchmark_lsc or 100
                    
                    score_ppa = (ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
                    score_lbw = (lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
                    score_glass = (glassware_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
                    score_lsc = (benchmark_lsc / guests_per_lsc) * 100 if guests_per_lsc and guests_per_lsc > 0 else 0
                    
                    # Compute base/total score through the canonical
                    # scoring engine so per-quarter weights stay in sync.
                    scored = compute_total_score_dict({
                        "score_ppa": score_ppa, "score_lbw": score_lbw,
                        "score_glass": score_glass, "score_lsc": score_lsc,
                    }, settings)
                    total_score = scored["total_score"]
                    
                    emp = {
                        "name": name,
                        "guests": guests,
                        "net_sales": round(net_sales, 2),
                        "lbw": round(lbw, 2),
                        "glassware_sales": round(glassware_sales, 2),
                        "lsc_count": lsc_count,
                        "ppa": round(ppa, 2),
                        "lbw_per_guest": round(lbw_per_guest, 2),
                        "glassware_per_guest": round(glassware_per_guest, 2),
                        "guests_per_lsc": round(guests_per_lsc, 2) if guests_per_lsc else None,
                        "score_ppa": round(score_ppa, 2),
                        "score_lbw": round(score_lbw, 2),
                        "score_glass": round(score_glass, 2),
                        "score_lsc": round(score_lsc, 2),
                        "total_score": total_score
                    }
                    employees.append(emp)
                
                await db.snapshots.update_one(
                    {"id": snapshot_id},
                    {"$set": {
                        "employees": employees,
                        "employee_count": len(employees),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                return {
                    "message": "POS report parsed successfully",
                    "employee_count": len(employees),
                    "format": "pos_report"
                }
            
            # Clean up temp file if not POS format
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            
            # Standard table format parsing
            if filename.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(contents))
            else:
                df = pd.read_excel(io.BytesIO(contents))
            
            # Clean column names
            df.columns = [str(col).strip() if col is not None else f"Unnamed_{i}" for i, col in enumerate(df.columns)]
            
            # Validate columns
            column_validation = validate_upload_columns(list(df.columns))
            if not column_validation["valid"]:
                raise HTTPException(status_code=400, detail=f"Missing required columns: {column_validation['missing_required']}")
            
            mapping = column_validation["mapping"]
            
            # Get settings for scoring
            settings_doc = await db.quarter_settings.find_one(
                {"year": snapshot["year"], "quarter": snapshot["quarter"]},
                {"_id": 0}
            )
            settings = QuarterSettings(**(settings_doc or {}))
            
            # Helper functions to safely convert values
            def safe_int(val, default=0):
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return default
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return default
            
            def safe_float(val, default=0.0):
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return default
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default
            
            def is_valid_employee_name(name: str) -> bool:
                """Filter out garbage names from XLSX parsing."""
                if not name or len(name) < 2:
                    return False
                
                invalid_patterns = [
                    "printed by", "net sls", "net sis", "net sales", "taxes",
                    "avg.", "average", "total", "subtotal", "grand total",
                    "report", "date:", "page", "location", "store",
                    "bglv", "edc", "pos", "server:", "employee:",
                    "unnamed", "column", "header", "footer",
                    "liquor", "beer", "wine", "glassware", "guests",
                    "lsc", "count", "sales", "-----", "=====", "____"
                ]
                
                name_lower = name.lower().strip()
                
                for pattern in invalid_patterns:
                    if pattern in name_lower:
                        return False
                
                if not any(c.isalpha() for c in name):
                    return False
                
                if name.replace(" ", "").replace(".", "").isdigit():
                    return False
                
                if name[0] in "0123456789.-_=+*&^%$#@!~`":
                    return False
                
                if len(name) > 50:
                    return False
                
                return True
            
            employees = []
            for idx, row in df.iterrows():
                try:
                    name = str(row.get(mapping["name"], "")).strip()
                    if not name or name == "nan":
                        continue
                    
                    if not is_valid_employee_name(name):
                        logging.info(f"Skipping invalid name: {name}")
                        continue
                    
                    job_title = "Server"
                    if mapping.get("job_title"):
                        val = row.get(mapping["job_title"])
                        if val is not None and not pd.isna(val) and str(val).strip() and str(val).strip().lower() != "nan":
                            job_title = str(val).strip()
                    
                    guests = safe_int(row.get(mapping.get("guests", "")))
                    if guests <= 0:
                        continue
                    
                    emp = EmployeeV2(
                        id=str(uuid.uuid4()),
                        name=name,
                        job_title=job_title,
                        guests=guests,
                        net_sales=safe_float(row.get(mapping.get("net_sales", ""))),
                        liquor_sales=safe_float(row.get(mapping.get("liquor_sales", ""))),
                        beer_sales=safe_float(row.get(mapping.get("beer_sales", ""))),
                        wine_sales=safe_float(row.get(mapping.get("wine_sales", ""))),
                        glassware_sales=safe_float(row.get(mapping.get("glassware_sales", ""))),
                        lsc_count=safe_int(row.get(mapping.get("lsc_count", ""))),
                        cv_promoters=safe_int(row.get(mapping.get("cv_promoters", ""))),
                        cv_detractors=safe_int(row.get(mapping.get("cv_detractors", ""))),
                        review_mentions=safe_int(row.get(mapping.get("review_mentions", ""))),
                        year=snapshot["year"],
                        quarter=snapshot["quarter"],
                    )
                    
                    emp = calculate_lbw_total(emp)
                    emp = calculate_derived_metrics(emp)
                    emp = calculate_customer_voice_score(emp)
                    emp = calculate_review_tracker_bonus(emp)
                    emp = calculate_combined_cv_rt(emp)
                    emp = calculate_normalized_scores(emp, settings)
                    emp = calculate_bonus_points(emp, settings)
                    emp = calculate_total_score(emp, settings)
                    
                    job_title = (emp.job_title or "Server").strip().lower()
                    if job_title == "trainer":
                        tier_label = "Trainer"
                    elif job_title == "bartender":
                        tier_label = "Bartender"
                    elif emp.total_score >= settings.a_server_min_score:
                        tier_label = "A-Server"
                    elif emp.total_score >= settings.b_server_min_score:
                        tier_label = "B-Server"
                    else:
                        tier_label = "C-Server"
                    
                    emp_dict = emp.model_dump()
                    emp_dict["tier_label"] = tier_label
                    employees.append(emp_dict)
                except Exception as e:
                    logging.warning(f"Error processing row {idx}: {e}")
                    continue
            
            # Sort employees by tier hierarchy and score
            tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
            employees.sort(key=lambda x: (tier_order.get(x.get("tier_label", "C-Server"), 4), -(x.get("total_score", 0) or 0)))
            
            # Update snapshot
            await db.snapshots.update_one(
                {"id": snapshot_id},
                {
                    "$set": {
                        "employees": employees,
                        "employee_count": len(employees),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # SYNC TO MAIN EMPLOYEES_V2 COLLECTION (only if latest snapshot)
            latest_snapshot = await db.snapshots.find_one(
                {"year": snapshot["year"], "quarter": snapshot["quarter"]},
                {"_id": 0, "snapshot_date": 1, "id": 1},
                sort=[("snapshot_date", -1)]
            )
            
            current_snapshot_date = snapshot.get("snapshot_date", "")
            latest_snapshot_date = latest_snapshot.get("snapshot_date", "") if latest_snapshot else ""
            
            should_sync = current_snapshot_date >= latest_snapshot_date
            
            if should_sync:
                await db.employees_v2.delete_many({
                    "year": snapshot["year"],
                    "quarter": snapshot["quarter"]
                })
                
                if employees:
                    main_employees = []
                    for emp in employees:
                        main_emp = emp.copy()
                        if isinstance(main_emp.get('created_at'), datetime):
                            main_emp['created_at'] = main_emp['created_at'].isoformat()
                        elif not main_emp.get('created_at'):
                            main_emp['created_at'] = datetime.now(timezone.utc).isoformat()
                        main_employees.append(main_emp)
                    
                    await db.employees_v2.insert_many(main_employees)
                    logging.info(f"Synced {len(main_employees)} employees to employees_v2 (snapshot_date: {current_snapshot_date})")
                
                return {
                    "message": "Snapshot data uploaded and synced to Dashboard",
                    "employee_count": len(employees),
                    "synced_to_dashboard": True
                }
            else:
                logging.info(f"Skipped sync - snapshot {current_snapshot_date} is not the latest (latest is {latest_snapshot_date})")
                return {
                    "message": f"Snapshot data uploaded. Dashboard NOT updated (this snapshot date {current_snapshot_date} is older than {latest_snapshot_date})",
                    "employee_count": len(employees),
                    "synced_to_dashboard": False,
                    "reason": f"Snapshot date {current_snapshot_date} is not the latest. Latest is {latest_snapshot_date}."
                }
            
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

    @router.post("/v2/snapshots/{snapshot_id}/recalculate")
    async def recalculate_snapshot(snapshot_id: str):
        """Recalculate all scores for an existing snapshot without re-uploading data."""
        snapshot = await db.snapshots.find_one({"id": snapshot_id})
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        employees_data = snapshot.get("employees", [])
        if not employees_data:
            raise HTTPException(status_code=400, detail="Snapshot has no employee data to recalculate")
        
        # Get settings for scoring
        settings_doc = await db.quarter_settings.find_one(
            {"year": snapshot["year"], "quarter": snapshot["quarter"]},
            {"_id": 0}
        )
        settings = QuarterSettings(**(settings_doc or {}))
        
        # Fetch NPS data from cv_nps collection for this quarter
        nps_records = await db.cv_nps.find(
            {"quarter": snapshot["quarter"], "year": snapshot["year"]},
            {"_id": 0}
        ).to_list(1000)
        
        # Create lookup by employee name (lowercase for matching)
        nps_lookup = {}
        for nps in nps_records:
            name = (nps.get("employee_name") or "").strip().lower()
            if name:
                nps_lookup[name] = nps
        
        # Import smart name matcher
        from name_matcher import get_nps_for_employee_smart, normalize_name
        
        # Build employee aliases lookup from employees collection
        all_employees = await db.employees_v2.find(
            {"quarter": snapshot["quarter"], "year": snapshot["year"]},
            {"_id": 0, "name": 1, "aliases": 1}
        ).to_list(1000)
        employee_aliases_map = {e["name"]: e.get("aliases", []) for e in all_employees}
        
        # Function to match NPS records with smart nickname handling
        def get_nps_for_employee(emp_name: str) -> dict:
            aliases = employee_aliases_map.get(emp_name, [])
            nps_data, match_reason = get_nps_for_employee_smart(emp_name, nps_lookup, aliases)
            return nps_data
        
        # Fetch review mentions from customer_reviews collection
        quarter_dates = {
            "Q1": ("01-01", "03-31"),
            "Q2": ("04-01", "06-30"),
            "Q3": ("07-01", "09-30"),
            "Q4": ("10-01", "12-31")
        }
        q_start, q_end = quarter_dates.get(snapshot["quarter"], ("01-01", "12-31"))
        date_start = f"{snapshot['year']}-{q_start}"
        date_end = f"{snapshot['year']}-{q_end}"
        
        review_pipeline = [
            {"$match": {
                "$or": [
                    {"review_date": {"$gte": date_start, "$lte": date_end}},
                    {"review_date": None, "quarter": snapshot["quarter"], "year": snapshot["year"]}
                ]
            }},
            {"$unwind": {"path": "$employee_mentions", "preserveNullAndEmptyArrays": False}},
            {"$group": {
                "_id": "$employee_mentions.name",
                "mentions": {"$sum": 1}
            }}
        ]
        review_mentions_cursor = db.customer_reviews.aggregate(review_pipeline)
        review_mentions_data = await review_mentions_cursor.to_list(1000)
        review_lookup = {r["_id"].lower(): r["mentions"] for r in review_mentions_data if r.get("_id")}
        
        # Build a function to match partial names
        def get_review_mentions_for_employee(emp_name: str) -> int:
            emp_lower = emp_name.lower()
            first_name = emp_lower.split()[0] if emp_lower.split() else ""
            
            if emp_lower in review_lookup:
                return review_lookup[emp_lower]
            
            if first_name in review_lookup:
                return review_lookup[first_name]
            
            for mention_name, count in review_lookup.items():
                if first_name.startswith(mention_name) or mention_name.startswith(first_name[:3]):
                    return count
            
            return 0
        
        recalculated_employees = []
        
        # Get actual job titles from employees_v2 for reference
        all_emp_data = await db.employees_v2.find(
            {"quarter": snapshot["quarter"], "year": snapshot["year"]},
            {"_id": 0, "name": 1, "job_title": 1}
        ).to_list(500)
        job_title_lookup = {e["name"].lower(): e.get("job_title", "Server") for e in all_emp_data}
        
        for emp_data in employees_data:
            try:
                emp_name = emp_data.get("name", "Unknown")
                emp_name_lower = emp_name.strip().lower()
                
                nps_data = get_nps_for_employee(emp_name)
                nps_score = nps_data.get("nps_score", 0) or 0
                cv_promoters = nps_data.get("promoters", 0) or 0
                cv_passives = nps_data.get("passives", 0) or 0
                cv_detractors = nps_data.get("detractors", 0) or 0
                
                review_mentions = get_review_mentions_for_employee(emp_name)
                
                actual_job_title = job_title_lookup.get(emp_name_lower, emp_data.get("job_title", "Server"))
                
                emp = EmployeeV2(
                    id=emp_data.get("id", str(uuid.uuid4())),
                    name=emp_name,
                    job_title=actual_job_title,
                    guests=emp_data.get("guests", 0),
                    net_sales=emp_data.get("net_sales", 0),
                    liquor_sales=emp_data.get("liquor_sales", 0),
                    beer_sales=emp_data.get("beer_sales", 0),
                    wine_sales=emp_data.get("wine_sales", 0),
                    glassware_sales=emp_data.get("glassware_sales", 0),
                    lsc_count=emp_data.get("lsc_count", 0),
                    cv_promoters=cv_promoters,
                    cv_passives=cv_passives,
                    cv_detractors=cv_detractors,
                    review_mentions=review_mentions,
                    nps_score=nps_score,
                    year=snapshot["year"],
                    quarter=snapshot["quarter"],
                )
                
                emp = calculate_lbw_total(emp)
                emp = calculate_derived_metrics(emp)
                emp = calculate_customer_voice_score(emp)
                emp = calculate_review_tracker_bonus(emp)
                emp = calculate_combined_cv_rt(emp)
                emp = calculate_normalized_scores(emp, settings)
                emp = calculate_bonus_points(emp, settings)
                emp = calculate_total_score(emp, settings)
                
                job_title = (emp.job_title or "Server").strip().lower()
                if job_title == "trainer":
                    tier_label = "Trainer"
                elif job_title == "bartender":
                    tier_label = "Bartender"
                elif emp.total_score >= settings.a_server_min_score:
                    tier_label = "A-Server"
                elif emp.total_score >= settings.b_server_min_score:
                    tier_label = "B-Server"
                else:
                    tier_label = "C-Server"
                
                emp_dict = emp.model_dump()
                emp_dict["tier_label"] = tier_label
                emp_dict["nps_score"] = nps_score
                recalculated_employees.append(emp_dict)
            except Exception as e:
                logging.warning(f"Error recalculating employee {emp_data.get('name')}: {e}")
                continue
        
        # Sort by tier and score
        tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
        recalculated_employees.sort(key=lambda x: (tier_order.get(x.get("tier_label", "C-Server"), 4), -(x.get("total_score", 0) or 0)))
        
        # Update snapshot
        await db.snapshots.update_one(
            {"id": snapshot_id},
            {
                "$set": {
                    "employees": recalculated_employees,
                    "employee_count": len(recalculated_employees),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # SYNC TO MAIN EMPLOYEES_V2 COLLECTION (only if latest snapshot)
        latest_snapshot = await db.snapshots.find_one(
            {"year": snapshot["year"], "quarter": snapshot["quarter"]},
            {"_id": 0, "snapshot_date": 1, "id": 1},
            sort=[("snapshot_date", -1)]
        )
        
        current_snapshot_date = snapshot.get("snapshot_date", "")
        latest_snapshot_date = latest_snapshot.get("snapshot_date", "") if latest_snapshot else ""
        
        should_sync = current_snapshot_date >= latest_snapshot_date
        
        if should_sync:
            # PRESERVE custom job titles from existing employees before deleting
            existing_employees = await db.employees_v2.find(
                {"year": snapshot["year"], "quarter": snapshot["quarter"]},
                {"_id": 0, "name": 1, "job_title": 1}
            ).to_list(500)
            
            preserved_job_titles = {}
            for emp in existing_employees:
                job = (emp.get("job_title") or "").lower()
                if job and job not in ["server", ""]:
                    preserved_job_titles[emp["name"].lower()] = emp["job_title"]
            
            logging.info(f"Recalculate: Preserved {len(preserved_job_titles)} custom job titles")
            
            await db.employees_v2.delete_many({
                "year": snapshot["year"],
                "quarter": snapshot["quarter"]
            })
            
            if recalculated_employees:
                main_employees = []
                for emp in recalculated_employees:
                    main_emp = emp.copy()
                    if isinstance(main_emp.get('created_at'), datetime):
                        main_emp['created_at'] = main_emp['created_at'].isoformat()
                    elif not main_emp.get('created_at'):
                        main_emp['created_at'] = datetime.now(timezone.utc).isoformat()
                    
                    # Restore preserved job title if this employee had one
                    emp_name_lower = main_emp['name'].lower()
                    if emp_name_lower in preserved_job_titles:
                        main_emp['job_title'] = preserved_job_titles[emp_name_lower]
                        if main_emp['job_title'].lower() in ['trainer', 'bartender']:
                            main_emp['tier_label'] = main_emp['job_title'].title()
                            logging.info(f"Restored job title '{main_emp['job_title']}' for {main_emp['name']}")
                    
                    main_employees.append(main_emp)
                
                await db.employees_v2.insert_many(main_employees)
                logging.info(f"Synced {len(main_employees)} recalculated employees to employees_v2 (snapshot_date: {current_snapshot_date})")
            
            return {
                "message": "Scores recalculated and synced to Dashboard",
                "employee_count": len(recalculated_employees),
                "synced_to_dashboard": True
            }
        else:
            logging.info(f"Skipped sync - snapshot {current_snapshot_date} is not the latest (latest is {latest_snapshot_date})")
            return {
                "message": f"Scores recalculated. Dashboard NOT updated (this snapshot date {current_snapshot_date} is older than {latest_snapshot_date})",
                "employee_count": len(recalculated_employees),
                "synced_to_dashboard": False,
                "reason": f"Snapshot date {current_snapshot_date} is not the latest. Latest is {latest_snapshot_date}."
            }

    @router.delete("/v2/snapshots/{snapshot_id}")
    async def delete_snapshot(snapshot_id: str):
        """Delete a snapshot."""
        result = await db.snapshots.delete_one({"id": snapshot_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return {"message": "Snapshot deleted successfully"}
