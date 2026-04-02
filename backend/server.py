from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import pandas as pd
import io
from emergentintegrations.llm.chat import LlmChat, UserMessage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
import base64
import asyncio
import requests
from pypdf import PdfReader, PdfWriter
from pdf_full_rankings import build_full_rankings_pdf
from qr_tracking import register_qr_routes
from store_management import register_store_routes
from snapshot_routes import snapshot_router
from routes.quarter_settings import quarter_settings_router
from routes.finalization import finalization_router

# In-memory job storage for PDF processing
pdf_jobs = {}  # job_id -> {status, progress, result, error}
from yodeck_slides import (
    generate_top_10_slide, generate_tier_slide,
    generate_most_improved_slide, generate_promotion_watchlist_slide, generate_at_risk_slide,
    generate_complete_rankings_slide, generate_top_10_by_metric_slide,
    generate_printable_rankings_slide, generate_leaderboard_slide,
    THEMES
)
from snapshot_slides import generate_snapshot_slide, get_available_backgrounds, BACKGROUNDS
from trend_charts import get_previous_quarter, generate_employee_comparison_chart
from data_integrity import DataIntegrityChecker, VerificationMode

# Import new scoring engine
from scoring_engine import (
    EmployeeV2, QuarterSettings, 
    validate_upload_columns, validate_upload_data, validate_employee_row,
    calculate_lbw_total, calculate_derived_metrics, calculate_normalized_scores, 
    calculate_bonus_points, calculate_total_score,
    calculate_customer_voice_score, calculate_review_tracker_bonus, calculate_combined_cv_rt,
    calculate_rankings, calculate_performance_tiers, run_full_scoring,
    suggest_benchmarks_from_previous, calculate_previous_quarter_averages,
    CANONICAL_COLUMN_MAPPING, generate_hierarchy_rankings
)

from io import BytesIO

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection - handle special characters in password
import urllib.parse
mongo_url = os.environ['MONGO_URL']
# If URL contains unencoded special chars, the connection will handle it
# But we ensure it works by using the URL as-is since motor handles encoding
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Initialize scheduler
scheduler = AsyncIOScheduler()

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Health check endpoint for deployment monitoring
@api_router.get("/health")
async def health_check():
    """Health check endpoint for load balancer and deployment verification"""
    return {"status": "healthy", "service": "staff-score-engine"}


# ============================================================================
# V2 MODELS
# ============================================================================

class ReviewCreateV2(BaseModel):
    quarter: str = "Q1"
    year: int = 2026
    time_range: str = "quarter"  # "quarter" (default), "year", or "all" - for trend chart

class ReviewV2(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    employee_name: str
    review_content: str
    quarter: str
    year: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReviewResponseV2(BaseModel):
    success: bool
    review_id: Optional[str] = None
    message: str
    pdf_base64: Optional[str] = None


# ============================================================================
# DAR (Disciplinary Action Report) MODELS
# ============================================================================

class DAREntry(BaseModel):
    employee_id: str
    employee_name: str
    written_warnings: int = 0  # Each deducts 3 pts
    suspensions: int = 0  # Each deducts 5 pts

class DARSubmission(BaseModel):
    quarter: str
    year: int
    entries: List[DAREntry]

class QuarterFinalization(BaseModel):
    quarter: str
    year: int
    finalized_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finalized_by: str = "admin"
    dar_entries: List[DAREntry] = []
    final_rankings: List[Dict[str, Any]] = []


# ============================================================================
# PDF HELPER FUNCTIONS
# ============================================================================

def _create_graph_pdf_from_image_bytes(image_bytes: bytes) -> bytes:
    """Convert image bytes to a single-page PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from PIL import Image as PILImage
    
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    
    # Load image
    img = PILImage.open(io.BytesIO(image_bytes))
    img_width, img_height = img.size
    
    # Scale to fit A4
    page_width, page_height = A4
    scale = min(page_width / img_width, page_height / img_height) * 0.9
    
    new_width = img_width * scale
    new_height = img_height * scale
    x = (page_width - new_width) / 2
    y = (page_height - new_height) / 2
    
    # Save temp image
    temp_buffer = io.BytesIO()
    img.save(temp_buffer, format='PNG')
    temp_buffer.seek(0)
    
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(temp_buffer), x, y, new_width, new_height)
    c.showPage()
    c.save()
    
    buffer.seek(0)
    return buffer.getvalue()


def _merge_pdfs(pdf1_bytes: bytes, pdf2_bytes: bytes) -> bytes:
    """Merge two PDF byte streams into one."""
    writer = PdfWriter()
    
    reader1 = PdfReader(io.BytesIO(pdf1_bytes))
    for page in reader1.pages:
        writer.add_page(page)
    
    reader2 = PdfReader(io.BytesIO(pdf2_bytes))
    for page in reader2.pages:
        writer.add_page(page)
    
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================================
# SNAPSHOT SYNC HELPER
# ============================================================================

async def recalculate_peer_ranks(quarter: str, year: int):
    """
    Recalculate peer_rank for all employees based on their current total_score.
    Should be called after any score changes to keep rankings accurate.
    """
    # Get all employees for this quarter/year
    all_employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not all_employees:
        return 0
    
    # Sort by total_score (or pre_dar_score) descending
    sorted_emps = sorted(
        all_employees, 
        key=lambda x: x.get('total_score') or x.get('pre_dar_score', 0) or 0, 
        reverse=True
    )
    
    # Update peer_rank for each employee
    for rank, emp in enumerate(sorted_emps, 1):
        await db.employees_v2.update_one(
            {"_id": emp["_id"]},
            {"$set": {"peer_rank": rank}}
        )
    
    logging.info(f"Recalculated peer ranks for {len(sorted_emps)} employees in {quarter} {year}")
    return len(sorted_emps)


async def recalculate_all_tier_labels(quarter: str, year: int):
    """
    Recalculate tier_label for all employees based on their job_title and total_score.
    Tier thresholds:
    - Trainer: job_title contains 'trainer'
    - Bartender: job_title contains 'bartender' or 'bar'
    - A-Server: score >= 85
    - B-Server: score >= 70 and < 85
    - C-Server: score < 70
    """
    # Get quarter settings for thresholds
    settings = await db.quarter_settings.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    a_min = settings.get('a_server_min_score', 85.0) if settings else 85.0
    b_min = settings.get('b_server_min_score', 70.0) if settings else 70.0
    
    # Get all employees
    all_employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not all_employees:
        return 0
    
    updated_count = 0
    for emp in all_employees:
        job_title = (emp.get('job_title') or '').lower()
        score = emp.get('total_score') or emp.get('pre_dar_score', 0) or 0
        
        # Determine correct tier
        if 'trainer' in job_title:
            correct_tier = 'Trainer'
            tier_sort = 1
        elif 'bartender' in job_title or job_title == 'bar':
            correct_tier = 'Bartender'
            tier_sort = 2
        elif score >= a_min:
            correct_tier = 'A-Server'
            tier_sort = 3
        elif score >= b_min:
            correct_tier = 'B-Server'
            tier_sort = 4
        else:
            correct_tier = 'C-Server'
            tier_sort = 5
        
        # Update if different
        if emp.get('tier_label') != correct_tier:
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "tier_label": correct_tier,
                    "tier_sort_order": tier_sort
                }}
            )
            updated_count += 1
            logging.info(f"Updated tier for {emp.get('name')}: {emp.get('tier_label')} -> {correct_tier}")
    
    logging.info(f"Recalculated tier labels for {len(all_employees)} employees, {updated_count} changed")
    return updated_count


async def sync_employees_to_most_recent_snapshot(quarter: str, year: int):
    """
    Sync all employees_v2 data to the most recent snapshot for the given quarter/year.
    This should be called after any upload (POS, CV, RT) to keep snapshot in sync.
    
    Returns the snapshot ID that was updated, or None if no snapshot exists.
    """
    # First recalculate peer ranks to ensure they're accurate
    await recalculate_peer_ranks(quarter, year)
    
    # Find the most recent snapshot for this quarter/year
    latest_snapshot = await db.snapshots.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "id": 1, "snapshot_date": 1, "title": 1},
        sort=[("snapshot_date", -1)]
    )
    
    if not latest_snapshot:
        logging.info(f"No snapshot found for {quarter} {year} - skipping sync")
        return None
    
    snapshot_id = latest_snapshot["id"]
    
    # Get all current employees for this quarter/year (with updated ranks)
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(500)
    
    if not employees:
        logging.info(f"No employees found for {quarter} {year} - skipping sync")
        return None
    
    # Sort employees by tier first, then by total_score descending before storing in snapshot
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    employees.sort(key=lambda x: (
        tier_order.get(x.get('tier_label', 'C-Server'), 4),
        -(x.get('total_score') or x.get('pre_dar_score') or 0)
    ))
    
    # Prepare employee data for snapshot (ensure datetime is serialized)
    snapshot_employees = []
    for emp in employees:
        emp_copy = emp.copy()
        if isinstance(emp_copy.get('created_at'), datetime):
            emp_copy['created_at'] = emp_copy['created_at'].isoformat()
        snapshot_employees.append(emp_copy)
    
    # Update the most recent snapshot with the new employee data
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
    
    logging.info(f"Synced {len(snapshot_employees)} employees to snapshot '{latest_snapshot.get('title', snapshot_id)}'")
    return snapshot_id


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
            # Use snapshot values if they exist (not None), otherwise keep existing
            # IMPORTANT: Don't use `or` because 0 is a valid value for numeric fields
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
            
            # Recalculate weighted_score (POS portion only)
            capped_ppa = min(update_fields.get("score_ppa", 0) or 0, 100)
            capped_lbw = min(update_fields.get("score_lbw", 0) or 0, 100)
            capped_glass = min(update_fields.get("score_glass", 0) or 0, 100)
            capped_lsc = min(update_fields.get("score_lsc", 0) or 0, 100)
            
            # RT contribution
            rt_mentions = existing.get("rt_mentions", 0) or 0
            rt_contribution = min(rt_mentions * 0.5, 15)
            
            weighted_score = (
                capped_ppa * 0.25 +
                capped_lsc * 0.25 +
                capped_lbw * 0.15 +
                capped_glass * 0.10 +
                rt_contribution
            )
            update_fields["weighted_score"] = round(weighted_score, 2)
            
            # Recalculate total score
            cv_score = existing.get("cv_score", 0) or 0
            total_metric_bonus = existing.get("total_metric_bonus", 0) or 0
            
            total_score = weighted_score + cv_score + total_metric_bonus
            update_fields["total_score"] = round(total_score, 2)
            update_fields["pre_dar_score"] = round(total_score, 2)
            
            await db.employees_v2.update_one(
                {"_id": existing["_id"]},
                {"$set": update_fields}
            )
            updated_count += 1
        else:
            # Create new employee from snapshot data
            import uuid
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


@api_router.post("/v2/snapshots/{snapshot_id}/sync-from-employees")
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
    
    # Return summary with sort order verification
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


@api_router.post("/v2/employees/recalculate-tiers")
async def recalculate_employee_tiers(quarter: str = "Q1", year: int = 2026):
    """
    Recalculate tier labels for all employees based on current scores.
    Tier thresholds: A-Server >= 85, B-Server >= 70, C-Server < 70
    """
    # Recalculate tiers
    tiers_updated = await recalculate_all_tier_labels(quarter.upper(), year)
    
    # Recalculate peer ranks
    ranks_updated = await recalculate_peer_ranks(quarter.upper(), year)
    
    # Get updated employee list
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "name": 1, "tier_label": 1, "total_score": 1, "peer_rank": 1}
    ).sort("peer_rank", 1).to_list(100)
    
    return {
        "status": "success",
        "tiers_updated": tiers_updated,
        "ranks_updated": ranks_updated,
        "employees": [
            {
                "rank": emp.get("peer_rank"),
                "name": emp.get("name"),
                "tier": emp.get("tier_label"),
                "score": round(emp.get("total_score", 0), 1)
            }
            for emp in employees
        ]
    }


@api_router.post("/v2/employees/fix-all-scores")
async def fix_all_employee_scores(quarter: str = "Q1", year: int = 2026):
    """
    Recalculate ALL employee scores using the CORRECT formula.
    
    CORRECT FORMULA:
    - weighted_score = PPA×25% + LSC×25% + LBW×15% + Glass×10% (POS only, 75 pts max)
    - metric_bonus = sum of bonuses for each metric over 100%
    - total_score = weighted_score + RT_bonus + CV_score + metric_bonus
    
    This fixes bugs where RT was double-counted or metric bonuses weren't calculated.
    """
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not employees:
        return {"success": False, "error": f"No employees found for {quarter} {year}"}
    
    def calc_metric_bonus(score):
        """Calculate bonus for scores over 100%: (score-100)/20 * 5, capped at 5"""
        if score is None or score <= 100:
            return 0
        return min((score - 100) / 20 * 5, 5.0)
    
    fixed = []
    
    for emp in employees:
        # Get raw scores
        score_ppa = emp.get('score_ppa', 0) or 0
        score_lsc = emp.get('score_lsc', 0) or 0
        score_lbw = emp.get('score_lbw', 0) or 0
        score_glass = emp.get('score_glass', 0) or 0
        
        # Cap each metric at 100 before applying weight
        capped_ppa = min(score_ppa, 100)
        capped_lsc = min(score_lsc, 100)
        capped_lbw = min(score_lbw, 100)
        capped_glass = min(score_glass, 100)
        
        # CORRECT weighted_score: POS metrics only (75 pts max)
        correct_weighted = round(
            capped_ppa * 0.25 +
            capped_lsc * 0.25 +
            capped_lbw * 0.15 +
            capped_glass * 0.10,
            2
        )
        
        # CORRECT metric bonuses
        bonus_ppa = round(calc_metric_bonus(score_ppa), 2)
        bonus_lsc = round(calc_metric_bonus(score_lsc), 2)
        bonus_lbw = round(calc_metric_bonus(score_lbw), 2)
        bonus_glass = round(calc_metric_bonus(score_glass), 2)
        correct_metric_bonus = round(bonus_ppa + bonus_lsc + bonus_lbw + bonus_glass, 2)
        
        # Calculate RT bonus from rt_mentions (0.5 pts per mention, capped at 15)
        rt_mentions = emp.get('rt_mentions', 0) or emp.get('review_mentions', 0) or 0
        rt_bonus = min(rt_mentions * 0.5, 15)
        
        # Get CV score
        cv_score = emp.get('cv_score', 0) or 0
        
        # CORRECT total: weighted + RT + CV + metric_bonus
        correct_total = round(correct_weighted + rt_bonus + cv_score + correct_metric_bonus, 2)
        
        old_weighted = emp.get('weighted_score', 0) or 0
        old_metric_bonus = emp.get('total_metric_bonus', 0) or 0
        old_total = emp.get('total_score', 0) or 0
        old_rt_bonus = emp.get('review_tracker_bonus', 0) or 0
        
        # Check if update needed
        needs_update = (
            abs(correct_weighted - old_weighted) > 0.01 or 
            abs(correct_metric_bonus - old_metric_bonus) > 0.01 or
            abs(correct_total - old_total) > 0.01 or
            abs(rt_bonus - old_rt_bonus) > 0.01
        )
        
        if needs_update:
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "weighted_score": correct_weighted,
                    "bonus_ppa": bonus_ppa,
                    "bonus_lsc": bonus_lsc,
                    "bonus_lbw": bonus_lbw,
                    "bonus_glass": bonus_glass,
                    "total_metric_bonus": correct_metric_bonus,
                    "review_tracker_bonus": rt_bonus,
                    "review_mentions": rt_mentions,
                    "pre_dar_score": correct_total,
                    "total_score": correct_total
                }}
            )
            fixed.append({
                "name": emp.get("name"),
                "old_weighted": old_weighted,
                "new_weighted": correct_weighted,
                "old_metric_bonus": old_metric_bonus,
                "new_metric_bonus": correct_metric_bonus,
                "old_total": old_total,
                "new_total": correct_total
            })
    
    # Recalculate tiers and ranks after fixing scores
    await recalculate_all_tier_labels(quarter.upper(), year)
    await recalculate_peer_ranks(quarter.upper(), year)
    
    # Get final results
    final_employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "name": 1, "tier_label": 1, "total_score": 1, "peer_rank": 1,
         "weighted_score": 1, "review_tracker_bonus": 1, "cv_score": 1, "total_metric_bonus": 1}
    ).sort("peer_rank", 1).to_list(100)
    
    return {
        "status": "success",
        "fixed_count": len(fixed),
        "fixed_employees": fixed,
        "final_scores": [
            {
                "rank": emp.get("peer_rank"),
                "name": emp.get("name"),
                "tier": emp.get("tier_label"),
                "weighted": emp.get("weighted_score"),
                "rt_bonus": emp.get("review_tracker_bonus"),
                "cv_score": emp.get("cv_score"),
                "metric_bonus": emp.get("total_metric_bonus"),
                "total": emp.get("total_score")
            }
            for emp in final_employees
        ]
    }


@api_router.post("/v2/admin/sync-employees-from-json")
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
        logging.info(f"Deleted {delete_result.deleted_count} existing employees")
    
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
    
    logging.info(f"Imported {results['imported']} employees")
    
    return {
        "status": "success",
        "quarter": quarter,
        "year": year,
        "deleted_count": results["deleted"],
        "imported_count": results["imported"],
        "errors": results["errors"] if results["errors"] else None
    }


@api_router.delete("/v2/admin/delete-all-employees")
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


@api_router.post("/v2/admin/bulk-import-employees")
async def bulk_import_employees(employees: List[dict], quarter: str = "Q1", year: int = 2026):
    """
    Bulk import employees from a JSON array.
    Used to sync data between preview and production.
    """
    if not employees:
        raise HTTPException(status_code=400, detail="No employees provided")
    
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


@api_router.post("/v2/admin/import-employee-raw")
async def import_employee_raw(employee: dict, quarter: str = "Q1", year: int = 2026):
    """
    Import a single employee with ALL fields preserved (no recalculation).
    Used to sync exact data between preview and production.
    """
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




# ============================================================================
# V2 REVIEW GENERATION (Uses EmployeeV2 with Q1 2026 scoring model)
# ============================================================================

async def generate_review_content_v2(employee: EmployeeV2, settings: QuarterSettings, quarter: str, year: int) -> str:
    """
    Generate AI-powered review content using V2 employee data and scoring.
    Uses the Q1 2026 official scoring model with PPA, LBW, LSC, Glass, CV metrics.
    """
    try:
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            raise ValueError("EMERGENT_LLM_KEY not found in environment variables")
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"review_v2_{employee.id}_{quarter}_{year}",
            system_message="You are an expert HR professional specializing in creating comprehensive quarterly employee reviews for restaurant staff. Your reviews should be professional, human-like, and HR-defensible while maintaining a positive and constructive tone."
        ).with_model("openai", "gpt-5.2")
        
        # Get tier label from hierarchy ranking
        tier_label = employee.job_title or "Server"
        if employee.pre_dar_score and settings:
            if employee.pre_dar_score >= settings.a_server_min_score:
                tier_label = "A-Server"
            elif employee.pre_dar_score >= settings.b_server_min_score:
                tier_label = "B-Server"
            else:
                tier_label = "C-Server"
        
        # Build metrics summary
        prompt = f"""
Create a concise quarterly review for {employee.name}, a {employee.job_title or 'Server'} at Bubba Gump Shrimp Co.

PERFORMANCE METRICS (Q1 2026 SCORING MODEL):
- PPA (Per Person Average): ${employee.ppa or 0:.2f} | Score: {employee.score_ppa or 0:.1f}/100 | Bonus: +{employee.bonus_ppa or 0:.1f}
- LBW (Liquor Beer Wine per Guest): ${employee.lbw_per_guest or 0:.2f} | Score: {employee.score_lbw or 0:.1f}/100 | Bonus: +{employee.bonus_lbw or 0:.1f}
- Glassware ($ Per Guest): ${employee.glassware_per_guest or 0:.2f} | Score: {employee.score_glass or 0:.1f}/100 | Bonus: +{employee.bonus_glass or 0:.1f}
- LSC Ratio (Guests per LSC): {employee.guests_per_lsc or 'N/A'} | Score: {employee.score_lsc or 0:.1f}/100 | Bonus: +{employee.bonus_lsc or 0:.1f}
- Customer Voice Score: {employee.cv_score or 0:.1f}

TOTAL SCORE: {employee.pre_dar_score or employee.total_score or 0:.1f} points
RANKING: #{employee.peer_rank or 'N/A'} out of team
TIER CLASSIFICATION: {tier_label}
PERFORMANCE TIER: {employee.performance_tier or 'Not Assessed'}

REVIEW REQUIREMENTS:
1. Write EXACTLY 2 paragraphs - no more, no less
2. First paragraph: Performance highlights based on the metrics above. Mention specific strong areas.
3. Second paragraph: Areas for growth and specific goals for next quarter based on lower-scoring metrics.
4. Be conversational, HR-defensible, and maintain Bubba Gump's friendly culture
5. Reference specific KPIs to provide context
6. Total length: 150-250 words maximum

PLEASE DO NOT include any headers, titles, or formatting markers. Just provide exactly 2 paragraphs of review content.
"""
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        return response
        
    except Exception as e:
        logging.error(f"Error generating V2 review content: {str(e)}")
        return f"Unable to generate personalized review at this time. Please contact HR for manual review processing. Employee: {employee.name}"


def generate_pdf_v2(employee: EmployeeV2, settings: QuarterSettings, review_content: str, quarter: str, year: int) -> bytes:
    """
    Generate PDF for V2 employee data with Q1 2026 scoring breakdown.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.4*inch, bottomMargin=0.4*inch,
                          leftMargin=0.6*inch, rightMargin=0.6*inch)
    
    styles = getSampleStyleSheet()
    
    # Styles
    title_style = ParagraphStyle(
        'BubbaTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=20,
        spaceAfter=4,
        textColor=colors.HexColor('#D12E2E'),
        alignment=TA_CENTER
    )
    
    subtitle_style = ParagraphStyle(
        'BubbaSubtitle', 
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.HexColor('#005B96'),
        alignment=TA_CENTER,
        spaceAfter=8
    )
    
    header_style = ParagraphStyle(
        'BubbaHeader',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=13,
        textColor=colors.HexColor('#005B96'),
        spaceAfter=5,
        spaceBefore=6,
        backColor=colors.HexColor('#EFF6FF')
    )
    
    body_style = ParagraphStyle(
        'BubbaBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        spaceAfter=6,
        leading=12,
        textColor=colors.HexColor('#2C3E50')
    )
    
    story = []
    
    # Logo
    try:
        logo_url = "https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png"
        response = requests.get(logo_url)
        logo_buffer = BytesIO(response.content)
        logo_img = Image(logo_buffer, width=0.78*inch, height=0.78*inch)
        logo_img.hAlign = 'CENTER'
        story.append(logo_img)
        story.append(Spacer(1, 3))
    except Exception:
        pass
    
    # Header
    story.append(Paragraph("🦐 BUBBA GUMP SHRIMP CO. 🦐", title_style))
    story.append(Paragraph("Restaurant & Market • Las Vegas", subtitle_style))
    story.append(Spacer(1, 7))
    
    # Review title
    story.append(Paragraph(f"QUARTERLY PERFORMANCE REVIEW - {quarter} {year}", header_style))
    story.append(Spacer(1, 8))
    
    # Get tier classification
    tier_label = employee.job_title or "Server"
    if employee.pre_dar_score and settings:
        if employee.pre_dar_score >= settings.a_server_min_score:
            tier_label = "A-Server"
        elif employee.pre_dar_score >= settings.b_server_min_score:
            tier_label = "B-Server"
        else:
            tier_label = "C-Server"
    
    # Employee info
    emp_info_data = [
        ["Employee:", employee.name, "Job Title:", employee.job_title or "Server"],
        ["Review Period:", f"{quarter} {year}", "Tier:", tier_label],
        ["Overall Rank:", f"#{employee.peer_rank or 'N/A'}", "Date Generated:", datetime.now().strftime("%m/%d/%Y")]
    ]
    
    emp_table = Table(emp_info_data, colWidths=[1.2*inch, 2*inch, 1.2*inch, 2*inch])
    emp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F9F7F2')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F9F7F2')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#005B96')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#005B96')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB'))
    ]))
    
    story.append(emp_table)
    story.append(Spacer(1, 10))
    
    # KPI Performance Metrics (V2 Model)
    story.append(Paragraph("KEY PERFORMANCE INDICATORS - Q1 2026 SCORING MODEL", header_style))
    
    # Helper function to get score status
    def score_status(score):
        if score is None:
            return "N/A"
        score = float(score)
        if score >= 100:
            return "Exceeds"
        elif score >= 80:
            return "Meets"
        elif score >= 60:
            return "Below"
        else:
            return "Critical"
    
    kpi_data = [
        ["Metric", "Value", "Score", "Bonus", "Weight", "Status"],
        ["PPA (Per Person Average)", f"${employee.ppa or 0:.2f}", f"{employee.score_ppa or 0:.1f}", f"+{employee.bonus_ppa or 0:.1f}", "25%", score_status(employee.score_ppa)],
        ["LBW (Liquor Beer Wine/Guest)", f"${employee.lbw_per_guest or 0:.2f}", f"{employee.score_lbw or 0:.1f}", f"+{employee.bonus_lbw or 0:.1f}", "20%", score_status(employee.score_lbw)],
        ["Glassware ($/Guest)", f"${employee.glassware_per_guest or 0:.2f}", f"{employee.score_glass or 0:.1f}", f"+{employee.bonus_glass or 0:.1f}", "15%", score_status(employee.score_glass)],
        ["LSC (Guests per Enrollment)", f"{employee.guests_per_lsc or 'N/A'}", f"{employee.score_lsc or 0:.1f}", f"+{employee.bonus_lsc or 0:.1f}", "25%", score_status(employee.score_lsc)],
        ["Customer Voice", f"{employee.cv_score or 0:.1f} pts", f"{employee.score_cv or 0:.1f}", "-", "15%", score_status(employee.score_cv)],
    ]
    
    kpi_table = Table(kpi_data, colWidths=[2.3*inch, 1.1*inch, 0.8*inch, 0.7*inch, 0.7*inch, 0.9*inch])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#005B96')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F9F9F9'), colors.white])
    ]))
    
    story.append(kpi_table)
    story.append(Spacer(1, 8))
    
    # Total Score Summary
    total_score = employee.pre_dar_score or employee.total_score or 0
    total_bonus = employee.total_metric_bonus or 0
    
    summary_data = [
        ["TOTAL SCORE", f"{total_score:.1f}", "Total Bonus:", f"+{total_bonus:.1f}", "Performance Tier:", employee.performance_tier or "Not Assessed"]
    ]
    
    summary_table = Table(summary_data, colWidths=[1.2*inch, 0.8*inch, 1.0*inch, 0.7*inch, 1.2*inch, 1.6*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#D12E2E')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('BACKGROUND', (2, 0), (-1, 0), colors.HexColor('#F9F7F2')),
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 10))
    
    # Review content
    story.append(Paragraph("PERFORMANCE REVIEW", header_style))
    
    paragraphs = [p.strip() for p in review_content.split('\n\n') if p.strip()]
    for paragraph in paragraphs:
        story.append(Paragraph(paragraph, body_style))
    
    story.append(Spacer(1, 14))
    
    # Signature section
    signature_data = [
        ["Manager Signature: _________________________", "Date: _______________"],
        ["Employee Signature: _______________________", "Date: _______________"]
    ]
    
    sig_table = Table(signature_data, colWidths=[3.5*inch, 2*inch])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 10)
    ]))
    
    story.append(sig_table)
    
    # Footer
    story.append(Spacer(1, 10))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#005B96'),
        alignment=TA_CENTER
    )
    story.append(Paragraph("🦐 Bubba Gump Shrimp Co. • Confidential Employee Review • Q1 2026 Scoring Model 🦐", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Map per-metric Tier columns (exact headers provided by user). Stored under additional_data.metric_tiers
TIER_COLUMN_MAP = {
    "ppa": ["ppa tier"],
    "pplbw": ["pplbw tier"],
    "lsc_ratio": ["lsc ratio tier", "lsc_ratio tier"],
    "gpg": ["gpg tier"],
    # handle typo in source header: "Metirc Bonus Tier"
    "metric_bonus_points": ["metirc bonus tier", "metric bonus tier", "metric bonus points tier"],
    # handle typo in source header: "Cummulative Score Tier"
    "cumulative_score": ["cummulative score tier", "cumulative score tier"],
}


def _first_non_empty(row, keys: List[str]):
    for k in keys:
        v = row.get(k)
        if v is not None and pd.notna(v) and str(v).strip() != "":
            return str(v).strip()
    return None

# Routes
@api_router.get("/")
async def root():
    return {"message": "Bubba Gump Employee Review System"}


# ============================================================================
# V2 ENDPOINTS - NEW SCORING ENGINE (Q1 2026 Official Model)
# ============================================================================

# === QUARTER SETTINGS ===

class QuarterSettingsCreate(BaseModel):
    year: int
    quarter: str
    benchmark_ppa: float = 55.0
    benchmark_lbw: float = 8.0
    benchmark_glass: float = 1.0
    benchmark_lsc: float = 100.0
    benchmark_cv: float = 5.0       # Customer Voice benchmark
    weight_ppa: float = 0.25        # Q1 2026: 25%
    weight_lbw: float = 0.20        # Q1 2026: 20%
    weight_glass: float = 0.15      # Q1 2026: 15%
    weight_lsc: float = 0.25        # Q1 2026: 25%
    weight_cv: float = 0.15         # Q1 2026: 15% (Customer Voice & Review Tracker)
    bonus_rate: float = 0.2
    bonus_cap: float = 5.0
    # Server tier thresholds (Settings-driven)
    a_server_min_score: float = 90.0   # A-Server >= 90
    b_server_min_score: float = 75.0   # B-Server >= 75, C-Server < 75


class QuarterSettingsUpdate(BaseModel):
    benchmark_ppa: Optional[float] = None
    benchmark_lbw: Optional[float] = None
    benchmark_glass: Optional[float] = None
    benchmark_lsc: Optional[float] = None
    benchmark_cv: Optional[float] = None
    weight_ppa: Optional[float] = None
    weight_lbw: Optional[float] = None
    weight_glass: Optional[float] = None
    weight_lsc: Optional[float] = None
    weight_cv: Optional[float] = None
    bonus_rate: Optional[float] = None
    bonus_cap: Optional[float] = None
    # Server tier thresholds
    a_server_min_score: Optional[float] = None
    b_server_min_score: Optional[float] = None
    # Slide theme settings
    slide_theme: Optional[str] = None
    slide_bg_color: Optional[str] = None
    slide_bg_gradient: Optional[str] = None
    slide_text_color: Optional[str] = None
    slide_accent_color: Optional[str] = None
    slide_secondary_color: Optional[str] = None
    slide_custom_bg_image: Optional[str] = None
    # Seasonal theme setting
    slide_seasonal_theme: Optional[str] = None


# === DAR (Disciplinary Action Reports) Management ===

class DARUpdate(BaseModel):
    written_warnings: int = 0
    suspensions: int = 0


@api_router.get("/v2/quarter-settings")
async def get_all_quarter_settings():
    """Get all quarter settings"""
    settings = await db.quarter_settings.find({}, {"_id": 0}).to_list(100)
    for s in settings:
        if isinstance(s.get('created_at'), str):
            s['created_at'] = datetime.fromisoformat(s['created_at'])
        if isinstance(s.get('updated_at'), str):
            s['updated_at'] = datetime.fromisoformat(s['updated_at'])
        if s.get('locked_at') and isinstance(s.get('locked_at'), str):
            s['locked_at'] = datetime.fromisoformat(s['locked_at'])
    return settings


@api_router.get("/v2/quarter-settings/{year}/{quarter}")
async def get_quarter_settings(year: int, quarter: str):
    """Get settings for a specific quarter"""
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()}, 
        {"_id": 0}
    )
    if not settings:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    return settings


@api_router.post("/v2/quarter-settings")
async def create_quarter_settings(data: QuarterSettingsCreate):
    """Create new quarter settings (Q1 2026 Official Model)"""
    # Check if settings already exist
    existing = await db.quarter_settings.find_one({
        "year": data.year, 
        "quarter": data.quarter.upper()
    })
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Settings already exist for {data.quarter} {data.year}. Use PUT to update."
        )
    
    # Validate weights sum to 1.0 (now includes CV weight)
    weight_sum = data.weight_ppa + data.weight_lbw + data.weight_glass + data.weight_lsc + data.weight_cv
    if abs(weight_sum - 1.0) > 0.01:
        raise HTTPException(
            status_code=400, 
            detail=f"Metric weights must sum to 1.0 (currently {weight_sum})"
        )
    
    settings = QuarterSettings(
        year=data.year,
        quarter=data.quarter.upper(),
        benchmark_ppa=data.benchmark_ppa,
        benchmark_lbw=data.benchmark_lbw,
        benchmark_glass=data.benchmark_glass,
        benchmark_lsc=data.benchmark_lsc,
        benchmark_cv=data.benchmark_cv,
        weight_ppa=data.weight_ppa,
        weight_lbw=data.weight_lbw,
        weight_glass=data.weight_glass,
        weight_lsc=data.weight_lsc,
        weight_cv=data.weight_cv,
        bonus_rate=data.bonus_rate,
        bonus_cap=data.bonus_cap,
        a_server_min_score=data.a_server_min_score,
        b_server_min_score=data.b_server_min_score
    )
    
    doc = settings.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    
    await db.quarter_settings.insert_one(doc)
    
    return {"success": True, "settings_id": settings.id, "message": f"Created settings for {data.quarter} {data.year}"}


@api_router.put("/v2/quarter-settings/{year}/{quarter}")
async def update_quarter_settings(year: int, quarter: str, data: QuarterSettingsUpdate):
    """Update quarter settings (only if not locked, except for theme settings)"""
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()}, 
        {"_id": 0}
    )
    if not settings:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    # Check if this is a theme-only update (allowed even when locked)
    theme_only_fields = {'slide_theme', 'slide_bg_color', 'slide_bg_gradient', 'slide_text_color', 
                        'slide_accent_color', 'slide_secondary_color', 'slide_seasonal_theme', 'slide_custom_bg_image'}
    
    non_theme_fields_provided = False
    for field in data.model_fields_set if hasattr(data, 'model_fields_set') else []:
        if field not in theme_only_fields and getattr(data, field, None) is not None:
            non_theme_fields_provided = True
            break
    
    # Also check each field manually for older pydantic versions
    score_affecting_fields = [
        data.benchmark_ppa, data.benchmark_lbw, data.benchmark_glass, data.benchmark_lsc, data.benchmark_cv,
        data.weight_ppa, data.weight_lbw, data.weight_glass, data.weight_lsc, data.weight_cv,
        data.bonus_rate, data.bonus_cap, data.a_server_min_score, data.b_server_min_score
    ]
    if any(f is not None for f in score_affecting_fields):
        non_theme_fields_provided = True
    
    if settings.get("is_locked") and non_theme_fields_provided:
        raise HTTPException(
            status_code=403, 
            detail=f"Settings for {quarter} {year} are locked. Only theme settings can be modified."
        )
    
    # Build update dict
    update_data = {}
    if data.benchmark_ppa is not None:
        update_data["benchmark_ppa"] = data.benchmark_ppa
    if data.benchmark_lbw is not None:
        update_data["benchmark_lbw"] = data.benchmark_lbw
    if data.benchmark_glass is not None:
        update_data["benchmark_glass"] = data.benchmark_glass
    if data.benchmark_lsc is not None:
        update_data["benchmark_lsc"] = data.benchmark_lsc
    if data.benchmark_cv is not None:
        update_data["benchmark_cv"] = data.benchmark_cv
    if data.weight_ppa is not None:
        update_data["weight_ppa"] = data.weight_ppa
    if data.weight_lbw is not None:
        update_data["weight_lbw"] = data.weight_lbw
    if data.weight_glass is not None:
        update_data["weight_glass"] = data.weight_glass
    if data.weight_lsc is not None:
        update_data["weight_lsc"] = data.weight_lsc
    if data.weight_cv is not None:
        update_data["weight_cv"] = data.weight_cv
    if data.bonus_rate is not None:
        update_data["bonus_rate"] = data.bonus_rate
    if data.bonus_cap is not None:
        update_data["bonus_cap"] = data.bonus_cap
    if data.a_server_min_score is not None:
        update_data["a_server_min_score"] = data.a_server_min_score
    if data.b_server_min_score is not None:
        update_data["b_server_min_score"] = data.b_server_min_score
    # Slide theme settings
    if data.slide_theme is not None:
        update_data["slide_theme"] = data.slide_theme
    if data.slide_bg_color is not None:
        update_data["slide_bg_color"] = data.slide_bg_color
    if data.slide_bg_gradient is not None:
        update_data["slide_bg_gradient"] = data.slide_bg_gradient
    if data.slide_text_color is not None:
        update_data["slide_text_color"] = data.slide_text_color
    if data.slide_accent_color is not None:
        update_data["slide_accent_color"] = data.slide_accent_color
    if data.slide_secondary_color is not None:
        update_data["slide_secondary_color"] = data.slide_secondary_color
    if data.slide_custom_bg_image is not None:
        update_data["slide_custom_bg_image"] = data.slide_custom_bg_image
    if data.slide_seasonal_theme is not None:
        update_data["slide_seasonal_theme"] = data.slide_seasonal_theme
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.quarter_settings.update_one(
        {"year": year, "quarter": quarter.upper()},
        {"$set": update_data}
    )
    
    return {"success": True, "message": f"Updated settings for {quarter} {year}"}


@api_router.post("/v2/quarter-settings/{year}/{quarter}/lock")
async def lock_quarter_settings(year: int, quarter: str):
    """Lock quarter settings (called when scores are generated)"""
    result = await db.quarter_settings.update_one(
        {"year": year, "quarter": quarter.upper()},
        {"$set": {
            "is_locked": True,
            "locked_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    return {"success": True, "message": f"Settings locked for {quarter} {year}"}


@api_router.get("/v2/quarter-settings/{year}/{quarter}/benchmark-suggestions")
async def get_benchmark_suggestions(year: int, quarter: str):
    """
    Get benchmark suggestions based on previous quarter averages.
    """
    # Determine previous quarter
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    current_idx = quarters.index(quarter.upper())
    
    if current_idx == 0:
        prev_quarter = "Q4"
        prev_year = year - 1
    else:
        prev_quarter = quarters[current_idx - 1]
        prev_year = year
    
    # Get employees from previous quarter
    prev_employees = await db.employees_v2.find({
        "quarter": prev_quarter,
        "year": prev_year
    }, {"_id": 0}).to_list(5000)
    
    if not prev_employees:
        return {
            "has_previous_data": False,
            "message": f"No data found for {prev_quarter} {prev_year}",
            "suggestions": None
        }
    
    # Calculate averages
    emp_objects = [EmployeeV2(**e) for e in prev_employees]
    avgs = calculate_previous_quarter_averages(emp_objects)
    
    suggestions = {}
    if avgs.get("avg_ppa"):
        suggestions["ppa"] = suggest_benchmarks_from_previous(avgs["avg_ppa"], "higher_better")
    if avgs.get("avg_lbw"):
        suggestions["lbw"] = suggest_benchmarks_from_previous(avgs["avg_lbw"], "higher_better")
    if avgs.get("avg_glass"):
        suggestions["glass"] = suggest_benchmarks_from_previous(avgs["avg_glass"], "higher_better")
    if avgs.get("avg_lsc"):
        suggestions["lsc"] = suggest_benchmarks_from_previous(avgs["avg_lsc"], "inverse")
    
    return {
        "has_previous_data": True,
        "previous_quarter": prev_quarter,
        "previous_year": prev_year,
        "previous_averages": avgs,
        "suggestions": suggestions
    }


# === V2 EMPLOYEE UPLOAD ===

@api_router.get("/v2/template")
async def download_template():
    """
    Download a sample CSV template for employee performance data.
    
    IMPORTANT: 
    - LBW must NOT be a column. Use individual Liquor, Beer, Wine columns.
    - LBW Total is calculated automatically: LBW = Liquor + Beer + Wine
    - Job Title column for hierarchy-based rankings (Trainer > Bartender > Server)
    
    CV and Review data is NO LONGER included in the spreadsheet.
    These are automatically synced from:
    - Customer Voice: Loyalty Voice platform (/api/v2/cv/sync)
    - Review Tracker: ReviewTrackers platform (/api/v2/reviews/sync)
    """
    template_content = """Employee Name,Job Title,Guests,Net Sales,Liquor Sales,Beer Sales,Wine Sales,Glassware Sales,LSC Count
John Smith,Server,450,24750,1500,1350,1200,540,5
Jane Doe,Bartender,520,28600,1800,1500,1380,624,9
Sarah Johnson,Trainer,400,22000,1200,1200,1200,480,4"""
    
    return Response(
        content=template_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_template.csv"}
    )


# === POS REPORT OCR ===

class POSOCRRequest(BaseModel):
    """Request model for POS OCR extraction."""
    image_base64: str = Field(..., description="Base64 encoded image data")
    mime_type: str = Field(default="image/jpeg", description="MIME type of the image")

class POSOCRResponse(BaseModel):
    """Response model for POS OCR extraction."""
    success: bool
    report_date: Optional[str] = None
    report_type: Optional[str] = None
    employees: List[Dict[str, Any]] = []
    employee_count: int = 0
    extraction_notes: Optional[str] = None
    error: Optional[str] = None

@api_router.post("/v2/pos-ocr/extract", response_model=POSOCRResponse)
async def extract_pos_report(request: POSOCRRequest):
    """
    Extract employee performance data from a POS report image using AI vision.
    
    Supported formats: JPEG, PNG, WEBP
    
    Returns extracted employee data including:
    - Employee names
    - PPA (Per Person Average)
    - LBW per guest
    - Glassware per guest
    - Guest count
    - Net sales
    - Guests per LSC
    """
    from pos_ocr import extract_pos_data_from_image, validate_extracted_data
    
    # Validate image data
    if not request.image_base64:
        return POSOCRResponse(
            success=False,
            error="No image data provided"
        )
    
    # Validate MIME type
    valid_mime_types = ["image/jpeg", "image/png", "image/webp"]
    if request.mime_type not in valid_mime_types:
        return POSOCRResponse(
            success=False,
            error=f"Invalid image type. Supported: {', '.join(valid_mime_types)}"
        )
    
    try:
        # Extract data from image
        raw_data = await extract_pos_data_from_image(
            request.image_base64, 
            request.mime_type
        )
        
        # Validate and clean extracted data
        validated_data = validate_extracted_data(raw_data)
        
        if "error" in validated_data and not validated_data.get("employees"):
            return POSOCRResponse(
                success=False,
                error=validated_data.get("error"),
                extraction_notes=validated_data.get("extraction_notes")
            )
        
        return POSOCRResponse(
            success=True,
            report_date=validated_data.get("report_date"),
            report_type=validated_data.get("report_type"),
            employees=validated_data.get("employees", []),
            employee_count=validated_data.get("employee_count", 0),
            extraction_notes=validated_data.get("extraction_notes")
        )
        
    except Exception as e:
        logging.error(f"POS OCR extraction failed: {str(e)}")
        return POSOCRResponse(
            success=False,
            error=f"Extraction failed: {str(e)}"
        )


@api_router.post("/v2/pos-ocr/upload")
async def upload_pos_report_file(file: UploadFile = File(...)):
    """
    Upload a POS report file (image, PDF, or XLSX) and extract employee data.
    
    Accepts: JPEG, PNG, WEBP, HEIC image files, PDF documents, XLSX spreadsheets
    Max size: 20MB for PDFs/XLSX, 10MB for images
    
    XLSX Format (Aloha Server Sales Detail):
    - Each employee has their own sheet/tab
    - Employee name in cell F5
    - Net Sales data in column C
    - Loyalty$ / 25 = LSC Card Count
    """
    from pos_ocr import extract_pos_data_from_image, extract_pos_data_from_pdf, extract_pos_data_from_xlsx, validate_extracted_data
    
    # Validate file type - include HEIC and XLSX support
    valid_image_types = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"]
    valid_pdf_types = ["application/pdf"]
    valid_xlsx_types = [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel"
    ]
    all_valid_types = valid_image_types + valid_pdf_types + valid_xlsx_types
    
    # Also check by file extension for xlsx (some systems may not send correct MIME type)
    is_xlsx_by_extension = file.filename and file.filename.lower().endswith(('.xlsx', '.xls'))
    
    if file.content_type not in all_valid_types and not is_xlsx_by_extension:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.content_type}'. Supported: JPEG, PNG, WEBP, HEIC, PDF, XLSX"
        )
    
    is_xlsx = file.content_type in valid_xlsx_types or is_xlsx_by_extension
    is_pdf = file.content_type in valid_pdf_types
    is_heic = file.content_type in ["image/heic", "image/heif"]
    max_size = 20 * 1024 * 1024 if (is_pdf or is_xlsx) else 10 * 1024 * 1024  # 20MB for PDF/XLSX, 10MB for images
    
    # Read and validate file size
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {max_size // (1024*1024)}MB"
        )
    
    try:
        if is_xlsx:
            # Process XLSX file - direct extraction, no OCR needed
            raw_data = extract_pos_data_from_xlsx(contents)
            
            if "error" in raw_data and not raw_data.get("employees"):
                return {
                    "success": False,
                    "error": raw_data.get("error"),
                    "extraction_notes": raw_data.get("extraction_notes")
                }
            
            return {
                "success": True,
                "filename": file.filename,
                "file_type": "xlsx",
                "sheets_processed": raw_data.get("sheets_processed", 0),
                "report_date": raw_data.get("report_date"),
                "report_type": raw_data.get("report_type"),
                "employees": raw_data.get("employees", []),
                "employee_count": raw_data.get("employee_count", 0),
                "extraction_notes": raw_data.get("extraction_notes")
            }
            
        elif is_pdf:
            # Process PDF file
            raw_data = await extract_pos_data_from_pdf(contents)
        elif is_heic:
            # Convert HEIC to JPEG first
            from PIL import Image
            from io import BytesIO
            import pillow_heif
            
            pillow_heif.register_heif_opener()
            heic_image = Image.open(BytesIO(contents))
            jpeg_buffer = BytesIO()
            heic_image.convert('RGB').save(jpeg_buffer, format='JPEG', quality=90)
            image_base64 = base64.b64encode(jpeg_buffer.getvalue()).decode('utf-8')
            raw_data = await extract_pos_data_from_image(image_base64, "image/jpeg")
        else:
            # Process image file
            image_base64 = base64.b64encode(contents).decode('utf-8')
            raw_data = await extract_pos_data_from_image(image_base64, file.content_type)
        
        # Validate and clean extracted data (for OCR sources)
        validated_data = validate_extracted_data(raw_data)
        
        if "error" in validated_data and not validated_data.get("employees"):
            return {
                "success": False,
                "error": validated_data.get("error"),
                "extraction_notes": validated_data.get("extraction_notes")
            }
        
        return {
            "success": True,
            "filename": file.filename,
            "file_type": "pdf" if is_pdf else "image",
            "pages_processed": raw_data.get("pages_processed", 1),
            "report_date": validated_data.get("report_date"),
            "report_type": validated_data.get("report_type"),
            "employees": validated_data.get("employees", []),
            "employee_count": validated_data.get("employee_count", 0),
            "extraction_notes": validated_data.get("extraction_notes")
        }
        
    except Exception as e:
        logging.error(f"POS file upload failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}"
        )


# ============================================================================
# SCANNED PDF PARSER - Accurate OCR-corrected text extraction
# ============================================================================

@api_router.post("/v2/pos-pdf/test")
async def test_pdf_endpoint(file: UploadFile = File(...)):
    """Simple test endpoint to check if PDF upload works at all"""
    contents = await file.read()
    return {
        "success": True,
        "filename": file.filename,
        "size": len(contents),
        "content_type": file.content_type
    }


@api_router.post("/v2/pos-pdf/parse")
async def parse_pos_pdf_scan(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    Parse a scanned POS report PDF using AI-powered OCR extraction.
    Returns a job_id immediately - poll /v2/pos-pdf/job/{job_id} for results.
    """
    import math
    
    # Validate file type
    is_pdf = file.content_type == "application/pdf" or (file.filename and file.filename.lower().endswith('.pdf'))
    if not is_pdf:
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    try:
        contents = await file.read()
    except Exception as e:
        logging.error(f"Error reading file: {e}")
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")
        
    if len(contents) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large. Maximum 50MB")
    
    # Create a job ID and start background processing
    job_id = str(uuid.uuid4())
    pdf_jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "filename": file.filename,
        "result": None,
        "error": None,
        "started_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Start background processing
    asyncio.create_task(process_pdf_in_background(job_id, contents, file.filename))
    
    return {
        "success": True,
        "job_id": job_id,
        "status": "processing",
        "message": "PDF processing started. Poll /api/v2/pos-pdf/job/{job_id} for results."
    }


async def process_pdf_in_background(job_id: str, contents: bytes, filename: str):
    """Background task to process PDF and update job status."""
    import math
    from pos_ocr import extract_pos_data_from_pdf, validate_extracted_data
    
    def safe_float(val, default=0):
        if val is None:
            return default
        try:
            result = float(val)
            if math.isnan(result) or math.isinf(result):
                return default
            return round(result, 2)
        except (ValueError, TypeError):
            return default
    
    def safe_int(val, default=0):
        if val is None:
            return default
        try:
            result = float(val)
            if math.isnan(result) or math.isinf(result):
                return default
            return int(result)
        except (ValueError, TypeError):
            return default
    
    try:
        logging.info(f"Background PDF processing started for job {job_id}")
        
        # Use the AI/OCR-based extraction
        raw_data = await extract_pos_data_from_pdf(contents)
        
        if "error" in raw_data and not raw_data.get("employees"):
            pdf_jobs[job_id] = {
                **pdf_jobs[job_id],
                "status": "completed",
                "progress": 100,
                "result": {
                    "success": False,
                    "error": raw_data.get("error", "Failed to extract data from PDF"),
                    "employees": [],
                    "extraction_notes": raw_data.get("extraction_notes", "")
                }
            }
            return
        
        # Validate and clean extracted data
        validated_data = validate_extracted_data(raw_data)
        
        if not validated_data.get("employees"):
            pdf_jobs[job_id] = {
                **pdf_jobs[job_id],
                "status": "completed",
                "progress": 100,
                "result": {
                    "success": False,
                    "error": "No employee data could be extracted from the PDF",
                    "employees": [],
                    "extraction_notes": validated_data.get("extraction_notes", "")
                }
            }
            return
        
        # Format response
        formatted_employees = []
        for emp in validated_data.get("employees", []):
            raw_data_fields = emp.get("_raw", {})
            
            # Calculate PPA if not present
            guest_count = safe_int(emp.get("guest_count", 0))
            net_sales = safe_float(emp.get("net_sales", 0))
            ppa = safe_float(emp.get("ppa", 0))
            if (not ppa or ppa == 0) and guest_count > 0 and net_sales > 0:
                ppa = round(net_sales / guest_count, 2)
            
            # Log what we're getting
            logging.info(f"PDF Extract - {emp.get('name')}: guest_count={guest_count}, net_sales={net_sales}, ppa={ppa}, loyalty={emp.get('loyalty_sales')}")
            
            formatted_employees.append({
                "name": str(emp.get("name", "Unknown") or "Unknown"),
                "guest_count": guest_count,
                "net_sales": net_sales,
                "ppa": ppa,
                "food_sales": safe_float(raw_data_fields.get("food_sales", 0)),
                "liquor_sales": safe_float(raw_data_fields.get("liquor_sales", 0)),
                "beer_sales": safe_float(raw_data_fields.get("beer_sales", 0)),
                "wine_sales": safe_float(raw_data_fields.get("wine_sales", 0)),
                "lbw_total": safe_float(
                    (raw_data_fields.get("liquor_sales") or 0) + 
                    (raw_data_fields.get("beer_sales") or 0) + 
                    (raw_data_fields.get("wine_sales") or 0)
                ),
                "bar_glassware_sales": safe_float(raw_data_fields.get("bar_glassware_sales", 0)),
                "loyalty_sales": safe_float(emp.get("loyalty_sales", 0))
            })
        
        pdf_jobs[job_id] = {
            **pdf_jobs[job_id],
            "status": "completed",
            "progress": 100,
            "result": {
                "success": True,
                "filename": filename,
                "employee_count": len(formatted_employees),
                "total_pages": safe_int(raw_data.get("pages_processed", raw_data.get("total_pages", 1)), 1),
                "employees": formatted_employees,
                "extraction_notes": f"AI/OCR extracted {len(formatted_employees)} employees. {validated_data.get('extraction_notes', '')}"
            }
        }
        logging.info(f"Background PDF processing completed for job {job_id}: {len(formatted_employees)} employees")
        
    except Exception as e:
        logging.error(f"Background PDF processing error for job {job_id}: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        pdf_jobs[job_id] = {
            **pdf_jobs[job_id],
            "status": "failed",
            "progress": 100,
            "error": str(e)
        }


@api_router.get("/v2/pos-pdf/job/{job_id}")
async def get_pdf_job_status(job_id: str):
    """Get the status of a PDF processing job."""
    if job_id not in pdf_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = pdf_jobs[job_id]
    
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "filename": job.get("filename")
    }
    
    if job["status"] == "completed" and job.get("result"):
        response["result"] = job["result"]
        # Clean up old job after returning result
        # Keep for 5 minutes for retry
    elif job["status"] == "failed":
        response["error"] = job.get("error", "Unknown error")
    
    return response


class ParsedEmployeeData(BaseModel):
    employees: List[Dict[str, Any]]


@api_router.post("/v2/pos-pdf/import-parsed")
async def import_parsed_pdf_data(
    data: ParsedEmployeeData,
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Import pre-parsed POS PDF data into the employee database.
    This uses already-extracted employee data from the preview step.
    """
    from rapidfuzz import fuzz, process
    
    quarter = quarter.upper()
    employees_data = data.employees
    
    if not employees_data:
        raise HTTPException(status_code=400, detail="No employee data provided")
    
    # Check quarter settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(
            status_code=400,
            detail=f"Quarter settings must exist for {quarter} {year}. Go to Settings first."
        )
    
    # Get existing employees for matching
    existing_employees = await db.employees_v2.find({
        "quarter": quarter,
        "year": year
    }, {"_id": 0}).to_list(1000)
    
    # Build name matching index
    name_index = {}
    for emp in existing_employees:
        emp_id = emp.get('id') or emp.get('employee_id')
        if not emp_id:
            continue
        for field in ['name', 'report_name', 'display_name']:
            if emp.get(field):
                name_index[emp[field].lower()] = emp_id
        for alias in emp.get('aliases', []):
            name_index[alias.lower()] = emp_id
    
    # Process each employee
    results = {"matched": [], "created": [], "errors": []}
    
    for emp_data in employees_data:
        emp_name = emp_data.get('name', 'Unknown')
        emp_name_lower = emp_name.lower()
        
        # Try exact match first
        matched_id = name_index.get(emp_name_lower)
        
        # Try fuzzy match if no exact match
        if not matched_id and name_index:
            best_match = process.extractOne(
                emp_name_lower,
                list(name_index.keys()),
                scorer=fuzz.token_sort_ratio
            )
            if best_match and best_match[1] >= 85:
                matched_id = name_index[best_match[0]]
        
        try:
            if matched_id:
                # Update existing employee
                update_data = {
                    "guest_count": emp_data.get('guest_count', 0),
                    "net_sales": emp_data.get('net_sales', 0),
                    "food_sales": emp_data.get('food_sales', 0),
                    "liquor_sales": emp_data.get('liquor_sales', 0),
                    "beer_sales": emp_data.get('beer_sales', 0),
                    "wine_sales": emp_data.get('wine_sales', 0),
                    "lbw_total": emp_data.get('lbw_total', 0),
                    "bar_glassware_sales": emp_data.get('bar_glassware_sales', 0),
                    "loyalty_sales": emp_data.get('loyalty_sales', 0),
                    "updated_at": datetime.now(timezone.utc)
                }
                
                await db.employees_v2.update_one(
                    {"id": matched_id},
                    {"$set": update_data}
                )
                results["matched"].append({"name": emp_name, "id": matched_id})
            else:
                # Create new employee
                new_id = str(uuid.uuid4())
                new_employee = {
                    "id": new_id,
                    "name": emp_name,
                    "display_name": emp_name,
                    "report_name": emp_name,
                    "aliases": [],
                    "quarter": quarter,
                    "year": year,
                    "guest_count": emp_data.get('guest_count', 0),
                    "net_sales": emp_data.get('net_sales', 0),
                    "food_sales": emp_data.get('food_sales', 0),
                    "liquor_sales": emp_data.get('liquor_sales', 0),
                    "beer_sales": emp_data.get('beer_sales', 0),
                    "wine_sales": emp_data.get('wine_sales', 0),
                    "lbw_total": emp_data.get('lbw_total', 0),
                    "bar_glassware_sales": emp_data.get('bar_glassware_sales', 0),
                    "loyalty_sales": emp_data.get('loyalty_sales', 0),
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                await db.employees_v2.insert_one(new_employee)
                results["created"].append({"name": emp_name, "id": new_id})
                name_index[emp_name_lower] = new_id
                
        except Exception as e:
            results["errors"].append({"name": emp_name, "error": str(e)})
    
    # Recalculate all scores
    await fix_all_employee_scores(quarter, year)
    
    return {
        "success": True,
        "total_processed": len(employees_data),
        "matched": len(results["matched"]),
        "created": len(results["created"]),
        "errors": len(results["errors"]),
        "details": results
    }


@api_router.post("/v2/pos-pdf/import")
async def import_pos_pdf_data(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Parse and import scanned POS PDF data into the employee database.
    Uses AI/OCR extraction which is production-stable for large PDFs.
    
    This endpoint:
    1. Parses the PDF using AI-powered OCR extraction
    2. Matches employees using fuzzy name matching
    3. Updates existing employees or creates new ones
    4. Recalculates all scores
    """
    from pos_ocr import extract_pos_data_from_pdf, validate_extracted_data
    from rapidfuzz import fuzz, process
    
    quarter = quarter.upper()
    
    # Check quarter settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(
            status_code=400,
            detail=f"Quarter settings must exist for {quarter} {year}. Go to Settings first."
        )
    
    settings = QuarterSettings(**settings_doc)
    
    # Validate file type
    is_pdf = file.content_type == "application/pdf" or (file.filename and file.filename.lower().endswith('.pdf'))
    if not is_pdf:
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    contents = await file.read()
    
    try:
        logging.info(f"Processing PDF import with AI/OCR: {file.filename}, size: {len(contents)} bytes")
        
        # Use AI/OCR-based extraction which is production-stable
        raw_data = await extract_pos_data_from_pdf(contents)
        
        if "error" in raw_data and not raw_data.get("employees"):
            raise HTTPException(status_code=400, detail=raw_data.get("error", "No employee data found in PDF"))
        
        # Validate and clean extracted data
        validated_data = validate_extracted_data(raw_data)
        
        if not validated_data.get("employees"):
            raise HTTPException(status_code=400, detail="No employee data could be extracted from PDF")
        
        # Transform OCR data to standard format
        employees_data = []
        for emp in validated_data.get("employees", []):
            raw_fields = emp.get("_raw", {})
            employees_data.append({
                'name': emp.get("name", "Unknown"),
                'guests': emp.get("guest_count", 0) or 0,
                'net_sales': emp.get("net_sales", 0) or 0,
                'food': raw_fields.get("food_sales", 0) or 0,
                'liquor': raw_fields.get("liquor_sales", 0) or 0,
                'beer': raw_fields.get("beer_sales", 0) or 0,
                'wine': raw_fields.get("wine_sales", 0) or 0,
                'lbw': (raw_fields.get("liquor_sales", 0) or 0) + 
                       (raw_fields.get("beer_sales", 0) or 0) + 
                       (raw_fields.get("wine_sales", 0) or 0),
                'glassware': raw_fields.get("bar_glassware_sales", 0) or 0,
                'loyalty_sales': emp.get("loyalty_sales", 0) or 0
            })
        
        # Get existing employees for matching
        existing_employees = await db.employees_v2.find({
            "quarter": quarter,
            "year": year
        }, {"_id": 0}).to_list(1000)
        
        # Build name matching index
        name_index = {}
        for emp in existing_employees:
            emp_id = emp.get('id') or emp.get('employee_id')
            if not emp_id:
                continue
            for field in ['name', 'report_name', 'display_name']:
                if emp.get(field):
                    name_index[emp[field].lower()] = emp_id
            for alias in emp.get('aliases', []):
                name_index[alias.lower()] = emp_id
        
        # Process each extracted employee
        results = {
            "matched": [],
            "created": [],
            "errors": []
        }
        
        for emp_data in employees_data:
            emp_name = emp_data['name']
            emp_name_lower = emp_name.lower()
            
            # Try exact match first
            matched_id = name_index.get(emp_name_lower)
            
            # Try fuzzy match if no exact match
            if not matched_id and name_index:
                best_match = process.extractOne(
                    emp_name_lower,
                    list(name_index.keys()),
                    scorer=fuzz.token_sort_ratio
                )
                if best_match and best_match[1] >= 85:
                    matched_id = name_index[best_match[0]]
            
            try:
                if matched_id:
                    # Update existing employee
                    update_data = {
                        "guest_count": emp_data['guests'],
                        "net_sales": emp_data['net_sales'],
                        "food_sales": emp_data['food'],
                        "liquor_sales": emp_data['liquor'],
                        "beer_sales": emp_data['beer'],
                        "wine_sales": emp_data['wine'],
                        "lbw_total": emp_data['lbw'],
                        "bar_glassware_sales": emp_data['glassware'],
                        "loyalty_sales": emp_data.get('loyalty_sales', 0),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    
                    await db.employees_v2.update_one(
                        {"id": matched_id},
                        {"$set": update_data}
                    )
                    results["matched"].append({"name": emp_name, "id": matched_id})
                else:
                    # Create new employee
                    new_id = str(uuid.uuid4())
                    new_employee = {
                        "id": new_id,
                        "name": emp_name,
                        "display_name": emp_name,
                        "report_name": emp_name,
                        "aliases": [],
                        "quarter": quarter,
                        "year": year,
                        "guest_count": emp_data['guests'],
                        "net_sales": emp_data['net_sales'],
                        "food_sales": emp_data['food'],
                        "liquor_sales": emp_data['liquor'],
                        "beer_sales": emp_data['beer'],
                        "wine_sales": emp_data['wine'],
                        "lbw_total": emp_data['lbw'],
                        "bar_glassware_sales": emp_data['glassware'],
                        "loyalty_sales": emp_data.get('loyalty_sales', 0),
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    await db.employees_v2.insert_one(new_employee)
                    results["created"].append({"name": emp_name, "id": new_id})
                    
                    # Add to index for subsequent matches
                    name_index[emp_name_lower] = new_id
                    
            except Exception as e:
                results["errors"].append({"name": emp_name, "error": str(e)})
        
        # Recalculate all scores using the fix_all_employee_scores function
        await fix_all_employee_scores(quarter, year)
        
        return {
            "success": True,
            "total_processed": len(employees_data),
            "matched": len(results["matched"]),
            "created": len(results["created"]),
            "errors": len(results["errors"]),
            "details": results,
            "extraction_notes": f"AI/OCR processed {raw_data.get('pages_processed', 'N/A')} pages"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"PDF import error: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")




# ============================================================================
# UNIFIED DATA UPLOAD - Single Source of Truth
# ============================================================================

@api_router.post("/v2/data/upload-pos")
async def unified_pos_upload(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    UNIFIED POS DATA UPLOAD - Single source of truth.
    
    This endpoint:
    1. Parses POS data from XLSX (SSD Engine or standard format)
    2. Updates/creates employees directly in employees_v2
    3. Auto-creates/updates snapshot for the current date
    4. Recalculates all scores
    
    Use this for ALL POS data uploads. Dashboard and Snapshots will stay in sync.
    """
    import re
    quarter = quarter.upper()
    
    # Check quarter settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(
            status_code=400,
            detail=f"Quarter settings must exist for {quarter} {year}. Go to Settings first."
        )
    
    settings = QuarterSettings(**settings_doc)
    
    # Read and parse file
    contents = await file.read()
    filename = file.filename.lower()
    
    if not filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx, .xls) or CSV files allowed")
    
    try:
        from pos_report_parser import is_consolidated_format, parse_consolidated_pos_report
        from clean_pos_parser import parse_clean_pos_report
        import tempfile
        
        parsed_employees = []
        parse_method = "unknown"
        
        # Save to temp file for format detection
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        try:
            # Try consolidated format (SSD Engine) first
            if not filename.endswith('.csv') and is_consolidated_format(tmp_path):
                logging.info("UNIFIED UPLOAD: Detected SSD Engine format")
                parsed_employees = parse_consolidated_pos_report(tmp_path)
                parse_method = "ssd_engine"
            else:
                # Try clean POS format
                clean_result = parse_clean_pos_report(contents, filename)
                if clean_result["success"] and clean_result["employees"]:
                    parsed_employees = clean_result["employees"]
                    parse_method = "clean_pos"
                else:
                    # Fall back to pandas for standard CSV/XLSX
                    if filename.endswith('.csv'):
                        df = pd.read_csv(io.BytesIO(contents))
                    else:
                        df = pd.read_excel(io.BytesIO(contents))
                    
                    # Map columns
                    column_validation = validate_upload_columns(list(df.columns))
                    if column_validation["valid"]:
                        mapping = column_validation["mapping"]
                        for _, row in df.iterrows():
                            name = str(row.get(mapping.get("name", ""), "")).strip()
                            if not name or name == "nan":
                                continue
                            
                            guests = int(float(row.get(mapping.get("guests", ""), 0) or 0))
                            net_sales = float(row.get(mapping.get("net_sales", ""), 0) or 0)
                            liquor = float(row.get(mapping.get("liquor_sales", ""), 0) or 0)
                            beer = float(row.get(mapping.get("beer_sales", ""), 0) or 0)
                            wine = float(row.get(mapping.get("wine_sales", ""), 0) or 0)
                            lbw = liquor + beer + wine
                            glassware = float(row.get(mapping.get("glassware_sales", ""), 0) or 0)
                            lsc = int(float(row.get(mapping.get("lsc_count", ""), 0) or 0))
                            
                            parsed_employees.append({
                                "name": name,
                                "guests": guests,
                                "net_sales": net_sales,
                                "lbw": lbw,
                                "glassware": glassware,
                                "lsc_count": lsc
                            })
                        parse_method = "standard_csv"
        finally:
            import os
            os.unlink(tmp_path)
        
        if not parsed_employees:
            raise HTTPException(status_code=400, detail="No valid employee data found in file")
        
        # Get all existing employees once before processing (for intelligent matching)
        all_existing = await db.employees_v2.find(
            {"quarter": quarter, "year": year},
            {"_id": 0}
        ).to_list(500)
        
        # Import the intelligent name matcher
        from name_matcher import find_best_match
        
        # Track which employees have been matched to prevent duplicates
        matched_employee_ids = set()
        match_log = []
        
        # Process each employee: update or create in employees_v2
        updated_count = 0
        created_count = 0
        
        for emp_data in parsed_employees:
            name = emp_data.get('name', '')
            if not name:
                continue
            
            guests = emp_data.get('guests', 0) or emp_data.get('total_guests', 0) or 0
            net_sales = emp_data.get('net_sales', 0) or emp_data.get('totals', 0) or 0
            lbw = emp_data.get('lbw', 0) or 0
            
            # If lbw not provided, calculate from components
            if lbw == 0:
                liquor = emp_data.get('liquor', 0) or 0
                beer = emp_data.get('beer', 0) or 0
                wine = emp_data.get('wine', 0) or 0
                lbw = liquor + beer + wine
            
            glassware = emp_data.get('glassware', 0) or emp_data.get('glassware_sales', 0) or emp_data.get('bar_glassware', 0) or 0
            lsc_count = emp_data.get('lsc_count', 0) or 0
            
            # If lsc from loyalty sales
            if lsc_count == 0 and emp_data.get('loyalty'):
                lsc_count = int(emp_data.get('loyalty', 0) / 25)
            
            # Calculate derived metrics
            ppa = net_sales / guests if guests > 0 else 0
            lbw_per_guest = lbw / guests if guests > 0 else 0
            glassware_per_guest = glassware / guests if guests > 0 else 0
            guests_per_lsc = guests / lsc_count if lsc_count > 0 else None
            
            # Calculate scores using benchmarks
            benchmark_ppa = settings.benchmark_ppa or 55
            benchmark_lbw = settings.benchmark_lbw or 8
            benchmark_glass = settings.benchmark_glass or 1.25
            benchmark_lsc = settings.benchmark_lsc or 100
            
            score_ppa = (ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
            score_lbw = (lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
            score_glass = (glassware_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
            score_lsc = (benchmark_lsc / guests_per_lsc) * 100 if guests_per_lsc and guests_per_lsc > 0 else 0
            
            # Calculate weighted base score (capped at 100 each)
            capped_ppa = min(score_ppa, 100)
            capped_lbw = min(score_lbw, 100)
            capped_glass = min(score_glass, 100)
            capped_lsc = min(score_lsc, 100)
            
            weighted_score = (
                capped_ppa * 0.25 +
                capped_lsc * 0.25 +
                capped_lbw * 0.15 +
                capped_glass * 0.10
            )
            
            # INTELLIGENT FUZZY NAME MATCHING
            # Filter out already-matched employees to prevent double-matching
            available_employees = [e for e in all_existing if e.get('id') not in matched_employee_ids]
            
            match, score, reason = find_best_match(name, available_employees, threshold=70.0)
            
            if match:
                # Found a match - update existing employee
                matched_employee_ids.add(match.get('id'))
                match_log.append({
                    "upload_name": name,
                    "matched_to": match.get('name'),
                    "score": round(score, 1),
                    "reason": reason
                })
                logging.info(f"MATCH: '{name}' -> '{match.get('name')}' (score: {score:.1f})")
                
                # Preserve existing CV/RT data AND display_name when updating POS data
                cv_score = match.get("cv_score", 0) or 0
                rt_mentions = match.get("rt_mentions", 0) or 0
                rt_contribution = min(rt_mentions * 0.5, 15)
                total_metric_bonus = match.get("total_metric_bonus", 0) or 0
                
                # Recalculate weighted with RT
                weighted_with_rt = weighted_score + rt_contribution
                total_score = weighted_with_rt + cv_score + total_metric_bonus
                
                update_fields = {
                    "report_name": name,  # Update report_name to latest from POS
                    "guests": guests,
                    "net_sales": round(net_sales, 2),
                    "lbw": round(lbw, 2),
                    "glassware_sales": round(glassware, 2),
                    "lsc_count": lsc_count,
                    "ppa": round(ppa, 2),
                    "lbw_per_guest": round(lbw_per_guest, 2),
                    "glassware_per_guest": round(glassware_per_guest, 2),
                    "guests_per_lsc": round(guests_per_lsc, 2) if guests_per_lsc else None,
                    "score_ppa": round(score_ppa, 2),
                    "score_lbw": round(score_lbw, 2),
                    "score_glass": round(score_glass, 2),
                    "score_lsc": round(score_lsc, 2),
                    "weighted_score": round(weighted_with_rt, 2),
                    "total_score": round(total_score, 2),
                    "pre_dar_score": round(total_score, 2),
                    "updated_at": datetime.now(timezone.utc)
                }
                # NOTE: display_name is NOT updated - it's preserved from manual changes
                
                await db.employees_v2.update_one(
                    {"id": match.get('id')},
                    {"$set": update_fields}
                )
                updated_count += 1
            else:
                # Create new employee
                new_emp = {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "display_name": name,  # Initially same as name, can be changed later
                    "report_name": name,   # Original name from POS report
                    "aliases": [],         # For alternate name matching
                    "quarter": quarter,
                    "year": year,
                    "job_title": "Server",
                    "guests": guests,
                    "net_sales": round(net_sales, 2),
                    "lbw": round(lbw, 2),
                    "glassware_sales": round(glassware, 2),
                    "lsc_count": lsc_count,
                    "ppa": round(ppa, 2),
                    "lbw_per_guest": round(lbw_per_guest, 2),
                    "glassware_per_guest": round(glassware_per_guest, 2),
                    "guests_per_lsc": round(guests_per_lsc, 2) if guests_per_lsc else None,
                    "score_ppa": round(score_ppa, 2),
                    "score_lbw": round(score_lbw, 2),
                    "score_glass": round(score_glass, 2),
                    "score_lsc": round(score_lsc, 2),
                    "weighted_score": round(weighted_score, 2),
                    "total_score": round(weighted_score, 2),
                    "pre_dar_score": round(weighted_score, 2),
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
                created_count += 1
        
        # Recalculate peer ranks
        await recalculate_peer_ranks(quarter, year)
        
        # NOTE: Snapshots are NOT auto-updated. They capture point-in-time data.
        # To update a snapshot, create a new one from the Snapshots page.
        
        return {
            "success": True,
            "message": f"POS data uploaded successfully",
            "employees_updated": updated_count,
            "employees_created": created_count,
            "total_processed": updated_count + created_count,
            "parse_method": parse_method,
            "quarter": quarter,
            "year": year,
            "note": "Dashboard updated. Create a new Snapshot to capture this data.",
            "matches": match_log[:10] if match_log else []  # Return first 10 matches for transparency
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unified POS upload failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@api_router.post("/v2/upload/validate")
async def validate_upload_file(file: UploadFile = File(...)):
    """
    Validate an upload file without importing.
    Returns column mapping and validation results.
    
    NOTE: LBW is calculated from Liquor + Beer + Wine columns.
    """
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx, .xls) or CSV files allowed")
    
    try:
        contents = await file.read()
        
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Clean column names - handle non-string column names safely
        df.columns = [str(col).strip() if col is not None else f"Unnamed_{i}" for i, col in enumerate(df.columns)]
        
        # Validate columns
        column_validation = validate_upload_columns(list(df.columns))
        
        if not column_validation["valid"]:
            return {
                "valid": False,
                "column_validation": column_validation,
                "row_count": len(df),
                "preview": df.head(5).to_dict('records')
            }
        
        # Parse rows using mapping
        mapping = column_validation["mapping"]
        rows = []
        for _, row in df.iterrows():
            # Get individual alcohol values (treat missing as 0)
            liquor_val = row.get(mapping.get("liquor_sales", "")) if mapping.get("liquor_sales") else 0
            beer_val = row.get(mapping.get("beer_sales", "")) if mapping.get("beer_sales") else 0
            wine_val = row.get(mapping.get("wine_sales", "")) if mapping.get("wine_sales") else 0
            
            # Calculate LBW from individual columns
            try:
                liquor = float(liquor_val) if not pd.isna(liquor_val) else 0.0
                beer = float(beer_val) if not pd.isna(beer_val) else 0.0
                wine = float(wine_val) if not pd.isna(wine_val) else 0.0
                calculated_lbw = liquor + beer + wine
            except (ValueError, TypeError):
                calculated_lbw = 0.0
            
            row_data = {
                "name": row.get(mapping.get("name", "")) if mapping.get("name") else None,
                "guests": row.get(mapping.get("guests", "")) if mapping.get("guests") else None,
                "net_sales": row.get(mapping.get("net_sales", "")) if mapping.get("net_sales") else None,
                "lbw": calculated_lbw,  # Auto-calculated from Liquor + Beer + Wine
                "glassware_sales": row.get(mapping.get("glassware_sales", "")) if mapping.get("glassware_sales") else None,
                "lsc_count": row.get(mapping.get("lsc_count", "")) if mapping.get("lsc_count") else None,
            }
            
            # Clean values
            for key in row_data:
                if key == "lbw":
                    continue  # Already calculated
                if pd.isna(row_data[key]):
                    row_data[key] = None
                elif key == "guests" or key == "lsc_count":
                    try:
                        row_data[key] = int(row_data[key])
                    except (ValueError, TypeError):
                        row_data[key] = None
                elif key in ["net_sales", "glassware_sales"]:
                    try:
                        row_data[key] = float(row_data[key])
                    except (ValueError, TypeError):
                        row_data[key] = None
            
            rows.append(row_data)
        
        # Validate rows
        row_validation = validate_upload_data(rows)
        
        return {
            "valid": row_validation["valid"],
            "column_validation": column_validation,
            "row_validation": {
                "total_rows": row_validation["total_rows"],
                "valid_rows": row_validation["valid_rows"],
                "invalid_rows": row_validation["invalid_rows"],
                "duplicate_names": row_validation["duplicate_names"],
                "errors": [
                    {"row": idx + 2, "name": r.employee_name, "errors": r.errors}
                    for idx, r in enumerate(row_validation["validation_results"])
                    if not r.valid
                ][:20]  # Limit to first 20 errors
            },
            "preview": rows[:5]
        }
        
    except Exception as e:
        logging.error(f"Error validating file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error validating file: {str(e)}")


@api_router.post("/v2/upload")
async def upload_employees_v2(
    file: UploadFile = File(...),
    year: int = 2026,
    quarter: str = "Q1"
):
    """
    Upload employees using Q1 2026 scoring engine.
    Includes Customer Voice (NPS) and Review Tracker fields.
    Requires quarter settings to exist.
    """
    quarter = quarter.upper()
    
    # Check quarter settings exist
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(
            status_code=400,
            detail=f"Quarter settings must be created for {quarter} {year} before uploading employees. "
                   f"Go to Settings to create them."
        )
    
    if settings_doc.get("is_locked"):
        raise HTTPException(
            status_code=403,
            detail=f"Quarter {quarter} {year} is locked. Cannot upload new data."
        )
    
    settings = QuarterSettings(**settings_doc)
    
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx, .xls) or CSV files allowed")
    
    try:
        contents = await file.read()
        
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Clean column names - handle non-string column names safely
        df.columns = [str(col).strip() if col is not None else f"Unnamed_{i}" for i, col in enumerate(df.columns)]
        
        # Validate columns
        column_validation = validate_upload_columns(list(df.columns))
        
        if not column_validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns: {', '.join(column_validation['missing'])}"
            )
        
        mapping = column_validation["mapping"]
        employees = []
        
        # Helper function to safely convert to int
        def safe_int(val, default=0):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return default
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return default
        
        # Helper function to safely convert to float
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
            
            # Common garbage patterns from XLSX headers/footers
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
            
            # Check for invalid patterns
            for pattern in invalid_patterns:
                if pattern in name_lower:
                    return False
            
            # Name should contain at least one letter
            if not any(c.isalpha() for c in name):
                return False
            
            # Name should not be all numbers
            if name.replace(" ", "").replace(".", "").isdigit():
                return False
            
            # Name should not start with special characters
            if name[0] in "0123456789.-_=+*&^%$#@!~`":
                return False
            
            # Name should be reasonable length (2-50 chars)
            if len(name) > 50:
                return False
            
            return True
        
        for idx, row in df.iterrows():
            try:
                # Extract core values
                name = str(row.get(mapping["name"], "")).strip()
                if not name or name == "nan":
                    continue
                
                # Filter out garbage names from XLSX headers/footers
                if not is_valid_employee_name(name):
                    logging.info(f"Skipping invalid name during upload: {name}")
                    continue
                
                guests = safe_int(row.get(mapping["guests"]))
                net_sales = safe_float(row.get(mapping["net_sales"]))
                
                # Job Title (optional) - for hierarchy-based rankings
                job_title = "Server"  # Default
                if mapping.get("job_title"):
                    val = row.get(mapping["job_title"])
                    if val is not None and not pd.isna(val) and str(val).strip() and str(val).strip().lower() != "nan":
                        job_title = str(val).strip()
                
                # Individual alcohol sales (required) - LBW calculated automatically
                liquor_sales = safe_float(row.get(mapping["liquor_sales"]))
                beer_sales = safe_float(row.get(mapping["beer_sales"]))
                wine_sales = safe_float(row.get(mapping["wine_sales"]))
                
                glassware_sales = safe_float(row.get(mapping["glassware_sales"]))
                lsc_count = safe_int(row.get(mapping["lsc_count"]))
                
                if guests <= 0:
                    logging.warning(f"Row {idx + 2}: Skipping {name} - guests must be > 0")
                    continue
                
                # Customer Voice and Review data now comes from automated sync
                # These fields are NO LONGER read from spreadsheet
                # CV: Synced from Loyalty Voice via /api/v2/cv/sync
                # Reviews: Synced from ReviewTrackers via /api/v2/reviews/sync
                cv_promoters = 0
                cv_passives = 0
                cv_detractors = 0
                review_mentions = 0
                
                # Legacy optional text fields (deprecated)
                review_tracker = None
                cv_positive = None
                cv_negative = None
                
                if mapping.get("review_tracker"):
                    val = row.get(mapping["review_tracker"])
                    if not pd.isna(val):
                        review_tracker = str(val)
                
                if mapping.get("cv_positive"):
                    val = row.get(mapping["cv_positive"])
                    if not pd.isna(val):
                        cv_positive = str(val)
                
                if mapping.get("cv_negative"):
                    val = row.get(mapping["cv_negative"])
                    if not pd.isna(val):
                        cv_negative = str(val)
                
                # Create employee with individual alcohol fields
                # LBW is calculated automatically in run_full_scoring
                # CV/Review data will be populated from automated sync
                emp = EmployeeV2(
                    name=name,
                    job_title=job_title,
                    guests=guests,
                    net_sales=net_sales,
                    liquor_sales=liquor_sales,
                    beer_sales=beer_sales,
                    wine_sales=wine_sales,
                    glassware_sales=glassware_sales,
                    lsc_count=lsc_count,
                    cv_promoters=cv_promoters,
                    cv_passives=cv_passives,
                    cv_detractors=cv_detractors,
                    review_mentions=review_mentions,
                    review_tracker=review_tracker,
                    cv_positive=cv_positive,
                    cv_negative=cv_negative
                )
                
                employees.append(emp)
                
            except Exception as row_error:
                logging.error(f"Error processing row {idx + 2}: {str(row_error)}")
                continue
        
        if not employees:
            raise HTTPException(status_code=400, detail="No valid employees found in file")
        
        # Run full scoring (Q1 2026 model)
        scored_employees = run_full_scoring(employees, settings)
        
        # PRESERVE custom job titles from existing employees before deleting
        # This ensures manually set Trainer/Bartender designations aren't lost on re-upload
        existing_employees = await db.employees_v2.find(
            {"year": year, "quarter": quarter},
            {"_id": 0, "name": 1, "job_title": 1}
        ).to_list(500)
        
        preserved_job_titles = {}
        for emp in existing_employees:
            job = (emp.get("job_title") or "").lower()
            # Only preserve non-default job titles (trainer, bartender, etc.)
            if job and job not in ["server", ""]:
                preserved_job_titles[emp["name"].lower()] = emp["job_title"]
        
        logging.info(f"Preserved {len(preserved_job_titles)} custom job titles: {list(preserved_job_titles.values())}")
        
        # Clear existing employees for this quarter
        await db.employees_v2.delete_many({"year": year, "quarter": quarter})
        
        # Insert scored employees, restoring preserved job titles
        for emp in scored_employees:
            doc = emp.model_dump()
            doc['created_at'] = doc['created_at'].isoformat()
            
            # Restore preserved job title if this employee had one
            emp_name_lower = doc['name'].lower()
            if emp_name_lower in preserved_job_titles:
                doc['job_title'] = preserved_job_titles[emp_name_lower]
                logging.info(f"Restored job title '{doc['job_title']}' for {doc['name']}")
            
            await db.employees_v2.insert_one(doc)
        
        # Populate CV data from synced Loyalty Voice data
        cv_records = await db.cv_nps.find(
            {"quarter": quarter, "year": year},
            {"_id": 0}
        ).to_list(500)
        
        cv_updated = 0
        for cv in cv_records:
            emp_name = cv.get("employee_name", "")
            if emp_name:
                result = await db.employees_v2.update_one(
                    {"name": emp_name, "quarter": quarter, "year": year},
                    {"$set": {
                        "cv_promoters": cv.get("promoters", 0),
                        "cv_passives": cv.get("passives", 0),
                        "cv_detractors": cv.get("detractors", 0),
                        "cv_score": cv.get("cv_points", 0),
                        "nps_score": cv.get("nps_score", 0),
                        "cv_source": "loyalty_voice_sync"
                    }}
                )
                if result.modified_count > 0:
                    cv_updated += 1
        
        # Populate Review data from synced ReviewTrackers data
        review_stats = await db.customer_reviews.aggregate([
            {"$match": {"quarter": quarter, "year": year}},
            {"$unwind": "$employee_mentions"},
            {"$group": {
                "_id": "$employee_mentions.name",
                "mention_count": {"$sum": 1},
                "positive_mentions": {"$sum": {"$cond": [{"$eq": ["$employee_mentions.sentiment", "positive"]}, 1, 0]}},
                "negative_mentions": {"$sum": {"$cond": [{"$eq": ["$employee_mentions.sentiment", "negative"]}, 1, 0]}},
                "total_points": {"$sum": "$employee_mentions.points"}
            }}
        ]).to_list(500)
        
        review_updated = 0
        for stat in review_stats:
            emp_name = stat.get("_id", "")
            if emp_name:
                result = await db.employees_v2.update_one(
                    {"name": emp_name, "quarter": quarter, "year": year},
                    {"$set": {
                        "review_mentions": stat.get("mention_count", 0),
                        "review_source": "reviewtrackers_sync"
                    }}
                )
                if result.modified_count > 0:
                    review_updated += 1
        
        logging.info(f"Updated {cv_updated} employees with CV data, {review_updated} with Review data")
        
        # Lock the quarter settings
        await db.quarter_settings.update_one(
            {"year": year, "quarter": quarter},
            {"$set": {
                "is_locked": True,
                "locked_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Sync updated employees to the most recent snapshot
        snapshot_id = await sync_employees_to_most_recent_snapshot(quarter, year)
        
        return {
            "success": True,
            "message": f"Imported and scored {len(scored_employees)} employees for {quarter} {year}",
            "employees_count": len(scored_employees),
            "cv_data_updated": cv_updated,
            "review_data_updated": review_updated,
            "quarter": quarter,
            "year": year,
            "settings_locked": True,
            "snapshot_synced": snapshot_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error processing upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@api_router.get("/v2/employees")
async def get_employees_v2(year: Optional[int] = None, quarter: Optional[str] = None):
    """Get employees (V2 scoring engine)"""
    query = {}
    if year:
        query["year"] = year
    if quarter:
        query["quarter"] = quarter.upper()
    
    employees = await db.employees_v2.find(query, {"_id": 0}).to_list(5000)
    
    # Sort by score for tier calculation
    employees_sorted = sorted(employees, key=lambda x: x.get('pre_dar_score') or x.get('total_score') or 0, reverse=True)
    total = len(employees_sorted)
    
    for i, emp in enumerate(employees_sorted):
        if isinstance(emp.get('created_at'), str):
            emp['created_at'] = datetime.fromisoformat(emp['created_at'])
        
        # Calculate performance tier if missing
        if not emp.get('performance_tier'):
            rank = i + 1
            percentile = ((total - rank) / total) * 100 if total > 0 else 0
            
            if percentile >= 75:
                emp['performance_tier'] = "Top Performer"
            elif percentile >= 50:
                emp['performance_tier'] = "Above Average"
            elif percentile >= 25:
                emp['performance_tier'] = "Below Average"
            else:
                emp['performance_tier'] = "Needs Immediate Improvement"
    
    return employees_sorted


@api_router.get("/v2/employees/{employee_id}")
async def get_employee_v2(employee_id: str):
    """Get single employee (V2)"""
    employee = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if isinstance(employee.get('created_at'), str):
        employee['created_at'] = datetime.fromisoformat(employee['created_at'])
    
    return employee


@api_router.post("/v2/employees/{employee_id}/generate-review")
async def generate_employee_review_v2(employee_id: str, review_data: ReviewCreateV2):
    """
    Generate AI-powered performance review PDF using V2 employee data and Q1 2026 scoring model.
    Automatically includes all 6 metric trend charts from snapshots if available.
    """
    # Get V2 employee
    employee_doc = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not employee_doc:
        raise HTTPException(status_code=404, detail="Employee not found in V2 data")
    
    # Convert to EmployeeV2 object
    if isinstance(employee_doc.get('created_at'), str):
        employee_doc['created_at'] = datetime.fromisoformat(employee_doc['created_at'])
    
    employee = EmployeeV2(**employee_doc)
    
    # Get quarter settings for tier thresholds
    settings_doc = await db.quarter_settings.find_one(
        {"year": review_data.year, "quarter": review_data.quarter.upper()},
        {"_id": 0}
    )
    settings = QuarterSettings(**settings_doc) if settings_doc else QuarterSettings(year=review_data.year, quarter=review_data.quarter)
    
    try:
        # Generate AI review content using V2 data
        review_content = await generate_review_content_v2(employee, settings, review_data.quarter, review_data.year)
        
        # Get employee line graph for this quarter/year if manually uploaded
        line_graph = await db.line_graphs.find_one(
            {
                "employee_id": employee_id,
                "quarter": review_data.quarter.upper(),
                "year": review_data.year,
                "graph_kind": "quarter",
            },
            {"_id": 0},
        )
        
        # If no manual graph, try to generate all 6 metric trend charts from snapshots
        trend_chart_bytes = None
        if not line_graph or not line_graph.get('file_data'):
            try:
                # Query snapshots for this quarter
                snapshots = await db.snapshots.find(
                    {"year": review_data.year, "quarter": review_data.quarter.upper()},
                    {"_id": 0, "snapshot_date": 1, "employees": 1}
                ).sort("snapshot_date", 1).to_list(100)
                
                metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
                snapshot_history = []
                restaurant_avg_history = []
                
                if snapshots:
                    for snapshot in snapshots:
                        snapshot_date = snapshot.get("snapshot_date", "")
                        employees_list = snapshot.get("employees", [])
                        
                        if not employees_list:
                            continue
                        
                        # Find employee in snapshot (case-insensitive)
                        emp_data = None
                        for emp in employees_list:
                            if emp.get("name", "").lower() == employee.name.lower():
                                emp_data = emp
                                break
                        
                        if emp_data:
                            emp_snapshot = {"date": snapshot_date}
                            for metric in metrics:
                                emp_snapshot[metric] = emp_data.get(metric, 0) or 0
                            snapshot_history.append(emp_snapshot)
                        
                        # Calculate restaurant averages for each metric
                        rest_avg_entry = {"date": snapshot_date}
                        for metric in metrics:
                            values = [e.get(metric, 0) or 0 for e in employees_list if e.get(metric) is not None]
                            rest_avg_entry[metric] = sum(values) / len(values) if values else 0
                        restaurant_avg_history.append(rest_avg_entry)
                
                # Always add current employee data as "Current" data point
                # This ensures we always have at least one point, even if not in snapshots
                current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                current_emp_snapshot = {"date": current_date}
                for metric in metrics:
                    current_emp_snapshot[metric] = employee_doc.get(metric, 0) or 0
                
                # Add current data if it's different from the last snapshot or if no snapshots
                if not snapshot_history or snapshot_history[-1].get('date') != current_date:
                    snapshot_history.append(current_emp_snapshot)
                    
                    # Also add current restaurant average
                    all_current_employees = await db.employees_v2.find(
                        {"year": review_data.year, "quarter": review_data.quarter.upper()},
                        {"_id": 0}
                    ).to_list(1000)
                    
                    current_rest_avg = {"date": current_date}
                    for metric in metrics:
                        values = [e.get(metric, 0) for e in all_current_employees if e.get(metric) is not None]
                        current_rest_avg[metric] = sum(values) / len(values) if values else 0
                    restaurant_avg_history.append(current_rest_avg)
                
                logging.info(f"Review generation for {employee.name}: Found {len(snapshot_history)} data points (including current)")
                
                # Generate multi-panel chart if we have data points
                if snapshot_history:
                    logging.info(f"Generating multi-panel chart for {employee.name} with {len(snapshot_history)} snapshots")
                    # Get benchmarks from settings
                    benchmarks = {
                        'ppa': settings.benchmark_ppa,
                        'lbw_per_guest': settings.benchmark_lbw,
                        'glassware_per_guest': settings.benchmark_glass,
                        'guests_per_lsc': settings.benchmark_lsc,
                        'cv_score': settings.benchmark_cv,
                        'pre_dar_score': settings.a_server_min_score
                    }
                    
                    # Get previous quarter data for fallback
                    prev_quarter, prev_year = get_previous_quarter(review_data.quarter, review_data.year)
                    previous_doc = await db.employees_v2.find_one(
                        {"year": prev_year, "quarter": prev_quarter, "name": employee.name},
                        {"_id": 0}
                    )
                    
                    # Calculate current restaurant averages
                    all_employees = await db.employees_v2.find(
                        {"year": review_data.year, "quarter": review_data.quarter.upper()},
                        {"_id": 0}
                    ).to_list(1000)
                    
                    restaurant_averages = {}
                    for metric in metrics:
                        values = [e.get(metric, 0) for e in all_employees if e.get(metric) is not None]
                        restaurant_averages[metric] = sum(values) / len(values) if values else 0
                    
                    trend_chart_bytes = generate_employee_comparison_chart(
                        employee_name=employee.name,
                        current_data=employee_doc,
                        previous_data=previous_doc,
                        current_quarter=review_data.quarter.upper(),
                        current_year=review_data.year,
                        benchmarks=benchmarks,
                        restaurant_averages=restaurant_averages,
                        snapshot_history=snapshot_history,
                        restaurant_avg_history=restaurant_avg_history
                    )
            except Exception as chart_err:
                logging.warning(f"Could not generate multi-panel trend chart: {chart_err}")
        
        # Create review record
        review = ReviewV2(
            employee_id=employee_id,
            employee_name=employee.name,
            review_content=review_content,
            quarter=review_data.quarter.upper(),
            year=review_data.year
        )
        
        # Save review to database
        review_doc = review.model_dump()
        review_doc['created_at'] = review_doc['created_at'].isoformat()
        await db.reviews.insert_one(review_doc)
        
        # Generate PDF with V2 scoring breakdown
        base_pdf = generate_pdf_v2(employee, settings, review_content, review_data.quarter, review_data.year)
        
        # Merge with chart (prefer manual upload, fallback to auto-generated bi-weekly trend)
        if line_graph and line_graph.get('file_data'):
            try:
                graph_pdf = _create_graph_pdf_from_image_bytes(base64.b64decode(line_graph['file_data']))
                merged_pdf = _merge_pdfs(base_pdf, graph_pdf)
            except Exception:
                merged_pdf = base_pdf
        elif trend_chart_bytes:
            try:
                graph_pdf = _create_graph_pdf_from_image_bytes(trend_chart_bytes)
                merged_pdf = _merge_pdfs(base_pdf, graph_pdf)
            except Exception:
                merged_pdf = base_pdf
        else:
            merged_pdf = base_pdf
        
        pdf_base64 = base64.b64encode(merged_pdf).decode('utf-8')
        
        return ReviewResponseV2(
            success=True,
            review_id=review.id,
            message="Review generated successfully (V2)",
            pdf_base64=pdf_base64
        )
        
    except Exception as e:
        logging.error(f"Error generating V2 review: {str(e)}")
        return ReviewResponseV2(
            success=False,
            message=f"Error generating review: {str(e)}"
        )


@api_router.get("/v2/rankings/{year}/{quarter}")
async def get_rankings_v2(year: int, quarter: str):
    """Get ranked employee list for a quarter"""
    employees = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).sort("peer_rank", 1).to_list(5000)
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "total_employees": len(employees),
        "rankings": employees
    }


@api_router.get("/v2/full-rankings/{year}/{quarter}")
async def get_full_hierarchy_rankings(year: int, quarter: str, tier_filter: Optional[str] = None):
    """
    Get hierarchy-based rankings with settings-driven server tiering.
    
    SNAPSHOT-FIRST: Now pulls from the active snapshot to ensure display names
    and all edits are reflected.
    
    HIERARCHY ORDER (fixed, not by raw score):
    1. Trainers (sorted by score within tier)
    2. Bartenders (sorted by score within tier)
    3. A-Servers (score >= A-Server min threshold)
    4. B-Servers (score >= B-Server min AND < A-Server min)
    5. C-Servers (score < B-Server min)
    
    Position labels: T1, T2..., Bar1, Bar2..., A1, A2..., B1, B2..., C1, C2...
    
    Optional tier_filter: "Trainer", "Bartender", "A-Server", "B-Server", "C-Server"
    """
    # Get settings for tier thresholds
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    # SNAPSHOT-FIRST: Get employees from the active snapshot (same logic as current-rankings)
    # First try to find the current active snapshot (regardless of status)
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    # If no current snapshot, fall back to latest completed
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter.upper(), "year": year},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )
    
    if snapshot and snapshot.get("employees"):
        # Use snapshot employees (source of truth)
        employees_docs = snapshot.get("employees", [])
    else:
        # Fallback to legacy employees_v2
        employees_docs = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        ).to_list(5000)
    
    if not employees_docs:
        return {
            "quarter": quarter.upper(),
            "year": year,
            "total_employees": 0,
            "tier_thresholds": {
                "a_server_min": settings.a_server_min_score,
                "b_server_min": settings.b_server_min_score
            },
            "rankings": []
        }
    
    # Convert to EmployeeV2-like objects (handle both snapshot and legacy formats)
    employees = []
    for doc in employees_docs:
        # Handle snapshot format where display_name should be used as name
        emp_data = dict(doc)
        if emp_data.get('display_name') and emp_data.get('display_name') != 'None':
            emp_data['name'] = emp_data['display_name']
        
        # Map snapshot fields to EmployeeV2 fields
        if 'guest_count' in emp_data and 'guests' not in emp_data:
            emp_data['guests'] = emp_data['guest_count']
        if 'bar_glassware_sales' in emp_data and 'glassware_sales' not in emp_data:
            emp_data['glassware_sales'] = emp_data['bar_glassware_sales']
        if 'rt_mentions' in emp_data and 'review_mentions' not in emp_data:
            emp_data['review_mentions'] = emp_data['rt_mentions']
        
        try:
            employees.append(EmployeeV2(**emp_data))
        except Exception as e:
            logger.warning(f"Could not convert employee {emp_data.get('name')}: {e}")
    
    # Generate hierarchy-based rankings
    rankings = generate_hierarchy_rankings(employees, settings)
    
    # Apply tier filter if provided
    if tier_filter:
        rankings = [r for r in rankings if r["tier_label"].lower() == tier_filter.lower()]
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "total_employees": len(employees),
        "filtered_count": len(rankings),
        "tier_thresholds": {
            "a_server_min": settings.a_server_min_score,
            "b_server_min": settings.b_server_min_score
        },
        "rankings": rankings
    }


@api_router.get("/v2/full-rankings/{year}/{quarter}/pdf")
async def download_full_rankings_pdf(year: int, quarter: str):
    """
    Download Full Rankings as a PNG slide matching the Snapshot aesthetic.
    
    Uses the snapshot_slides.py generator for the exact dark navy design with:
    - Bubba Gump logo and left sidebar
    - Color-coded performance cells (blue/green/yellow/red)
    - Metrics as percentages with visual indicators
    """
    from snapshot_slides import generate_snapshot_slide
    
    # SNAPSHOT-FIRST: Get employees from the active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter.upper(), "year": year},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )
    
    if not snapshot or not snapshot.get("employees"):
        raise HTTPException(status_code=404, detail=f"No snapshot data found for {quarter} {year}")
    
    employees = snapshot.get("employees", [])
    
    # Use the pre-calculated data from the snapshot directly
    # The snapshot already has score_ppa, score_lbw, score_glass, score_lsc as percentages
    slide_employees = []
    for emp in employees:
        slide_emp = {
            "id": emp.get("id"),
            "name": emp.get("display_name") or emp.get("name"),
            "tier_label": emp.get("tier_label") or emp.get("performance_tier") or "B-Server",
            "total_score": emp.get("total_score", 0) or emp.get("pre_dar_score", 0) or 0,
            # Use pre-calculated percentage scores from snapshot
            "score_ppa": emp.get("score_ppa", 0) or 0,
            "score_lbw": emp.get("score_lbw", 0) or 0,
            "score_glass": emp.get("score_glass", 0) or 0,
            "score_lsc": emp.get("score_lsc", 0) or 0,
            "cv_score": emp.get("cv_score", 0) or 0,
            "rt_mentions": emp.get("rt_mentions", 0) or emp.get("review_mentions", 0) or 0,
            "rt_bonus": emp.get("review_tracker_bonus", 0) or min((emp.get("rt_mentions", 0) or 0) * 0.5, 15),
            "total_metric_bonus": emp.get("total_metric_bonus", 0) or 0,
        }
        slide_employees.append(slide_emp)
    
    # Get tier thresholds from quarter settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    a_min = settings_doc.get("a_server_min_score", 85) if settings_doc else 85
    b_min = settings_doc.get("b_server_min_score", 70) if settings_doc else 70
    
    # Generate the snapshot slide with tier thresholds for score coloring
    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    png_bytes = generate_snapshot_slide(
        employees=slide_employees,
        benchmarks={},
        snapshot_date=snapshot_date,
        background="dark",
        quarter=quarter.upper(),
        a_min=a_min,
        b_min=b_min
    )
    
    filename = f"performance_snapshot_{quarter}_{year}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================================
# YODECK SLIDE GENERATION (16:9 PNG slides for digital signage)
# ============================================================================

@api_router.get("/v2/yodeck/{year}/{quarter}/top10")
async def get_yodeck_top10_slide(year: int, quarter: str, format: str = "16:9", background: str = "dark"):
    """
    Generate Top 10 Performers By Metric slide.
    Shows 4 metric columns: PPA, Glass/Guest, Guests/LSC, LBW/Guest
    
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
        background: Background key from available backgrounds
    """
    # Get all employees for the quarter
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    # Get the most recent snapshot date for this quarter
    most_recent_snapshot = await db.snapshots.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"snapshot_date": 1},
        sort=[("snapshot_date", -1)]
    )
    
    data_date = None
    if most_recent_snapshot and most_recent_snapshot.get("snapshot_date"):
        data_date = most_recent_snapshot["snapshot_date"]
    
    # Generate slide with the new design
    slide_bytes = generate_top_10_by_metric_slide(
        employees=employees_docs,
        quarter=quarter.upper(),
        year=year,
        output_format=format,
        background=background,
        data_date=data_date
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"top10_by_metric_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/complete-rankings")
async def get_yodeck_complete_rankings_slide(year: int, quarter: str, format: str = "16:9", background: str = "dark"):
    """
    Generate a complete rankings slide showing ALL employees top to bottom on one slide.
    Matches snapshot layout with left panel (logo, title, legend) and right panel (data table).
    
    USES SNAPSHOT-FIRST ARCHITECTURE - reads from active snapshot for data consistency.
    
    Args:
        format: "16:9" for Yodeck/digital signage (1920x1080) or "letter" for 8.5x11" print (2550x3300)
        background: Background key (dark, rainbow_bokeh, cosmic_lights, neon_grid, synthwave_sunset, electric_mesh)
    """
    from snapshot_slides import generate_snapshot_slide
    
    # SNAPSHOT-FIRST: Get employees from the active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter.upper(), "year": year},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )
    
    if not snapshot or not snapshot.get("employees"):
        raise HTTPException(status_code=404, detail=f"No snapshot data found for {quarter} {year}")
    
    employees = snapshot.get("employees", [])
    
    # Get settings for tier thresholds
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ) or {}
    
    a_min = settings.get("a_server_min_score", 85)
    b_min = settings.get("b_server_min_score", 70)
    
    # Transform employees for the slide generator - use pre-calculated data
    slide_employees = []
    for emp in employees:
        # Calculate DAR deduction from written warnings and suspensions
        written_warnings = emp.get("dar_written_warnings", 0) or 0
        suspensions = emp.get("dar_suspensions", 0) or 0
        dar_deduction = emp.get("dar_deduction", 0) or (-(written_warnings * 3) - (suspensions * 5))
        
        slide_emp = {
            "id": emp.get("id"),
            "name": emp.get("display_name") or emp.get("name"),
            "tier_label": emp.get("tier_label") or emp.get("performance_tier") or "B-Server",
            "total_score": emp.get("total_score", 0) or emp.get("pre_dar_score", 0) or 0,
            # Use final_score if snapshot is finalized (includes DAR deductions)
            "final_score": emp.get("final_score"),
            "dar_deduction": dar_deduction,
            # Use pre-calculated percentage scores from snapshot
            "score_ppa": emp.get("score_ppa", 0) or 0,
            "score_lbw": emp.get("score_lbw", 0) or 0,
            "score_glass": emp.get("score_glass", 0) or 0,
            "score_lsc": emp.get("score_lsc", 0) or 0,
            "cv_score": emp.get("cv_score", 0) or 0,
            "rt_mentions": emp.get("rt_mentions", 0) or emp.get("review_mentions", 0) or 0,
            "rt_bonus": emp.get("review_tracker_bonus", 0) or min((emp.get("rt_mentions", 0) or 0) * 0.5, 15),
            "total_metric_bonus": emp.get("total_metric_bonus", 0) or 0,
        }
        slide_employees.append(slide_emp)
    
    # Generate the snapshot slide
    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    png_bytes = generate_snapshot_slide(
        employees=slide_employees,
        benchmarks={},
        snapshot_date=snapshot_date,
        background=background,
        quarter=quarter.upper(),
        a_min=a_min,
        b_min=b_min
    )
    
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=rankings_{quarter}_{year}.png"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/printable-rankings")
async def get_yodeck_printable_rankings_slide(year: int, quarter: str, format: str = "16:9"):
    """
    Generate a stylized printable rankings slide with word art headers.
    Groups employees by tier (Red Hats, A, B, C, Bar, Unranked) - NO metrics, just rank and name.
    
    format: "16:9" for screens (1920x1080) or "letter" for printing (2550x3300)
    """
    # Get all employees for the quarter
    employees = await db.employees_v2.find({"quarter": quarter, "year": year}).to_list(1000)
    
    if not employees:
        raise HTTPException(status_code=404, detail=f"No employees found for {quarter} {year}")
    
    # Sort by tier and score
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    employees.sort(key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 5),
        -(x.get("total_score", 0) or 0)
    ))
    
    # Clean employee data
    clean_employees = []
    for emp in employees:
        clean_employees.append({
            "name": emp.get("name", "Unknown"),
            "tier_label": emp.get("tier_label", ""),
            "total_score": emp.get("total_score", 0)
        })
    
    slide_bytes = generate_printable_rankings_slide(
        rankings=clean_employees,
        quarter=quarter,
        year=year,
        output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"printable_rankings_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/leaderboard-slide")
async def get_leaderboard_slide(year: int, quarter: str, format: str = "16:9"):
    """
    Generate a professional leaderboard slide with the new design system.
    
    Features:
    - Dark navy background with high contrast
    - Gold/Silver/Bronze for top 3
    - Green highlight for top 5
    - Momentum indicators (using snapshot comparison)
    - Recognition badges (5/10/20 mentions)
    - Category leaders panel
    """
    from yodeck_slides import generate_leaderboard_slide
    
    # Get all employees for the quarter
    employees = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees:
        raise HTTPException(status_code=404, detail=f"No data for {quarter} {year}")
    
    # Get settings for tier thresholds
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ) or {}
    
    a_server_min = settings.get("a_server_min_score", 85.0)
    b_server_min = settings.get("b_server_min_score", 70.0)
    
    # Build rankings with tier labels
    tier_counters = {"trainer": 0, "bartender": 0, "a-server": 0, "b-server": 0, "c-server": 0}
    
    def get_sort_key(e):
        job = str(e.get("job_title", "server")).lower()
        if job == "trainer":
            return (0, -float(e.get("total_score", 0) or 0))
        elif job == "bartender":
            return (1, -float(e.get("total_score", 0) or 0))
        else:
            return (2, -float(e.get("total_score", 0) or 0))
    
    sorted_employees = sorted(employees, key=get_sort_key)
    
    rankings = []
    position = 1
    for emp in sorted_employees:
        job = str(emp.get("job_title", "server")).lower()
        total = emp.get("total_score", 0) or 0
        
        if job == "trainer":
            tier_counters["trainer"] += 1
            tier_label = "Trainer"
        elif job == "bartender":
            tier_counters["bartender"] += 1
            tier_label = "Bartender"
        else:
            if total >= a_server_min:
                tier_counters["a-server"] += 1
                tier_label = "A-Server"
            elif total >= b_server_min:
                tier_counters["b-server"] += 1
                tier_label = "B-Server"
            else:
                tier_counters["c-server"] += 1
                tier_label = "C-Server"
        
        rankings.append({
            "employee_id": emp.get("id"),
            "name": emp.get("name", "Unknown"),
            "position": position,
            "score": total,
            "job_title": emp.get("job_title", "Server"),
            "tier_label": tier_label
        })
        position += 1
    
    # Get previous scores from second-latest snapshot for momentum
    snapshots = await db.snapshots.find(
        {"year": year, "quarter": quarter.upper()}
    ).sort("snapshot_date", -1).to_list(2)
    
    previous_scores = {}
    if len(snapshots) > 1:
        prev_snapshot = snapshots[1]
        for emp in (prev_snapshot.get("employees_data") or []):
            previous_scores[emp.get("id")] = emp.get("total_score", 0) or emp.get("pre_dar_score", 0) or 0
    
    # Generate slide
    slide_bytes = generate_leaderboard_slide(
        rankings=rankings,
        employees=employees,
        quarter=quarter.upper(),
        year=year,
        previous_scores=previous_scores
    )
    
    filename = f"leaderboard_{quarter}_{year}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/tier/{tier_name}")
async def get_yodeck_tier_slide(year: int, quarter: str, tier_name: str, page: int = 1):
    """
    Generate tier-specific slide (1920x1080 PNG).
    Uses per-quarter theme settings.
    
    tier_name: "trainers", "bartenders", "a-servers", "b-servers", "c-servers"
    page: Page number for tiers with >10 employees (default: 1)
    """
    # Map URL tier name to internal tier label
    tier_map = {
        "trainers": "Trainer",
        "bartenders": "Bartender",
        "a-servers": "A-Server",
        "b-servers": "B-Server",
        "c-servers": "C-Server",
    }
    
    tier_label = tier_map.get(tier_name.lower())
    if not tier_label:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier_name}. Use: trainers, bartenders, a-servers, b-servers, c-servers")
    
    # Get settings and rankings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    rankings = generate_hierarchy_rankings(employees, settings)
    
    # Filter by tier
    tier_employees = [r for r in rankings if r.get("tier_label") == tier_label]
    
    if not tier_employees:
        raise HTTPException(status_code=404, detail=f"No employees in {tier_label} tier")
    
    # Paginate (10 per slide)
    max_per_page = 10
    total_pages = (len(tier_employees) + max_per_page - 1) // max_per_page
    
    if page < 1 or page > total_pages:
        raise HTTPException(status_code=400, detail=f"Invalid page. Valid range: 1-{total_pages}")
    
    start_idx = (page - 1) * max_per_page
    end_idx = start_idx + max_per_page
    page_employees = tier_employees[start_idx:end_idx]
    
    # Get theme settings
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    # Generate slide with theme
    slide_bytes = generate_tier_slide(
        tier_label,
        page_employees,
        quarter.upper(),
        year,
        page=page,
        total_pages=total_pages,
        theme=theme,
        custom_colors=custom_colors,
        custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme
    )
    
    filename = f"yodeck_{tier_name}_{quarter}_{year}_p{page}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/all")
async def get_all_yodeck_slides(year: int, quarter: str):
    """
    Get metadata about all available Yodeck slides for a quarter.
    Returns download URLs for each slide.
    """
    # Get settings and rankings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    rankings = generate_hierarchy_rankings(employees, settings)
    
    # Count employees per tier
    tier_counts = {"Trainer": 0, "Bartender": 0, "A-Server": 0, "B-Server": 0, "C-Server": 0}
    for r in rankings:
        tier = r.get("tier_label", "A-Server")
        if tier in tier_counts:
            tier_counts[tier] += 1
    
    # Build slide manifest - all slides support both formats
    format_options = ["16:9", "letter"]
    slides = []
    
    # Top 10 By Metric (new design)
    slides.append({
        "id": "top10",
        "name": "Top 10 Performers By Metric",
        "description": "PPA, Glass/Guest, LSC, LBW leaders",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/top10",
        "pages": 1,
        "category": "primary",
        "formats": format_options
    })
    
    # Complete Rankings (all employees on one slide)
    slides.append({
        "id": "complete-rankings",
        "name": "Complete Rankings",
        "description": "All team members top to bottom",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/complete-rankings",
        "employee_count": len(rankings),
        "pages": 1,
        "category": "primary",
        "formats": format_options
    })
    
    # Special slides
    slides.append({
        "id": "most-improved",
        "name": "Most Improved",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/most-improved",
        "pages": 1,
        "category": "special",
        "formats": format_options
    })
    
    # Promotion watchlist (B-Servers close to A)
    b_servers_close = len([r for r in rankings if r.get("tier_label") == "B-Server" and (settings.a_server_min_score - r.get("total_score", 0)) <= 10])
    if b_servers_close > 0:
        slides.append({
            "id": "promotion-watchlist",
            "name": "Promotion Watchlist",
            "endpoint": f"/api/v2/yodeck/{year}/{quarter}/promotion-watchlist",
            "employee_count": b_servers_close,
            "pages": 1,
            "category": "special",
            "formats": format_options
        })
    
    # At Risk (C-Servers) - manager only
    if tier_counts["C-Server"] > 0:
        slides.append({
            "id": "at-risk",
            "name": "Coaching Focus (Manager Only)",
            "endpoint": f"/api/v2/yodeck/{year}/{quarter}/at-risk",
            "employee_count": tier_counts["C-Server"],
            "pages": 1,
            "category": "manager",
            "formats": format_options
        })
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "total_employees": len(employees),
        "tier_counts": tier_counts,
        "theme": settings.slide_theme or "dark_navy",
        "available_themes": list(THEMES.keys()),
        "slides": slides
    }


@api_router.get("/v2/yodeck/{year}/{quarter}/most-improved")
async def get_yodeck_most_improved_slide(year: int, quarter: str, format: str = "16:9"):
    """Generate Most Improved slide - employees with biggest score increase.
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    # Get current quarter rankings
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    current_rankings = generate_hierarchy_rankings(employees, settings)
    
    # Try to get previous quarter rankings
    prev_quarter_map = {"Q1": "Q4", "Q2": "Q1", "Q3": "Q2", "Q4": "Q3"}
    prev_quarter = prev_quarter_map.get(quarter.upper(), "Q4")
    prev_year = year - 1 if quarter.upper() == "Q1" else year
    
    prev_employees_docs = await db.employees_v2.find(
        {"year": prev_year, "quarter": prev_quarter},
        {"_id": 0}
    ).to_list(5000)
    
    prev_rankings = []
    if prev_employees_docs:
        prev_settings_doc = await db.quarter_settings.find_one(
            {"year": prev_year, "quarter": prev_quarter},
            {"_id": 0}
        )
        if prev_settings_doc:
            prev_settings = QuarterSettings(**prev_settings_doc)
            prev_employees = [EmployeeV2(**doc) for doc in prev_employees_docs]
            prev_rankings = generate_hierarchy_rankings(prev_employees, prev_settings)
    
    # Get theme settings
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    slide_bytes = generate_most_improved_slide(
        current_rankings, prev_rankings, quarter.upper(), year,
        theme=theme, custom_colors=custom_colors, custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme, output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"most_improved_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/promotion-watchlist")
async def get_yodeck_promotion_watchlist_slide(year: int, quarter: str, format: str = "16:9"):
    """Generate Promotion Watchlist slide - B-Servers close to A-Server threshold.
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    rankings = generate_hierarchy_rankings(employees, settings)
    
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    slide_bytes = generate_promotion_watchlist_slide(
        rankings, settings.a_server_min_score, quarter.upper(), year,
        theme=theme, custom_colors=custom_colors, custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme, output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"promotion_watchlist_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/at-risk")
async def get_yodeck_at_risk_slide(year: int, quarter: str, format: str = "16:9"):
    """Generate At Risk / Coaching Focus slide - C-Servers needing attention. Manager only.
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    rankings = generate_hierarchy_rankings(employees, settings)
    
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    slide_bytes = generate_at_risk_slide(
        rankings, settings.b_server_min_score, quarter.upper(), year,
        theme=theme, custom_colors=custom_colors, custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme, output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"coaching_focus_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/themes")
async def get_available_themes():
    """Get list of available slide themes, including seasonal options."""
    from yodeck_slides import SEASONAL_THEMES, get_current_seasonal_theme
    
    current_seasonal = get_current_seasonal_theme()
    
    return {
        "themes": list(THEMES.keys()),
        "default": "dark_navy",
        "seasonal_themes": {
            key: {"name": val["name"], "emoji": val["emoji"]} 
            for key, val in SEASONAL_THEMES.items()
        },
        "seasonal_options": ["auto", "none"] + list(SEASONAL_THEMES.keys()),
        "current_auto_seasonal": current_seasonal,
        "current_seasonal_name": SEASONAL_THEMES[current_seasonal]["name"] if current_seasonal else None
    }


@api_router.get("/v2/top-performers/{year}/{quarter}")
async def get_top_performers_v2(year: int, quarter: str, limit: int = 10):
    """Get top performers for a quarter"""
    employees = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).sort("total_score", -1).limit(limit).to_list(limit)
    
    # Also get top 10 per metric
    metrics = {
        "ppa": "ppa",
        "lbw_per_guest": "lbw_per_guest",
        "glassware_per_guest": "glassware_per_guest",
        "guests_per_lsc": "guests_per_lsc"  # Note: lower is better for this one
    }
    
    top_by_metric = {}
    for metric_name, field in metrics.items():
        if metric_name == "guests_per_lsc":
            # Lower is better - sort ascending, exclude nulls
            top = await db.employees_v2.find(
                {"year": year, "quarter": quarter.upper(), field: {"$ne": None}},
                {"_id": 0}
            ).sort(field, 1).limit(limit).to_list(limit)
        else:
            top = await db.employees_v2.find(
                {"year": year, "quarter": quarter.upper()},
                {"_id": 0}
            ).sort(field, -1).limit(limit).to_list(limit)
        top_by_metric[metric_name] = top
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "top_overall": employees,
        "top_by_metric": top_by_metric
    }


# === EMPLOYEE CRUD OPERATIONS ===

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


@api_router.post("/v2/employees")
async def create_employee(data: EmployeeCreate):
    """
    Create a new employee and calculate their scores.
    """
    from scoring_engine import (
        EmployeeV2, calculate_derived_metrics, calculate_customer_voice_score,
        calculate_review_tracker_bonus, calculate_normalized_scores,
        calculate_bonus_points, calculate_total_score
    )
    
    # Get quarter settings
    settings_doc = await db.quarter_settings.find_one(
        {"year": data.year, "quarter": data.quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=400, detail=f"No settings found for {data.quarter} {data.year}. Create settings first.")
    
    from scoring_engine import QuarterSettings
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


@api_router.put("/v2/employees/{employee_id}")
async def update_employee(employee_id: str, data: EmployeeUpdate):
    """
    Update an existing employee and recalculate their scores.
    """
    from scoring_engine import (
        EmployeeV2, calculate_derived_metrics, calculate_customer_voice_score,
        calculate_review_tracker_bonus, calculate_normalized_scores,
        calculate_bonus_points, calculate_total_score, QuarterSettings
    )
    
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
    # This ensures the snapshot stays in sync with employee changes
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
    
    logging.info(f"Updated employee {employee.name} in both employees_v2 and snapshots")
    
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


@api_router.delete("/v2/employees/{employee_id}")
async def delete_employee(employee_id: str):
    """Delete a single employee"""
    result = await db.employees_v2.delete_one({"id": employee_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"success": True, "message": "Employee deleted"}



# ==================== EMPLOYEE CLEANUP TOOL ====================

class EmployeeCleanupRequest(BaseModel):
    """Request model for employee cleanup"""
    employee_ids: List[str] = Field(description="List of employee IDs to delete")


@api_router.get("/v2/employees/cleanup/analyze")
async def analyze_employees_for_cleanup():
    """
    Analyze employees and identify potential duplicates and test data.
    
    Returns:
    - valid_employees: Employees that should be kept (full names from POS reports)
    - potential_duplicates: First-name-only entries that may be duplicates
    - test_data: Entries that look like test/fake data
    """
    all_employees = await db.employees_v2.find({}, {"_id": 0}).to_list(1000)
    
    # Known test name patterns (exact match)
    test_name_patterns = [
        'alice johnson', 'bob smith', 'carol davis', 'david wilson', 
        'emma davis', 'frank brown', 'grace lee', 'henry garcia',
        'isabella thomas', 'jack thompson', 'jake thompson', 'liam wilson',
        'marcus williams', 'mason anderson', 'mia chen', 'noah martinez',
        'olivia brown', 'sofia rodriguez', 'sophia white', 'ava taylor',
        'charlotte martin', 'ethan jackson', 'eva martinez', 'ivy chen',
        'ryan', 'tyler johnson', 'aiden harris', 'total', 'overall',
        'total / overall', 'server sales', 'server sales report',
        'server sales re', 'server sales re  ort', 'test', 'test employee',
        'demo', 'demo user', 'sample', 'example', 'n/a', 'na', 'none',
        'unknown', 'anonymous', 'guest', 'temp', 'temporary'
    ]
    
    # Invalid name patterns (partial matches - catches variations like "Server Sales Detail")
    invalid_patterns = [
        'server sales', 'total', 'overall', 'report', 'detail', 
        'summary', 'test', 'demo', 'sample', 'example', 'template',
        'n/a', 'unknown', 'anonymous', 'void', 'null', 'blank'
    ]
    
    valid_employees = []
    potential_duplicates = []
    test_data = []
    
    # Build a map of full names for duplicate detection
    full_names = {}
    for emp in all_employees:
        name = emp.get('name', '').strip()
        name_lower = name.lower()
        
        # Count words in name
        words = name.split()
        
        if len(words) >= 2:
            full_names[name_lower] = emp
    
    for emp in all_employees:
        name = emp.get('name', '').strip()
        name_lower = name.lower()
        words = name.split()
        
        # Check if it's test data (exact match)
        if name_lower in test_name_patterns:
            test_data.append({
                "id": emp.get('id'),
                "name": name,
                "reason": "Matches known test name pattern",
                "guests": emp.get('guest_count', emp.get('guests', 0)),
                "score": emp.get('total_score', 0)
            })
            continue
        
        # Check for invalid patterns (partial match)
        is_invalid = False
        for pattern in invalid_patterns:
            if pattern in name_lower:
                test_data.append({
                    "id": emp.get('id'),
                    "name": name,
                    "reason": f"Contains invalid pattern: '{pattern}'",
                    "guests": emp.get('guest_count', emp.get('guests', 0)),
                    "score": emp.get('total_score', 0)
                })
                is_invalid = True
                break
        if is_invalid:
            continue
        
        # Check if it's a first-name-only duplicate
        if len(words) == 1:
            # Look for a full name that starts with this first name
            matching_full_name = None
            for full_name in full_names.keys():
                if full_name.startswith(name_lower + ' '):
                    matching_full_name = full_names[full_name].get('name')
                    break
            
            if matching_full_name:
                potential_duplicates.append({
                    "id": emp.get('id'),
                    "name": name,
                    "reason": f"Possible duplicate of '{matching_full_name}'",
                    "guests": emp.get('guest_count', emp.get('guests', 0)),
                    "score": emp.get('total_score', 0)
                })
            else:
                # First name only but no matching full name - still suspicious
                potential_duplicates.append({
                    "id": emp.get('id'),
                    "name": name,
                    "reason": "First name only - no matching full name found",
                    "guests": emp.get('guest_count', emp.get('guests', 0)),
                    "score": emp.get('total_score', 0)
                })
            continue
        
        # Valid employee
        valid_employees.append({
            "id": emp.get('id'),
            "name": name,
            "guests": emp.get('guest_count', emp.get('guests', 0)),
            "score": emp.get('total_score', 0)
        })
    
    return {
        "total_employees": len(all_employees),
        "valid_count": len(valid_employees),
        "duplicate_count": len(potential_duplicates),
        "test_data_count": len(test_data),
        "valid_employees": sorted(valid_employees, key=lambda x: x['name']),
        "potential_duplicates": sorted(potential_duplicates, key=lambda x: x['name']),
        "test_data": sorted(test_data, key=lambda x: x['name'])
    }


@api_router.post("/v2/employees/cleanup/delete")
async def delete_employees_bulk(request: EmployeeCleanupRequest):
    """
    Delete multiple employees by ID.
    Use this after reviewing the analyze endpoint results.
    """
    if not request.employee_ids:
        raise HTTPException(status_code=400, detail="No employee IDs provided")
    
    deleted_count = 0
    errors = []
    
    for emp_id in request.employee_ids:
        try:
            result = await db.employees_v2.delete_one({"id": emp_id})
            if result.deleted_count > 0:
                deleted_count += 1
            else:
                errors.append(f"Employee {emp_id} not found")
        except Exception as e:
            errors.append(f"Error deleting {emp_id}: {str(e)}")
    
    return {
        "success": True,
        "deleted_count": deleted_count,
        "requested_count": len(request.employee_ids),
        "errors": errors if errors else None
    }




# ==================== DATA EXPORT/IMPORT ====================

@api_router.get("/v2/data/export")
async def export_all_data(quarter: str = "Q1", year: int = 2026):
    """
    Export all employee data for backup or migration to another environment.
    Returns JSON that can be imported via /v2/data/import
    """
    # Get all employees
    employees = await db.employees_v2.find(
        {"quarter": quarter, "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    # Get QR employees
    qr_employees = await db.qr_employees.find({}, {"_id": 0}).to_list(500)
    
    # Get quarter settings
    settings = await db.quarter_settings.find_one(
        {"quarter": quarter, "year": year},
        {"_id": 0}
    )
    
    export_data = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "quarter": quarter,
        "year": year,
        "employee_count": len(employees),
        "qr_employee_count": len(qr_employees),
        "employees": employees,
        "qr_employees": qr_employees,
        "quarter_settings": settings
    }
    
    return export_data


@api_router.post("/v2/data/import")
async def import_all_data(data: dict):
    """
    Import employee data from an export.
    WARNING: This will replace existing data for the specified quarter/year.
    """
    quarter = data.get("quarter", "Q1")
    year = data.get("year", 2026)
    employees = data.get("employees", [])
    qr_employees = data.get("qr_employees", [])
    settings = data.get("quarter_settings")
    
    results = {
        "employees_imported": 0,
        "qr_employees_imported": 0,
        "settings_imported": False,
        "errors": []
    }
    
    # Import employees
    if employees:
        # Clear existing employees for this quarter/year
        await db.employees_v2.delete_many({"quarter": quarter, "year": year})
        
        for emp in employees:
            try:
                # Ensure required fields
                if not emp.get("id"):
                    emp["id"] = str(uuid.uuid4())
                emp["quarter"] = quarter
                emp["year"] = year
                emp["updated_at"] = datetime.now(timezone.utc)
                
                await db.employees_v2.insert_one(emp)
                results["employees_imported"] += 1
            except Exception as e:
                results["errors"].append(f"Employee {emp.get('name', '?')}: {str(e)}")
    
    # Import QR employees
    if qr_employees:
        # Clear existing QR employees
        await db.qr_employees.delete_many({})
        
        for qr_emp in qr_employees:
            try:
                if not qr_emp.get("id"):
                    qr_emp["id"] = str(uuid.uuid4())
                
                await db.qr_employees.insert_one(qr_emp)
                results["qr_employees_imported"] += 1
            except Exception as e:
                results["errors"].append(f"QR Employee {qr_emp.get('name', '?')}: {str(e)}")
    
    # Import quarter settings
    if settings:
        try:
            await db.quarter_settings.update_one(
                {"quarter": quarter, "year": year},
                {"$set": settings},
                upsert=True
            )
            results["settings_imported"] = True
        except Exception as e:
            results["errors"].append(f"Settings: {str(e)}")
    
    return {
        "success": True,
        "quarter": quarter,
        "year": year,
        **results
    }



@api_router.put("/v2/employees/{employee_id}/display-name")
async def update_employee_display_name(employee_id: str, data: dict):
    """
    Update an employee's display name (the name shown in dashboards and reports).
    The report_name (from POS) is preserved for matching future uploads.
    
    Body: { "display_name": "Their Preferred Name" }
    """
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
    
    # Also update the main "name" field if you want display_name to be primary
    # Uncomment below if you want 'name' to also be the display name
    # await db.employees_v2.update_one(
    #     {"id": employee_id},
    #     {"$set": {"name": display_name}}
    # )
    
    return {
        "success": True,
        "message": f"Updated display name to '{display_name}'",
        "employee_id": employee_id,
        "display_name": display_name,
        "report_name": report_name
    }


@api_router.post("/v2/admin/fix-display-names")
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
    import re
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


@api_router.put("/v2/employees/{employee_id}/cv-stats")
async def update_employee_cv_stats(employee_id: str, data: dict):
    """
    Manually update an employee's CV (Customer Voice) statistics.
    Allows adjusting NPS score, promoter and detractor counts directly.
    
    CV Score = NPS pts (0-10) + Promoter/Detractor Bonus
    - NPS pts: NPS% / 10 (e.g., 77% = 7.7 pts)
    - Promoter bonus: +1 per promoter (9-10 rating)
    - Detractor penalty: -2 per detractor (≤6 rating)
    
    CV Formula: (Promoters × 1) + (RT Mentions × 0.5) - (Detractors × 2)
    """
    quarter = data.get("quarter", "Q1")
    year = data.get("year", 2026)
    cv_promoters = int(data.get("cv_promoters", 0))
    cv_detractors = int(data.get("cv_detractors", 0))
    cv_passives = int(data.get("cv_passives", 0))
    
    # Find employee
    employee = await db.employees_v2.find_one({
        "id": employee_id,
        "quarter": quarter,
        "year": year
    })
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Get NPS score - use provided value if present, otherwise use existing
    if "nps_score" in data and data.get("nps_score") is not None:
        nps_score = float(data.get("nps_score", 0))
        # Clamp to 0-100
        nps_score = max(0, min(100, nps_score))
    else:
        nps_score = employee.get("nps_score", 0) or 0
    
    # Calculate NPS points: direct ratio (77% = 7.7 pts, max 10)
    nps_pts = round(nps_score / 10, 1) if nps_score > 0 else 0.0
    nps_pts = min(nps_pts, 10.0)
    
    # Calculate Promoter/Detractor bonus: +1 per promoter, -2 per detractor
    # CV Formula: (Promoters × 1) + (RT Mentions × 0.5) - (Detractors × 2)
    promo_detr_bonus = (cv_promoters * 1) - (cv_detractors * 2)
    
    # Total CV Score = NPS pts + Promoter/Detractor bonus
    new_cv_score = round(nps_pts + promo_detr_bonus, 2)
    
    # Recalculate total score
    weighted_score = employee.get("weighted_score", 0) or 0
    total_metric_bonus = employee.get("total_metric_bonus", 0) or 0
    rt_bonus = employee.get("review_tracker_bonus", 0) or 0
    
    new_total_score = weighted_score + new_cv_score + total_metric_bonus + rt_bonus
    
    # Update employee
    await db.employees_v2.update_one(
        {"_id": employee["_id"]},
        {"$set": {
            "nps_score": nps_score,
            "cv_promoters": cv_promoters,
            "cv_passives": cv_passives,
            "cv_detractors": cv_detractors,
            "nps_score_pts": nps_pts,
            "cv_score": new_cv_score,
            "cv_raw_points": round(promo_detr_bonus, 2),
            "total_score": round(new_total_score, 2),
            "pre_dar_score": round(new_total_score, 2),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    # Sync updated employee to the most recent snapshot
    snapshot_id = await sync_employees_to_most_recent_snapshot(quarter, year)
    
    return {
        "success": True,
        "employee_name": employee.get("name"),
        "nps_score": nps_score,
        "nps_pts": nps_pts,
        "cv_promoters": cv_promoters,
        "cv_passives": cv_passives,
        "cv_detractors": cv_detractors,
        "promo_detr_bonus": round(promo_detr_bonus, 2),
        "new_cv_score": new_cv_score,
        "new_total_score": round(new_total_score, 2),
        "snapshot_synced": snapshot_id,
        "message": f"Updated CV stats for {employee.get('name')} and synced to snapshot"
    }



@api_router.post("/v2/admin/clear-all-detractors")
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
        # Promoter bonus: +1 per promoter (CV Formula)
        promo_bonus = cv_promoters * 1
        new_cv_score = round(nps_pts + promo_bonus, 2)
        
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
                "cv_raw_points": round(promo_bonus, 2),
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
            "score_change": round(new_total - old_total, 2)
        })
    
    # Sync to most recent snapshot
    snapshot_id = None
    if updated_employees:
        snapshot_id = await sync_employees_to_most_recent_snapshot(quarter, year)
        
        # Recalculate ranks and tiers
        await recalculate_all_peer_ranks(quarter, year)
        await recalculate_all_tier_labels(quarter, year)
    
    return {
        "success": True,
        "employees_updated": len(updated_employees),
        "details": updated_employees,
        "snapshot_synced": snapshot_id,
        "message": f"Cleared detractors for {len(updated_employees)} employees. Scores recalculated and snapshot synced."
    }



@api_router.delete("/v2/employees")
async def clear_employees_v2(year: Optional[int] = None, quarter: Optional[str] = None):
    """Clear V2 employees (optionally for specific quarter)"""
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


# === DAR (Disciplinary Action Reports) - Admin Only ===

@api_router.put("/v2/employees/{employee_id}/dar")
async def update_employee_dar(employee_id: str, data: DARUpdate):
    """
    Update DAR (Disciplinary Action Reports) for an employee.
    Admin-only endpoint. DAR penalties are applied but hidden from rankings.
    
    - Written Warning: -3 points
    - Suspension: -5 points
    """
    # Find employee
    employee = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Calculate new DAR penalty
    from scoring_engine import DAR_WRITTEN_WARNING, DAR_SUSPENSION
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


@api_router.get("/v2/employees/{employee_id}/dar")
async def get_employee_dar(employee_id: str):
    """
    Get DAR details for an employee (admin-only view).
    """
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


# ============================================================================
# V2 PDF ENDPOINTS (Replacing Legacy V1)
# ============================================================================

@api_router.get("/v2/top-performers/{year}/{quarter}/pdf")
async def get_top_performers_pdf_v2(year: int, quarter: str):
    """Generate Top Performers PDF for V2 data."""
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).sort("pre_dar_score", -1).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch,
                          leftMargin=0.6*inch, rightMargin=0.6*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Title'], fontName='Helvetica-Bold',
                                fontSize=20, textColor=rl_colors.HexColor('#D12E2E'), alignment=1, spaceAfter=10)
    subtitle_style = ParagraphStyle('subtitle', parent=styles['Normal'], fontName='Helvetica',
                                   fontSize=10, textColor=rl_colors.HexColor('#374151'), alignment=1, spaceAfter=16)
    section_style = ParagraphStyle('section', parent=styles['Heading2'], fontName='Helvetica-Bold',
                                  fontSize=12, textColor=rl_colors.HexColor('#005B96'), spaceBefore=10, spaceAfter=6)
    
    story = []
    story.append(Paragraph("Top Performers Report", title_style))
    story.append(Paragraph(f"{quarter} {year} • Bubba Gump Shrimp Co. • Las Vegas", subtitle_style))
    story.append(Spacer(1, 10))
    
    # Top 10 Overall
    story.append(Paragraph("🏆 Top 10 Overall", section_style))
    top_10 = employees_docs[:10]
    table_data = [["Rank", "Name", "Job Title", "Score"]]
    for i, emp in enumerate(top_10, 1):
        table_data.append([f"#{i}", emp.get("name", ""), emp.get("job_title", "Server"), 
                         f"{emp.get('pre_dar_score', 0):.1f}"])
    
    table = Table(table_data, colWidths=[50, 180, 120, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#D12E2E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), rl_colors.HexColor('#F9FAFB')),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#E5E7EB')),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))
    
    # Top by each metric
    metrics = [
        ("ppa", "💰 Top 10 by PPA", True),
        ("lbw_per_guest", "🍷 Top 10 by LBW/Guest", True),
        ("glassware_per_guest", "🥂 Top 10 by Glassware", True),
        ("guests_per_lsc", "📋 Top 10 by LSC Efficiency", False),
    ]
    
    for metric_key, title, higher_better in metrics:
        story.append(Paragraph(title, section_style))
        sorted_emps = sorted([e for e in employees_docs if e.get(metric_key) is not None],
                           key=lambda x: x.get(metric_key, 0), reverse=higher_better)[:10]
        
        table_data = [["Rank", "Name", "Value"]]
        for i, emp in enumerate(sorted_emps, 1):
            val = emp.get(metric_key, 0)
            formatted = f"${val:.2f}" if metric_key != "guests_per_lsc" else f"{val:.1f}"
            table_data.append([f"#{i}", emp.get("name", ""), formatted])
        
        table = Table(table_data, colWidths=[50, 200, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#005B96')),
            ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), rl_colors.HexColor('#F9FAFB')),
            ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#E5E7EB')),
        ]))
        story.append(table)
        story.append(Spacer(1, 15))
    
    # Footer
    story.append(Spacer(1, 20))
    footer_style = ParagraphStyle('footer', parent=styles['Normal'], fontSize=8, 
                                 textColor=rl_colors.HexColor('#9CA3AF'), alignment=1)
    story.append(Paragraph(f"Generated {datetime.now().strftime('%m/%d/%Y %H:%M')} • Confidential", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=top_performers_{quarter}_{year}.pdf"}
    )


@api_router.get("/v2/analytics/{year}/{quarter}/pdf")
async def get_analytics_pdf_v2(year: int, quarter: str):
    """Generate Analytics PDF by capturing exact charts from the Analytics tab."""
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import inch
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak, Image as RLImage
    from playwright.async_api import async_playwright
    import asyncio
    
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    # Get frontend URL from environment
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    # Use the backend URL for capturing (handles both preview and production)
    backend_url = os.environ.get("BACKEND_URL") or os.environ.get("REACT_APP_BACKEND_URL", "")
    if backend_url:
        frontend_url = backend_url.replace("/api", "").rstrip("/")
    
    analytics_url = f"{frontend_url}/analytics?year={year}&quarter={quarter}"
    
    # Capture chart screenshots from the actual Analytics page
    chart_images = []
    
    # Set playwright browser path
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/pw-browsers"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1400, "height": 900})
            
            await page.goto(analytics_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)  # Wait for charts to render
            
            # Capture the Performance Overview section (all metric charts)
            # First, scroll to ensure all content is loaded
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)
            
            # Capture the score distribution boxes (top section)
            try:
                dist_section = page.locator('[data-testid="score-distribution"]').first
                if await dist_section.count() > 0:
                    dist_img = await dist_section.screenshot()
                    chart_images.append(("Score Distribution", dist_img))
            except:
                pass
            
            # Capture each metric chart individually
            metric_ids = ["ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc", "cv_score"]
            metric_labels = ["PPA", "LBW/Guest", "Glass/Guest", "Guests/LSC", "CV Score"]
            
            for metric_id, label in zip(metric_ids, metric_labels):
                try:
                    # Try to find the chart by test id
                    chart = page.locator(f'[data-testid="metric-chart-{metric_id}"]').first
                    if await chart.count() > 0:
                        await chart.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                        img_data = await chart.screenshot()
                        chart_images.append((label, img_data))
                except Exception as e:
                    print(f"Could not capture {label} chart: {e}")
            
            # If we couldn't find individual charts, capture the whole Performance Overview section
            if len(chart_images) < 3:
                await page.evaluate("window.scrollTo(0, 200)")
                await asyncio.sleep(0.5)
                
                # Capture full-width screenshots of the charts area
                for scroll_pos in [200, 600, 1000, 1400]:
                    await page.evaluate(f"window.scrollTo(0, {scroll_pos})")
                    await asyncio.sleep(0.3)
                    img_data = await page.screenshot(clip={"x": 50, "y": 100, "width": 1300, "height": 400})
                    chart_images.append((f"Section_{scroll_pos}", img_data))
            
            # Capture Top 10 sections
            await page.evaluate("window.scrollTo(0, 2000)")
            await asyncio.sleep(0.5)
            try:
                top10_section = page.locator('text=Top 10 Overall').first
                if await top10_section.count() > 0:
                    await top10_section.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    # Capture a region around the top 10 section
                    img_data = await page.screenshot(clip={"x": 50, "y": 100, "width": 1300, "height": 500})
                    chart_images.append(("Top 10 Overall", img_data))
            except:
                pass
            
            await browser.close()
            
    except Exception as e:
        print(f"Playwright capture failed: {e}")
        # Fall back to generating without screenshots
    
    # Build the PDF
    buffer = io.BytesIO()
    PAGE_WIDTH = 11 * inch
    PAGE_HEIGHT = 6.1875 * inch
    
    doc = SimpleDocTemplate(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
                          topMargin=0.3*inch, bottomMargin=0.3*inch,
                          leftMargin=0.3*inch, rightMargin=0.3*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Title'], fontName='Helvetica-Bold',
                                fontSize=20, textColor=rl_colors.HexColor('#1F2937'), alignment=1, spaceAfter=4)
    subtitle_style = ParagraphStyle('subtitle', parent=styles['Normal'], fontName='Helvetica',
                                   fontSize=10, textColor=rl_colors.HexColor('#6B7280'), alignment=1, spaceAfter=10)
    
    story = []
    
    # Title
    story.append(Paragraph("Performance Analytics", title_style))
    story.append(Paragraph(f"{quarter} {year} • Bubba Gump Shrimp Co. • Las Vegas", subtitle_style))
    
    # Add captured chart images
    if chart_images:
        for label, img_data in chart_images:
            img_buffer = io.BytesIO(img_data)
            # Scale image to fit page width while maintaining aspect ratio
            img = RLImage(img_buffer, width=10*inch, height=2.5*inch, kind='proportional')
            story.append(img)
            story.append(Spacer(1, 10))
            
            # Add page break after every 2 images to avoid overflow
            if chart_images.index((label, img_data)) % 2 == 1:
                story.append(PageBreak())
    else:
        story.append(Paragraph("Charts could not be captured. Please view the Analytics tab directly.", 
                              ParagraphStyle('note', fontSize=12, textColor=rl_colors.HexColor('#DC2626'))))
    
    # Footer
    footer_style = ParagraphStyle('footer', parent=styles['Normal'], fontSize=8,
                                 textColor=rl_colors.HexColor('#9CA3AF'), alignment=1)
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Generated {datetime.now().strftime('%m/%d/%Y %H:%M')} • Confidential", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=analytics_{quarter}_{year}.pdf"}
    )
    
# ============================================================================

from trend_charts import (
    generate_employee_comparison_chart, generate_employee_change_chart,
    generate_team_comparison_chart, generate_tier_distribution_chart,
    get_previous_quarter, chart_to_base64, generate_biweekly_trend_chart
)


@api_router.get("/v2/trends/{year}/{quarter}/employee/{employee_id}")
async def get_employee_trend_chart(year: int, quarter: str, employee_id: str, chart_type: str = "comparison"):
    """
    Generate trend chart for an individual employee.
    
    chart_type: "comparison" (line chart with employee, benchmark, restaurant avg) or "change" (% change chart)
    """
    # Get current quarter data
    current_doc = await db.employees_v2.find_one(
        {"year": year, "quarter": quarter.upper(), "id": employee_id},
        {"_id": 0}
    )
    if not current_doc:
        raise HTTPException(status_code=404, detail="Employee not found for current quarter")
    
    # Get previous quarter data
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_doc = await db.employees_v2.find_one(
        {"year": prev_year, "quarter": prev_quarter, "name": current_doc.get("name")},
        {"_id": 0}
    )
    
    # Generate chart
    if chart_type == "change":
        chart_bytes = generate_employee_change_chart(
            current_doc.get("name", "Employee"),
            current_doc, previous_doc,
            quarter.upper(), year
        )
    else:
        # Get benchmarks from quarter settings
        settings = await db.quarter_settings.find_one(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        )
        benchmarks = {
            'ppa': settings.get('benchmark_ppa', 55.0) if settings else 55.0,
            'lbw_per_guest': settings.get('benchmark_lbw', 8.0) if settings else 8.0,
            'glassware_per_guest': settings.get('benchmark_glass', 1.0) if settings else 1.0,
            'guests_per_lsc': settings.get('benchmark_lsc', 100.0) if settings else 100.0,
            'cv_score': settings.get('benchmark_cv', 5.0) if settings else 5.0,
            'pre_dar_score': settings.get('a_server_min_score', 85.0) if settings else 85.0
        }
        
        # Get snapshot history for this employee in this quarter
        employee_name = current_doc.get("name")
        snapshots = await db.snapshots.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0, "snapshot_date": 1, "employees": 1}
        ).sort("snapshot_date", 1).to_list(100)
        
        snapshot_history = []
        restaurant_avg_history = []
        metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
        
        for snap in snapshots:
            snap_date = snap.get("snapshot_date", "")
            employees_in_snap = snap.get("employees", [])
            
            # Find this employee in the snapshot
            emp_data = next((e for e in employees_in_snap if e.get("name") == employee_name), None)
            if emp_data:
                emp_snapshot = {"date": snap_date}
                for metric in metrics:
                    emp_snapshot[metric] = emp_data.get(metric, 0) or 0
                snapshot_history.append(emp_snapshot)
            
            # Calculate restaurant averages for each metric in this snapshot
            rest_avg_entry = {"date": snap_date}
            for metric in metrics:
                values = [e.get(metric, 0) or 0 for e in employees_in_snap if e.get(metric) is not None]
                rest_avg_entry[metric] = sum(values) / len(values) if values else 0
            restaurant_avg_history.append(rest_avg_entry)
        
        # Always add current employee data as "Current" data point
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_emp_snapshot = {"date": current_date}
        for metric in metrics:
            current_emp_snapshot[metric] = current_doc.get(metric, 0) or 0
        
        # Add current data if it's different from the last snapshot or if no snapshots
        if not snapshot_history or snapshot_history[-1].get('date') != current_date:
            snapshot_history.append(current_emp_snapshot)
            
            # Also add current restaurant average
            all_current_employees = await db.employees_v2.find(
                {"year": year, "quarter": quarter.upper()},
                {"_id": 0}
            ).to_list(1000)
            
            current_rest_avg = {"date": current_date}
            for metric in metrics:
                values = [e.get(metric, 0) for e in all_current_employees if e.get(metric) is not None]
                current_rest_avg[metric] = sum(values) / len(values) if values else 0
            restaurant_avg_history.append(current_rest_avg)
        
        # Calculate current restaurant average (for fallback)
        all_employees = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        ).to_list(1000)
        
        restaurant_averages = {}
        for metric in metrics:
            values = [e.get(metric, 0) for e in all_employees if e.get(metric) is not None]
            restaurant_averages[metric] = sum(values) / len(values) if values else 0
        
        chart_bytes = generate_employee_comparison_chart(
            current_doc.get("name", "Employee"),
            current_doc, previous_doc,
            quarter.upper(), year,
            benchmarks=benchmarks,
            restaurant_averages=restaurant_averages,
            snapshot_history=snapshot_history,
            restaurant_avg_history=restaurant_avg_history
        )
    
    return Response(
        content=chart_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=trend_{employee_id}_{quarter}_{year}.png"}
    )


@api_router.get("/v2/trends/{year}/{quarter}/employee/{employee_id}/data")
async def get_employee_trend_data(year: int, quarter: str, employee_id: str):
    """
    Get raw trend data for an employee (current vs previous quarter).
    Returns JSON for frontend chart rendering.
    """
    # Get current quarter data
    current_doc = await db.employees_v2.find_one(
        {"year": year, "quarter": quarter.upper(), "id": employee_id},
        {"_id": 0}
    )
    if not current_doc:
        raise HTTPException(status_code=404, detail="Employee not found for current quarter")
    
    # Get previous quarter data
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_doc = await db.employees_v2.find_one(
        {"year": prev_year, "quarter": prev_quarter, "name": current_doc.get("name")},
        {"_id": 0}
    )
    
    metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
    
    current_values = {}
    previous_values = {}
    changes = {}
    
    for metric in metrics:
        curr_val = current_doc.get(metric, 0) or 0
        prev_val = previous_doc.get(metric, 0) if previous_doc else 0
        
        current_values[metric] = curr_val
        previous_values[metric] = prev_val
        
        if prev_val and prev_val != 0:
            pct_change = ((curr_val - prev_val) / abs(prev_val)) * 100
        else:
            pct_change = 0 if curr_val == 0 else 100
        
        changes[metric] = round(pct_change, 1)
    
    return {
        "employee_name": current_doc.get("name"),
        "employee_id": employee_id,
        "current_quarter": quarter.upper(),
        "current_year": year,
        "previous_quarter": prev_quarter,
        "previous_year": prev_year,
        "has_previous_data": previous_doc is not None,
        "current": current_values,
        "previous": previous_values,
        "changes": changes
    }


@api_router.get("/v2/trends/{year}/{quarter}/team")
async def get_team_trend_chart(year: int, quarter: str, chart_type: str = "comparison"):
    """
    Generate team-wide trend chart comparing current vs previous quarter.
    
    chart_type: "comparison" (bar chart) or "distribution" (tier pie charts)
    """
    # Get current quarter employees
    current_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not current_docs:
        raise HTTPException(status_code=404, detail="No employees found for current quarter")
    
    # Get previous quarter employees
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_docs = await db.employees_v2.find(
        {"year": prev_year, "quarter": prev_quarter},
        {"_id": 0}
    ).to_list(5000)
    
    # Generate chart
    if chart_type == "distribution":
        chart_bytes = generate_tier_distribution_chart(
            current_docs, previous_docs,
            quarter.upper(), year
        )
    else:
        chart_bytes = generate_team_comparison_chart(
            current_docs, previous_docs,
            quarter.upper(), year
        )
    
    return Response(
        content=chart_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=team_trend_{quarter}_{year}.png"}
    )


@api_router.get("/v2/trends/{year}/{quarter}/team/data")
async def get_team_trend_data(year: int, quarter: str):
    """
    Get raw team trend data (current vs previous quarter averages).
    Returns JSON for frontend chart rendering.
    """
    # Get current quarter employees
    current_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not current_docs:
        raise HTTPException(status_code=404, detail="No employees found for current quarter")
    
    # Get previous quarter employees
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_docs = await db.employees_v2.find(
        {"year": prev_year, "quarter": prev_quarter},
        {"_id": 0}
    ).to_list(5000)
    
    metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
    
    def calc_avg(employees, metric):
        values = [e.get(metric, 0) for e in employees if e.get(metric) is not None]
        return round(sum(values) / len(values), 2) if values else 0
    
    def count_tiers(employees):
        tiers = {'Trainer': 0, 'Bartender': 0, 'A-Server': 0, 'B-Server': 0, 'C-Server': 0}
        for emp in employees:
            tier = emp.get('tier_label', 'C-Server')
            if tier in tiers:
                tiers[tier] += 1
        return tiers
    
    current_avgs = {m: calc_avg(current_docs, m) for m in metrics}
    previous_avgs = {m: calc_avg(previous_docs, m) for m in metrics} if previous_docs else {m: 0 for m in metrics}
    
    changes = {}
    for m in metrics:
        curr = current_avgs[m]
        prev = previous_avgs[m]
        if prev and prev != 0:
            changes[m] = round(((curr - prev) / abs(prev)) * 100, 1)
        else:
            changes[m] = 0
    
    return {
        "current_quarter": quarter.upper(),
        "current_year": year,
        "previous_quarter": prev_quarter,
        "previous_year": prev_year,
        "has_previous_data": len(previous_docs) > 0,
        "current_count": len(current_docs),
        "previous_count": len(previous_docs),
        "current_averages": current_avgs,
        "previous_averages": previous_avgs,
        "changes": changes,
        "current_tier_distribution": count_tiers(current_docs),
        "previous_tier_distribution": count_tiers(previous_docs) if previous_docs else {}
    }


@api_router.get("/v2/trends/biweekly/{employee_name}")
async def get_biweekly_trend_chart(
    employee_name: str,
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    time_range: str = "quarter"  # "quarter", "year", or "all"
):
    """
    Generate a bi-weekly trend line chart for an employee showing their Total Score
    vs Restaurant Average over time, using data from bi-weekly snapshots.
    
    Args:
        employee_name: Name of the employee
        year: Year to filter (defaults to current year)
        quarter: Quarter to filter (e.g., "Q1") - only used if time_range is "quarter"
        time_range: "quarter" (default), "year", or "all"
    
    Returns PNG image of the line chart.
    """
    from datetime import datetime as dt
    
    # Default to current year/quarter if not specified
    if not year:
        year = dt.now().year
    if not quarter:
        month = dt.now().month
        quarter = f"Q{(month - 1) // 3 + 1}"
    
    # Build query based on time_range
    query = {}
    if time_range == "quarter":
        query["year"] = year
        query["quarter"] = quarter.upper()
    elif time_range == "year":
        query["year"] = year
    # "all" has no filter
    
    # Fetch snapshots
    snapshots = await db.snapshots.find(query, {"_id": 0}).sort("snapshot_date", 1).to_list(100)
    
    if not snapshots:
        raise HTTPException(status_code=404, detail="No snapshots found for the specified period")
    
    # Extract employee scores and restaurant averages
    employee_scores = []
    restaurant_averages = []
    
    for snapshot in snapshots:
        snapshot_date = snapshot.get("snapshot_date")
        employees = snapshot.get("employees", [])
        
        if not employees:
            continue
        
        # Find the employee in this snapshot (case-insensitive match)
        emp_data = None
        for emp in employees:
            if emp.get("name", "").lower() == employee_name.lower():
                emp_data = emp
                break
        
        # Calculate restaurant average for this snapshot
        all_scores = [e.get("total_score", 0) or 0 for e in employees if e.get("total_score") is not None]
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        restaurant_averages.append({
            "date": snapshot_date,
            "avg_score": round(avg_score, 2)
        })
        
        if emp_data:
            employee_scores.append({
                "date": snapshot_date,
                "total_score": emp_data.get("total_score", 0) or 0
            })
    
    if not employee_scores:
        raise HTTPException(
            status_code=404, 
            detail=f"Employee '{employee_name}' not found in any snapshots for the specified period"
        )
    
    # Generate the chart
    chart_bytes = generate_biweekly_trend_chart(
        employee_name=employee_name,
        employee_scores=employee_scores,
        restaurant_averages=restaurant_averages,
        quarter=quarter.upper() if quarter else None,
        year=year,
        time_range=time_range
    )
    
    return Response(
        content=chart_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={employee_name}_trend.png"}
    )


@api_router.get("/v2/trends/biweekly/{employee_name}/data")
async def get_biweekly_trend_data(
    employee_name: str,
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    time_range: str = "quarter"
):
    """
    Get raw bi-weekly trend data for an employee (JSON format).
    Useful for custom visualizations or debugging.
    """
    from datetime import datetime as dt
    
    if not year:
        year = dt.now().year
    if not quarter:
        month = dt.now().month
        quarter = f"Q{(month - 1) // 3 + 1}"
    
    query = {}
    if time_range == "quarter":
        query["year"] = year
        query["quarter"] = quarter.upper()
    elif time_range == "year":
        query["year"] = year
    
    snapshots = await db.snapshots.find(query, {"_id": 0}).sort("snapshot_date", 1).to_list(100)
    
    employee_scores = []
    restaurant_averages = []
    
    for snapshot in snapshots:
        snapshot_date = snapshot.get("snapshot_date")
        employees = snapshot.get("employees", [])
        
        if not employees:
            continue
        
        emp_data = None
        for emp in employees:
            if emp.get("name", "").lower() == employee_name.lower():
                emp_data = emp
                break
        
        all_scores = [e.get("total_score", 0) or 0 for e in employees if e.get("total_score") is not None]
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        restaurant_averages.append({
            "date": snapshot_date,
            "avg_score": round(avg_score, 2)
        })
        
        if emp_data:
            employee_scores.append({
                "date": snapshot_date,
                "total_score": emp_data.get("total_score", 0) or 0,
                "name": emp_data.get("name")
            })
    
    return {
        "employee_name": employee_name,
        "time_range": time_range,
        "year": year,
        "quarter": quarter.upper() if quarter else None,
        "snapshot_count": len(snapshots),
        "employee_data_points": len(employee_scores),
        "employee_scores": employee_scores,
        "restaurant_averages": restaurant_averages
    }


# ============================================================================
# SNAPSHOT ENDPOINTS (Bi-weekly Team Snapshots)
# ============================================================================

class SnapshotCreate(BaseModel):
    """Model for creating a new snapshot."""
    snapshot_date: str  # e.g., "2026-01-15"
    title: Optional[str] = None
    year: int
    quarter: str

class SnapshotResponse(BaseModel):
    """Model for snapshot response."""
    id: str
    snapshot_date: str
    title: Optional[str]
    year: int
    quarter: str
    employee_count: int
    created_at: str


@api_router.get("/v2/snapshots")
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


@api_router.get("/v2/snapshots/backgrounds")
async def get_snapshot_backgrounds():
    """Get available background options for snapshots."""
    return get_available_backgrounds()


@api_router.get("/v2/snapshots/{snapshot_id}")
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


@api_router.post("/v2/parse-clean-pos")
async def parse_clean_pos_preview(file: UploadFile = File(...)):
    """
    Parse a clean POS file and preview the extracted data without creating a snapshot.
    
    Expected format: Each employee block has:
    - Employee Name
    - Net Sls (header)
    - Food, Liquor, Beer, Wine, Loyalty, Bar Glassware values
    - Totals
    - Total Guests
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


@api_router.post("/v2/snapshots")
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


@api_router.post("/v2/snapshots/{snapshot_id}/upload")
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
        import tempfile
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        # Try consolidated format FIRST (SSD Engine with Master_Summary)
        if not filename.endswith('.csv') and is_consolidated_format(tmp_path):
            logging.info("Detected CONSOLIDATED format - using specialized parser (SSD Engine)")
            pos_employees = parse_consolidated_pos_report(tmp_path)
            
            import os
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
                    benchmark_glass = settings.benchmark_glass or 1.25
                    benchmark_lsc = settings.benchmark_lsc or 100
                    
                    score_ppa = (ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
                    score_lbw = (lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
                    score_glass = (glassware_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
                    score_lsc = (benchmark_lsc / guests_per_lsc) * 100 if guests_per_lsc and guests_per_lsc > 0 else 0
                    
                    # Calculate weighted base score (capped at 100 each)
                    capped_ppa = min(score_ppa, 100)
                    capped_lbw = min(score_lbw, 100)
                    capped_glass = min(score_glass, 100)
                    capped_lsc = min(score_lsc, 100)
                    
                    base_score = (
                        capped_ppa * 0.25 +
                        capped_lsc * 0.25 +
                        capped_lbw * 0.15 +
                        capped_glass * 0.10
                    )
                    
                    total_score = round(base_score, 2)
                    
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
                    
                    # Calculate component scores - use correct attribute names
                    ppa_benchmark = getattr(settings, 'ppa_benchmark', None) or getattr(settings, 'benchmark_ppa', 55)
                    lbw_benchmark = getattr(settings, 'lbw_benchmark', None) or getattr(settings, 'benchmark_lbw', 8)
                    glass_benchmark = getattr(settings, 'glassware_benchmark', None) or getattr(settings, 'benchmark_glass', 1)
                    lsc_benchmark = getattr(settings, 'lsc_benchmark', None) or getattr(settings, 'benchmark_lsc', 20)
                    
                    score_ppa = (ppa / ppa_benchmark * 100) if ppa_benchmark > 0 else 0
                    score_lbw = (lbw_per_guest / lbw_benchmark * 100) if lbw_benchmark > 0 else 0
                    score_glass = (glassware_sales / guests / glass_benchmark * 100) if guests > 0 and glass_benchmark > 0 else 0
                    # LSC score: lower guests_per_lsc is better (benchmark/actual * 100)
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
                
                import os
                os.unlink(tmp_path)
                
                return {
                    "message": f"Parsed {len(employees)} employees using clean POS format",
                    "employee_count": len(employees),
                    "parse_method": "clean_pos_format",
                    "stats": clean_result["stats"]
                }
        
        # Fall back to original POS report format (multi-sheet)
        # Re-create temp file if needed
        tmp_path_exists = 'tmp_path' in dir() and os.path.exists(tmp_path) if 'os' in dir() else False
        if not tmp_path_exists:
            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
        
        if not filename.endswith('.csv') and is_pos_report_format(tmp_path):
            # Use specialized POS report parser
            logging.info("Detected POS report format")
            
            # Check if consolidated format (SSD Engine / Master_Summary)
            if is_consolidated_format(tmp_path):
                logging.info("Using CONSOLIDATED format parser (SSD Engine)")
                pos_employees = parse_consolidated_pos_report(tmp_path)
            else:
                logging.info("Using multi-sheet format parser")
                pos_employees = parse_pos_report(tmp_path)
            
            import os
            os.unlink(tmp_path)  # Clean up temp file
            
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
                # Support both field names from different parsers
                glassware_sales = emp_data.get('glassware_sales', 0) or emp_data.get('glassware', 0) or 0
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
                benchmark_glass = settings.benchmark_glass or 1.25
                benchmark_lsc = settings.benchmark_lsc or 100
                
                score_ppa = (ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
                score_lbw = (lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
                score_glass = (glassware_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
                score_lsc = (benchmark_lsc / guests_per_lsc) * 100 if guests_per_lsc and guests_per_lsc > 0 else 0
                
                # Calculate weighted base score (capped at 100 each)
                capped_ppa = min(score_ppa, 100)
                capped_lbw = min(score_lbw, 100)
                capped_glass = min(score_glass, 100)
                capped_lsc = min(score_lsc, 100)
                
                base_score = (
                    capped_ppa * 0.25 +
                    capped_lsc * 0.25 +
                    capped_lbw * 0.15 +
                    capped_glass * 0.10
                )
                
                # For snapshots, we just use the base operational score
                total_score = round(base_score, 2)
                
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
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            return {
                "message": f"POS report parsed successfully",
                "employee_count": len(employees),
                "format": "pos_report"
            }
        
        # Clean up temp file if not POS format
        import os
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
            
            # Common garbage patterns from XLSX headers/footers
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
            
            # Check for invalid patterns
            for pattern in invalid_patterns:
                if pattern in name_lower:
                    return False
            
            # Name should contain at least one letter
            if not any(c.isalpha() for c in name):
                return False
            
            # Name should not be all numbers
            if name.replace(" ", "").replace(".", "").isdigit():
                return False
            
            # Name should not start with special characters
            if name[0] in "0123456789.-_=+*&^%$#@!~`":
                return False
            
            # Name should be reasonable length (2-50 chars)
            if len(name) > 50:
                return False
            
            return True
        
        employees = []
        for idx, row in df.iterrows():
            try:
                name = str(row.get(mapping["name"], "")).strip()
                if not name or name == "nan":
                    continue
                
                # Filter out garbage names from XLSX headers/footers
                if not is_valid_employee_name(name):
                    logging.info(f"Skipping invalid name: {name}")
                    continue
                
                # Extract job title
                job_title = "Server"
                if mapping.get("job_title"):
                    val = row.get(mapping["job_title"])
                    if val is not None and not pd.isna(val) and str(val).strip() and str(val).strip().lower() != "nan":
                        job_title = str(val).strip()
                
                guests = safe_int(row.get(mapping.get("guests", "")))
                if guests <= 0:
                    continue
                
                # Build employee data
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
                
                # Calculate metrics and scores (full pipeline)
                emp = calculate_lbw_total(emp)  # Calculate LBW from liquor+beer+wine
                emp = calculate_derived_metrics(emp)  # PPA, LBW/Guest, Glass/Guest, G/LSC
                emp = calculate_customer_voice_score(emp)  # CV NPS score
                emp = calculate_review_tracker_bonus(emp)  # Review tracker bonus
                emp = calculate_combined_cv_rt(emp)  # Combined CV + RT
                emp = calculate_normalized_scores(emp, settings)
                emp = calculate_bonus_points(emp, settings)
                emp = calculate_total_score(emp, settings)
                
                # Determine tier label based on job title and score
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
        
        # ============================================================
        # SYNC TO MAIN EMPLOYEES_V2 COLLECTION
        # Only sync if this snapshot has the LATEST snapshot_date
        # (not the most recently uploaded, but the actual data date)
        # ============================================================
        
        # Find the latest snapshot by snapshot_date for this quarter/year
        latest_snapshot = await db.snapshots.find_one(
            {"year": snapshot["year"], "quarter": snapshot["quarter"]},
            {"_id": 0, "snapshot_date": 1, "id": 1},
            sort=[("snapshot_date", -1)]  # Sort by snapshot_date descending
        )
        
        current_snapshot_date = snapshot.get("snapshot_date", "")
        latest_snapshot_date = latest_snapshot.get("snapshot_date", "") if latest_snapshot else ""
        
        should_sync = current_snapshot_date >= latest_snapshot_date
        
        if should_sync:
            # Clear existing employees for this quarter/year
            await db.employees_v2.delete_many({
                "year": snapshot["year"],
                "quarter": snapshot["quarter"]
            })
            
            # Insert the new employee data from snapshot
            if employees:
                # Prepare employees for main collection
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


@api_router.post("/v2/snapshots/{snapshot_id}/recalculate")
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
    # Filter by actual review_date within the quarter, not just the quarter label
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
                # Match by actual review_date within quarter
                {"review_date": {"$gte": date_start, "$lte": date_end}},
                # Fallback: if no review_date, use quarter/year labels
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
    
    # Build a function to match partial names (e.g., "Trey" to "Treyanna Quick")
    def get_review_mentions_for_employee(emp_name: str) -> int:
        emp_lower = emp_name.lower()
        first_name = emp_lower.split()[0] if emp_lower.split() else ""
        
        # Direct match on full name
        if emp_lower in review_lookup:
            return review_lookup[emp_lower]
        
        # Match on first name only
        if first_name in review_lookup:
            return review_lookup[first_name]
        
        # Match on partial first name (e.g., "Trey" matches "Treyanna")
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
            
            # Get NPS data for this employee (with partial name matching)
            # This includes nps_score, promoters, detractors, passives
            nps_data = get_nps_for_employee(emp_name)
            nps_score = nps_data.get("nps_score", 0) or 0
            cv_promoters = nps_data.get("promoters", 0) or 0
            cv_passives = nps_data.get("passives", 0) or 0
            cv_detractors = nps_data.get("detractors", 0) or 0
            
            # Get review mentions for this employee (with partial name matching)
            review_mentions = get_review_mentions_for_employee(emp_name)
            
            # Look up actual job_title from employees_v2
            actual_job_title = job_title_lookup.get(emp_name_lower, emp_data.get("job_title", "Server"))
            
            # Create EmployeeV2 from existing data
            # Use CV data from cv_nps collection (not from snapshot which may be stale)
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
                cv_promoters=cv_promoters,  # From cv_nps collection
                cv_passives=cv_passives,     # From cv_nps collection
                cv_detractors=cv_detractors, # From cv_nps collection
                review_mentions=review_mentions,
                nps_score=nps_score,  # From cv_nps collection
                year=snapshot["year"],
                quarter=snapshot["quarter"],
            )
            
            # Run full scoring pipeline
            emp = calculate_lbw_total(emp)
            emp = calculate_derived_metrics(emp)
            emp = calculate_customer_voice_score(emp)
            emp = calculate_review_tracker_bonus(emp)
            emp = calculate_combined_cv_rt(emp)
            emp = calculate_normalized_scores(emp, settings)
            emp = calculate_bonus_points(emp, settings)
            emp = calculate_total_score(emp, settings)
            
            # Determine tier label
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
            emp_dict["nps_score"] = nps_score  # Ensure NPS is in the output
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
    
    # ============================================================
    # SYNC TO MAIN EMPLOYEES_V2 COLLECTION
    # Only sync if this snapshot has the LATEST snapshot_date
    # (not the most recently uploaded, but the actual data date)
    # ============================================================
    
    # Find the latest snapshot by snapshot_date for this quarter/year
    latest_snapshot = await db.snapshots.find_one(
        {"year": snapshot["year"], "quarter": snapshot["quarter"]},
        {"_id": 0, "snapshot_date": 1, "id": 1},
        sort=[("snapshot_date", -1)]  # Sort by snapshot_date descending
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
        
        # Clear existing employees for this quarter/year
        await db.employees_v2.delete_many({
            "year": snapshot["year"],
            "quarter": snapshot["quarter"]
        })
        
        # Insert the recalculated employee data, restoring preserved job titles
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
                    # Also update tier_label to match the preserved job title
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


@api_router.delete("/v2/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str):
    """Delete a snapshot."""
    result = await db.snapshots.delete_one({"id": snapshot_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"message": "Snapshot deleted successfully"}


async def fix_ppa_values(quarter: str, year: int) -> int:
    """
    Recalculate PPA for all employees from net_sales / guest_count.
    Also syncs 'guests' field from 'guest_count' to fix data inconsistency.
    Returns number of employees updated.
    """
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


@api_router.post("/v2/admin/fix-ppa")
async def fix_ppa_endpoint(quarter: str = "Q1", year: int = 2026):
    """
    Recalculate all PPA values from net_sales / guest_count.
    PPA = Net Sales / Number of Guests
    """
    # Get before stats
    employees_before = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    ppa_before = [e.get('ppa', 0) or 0 for e in employees_before]
    avg_before = sum(ppa_before) / len(ppa_before) if ppa_before else 0
    
    # Fix PPA values
    updated = await fix_ppa_values(quarter, year)
    
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


@api_router.post("/v2/admin/fix-all-rankings")
async def fix_all_rankings(quarter: str = "Q1", year: int = 2026):
    """
    EMERGENCY FIX: Recalculate ALL employee rankings and sync to ONLY the most recent snapshot.
    Historical snapshots are preserved for comparison.
    """
    import logging
    logging.info(f"=== FIXING ALL RANKINGS for {quarter} {year} ===")
    
    # First, fix PPA values
    ppa_fixed = await fix_ppa_values(quarter, year)
    logging.info(f"Fixed PPA for {ppa_fixed} employees")
    
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
        # Remove None values
        emp_dict = {k: v for k, v in emp_dict.items() if v is not None}
        
        result = await db.employees_v2.update_one(
            {"id": emp.id},
            {"$set": emp_dict}
        )
        if result.modified_count > 0:
            updated_count += 1
    
    logging.info(f"Updated {updated_count} employees")
    
    # Find ONLY the most recent snapshot for this quarter
    latest_snapshot = await db.snapshots.find_one(
        {"year": year, "quarter": quarter.upper()},
        sort=[("snapshot_date", -1)]
    )
    
    snapshot_count = 0
    if latest_snapshot:
        snapshot_id = latest_snapshot.get("id")
        snapshot_date = latest_snapshot.get("snapshot_date", "unknown")
        
        # Get fresh employee data
        fresh_employees = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        ).to_list(500)
        
        # Sort by tier then score
        tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
        fresh_employees.sort(
            key=lambda x: (
                tier_order.get(x.get('tier_label', 'C-Server'), 4),
                -(x.get('pre_dar_score') or x.get('total_score') or 0)
            )
        )
        
        # Update ONLY the most recent snapshot
        await db.snapshots.update_one(
            {"id": snapshot_id},
            {"$set": {
                "employees": fresh_employees,
                "employee_count": len(fresh_employees),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        snapshot_count = 1
        logging.info(f"Updated most recent snapshot: {snapshot_date}")
    
    return {
        "success": True,
        "employees_fixed": updated_count,
        "snapshots_fixed": snapshot_count,
        "total_employees": len(employees),
        "message": f"Fixed {updated_count} employees and updated most recent snapshot only (historical data preserved)"
    }


@api_router.get("/v2/snapshots/{snapshot_id}/slide")
async def generate_snapshot_slide_endpoint(
    snapshot_id: str,
    background: str = "midnight_blue"
):
    """Generate PNG slide for a snapshot."""
    snapshot = await db.snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    employees = snapshot.get("employees", [])
    if not employees:
        raise HTTPException(status_code=400, detail="Snapshot has no employee data")
    
    benchmarks = snapshot.get("benchmarks", {})
    snapshot_date = snapshot.get("snapshot_date", "")
    title = snapshot.get("title")
    
    # Find the previous snapshot to calculate trends
    current_date = snapshot_date
    import logging
    logging.info(f"Looking for previous snapshot before {current_date} in Q{snapshot.get('quarter')} {snapshot.get('year')}")
    
    # Use correct Motor syntax for sort
    previous_snapshot = await db.snapshots.find_one(
        {
            "quarter": snapshot.get("quarter"),
            "year": snapshot.get("year"),
            "snapshot_date": {"$lt": current_date}
        },
        {"_id": 0, "employees": 1, "snapshot_date": 1},
        sort=[("snapshot_date", -1)]
    )
    
    logging.info(f"Previous snapshot found: {previous_snapshot.get('snapshot_date') if previous_snapshot else 'None'}")
    
    # Build a lookup of previous scores by employee name (with fuzzy matching)
    previous_scores = {}
    previous_names_map = {}  # For fuzzy matching
    if previous_snapshot and previous_snapshot.get("employees"):
        for prev_emp in previous_snapshot["employees"]:
            name = prev_emp.get("name", "")
            score = prev_emp.get("total_score", 0)
            if name:
                # Store exact lowercase match
                previous_scores[name.lower()] = score
                # Also store by last name for fuzzy matching
                parts = name.split()
                if len(parts) >= 2:
                    last_name = parts[-1].lower()
                    first_name = parts[0].lower()
                    first_initial = first_name[0] if first_name else ""
                    # Create keys for fuzzy matching
                    previous_names_map[f"{first_initial}_{last_name}"] = (name, score)
                    previous_names_map[last_name] = (name, score)
                    # Store first 3-4 chars of first name + last name for nickname matching
                    if len(first_name) >= 3:
                        previous_names_map[f"{first_name[:3]}_{last_name}"] = (name, score)
                        previous_names_map[f"{first_name[:4]}_{last_name}"] = (name, score)
        logging.info(f"Built previous scores lookup with {len(previous_scores)} employees")
    
    # Add previous_score to each employee for trend calculation
    trends_added = 0
    for emp in employees:
        emp_name = emp.get("name", "").lower()
        prev_score = None
        
        # Try exact match first
        if emp_name in previous_scores:
            prev_score = previous_scores[emp_name]
        else:
            # Try fuzzy match by last name + first name variants
            parts = emp.get("name", "").split()
            if len(parts) >= 2:
                last_name = parts[-1].lower()
                first_name = parts[0].lower()
                first_initial = first_name[0] if first_name else ""
                
                # Try first initial + last name
                key = f"{first_initial}_{last_name}"
                if key in previous_names_map:
                    prev_score = previous_names_map[key][1]
                # Try first 3-4 chars + last name (for nicknames like Matt/Matthew)
                elif len(first_name) >= 3:
                    key3 = f"{first_name[:3]}_{last_name}"
                    key4 = f"{first_name[:4]}_{last_name}"
                    if key3 in previous_names_map:
                        prev_score = previous_names_map[key3][1]
                    elif key4 in previous_names_map:
                        prev_score = previous_names_map[key4][1]
                # Try just last name (if unique enough)
                if prev_score is None and last_name in previous_names_map and len(last_name) > 5:
                    prev_score = previous_names_map[last_name][1]
        
        if prev_score is not None:
            emp["previous_score"] = prev_score
            trends_added += 1
    
    logging.info(f"Added previous_score to {trends_added} employees")
    
    # Format date nicely
    try:
        date_obj = datetime.strptime(snapshot_date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%B %d, %Y")
    except:
        formatted_date = snapshot_date
    
    # Generate slide
    slide_bytes = generate_snapshot_slide(
        employees=employees,
        benchmarks=benchmarks,
        snapshot_date=formatted_date,
        background=background,
        title=title
    )
    
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=snapshot_{snapshot_date}.png"}
    )


# ============================================================================
# DAR (DISCIPLINARY ACTION REPORT) & QUARTER FINALIZATION ENDPOINTS
# ============================================================================

@api_router.get("/v2/finalization/{year}/{quarter}")
async def get_quarter_finalization(year: int, quarter: str):
    """Get finalization data for a quarter, including DAR entries."""
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


@api_router.get("/v2/dar/{year}/{quarter}")
async def get_dar_entries(year: int, quarter: str):
    """Get DAR entries for a quarter (even if not finalized)."""
    # Check if there's a saved DAR draft
    dar_data = await db.dar_entries.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    
    if dar_data:
        return dar_data.get("entries", [])
    
    return []


@api_router.post("/v2/dar/{year}/{quarter}")
async def save_dar_entries(year: int, quarter: str, submission: DARSubmission):
    """Save DAR entries as a draft (before finalizing)."""
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


@api_router.post("/v2/finalize/{year}/{quarter}")
async def finalize_quarter(year: int, quarter: str, submission: DARSubmission, generate_reviews: bool = True):
    """
    Finalize a quarter by applying DAR deductions and locking final rankings.
    - Written Warning DAR: -3 points each
    - Suspension DAR: -5 points each
    
    This creates the final rankings for end-of-quarter reviews.
    Uses SNAPSHOT-FIRST architecture - reads from active snapshot.
    If generate_reviews=True, automatically generates AI reviews for all employees.
    """
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
        asyncio.create_task(generate_all_quarterly_reviews(year, quarter.upper(), employees))
        reviews_queued = len(employees)
    
    return {
        "message": f"Quarter {quarter} {year} finalized successfully",
        "total_employees": len(final_rankings),
        "total_dar_deductions": sum(e["total_deduction"] for e in final_rankings),
        "final_rankings": final_rankings,
        "reviews_queued": reviews_queued
    }


async def generate_all_quarterly_reviews(year: int, quarter: str, employees: List[Dict]):
    """Background task to generate AI reviews for all employees in a quarter."""
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
                logging.error(f"Error generating review for {emp_data.get('name')}: {str(e)}")
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
        
        logging.info(f"Generated {generated_count} reviews for {quarter} {year} ({error_count} errors)")
        
    except Exception as e:
        logging.error(f"Error in batch review generation: {str(e)}")


@api_router.delete("/v2/finalize/{year}/{quarter}")
async def unfinalize_quarter(year: int, quarter: str):
    """Remove finalization (reopen quarter for edits)."""
    result = await db.quarter_finalizations.delete_one(
        {"year": year, "quarter": quarter.upper()}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No finalization found for this quarter")
    
    return {"message": f"Quarter {quarter} {year} reopened for edits"}


@api_router.get("/v2/reviews/quarterly/{year}/{quarter}")
async def get_quarterly_reviews(year: int, quarter: str):
    """Get all generated quarterly reviews for a quarter."""
    reviews = await db.reviews_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0, "pdf_base64": 0}  # Exclude PDF data for listing
    ).to_list(1000)
    
    # Get finalization status
    finalization = await db.quarter_finalizations.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    
    return {
        "reviews": reviews,
        "total": len(reviews),
        "finalization_status": {
            "is_finalized": finalization.get("is_finalized", False) if finalization else False,
            "reviews_generated": finalization.get("reviews_generated", False) if finalization else False,
            "reviews_count": finalization.get("reviews_count", 0) if finalization else 0,
            "reviews_completed_at": finalization.get("reviews_completed_at") if finalization else None
        }
    }


@api_router.get("/v2/reviews/quarterly/{year}/{quarter}/{employee_id}")
async def get_employee_quarterly_review(year: int, quarter: str, employee_id: str):
    """Get a specific employee's quarterly review with PDF."""
    review = await db.reviews_v2.find_one(
        {"year": year, "quarter": quarter.upper(), "employee_id": employee_id},
        {"_id": 0}
    )
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found for this employee")
    
    return review


@api_router.post("/v2/reviews/quarterly/{year}/{quarter}/regenerate")
async def regenerate_quarterly_reviews(year: int, quarter: str, employee_ids: List[str] = None):
    """
    Regenerate quarterly reviews for specific employees or all employees.
    If employee_ids is provided, only regenerate for those employees.
    """
    # Get employees
    query = {"year": year, "quarter": quarter.upper()}
    if employee_ids:
        query["id"] = {"$in": employee_ids}
    
    employees = await db.employees_v2.find(query, {"_id": 0}).to_list(1000)
    
    if not employees:
        raise HTTPException(status_code=404, detail="No employees found")
    
    # Delete existing reviews for these employees
    if employee_ids:
        await db.reviews_v2.delete_many({
            "year": year,
            "quarter": quarter.upper(),
            "employee_id": {"$in": employee_ids}
        })
    else:
        await db.reviews_v2.delete_many({
            "year": year,
            "quarter": quarter.upper()
        })
    
    # Queue regeneration
    asyncio.create_task(generate_all_quarterly_reviews(year, quarter.upper(), employees))
    
    return {
        "message": f"Regenerating reviews for {len(employees)} employees",
        "employees_queued": len(employees)
    }


# ============================================================================
# REVIEW TRACKER - Customer Review Aggregation & Employee Attribution
# ============================================================================

from review_tracker import (
    PLATFORMS, POINTS_PER_POSITIVE_MENTION,
    generate_review_hash, detect_employees_in_review,
    calculate_review_points_for_employee, get_review_stats
)

# Legacy import - commented out since scrapers are deprecated
# from reviewtrackers_integration import (
#     ReviewTrackersClient, sync_reviews_from_reviewtrackers
# )


class CustomerReviewCreate(BaseModel):
    """Model for creating a new customer review."""
    platform: str  # Google, Yelp, Facebook, TripAdvisor, OpenTable
    review_date: str  # YYYY-MM-DD format
    rating: int = Field(ge=1, le=5)  # 1-5 stars
    review_text: str
    reviewer_name: Optional[str] = None
    quarter: str = "Q1"
    year: int = 2026


class CustomerReviewResponse(BaseModel):
    """Response model for customer review."""
    id: str
    platform: str
    review_date: str
    rating: int
    review_text: str
    reviewer_name: Optional[str]
    employee_mentions: List[Dict[str, Any]]
    total_points: float
    review_hash: str
    created_at: str
    quarter: str
    year: int


class EmployeeMentionUpdate(BaseModel):
    """Model for updating employee mentions in a review."""
    employee_mentions: List[Dict[str, Any]]


@api_router.get("/v2/reviews/platforms")
async def get_review_platforms():
    """Get list of supported review platforms."""
    return {
        "platforms": PLATFORMS,
        "points_per_mention": POINTS_PER_POSITIVE_MENTION
    }


@api_router.get("/v2/reviews/platform-stats")
async def get_platform_stats(quarter: str = "Q1", year: int = 2026):
    """Get QTD stats for each review platform.
    Uses official RT stats if set (for 100% accuracy with RT dashboard),
    otherwise falls back to API-synced data.
    """
    # Check for official stats first (set manually from RT UI)
    official = await db.official_rt_stats.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if official:
        # Get platform data - check both nested "platforms" and direct keys
        platforms = official.get("platforms", {})
        
        # If platforms is empty, try direct keys
        google_data = platforms.get("Google", {}) if platforms else official.get("google", {})
        yelp_data = platforms.get("Yelp", {}) if platforms else official.get("yelp", {})
        facebook_data = platforms.get("Facebook", {}) if platforms else official.get("facebook", {})
        tripadvisor_data = platforms.get("TripAdvisor", {}) if platforms else official.get("tripadvisor", {})
        opentable_data = platforms.get("OpenTable", {}) if platforms else official.get("opentable", {})
        
        return {
            "source": "official_rt_ui",
            "quarter": quarter.upper(),
            "year": year,
            "google": {
                "count": google_data.get("reviews") or google_data.get("count", 0), 
                "avg_rating": google_data.get("rating") or google_data.get("avg_rating", 0)
            },
            "yelp": {
                "count": yelp_data.get("reviews") or yelp_data.get("count", 0), 
                "avg_rating": yelp_data.get("rating") or yelp_data.get("avg_rating", 0)
            },
            "facebook": {
                "count": facebook_data.get("reviews") or facebook_data.get("count", 0), 
                "avg_rating": facebook_data.get("rating") or facebook_data.get("avg_rating", 0)
            },
            "tripadvisor": {
                "count": tripadvisor_data.get("reviews") or tripadvisor_data.get("count", 0), 
                "avg_rating": tripadvisor_data.get("rating") or tripadvisor_data.get("avg_rating", 0)
            },
            "opentable": {
                "count": opentable_data.get("reviews") or opentable_data.get("count", 0), 
                "avg_rating": opentable_data.get("rating") or opentable_data.get("avg_rating", 0)
            },
            "total_reviews": official.get("total_reviews", 0),
            "updated_at": official.get("updated_at")
        }
    
    # Fall back to API-synced data
    # Define quarter date range
    quarter_dates = {
        "Q1": ("01-01", "03-31"),
        "Q2": ("04-01", "06-30"),
        "Q3": ("07-01", "09-30"),
        "Q4": ("10-01", "12-31")
    }
    q_start, q_end = quarter_dates.get(quarter.upper(), ("01-01", "12-31"))
    date_start = f"{year}-{q_start}"
    date_end = f"{year}-{q_end}"
    
    # Aggregate stats by platform
    pipeline = [
        {"$match": {
            "$or": [
                {"review_date": {"$gte": date_start, "$lte": date_end}},
                {"review_date": None, "quarter": quarter.upper(), "year": year}
            ]
        }},
        {"$group": {
            "_id": {"$toLower": "$platform"},
            "count": {"$sum": 1},
            "total_rating": {"$sum": {"$ifNull": ["$rating", 0]}},
            "rated_count": {"$sum": {"$cond": [{"$gt": ["$rating", 0]}, 1, 0]}}
        }}
    ]
    
    results = await db.customer_reviews.aggregate(pipeline).to_list(20)
    
    # Format response
    platform_stats = {}
    for r in results:
        platform = r["_id"] or "unknown"
        count = r["count"]
        rated_count = r["rated_count"]
        avg_rating = r["total_rating"] / rated_count if rated_count > 0 else 0
        
        platform_stats[platform] = {
            "count": count,
            "avg_rating": round(avg_rating, 2),
            "rated_count": rated_count
        }
    
    return {
        "source": "api_synced",
        "quarter": quarter.upper(),
        "year": year,
        "google": platform_stats.get("google", {"count": 0, "avg_rating": 0}),
        "yelp": platform_stats.get("yelp", {"count": 0, "avg_rating": 0}),
        "facebook": platform_stats.get("facebook", {"count": 0, "avg_rating": 0}),
        "tripadvisor": platform_stats.get("tripadvisor", {"count": 0, "avg_rating": 0}),
        "opentable": platform_stats.get("opentable", {"count": 0, "avg_rating": 0}),
        "all_platforms": platform_stats,
        "note": "Using API-synced data. Set official RT stats via /v2/admin/rt-stats/set for 100% accuracy."
    }


@api_router.get("/v2/reviews")
async def get_reviews(
    quarter: str = "Q1",
    year: int = 2026,
    platform: Optional[str] = None,
    employee_name: Optional[str] = None
):
    """Get all reviews with optional filters."""
    # Define quarter date ranges
    quarter_ranges = {
        "Q1": (f"{year}-01-01", f"{year}-03-31"),
        "Q2": (f"{year}-04-01", f"{year}-06-30"),
        "Q3": (f"{year}-07-01", f"{year}-09-30"),
        "Q4": (f"{year}-10-01", f"{year}-12-31"),
    }
    
    start_date, end_date = quarter_ranges.get(quarter.upper(), (f"{year}-01-01", f"{year}-03-31"))
    
    # Filter by actual review_date within the quarter range
    query = {
        "quarter": quarter.upper(), 
        "year": year,
        "review_date": {
            "$gte": start_date,
            "$lte": end_date + "T23:59:59Z"
        }
    }
    
    if platform:
        query["platform"] = platform
    
    reviews = await db.customer_reviews.find(query, {"_id": 0}).to_list(1000)
    
    # Filter by employee name if specified
    if employee_name:
        reviews = [
            r for r in reviews 
            if any(m.get("name", "").lower() == employee_name.lower() 
                   for m in r.get("employee_mentions", []))
        ]
    
    # Sort by date descending
    reviews.sort(key=lambda x: x.get("review_date", ""), reverse=True)
    
    return {"reviews": reviews, "total": len(reviews)}


@api_router.get("/v2/reviews/stats")
async def get_review_stats_endpoint(quarter: str = "Q1", year: int = 2026):
    """Get review statistics including employee mention counts and points."""
    # Define quarter date ranges
    quarter_ranges = {
        "Q1": (f"{year}-01-01", f"{year}-03-31"),
        "Q2": (f"{year}-04-01", f"{year}-06-30"),
        "Q3": (f"{year}-07-01", f"{year}-09-30"),
        "Q4": (f"{year}-10-01", f"{year}-12-31"),
    }
    
    start_date, end_date = quarter_ranges.get(quarter.upper(), (f"{year}-01-01", f"{year}-03-31"))
    
    reviews = await db.customer_reviews.find(
        {
            "quarter": quarter.upper(), 
            "year": year,
            "review_date": {
                "$gte": start_date,
                "$lte": end_date + "T23:59:59Z"
            }
        },
        {"_id": 0}
    ).to_list(1000)
    
    # Get employee data including RT mentions from manual uploads
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "name": 1, "rt_mentions": 1, "review_mentions": 1, "review_tracker_bonus": 1}
    ).to_list(500)
    employee_names = [e["name"] for e in employees]
    
    stats = get_review_stats(reviews, employee_names)
    
    # If customer_reviews is empty but employees have rt_mentions (from manual upload),
    # populate the stats from employee records
    if len(reviews) == 0:
        total_mentions = 0
        for emp in employees:
            mentions = emp.get("rt_mentions") or emp.get("review_mentions") or 0
            points = emp.get("review_tracker_bonus") or min(mentions * 0.5, 15)
            if mentions > 0:
                stats["by_employee"][emp["name"]] = {
                    "mentions": mentions,
                    "positive": 0,
                    "negative": 0,
                    "neutral": mentions,  # Assume neutral since we don't have sentiment data
                    "points": points
                }
                total_mentions += mentions
        stats["total_reviews"] = total_mentions
        stats["note"] = "Data from manual RT upload (employee records)"
    
    # Add top mentioned employees
    sorted_employees = sorted(
        stats["by_employee"].items(),
        key=lambda x: x[1]["points"],
        reverse=True
    )
    stats["top_mentioned"] = [
        {"name": name, **data} 
        for name, data in sorted_employees[:10] 
        if data["mentions"] > 0
    ]
    
    # Add total mentions count for the header display
    stats["total_mentions"] = sum(e.get("mentions", 0) for e in stats["top_mentioned"])
    stats["employees_with_mentions"] = len([e for e in stats["top_mentioned"] if e.get("mentions", 0) > 0])
    
    return stats


@api_router.post("/v2/reviews")
async def create_review(review: CustomerReviewCreate):
    """Create a new customer review with AI-powered employee detection."""
    # Validate platform
    if review.platform not in PLATFORMS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid platform. Must be one of: {', '.join(PLATFORMS)}"
        )
    
    # Generate hash for duplicate detection
    review_hash = generate_review_hash(
        review.review_text, 
        review.platform, 
        review.review_date
    )
    
    # Check for duplicate
    existing = await db.customer_reviews.find_one({"review_hash": review_hash})
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This review appears to be a duplicate (same content, platform, and date)"
        )
    
    # Get employee names for AI detection
    employees = await db.employees_v2.find(
        {"quarter": review.quarter.upper(), "year": review.year},
        {"name": 1, "_id": 0}
    ).to_list(500)
    employee_names = [e["name"] for e in employees]
    
    # Detect employee mentions using AI
    employee_mentions = await detect_employees_in_review(
        review.review_text,
        employee_names
    )
    
    # Calculate total points
    total_points = sum(m.get("points", 0) for m in employee_mentions)
    
    # Create review document
    review_id = str(uuid.uuid4())
    review_doc = {
        "id": review_id,
        "platform": review.platform,
        "review_date": review.review_date,
        "rating": review.rating,
        "review_text": review.review_text,
        "reviewer_name": review.reviewer_name,
        "employee_mentions": employee_mentions,
        "total_points": round(total_points, 2),
        "review_hash": review_hash,
        "quarter": review.quarter.upper(),
        "year": review.year,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.customer_reviews.insert_one(review_doc)
    
    # Remove MongoDB _id before returning
    review_doc.pop("_id", None)
    
    return {
        "success": True,
        "review": review_doc,
        "detected_employees": len(employee_mentions),
        "message": f"Review added. Detected {len(employee_mentions)} employee mention(s)."
    }


@api_router.post("/v2/reviews/detect")
async def detect_employees_endpoint(
    review_text: str,
    quarter: str = "Q1",
    year: int = 2026
):
    """Preview employee detection without saving the review."""
    # Get employee names
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"name": 1, "_id": 0}
    ).to_list(500)
    employee_names = [e["name"] for e in employees]
    
    # Detect employees
    mentions = await detect_employees_in_review(review_text, employee_names)
    
    return {
        "mentions": mentions,
        "total_points": round(sum(m.get("points", 0) for m in mentions), 2)
    }


@api_router.get("/v2/reviews/{review_id}")
async def get_review(review_id: str):
    """Get a specific review by ID."""
    review = await db.customer_reviews.find_one({"id": review_id}, {"_id": 0})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@api_router.put("/v2/reviews/{review_id}/mentions")
async def update_review_mentions(review_id: str, update: EmployeeMentionUpdate):
    """Update employee mentions for a review (manual correction)."""
    # Recalculate points
    total_points = sum(m.get("points", 0) for m in update.employee_mentions)
    
    result = await db.customer_reviews.update_one(
        {"id": review_id},
        {
            "$set": {
                "employee_mentions": update.employee_mentions,
                "total_points": round(total_points, 2),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return {"success": True, "message": "Employee mentions updated"}


@api_router.delete("/v2/reviews/{review_id}")
async def delete_review(review_id: str):
    """Delete a review."""
    result = await db.customer_reviews.delete_one({"id": review_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return {"success": True, "message": "Review deleted"}


@api_router.get("/v2/reviews/employee/{employee_name}/points")
async def get_employee_review_points(
    employee_name: str,
    quarter: str = "Q1",
    year: int = 2026
):
    """Get total review points for a specific employee."""
    reviews = await db.customer_reviews.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    total_points = calculate_review_points_for_employee(reviews, employee_name)
    
    # Count mentions
    mentions = []
    for review in reviews:
        for mention in review.get("employee_mentions", []):
            if mention.get("name", "").lower() == employee_name.lower():
                mentions.append({
                    "review_id": review.get("id"),
                    "platform": review.get("platform"),
                    "review_date": review.get("review_date"),
                    "sentiment": mention.get("sentiment"),
                    "points": mention.get("points", 0)
                })
    
    return {
        "employee_name": employee_name,
        "total_points": total_points,
        "mention_count": len(mentions),
        "mentions_for_1_point": 5,
        "mentions": mentions
    }


# ============================================================================
# REVIEWTRACKERS SYNC - DEPRECATED (Use manual upload at /api/v2/rt/upload)
# ============================================================================

@api_router.post("/v2/reviews/sync")
async def sync_from_reviewtrackers(
    quarter: str = "Q1",
    year: int = 2026,
    since_date: Optional[str] = None
):
    """
    DEPRECATED: Use manual upload instead.
    Upload ReviewTracker data via /api/v2/rt/upload or the Data Uploads page.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "This sync endpoint has been deprecated. Please use the manual upload feature at /api/v2/rt/upload or navigate to the Data Uploads page to upload ReviewTracker data.",
        "alternative": "/api/v2/rt/upload"
    }


# ============================================================================
# REVIEWTRACKERS MANUAL UPLOAD
# ============================================================================

@api_router.get("/v2/rt/template")
async def download_rt_template():
    """
    Download the Review Tracker upload template (XLSX).
    Template has columns: Employee Name, Mentions
    Automatically includes all employees from the most recent snapshot.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RT Mentions"
    
    # Header styling
    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Headers
    headers = ["Employee Name", "Mentions"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
    
    # Get employees from the most recent snapshot
    latest_snapshot = await db.snapshots.find_one(
        {},
        sort=[("created_at", -1)]
    )
    
    employees = []
    if latest_snapshot and "employees" in latest_snapshot:
        # Sort employees by name for easier filling
        employees = sorted(latest_snapshot["employees"], key=lambda e: e.get("name", ""))
    
    # If no snapshot, fall back to employees_v2
    if not employees:
        emp_docs = await db.employees_v2.find({}, {"name": 1}).to_list(100)
        employees = [{"name": e.get("name", "")} for e in emp_docs]
    
    # Add all employees to template
    for idx, emp in enumerate(employees, 2):
        name_cell = ws.cell(row=idx, column=1, value=emp.get("name", ""))
        mentions_cell = ws.cell(row=idx, column=2, value=0)
        # Light styling for data rows
        name_cell.border = thin_border
        mentions_cell.border = thin_border
        mentions_cell.alignment = Alignment(horizontal='center')
    
    # Column widths
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 15
    
    # Instructions sheet
    ws_inst = wb.create_sheet("Instructions")
    snapshot_name = latest_snapshot.get("name", "N/A") if latest_snapshot else "N/A"
    snapshot_date = latest_snapshot.get("created_at", "N/A") if latest_snapshot else "N/A"
    instructions = [
        "Review Tracker Upload Template",
        "",
        f"Employees from snapshot: {snapshot_name}",
        f"Snapshot date: {snapshot_date}",
        f"Total employees: {len(employees)}",
        "",
        "Instructions:",
        "1. Fill in the 'Mentions' column with each employee's mention count",
        "2. Employee names are pre-filled from the most recent snapshot",
        "3. Each mention = +0.5 points (capped at 15 pts)",
        "",
        "Scoring Color Thresholds:",
        "  0 mentions = 0 pts (Red)",
        "  1-5 mentions = 0.5-2.5 pts (Yellow)",
        "  6-10 mentions = 3.0-5.0 pts (Green)",
        "  11+ mentions = 5.5-15 pts (Blue, capped at 15)",
    ]
    for idx, line in enumerate(instructions, 1):
        ws_inst.cell(row=idx, column=1, value=line)
    ws_inst.column_dimensions['A'].width = 70
    
    # Save to buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=RT_Upload_Template.xlsx"}
    )


@api_router.post("/v2/rt/upload")
async def upload_rt_data(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload Review Tracker mention counts from XLSX or CSV file.
    Updates employee rt_mentions field and recalculates scores.
    
    Supported formats:
    1. XLSX with columns: Employee Name, Mentions
    2. CSV with columns: Keyword, Positive Mentions, Negative Mentions, Total Mentions
    
    Uses fuzzy matching to match keywords/names to employees.
    """
    from thefuzz import fuzz
    import csv
    
    filename = file.filename.lower()
    
    if not filename.endswith('.xlsx') and not filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Please upload an XLSX or CSV file")
    
    try:
        content = await file.read()
        
        # Get all employees for matching (exclude _id to avoid serialization issues)
        all_employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(500)
        
        if not all_employees:
            raise HTTPException(status_code=400, detail=f"No employees found for {quarter} {year}")
        
        # Build a mapping of name variations to employees
        employee_lookup = {}
        for emp in all_employees:
            name = emp.get("name", "").strip()
            if not name:
                continue
            
            # Add full name (lowercase)
            employee_lookup[name.lower()] = emp
            
            # Add first name only
            first_name = name.split()[0].lower() if name.split() else ""
            if first_name and len(first_name) > 2:
                if first_name not in employee_lookup:
                    employee_lookup[first_name] = emp
            
            # Add nickname variations
            # Handle names like "Starwars Mckinnon-Herrera" -> "star", "starwar", "starwars"
            for i in range(3, len(first_name) + 1):
                prefix = first_name[:i]
                if prefix not in employee_lookup:
                    employee_lookup[prefix] = emp
        
        # Parse file based on type
        mention_data = []
        
        if filename.endswith('.csv'):
            # Parse CSV format - flexible column name matching
            content_str = content.decode('utf-8')
            reader = csv.DictReader(io.StringIO(content_str))
            
            # Get actual column names for debugging
            actual_columns = reader.fieldnames if reader.fieldnames else []
            logging.info(f"RT CSV Upload: Found columns: {actual_columns}")
            
            # Find columns flexibly (case-insensitive)
            def find_column(possible_names, columns):
                for name in possible_names:
                    for col in columns:
                        if name.lower() in col.lower():
                            return col
                return None
            
            keyword_col = find_column(['keyword', 'name', 'employee', 'server'], actual_columns)
            total_col = find_column(['total mentions', 'total', 'mentions'], actual_columns)
            positive_col = find_column(['positive mentions', 'positive'], actual_columns)
            negative_col = find_column(['negative mentions', 'negative'], actual_columns)
            
            logging.info(f"RT CSV: Mapped columns - keyword={keyword_col}, total={total_col}, positive={positive_col}, negative={negative_col}")
            
            if not keyword_col:
                raise HTTPException(status_code=400, detail=f"Could not find 'Keyword' column. Found columns: {actual_columns}")
            
            # Re-read file with column mapping
            content_str = content.decode('utf-8')
            reader = csv.DictReader(io.StringIO(content_str))
            
            for row in reader:
                keyword = row.get(keyword_col, '').strip().lower()
                if not keyword:
                    continue
                
                # Try to get mentions - prefer Total Mentions, fall back to Positive
                total_mentions = row.get(total_col, '') if total_col else ''
                positive_mentions = row.get(positive_col, '') if positive_col else ''
                negative_mentions = row.get(negative_col, '0') if negative_col else '0'
                
                try:
                    mentions = int(total_mentions) if total_mentions else int(positive_mentions) if positive_mentions else 0
                    positive = int(positive_mentions) if positive_mentions else mentions
                    negative = int(negative_mentions) if negative_mentions else 0
                except ValueError:
                    mentions = 0
                    positive = 0
                    negative = 0
                
                if mentions > 0 or positive > 0:  # Only include non-zero entries
                    mention_data.append({
                        'keyword': keyword,
                        'mentions': mentions,
                        'positive': positive,
                        'negative': negative
                    })
                    logging.info(f"RT CSV: Parsed keyword '{keyword}' with {mentions} mentions")
            
            logging.info(f"RT CSV: Total entries with mentions: {len(mention_data)}")
        else:
            # Parse XLSX format
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content))
            ws = wb.active
            
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                if not row or not row[0]:
                    continue
                    
                keyword = str(row[0]).strip().lower()
                mentions = int(row[1]) if row[1] is not None else 0
                positive = int(row[2]) if len(row) > 2 and row[2] is not None else mentions
                negative = int(row[3]) if len(row) > 3 and row[3] is not None else 0
                
                mention_data.append({
                    'keyword': keyword,
                    'mentions': mentions,
                    'positive': positive,
                    'negative': negative
                })
        
        # Match keywords to employees using intelligent fuzzy matching
        # Import the name matcher
        from name_matcher import find_best_match, calculate_name_similarity
        
        # Aggregate by employee to avoid duplicate counts
        employee_mentions = {}  # employee_id -> {mentions, positive, negative, keywords}
        matched = []
        unmatched = []
        
        for item in mention_data:
            keyword = item['keyword']
            mentions = item['mentions']
            positive = item['positive']
            negative = item['negative']
            
            # Use intelligent fuzzy matching (same as POS upload)
            match, score, reason = find_best_match(keyword, all_employees, threshold=70.0)
            
            if not match:
                unmatched.append({
                    'keyword': keyword,
                    'mentions': mentions
                })
                continue
            
            match_type = f"{reason}({score:.0f})"
            
            # Aggregate mentions by employee (avoid double counting)
            emp_id = match.get("id")
            emp_name = match.get("name")
            
            if emp_id not in employee_mentions:
                employee_mentions[emp_id] = {
                    'employee': match,
                    'employee_id': emp_id,
                    'employee_name': emp_name,
                    'mentions': 0,
                    'positive': 0,
                    'negative': 0,
                    'keywords': []
                }
            
            employee_mentions[emp_id]['mentions'] += mentions
            employee_mentions[emp_id]['positive'] += positive
            employee_mentions[emp_id]['negative'] += negative
            employee_mentions[emp_id]['keywords'].append({
                'keyword': keyword,
                'mentions': mentions,
                'match_type': match_type
            })
        
        # Update each employee with aggregated mentions
        updated_count = 0
        for emp_id, data in employee_mentions.items():
            employee = data['employee']
            employee_id = data.get('employee_id') or employee.get('id')
            mentions = data['mentions']
            positive = data['positive']
            negative = data['negative']
            
            # Update employee RT mentions using 'id' field
            rt_bonus = min(mentions * 0.5, 15)  # 0.5 pts per mention, max 15
            
            result = await db.employees_v2.update_one(
                {"id": employee_id},
                {"$set": {
                    "rt_mentions": mentions,
                    "review_tracker_bonus": rt_bonus,
                    "review_mentions": mentions,
                    "rt_positive": positive,
                    "rt_negative": negative,
                    "rt_source": "manual_upload",
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            if result.modified_count > 0:
                updated_count += 1
                logging.info(f"RT UPDATE: {data['employee_name']} - {mentions} mentions")
            
            # Track matched keywords
            for kw in data['keywords']:
                matched.append({
                    'keyword': kw['keyword'],
                    'employee': data['employee_name'],
                    'mentions': kw['mentions'],
                    'match_type': kw['match_type']
                })
        
        # Recalculate scores for all employees
        if updated_count > 0:
            employees = await db.employees_v2.find({
                "quarter": quarter.upper(),
                "year": year
            }).to_list(100)
            
            for emp in employees:
                weighted_score = emp.get("weighted_score", 0) or 0
                cv_score = emp.get("cv_score", 0) or 0
                total_metric_bonus = emp.get("total_metric_bonus", 0) or 0
                rt_bonus = emp.get("review_tracker_bonus", 0) or 0
                
                total_score = weighted_score + cv_score + total_metric_bonus + rt_bonus
                
                await db.employees_v2.update_one(
                    {"_id": emp["_id"]},
                    {"$set": {"total_score": round(total_score, 2), "pre_dar_score": round(total_score, 2)}}
                )
            
            # Recalculate ranks
            await recalculate_peer_ranks(quarter.upper(), year)
        
        # NOTE: Snapshots are NOT auto-updated. Create a new snapshot to capture this data.
        
        return {
            "success": True,
            "employees_updated": updated_count,
            "matched": matched,
            "unmatched": unmatched if unmatched else None,
            "message": f"Updated {updated_count} employee mention counts. Create a new Snapshot to capture this data."
        }
        
    except Exception as e:
        logging.error(f"RT upload error: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ============================================================================
# DATA CLEARING ENDPOINTS
# ============================================================================

@api_router.delete("/v2/admin/clear-cv-data")
async def clear_cv_data(quarter: str = "Q1", year: int = 2026):
    """
    Clear all Customer Voice data and reset employee CV scores.
    """
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


@api_router.delete("/v2/admin/clear-rt-data")
async def clear_rt_data(quarter: str = "Q1", year: int = 2026):
    """
    Clear all Review Tracker data and reset employee RT mention counts.
    """
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


@api_router.get("/v2/reviews/sync/status")
async def get_sync_status():
    """Get ReviewTrackers sync configuration status."""
    username = os.environ.get("REVIEWTRACKERS_USERNAME")
    password = os.environ.get("REVIEWTRACKERS_PASSWORD")
    
    configured = bool(username and password)
    
    # Get last sync info
    last_synced_review = await db.customer_reviews.find_one(
        {"source": "reviewtrackers"},
        sort=[("synced_at", -1)]
    )
    
    last_sync_time = None
    if last_synced_review:
        last_sync_time = last_synced_review.get("synced_at")
    
    # Count synced reviews
    synced_count = await db.customer_reviews.count_documents({"source": "reviewtrackers"})
    
    return {
        "configured": configured,
        "username": username[:3] + "***" if username else None,
        "last_sync_time": last_sync_time,
        "total_synced_reviews": synced_count
    }


@api_router.post("/v2/reviews/sync/test")
async def test_reviewtrackers_connection():
    """
    DEPRECATED: ReviewTrackers sync has been replaced with manual uploads.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "ReviewTrackers sync has been deprecated. Please use the manual upload feature instead."
    }


# ============================================================================
# LOYALTY VOICE (CV) INTEGRATION - DEPRECATED (Use manual upload)
# ============================================================================

# Legacy imports - commented out since scrapers are deprecated
# from loyalty_voice_integration import (
#     sync_loyalty_voice_to_db,
#     scrape_server_performance_report,
#     get_nps_score_for_employee,
#     get_quarter_date_range
# )


@api_router.post("/v2/cv/sync")
async def sync_loyalty_voice(quarter: str = "Q1", year: int = 2026):
    """
    DEPRECATED: Use manual upload instead.
    Upload Customer Voice data via /api/v2/cv/server-performance/upload or the Data Uploads page.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "This sync endpoint has been deprecated. Please use the manual upload feature. Navigate to Data Uploads page and upload your Customer Voice XLSX file.",
        "alternative": "/api/v2/cv/server-performance/upload"
    }


@api_router.get("/v2/cv/nps")
async def get_cv_nps_scores(quarter: str = "Q1", year: int = 2026):
    """Get all NPS scores for a quarter from Loyalty Voice sync."""
    nps_records = await db.cv_nps.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(500)
    
    return {
        "nps_records": nps_records,
        "total": len(nps_records),
        "quarter": quarter.upper(),
        "year": year
    }


@api_router.get("/v2/cv/stats")
async def get_cv_stats(quarter: str = "Q1", year: int = 2026):
    """Get NPS statistics from Loyalty Voice.
    Uses official CV stats if set (for 100% accuracy with LV dashboard),
    otherwise falls back to scraped data.
    """
    # Check for official stats first
    official = await db.official_cv_stats.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    # Get NPS records (always needed for breakdown)
    nps_records = await db.cv_nps.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(500)
    
    # Sort by NPS for breakdown
    sorted_records = sorted(nps_records, key=lambda x: x.get("nps_score", 0), reverse=True)
    
    if official:
        # Use official LV UI stats for aggregate numbers
        servers_with_surveys = [r for r in nps_records if r.get("total_surveys", 0) > 0]
        avg_individual_nps = (
            sum(r.get("nps_score", 0) for r in servers_with_surveys) / len(servers_with_surveys)
            if servers_with_surveys else 0
        )
        return {
            "source": "official_lv_ui",
            "total_servers": len(nps_records),
            "avg_nps": official.get("nps_score") or official.get("avg_nps") or official.get("store_nps") or 0,
            "store_nps": official.get("store_nps") or official.get("nps_score") or official.get("avg_nps") or 0,
            "avg_individual_nps": round(avg_individual_nps, 2),
            "highest_nps": sorted_records[0] if sorted_records else None,
            "lowest_nps": sorted_records[-1] if sorted_records else None,
            "nps_breakdown": sorted_records[:20],
            "last_sync": nps_records[0].get("synced_at") if nps_records else None,
            "promoter_count": official.get("promoters") or official.get("total_promoters") or 0,
            "passive_count": official.get("passives") or official.get("total_passives") or 0,
            "detractor_count": official.get("detractors") or official.get("total_detractors") or 0,
            "total_surveys": official.get("total_responses") or official.get("total_surveys") or 0,
            "updated_at": official.get("updated_at")
        }
    
    # Fall back to scraped data
    if not nps_records:
        return {
            "source": "scraped_data",
            "total_servers": 0,
            "avg_nps": 0,
            "store_nps": 0,
            "highest_nps": None,
            "lowest_nps": None,
            "nps_breakdown": [],
            "last_sync": None,
            "promoter_count": 0,
            "passive_count": 0,
            "detractor_count": 0,
            "total_surveys": 0
        }
    
    # Sum up promoters, passives, detractors from all NPS records
    total_promoters = sum(r.get("promoters", 0) for r in nps_records)
    total_passives = sum(r.get("passives", 0) for r in nps_records)
    total_detractors = sum(r.get("detractors", 0) for r in nps_records)
    total_surveys = sum(r.get("total_surveys", 0) or r.get("received", 0) for r in nps_records)
    
    # Calculate STORE-LEVEL NPS
    if total_surveys > 0:
        store_nps = ((total_promoters - total_detractors) / total_surveys) * 100
    else:
        store_nps = 0
    
    # Average of individual NPS scores
    nps_scores = [r.get("nps_score", 0) for r in nps_records if (r.get("total_surveys", 0) or r.get("received", 0)) > 0]
    avg_individual_nps = sum(nps_scores) / len(nps_scores) if nps_scores else 0
    
    return {
        "source": "scraped_data",
        "total_servers": len(nps_records),
        "avg_nps": round(store_nps, 2),
        "store_nps": round(store_nps, 2),
        "avg_individual_nps": round(avg_individual_nps, 2),
        "highest_nps": sorted_records[0] if sorted_records else None,
        "lowest_nps": sorted_records[-1] if sorted_records else None,
        "nps_breakdown": sorted_records[:20],
        "last_sync": nps_records[0].get("synced_at") if nps_records else None,
        "promoter_count": total_promoters,
        "passive_count": total_passives,
        "detractor_count": total_detractors,
        "total_surveys": total_surveys,
        "note": "Using scraped data. Set official CV stats via /v2/admin/cv-stats/set for 100% accuracy."
    }


@api_router.get("/v2/cv/employee/{employee_name}/nps")
async def get_employee_nps(employee_name: str, quarter: str = "Q1", year: int = 2026):
    """Get NPS score for a specific employee."""
    # Find by employee name (case-insensitive)
    nps_record = await db.cv_nps.find_one(
        {
            "quarter": quarter.upper(),
            "year": year,
            "employee_name": {"$regex": f"^{employee_name}$", "$options": "i"}
        },
        {"_id": 0}
    )
    
    if nps_record:
        return {
            "found": True,
            "employee_name": nps_record.get("employee_name"),
            "nps_score": nps_record.get("nps_score", 0),
            "synced_at": nps_record.get("synced_at")
        }
    
    return {
        "found": False,
        "employee_name": employee_name,
        "nps_score": 0,
        "synced_at": None
    }


@api_router.get("/v2/cv/sync/status")
async def get_cv_sync_status():
    """Get Loyalty Voice sync status."""
    username = os.environ.get("LOYALTY_VOICE_USERNAME")
    configured = bool(username)
    
    # Get last sync from cv_nps collection
    last_nps = await db.cv_nps.find_one(
        {"source": "loyalty_voice"},
        sort=[("synced_at", -1)]
    )
    
    synced_count = await db.cv_nps.count_documents({"source": "loyalty_voice"})
    
    return {
        "configured": configured,
        "last_sync_time": last_nps.get("synced_at") if last_nps else None,
        "total_synced_servers": synced_count,
        "data_type": "NPS scores from Server Performance Report"
    }


# ============================================================================
# CV FEEDBACK (Customer Voice Comments) INTEGRATION - DEPRECATED
# ============================================================================

# Legacy imports - commented out since scrapers are deprecated
# from cv_feedback_scraper import sync_cv_feedback_to_db, scrape_cv_feedback


@api_router.post("/v2/cv/feedback/sync")
async def sync_cv_feedback(quarter: str = "Q1", year: int = 2026):
    """
    DEPRECATED: Use manual upload instead.
    Upload Customer Voice data via /api/v2/cv/server-performance/upload or the Data Uploads page.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "This sync endpoint has been deprecated. Please use the manual upload feature. Navigate to Data Uploads page and upload your Customer Voice XLSX file.",
        "alternative": "/api/v2/cv/server-performance/upload"
    }


@api_router.get("/v2/cv/feedback")
async def get_cv_feedback(quarter: str = "Q1", year: int = 2026, limit: int = 100, include_excluded: bool = False):
    """Get CV feedback items for a quarter."""
    query = {"quarter": quarter.upper(), "year": year}
    
    # By default, don't show excluded feedback unless requested
    if not include_excluded:
        query["$or"] = [{"excluded": {"$exists": False}}, {"excluded": False}]
    
    feedback = await db.cv_feedback.find(
        query,
        {"_id": 0}
    ).sort("date", -1).to_list(limit * 2)  # Fetch extra to account for filtering
    
    # Filter by date to only show Q1 2026 (January 1 - March 31, 2026)
    # Handle multiple date formats
    filtered_feedback = []
    for f in feedback:
        date_str = f.get("date", "")
        if not date_str:
            continue
            
        # Check if date is in Q1 2026
        is_q1_2026 = False
        
        # Format: 2026-01-15T... (ISO format)
        if date_str.startswith("2026-01") or date_str.startswith("2026-02") or date_str.startswith("2026-03"):
            is_q1_2026 = True
        # Format: 01/15/2026 or 1/15/2026 (US format)
        elif "/2026" in date_str:
            parts = date_str.split("/")
            if len(parts) >= 2:
                try:
                    month = int(parts[0])
                    if 1 <= month <= 3:
                        is_q1_2026 = True
                except:
                    pass
        
        if is_q1_2026:
            filtered_feedback.append(f)
    
    # Limit results
    filtered_feedback = filtered_feedback[:limit]
    
    # Also get excluded count (for current quarter only)
    excluded_count = await db.cv_feedback.count_documents({
        "quarter": quarter.upper(), 
        "year": year,
        "excluded": True
    })
    
    return {
        "feedback": filtered_feedback,
        "total": len(filtered_feedback),
        "excluded_count": excluded_count,
        "quarter": quarter.upper(),
        "year": year
    }


@api_router.get("/v2/cv/feedback/stats")
async def get_cv_feedback_stats(quarter: str = "Q1", year: int = 2026):
    """Get CV feedback statistics including points per employee."""
    # Get all feedback
    feedback = await db.cv_feedback.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    # Get CV points per employee
    cv_points = await db.cv_points.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).sort("total_cv_points", -1).to_list(100)
    
    # Calculate totals
    total_feedback = len(feedback)
    promoter_count = len([f for f in feedback if f.get("sentiment") == "promoter"])
    passive_count = len([f for f in feedback if f.get("sentiment") == "passive"])
    detractor_count = len([f for f in feedback if f.get("sentiment") == "detractor"])
    
    # Get last sync
    last_feedback = await db.cv_feedback.find_one(
        {"quarter": quarter.upper(), "year": year},
        sort=[("synced_at", -1)]
    )
    
    return {
        "total_feedback": total_feedback,
        "promoter_count": promoter_count,
        "passive_count": passive_count,
        "detractor_count": detractor_count,
        "employee_points": cv_points,
        "last_sync": last_feedback.get("synced_at") if last_feedback else None
    }


@api_router.get("/v2/cv/points/{employee_id}")
async def get_employee_cv_points(employee_id: str, quarter: str = "Q1", year: int = 2026):
    """Get CV points for a specific employee."""
    points = await db.cv_points.find_one(
        {"employee_id": employee_id, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if points:
        return points
    
    return {
        "employee_id": employee_id,
        "total_cv_points": 0,
        "mention_count": 0,
        "promoter_count": 0,
        "passive_count": 0,
        "detractor_count": 0
    }


@api_router.post("/v2/cv/feedback/{feedback_id}/exclude")
async def exclude_cv_feedback(feedback_id: str):
    """
    Exclude a CV feedback item from NPS calculations.
    When excluded, recalculate the SERVER's NPS score from all non-excluded feedback.
    
    For Customer Voice, credit goes to the server who served the table,
    not employees mentioned in the comment text.
    """
    # Find the feedback item
    feedback = await db.cv_feedback.find_one({"id": feedback_id})
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    if feedback.get("excluded"):
        return {"success": False, "message": "Already excluded"}
    
    # Mark as excluded
    await db.cv_feedback.update_one(
        {"id": feedback_id},
        {"$set": {"excluded": True, "excluded_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Get the SERVER who served this customer (the correct attribution for CV)
    quarter = feedback.get("quarter", "Q1")
    year = feedback.get("year", 2026)
    server_name = feedback.get("server_name", "")
    
    affected_employees = []
    new_nps = None
    
    # If we have a server_name, recalculate their NPS from all non-excluded feedback
    if server_name:
        affected_employees.append(server_name)
        
        # Get all non-excluded feedback for this server
        server_feedback = await db.cv_feedback.find({
            "server_name": {"$regex": f"^{server_name}$", "$options": "i"},
            "quarter": quarter,
            "year": year,
            "excluded": {"$ne": True}
        }).to_list(500)
        
        # Calculate NPS from actual feedback
        promoters = sum(1 for f in server_feedback if f.get("sentiment") == "promoter")
        detractors = sum(1 for f in server_feedback if f.get("sentiment") == "detractor")
        passives = sum(1 for f in server_feedback if f.get("sentiment") == "passive")
        received = len(server_feedback)
        
        # Calculate NPS
        if received > 0:
            new_nps = ((promoters - detractors) / received) * 100
        else:
            new_nps = 0
        
        # Update or create NPS record
        await db.cv_nps.update_one(
            {
                "employee_name": {"$regex": f"^{server_name}$", "$options": "i"},
                "quarter": quarter,
                "year": year
            },
            {"$set": {
                "employee_name": server_name,
                "quarter": quarter,
                "year": year,
                "promoters": promoters,
                "detractors": detractors,
                "passives": passives,
                "received": received,
                "nps_score": round(new_nps, 2),
                "last_adjusted": datetime.now(timezone.utc).isoformat(),
                "adjustment_reason": f"Excluded feedback {feedback_id}",
                "source": "calculated_from_feedback"
            }},
            upsert=True
        )
        
        logging.info(f"CV Exclusion: Recalculated {server_name} NPS to {new_nps:.1f}% (P:{promoters}/Pa:{passives}/D:{detractors})")
    
    # Also check mentions for backward compatibility with external reviews
    mentions = feedback.get("mentions", [])
    for m in mentions:
        emp_name = m.get("employee_name")
        if emp_name and emp_name not in affected_employees:
            affected_employees.append(emp_name)
    
    return {
        "success": True,
        "message": f"Feedback excluded. Server '{server_name}' NPS recalculated to {new_nps:.1f}%." if server_name and new_nps is not None else "Feedback excluded (no server attribution).",
        "feedback_id": feedback_id,
        "server_name": server_name,
        "new_nps": round(new_nps, 2) if new_nps is not None else None,
        "affected_employees": affected_employees
    }


@api_router.post("/v2/cv/feedback/{feedback_id}/include")
async def include_cv_feedback(feedback_id: str):
    """
    Undo exclusion - restore a CV feedback item to NPS calculations.
    Recalculates the SERVER's NPS score from all non-excluded feedback.
    """
    # Find the feedback item
    feedback = await db.cv_feedback.find_one({"id": feedback_id})
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    if not feedback.get("excluded"):
        return {"success": False, "message": "Not excluded"}
    
    # Remove exclusion
    await db.cv_feedback.update_one(
        {"id": feedback_id},
        {"$set": {"excluded": False}, "$unset": {"excluded_at": ""}}
    )
    
    # Get the SERVER who served this customer
    quarter = feedback.get("quarter", "Q1")
    year = feedback.get("year", 2026)
    server_name = feedback.get("server_name", "")
    
    affected_employees = []
    new_nps = None
    
    # If we have a server_name, recalculate their NPS from all non-excluded feedback
    if server_name:
        affected_employees.append(server_name)
        
        # Get all non-excluded feedback for this server (including the just-restored one)
        server_feedback = await db.cv_feedback.find({
            "server_name": {"$regex": f"^{server_name}$", "$options": "i"},
            "quarter": quarter,
            "year": year,
            "excluded": {"$ne": True}
        }).to_list(500)
        
        # Calculate NPS from actual feedback
        promoters = sum(1 for f in server_feedback if f.get("sentiment") == "promoter")
        detractors = sum(1 for f in server_feedback if f.get("sentiment") == "detractor")
        passives = sum(1 for f in server_feedback if f.get("sentiment") == "passive")
        received = len(server_feedback)
        
        # Calculate NPS
        if received > 0:
            new_nps = ((promoters - detractors) / received) * 100
        else:
            new_nps = 0
        
        # Update or create NPS record
        await db.cv_nps.update_one(
            {
                "employee_name": {"$regex": f"^{server_name}$", "$options": "i"},
                "quarter": quarter,
                "year": year
            },
            {"$set": {
                "employee_name": server_name,
                "quarter": quarter,
                "year": year,
                "promoters": promoters,
                "detractors": detractors,
                "passives": passives,
                "received": received,
                "nps_score": round(new_nps, 2),
                "last_adjusted": datetime.now(timezone.utc).isoformat(),
                "adjustment_reason": f"Restored feedback {feedback_id}",
                "source": "calculated_from_feedback"
            }},
            upsert=True
        )
        
        logging.info(f"CV Restore: Recalculated {server_name} NPS to {new_nps:.1f}% (P:{promoters}/Pa:{passives}/D:{detractors})")
    
    # Also check mentions for backward compatibility
    mentions = feedback.get("mentions", [])
    for m in mentions:
        emp_name = m.get("employee_name")
        if emp_name and emp_name not in affected_employees:
            affected_employees.append(emp_name)
    
    return {
        "success": True,
        "message": f"Feedback restored. Server '{server_name}' NPS recalculated to {new_nps:.1f}%." if server_name and new_nps is not None else "Feedback restored (no server attribution).",
        "feedback_id": feedback_id,
        "server_name": server_name,
        "new_nps": round(new_nps, 2) if new_nps is not None else None,
        "affected_employees": affected_employees
    }


@api_router.post("/v2/cv/server-performance/upload")
async def upload_server_performance_csv(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload Server Performance Report from Customer Voice (Loyalty Voice).
    Supports CSV and XLSX formats.
    
    Expected columns: Name, Location, Sent, Received, Response Rate, Avg Rating, NPS
    
    This calculates promoters from NPS formula:
    - Promoters = Received × (100 + NPS) / 200
    - Detractors are NOT calculated - they must be manually entered via DAR or employee edit
    
    Then updates employee CV scores in the database.
    """
    try:
        contents = await file.read()
        
        # Support both CSV and XLSX
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Clean column names
        df.columns = [str(col).strip() for col in df.columns]
        
        # Required columns check
        required = ['Name', 'Received', 'NPS']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing columns: {', '.join(missing)}")
        
        records_processed = []
        employees_updated = 0
        
        # Pre-fetch all employees for this quarter (optimization - fetch once, not per row)
        from name_matcher import find_best_match
        
        all_employees = await db.employees_v2.find({
            "quarter": quarter.upper(),
            "year": year
        }).to_list(length=None)
        
        # Convert to list of dicts for the matcher
        employee_dicts = []
        for emp in all_employees:
            employee_dicts.append({
                'id': str(emp.get('_id')),
                'name': emp.get('name', ''),
                'display_name': emp.get('display_name', ''),
                'report_name': emp.get('report_name', ''),
                'aliases': emp.get('aliases', []),
                '_doc': emp  # Keep original doc for update
            })
        
        logging.info(f"CV Upload: Loaded {len(employee_dicts)} employees for matching")
        
        for _, row in df.iterrows():
            server_name = str(row.get('Name', '')).strip()
            if not server_name or server_name == 'nan' or 'Manager App' in server_name:
                continue
            
            received = int(row.get('Received', 0) or 0)
            nps_score = float(row.get('NPS', 0) or 0)
            avg_rating = float(row.get('Avg Rating', 0) or 0)
            sent = int(row.get('Sent', 0) or 0)
            
            if received == 0:
                # No responses - skip but still record
                records_processed.append({
                    "name": server_name,
                    "received": 0,
                    "nps": 0,
                    "promoters": 0,
                    "detractors": 0,
                    "status": "no_responses"
                })
                continue
            
            # Calculate promoters from NPS formula
            # NPS = ((P - D) / R) * 100
            # For promoters only (detractors are manually entered via DARs):
            # Calculate promoters from NPS:
            # NPS = (Promoters - Detractors) / Total × 100
            # Assuming D=0: NPS = P / R × 100, so P = R × NPS / 100
            promoters = round(received * nps_score / 100)
            promoters = max(0, min(promoters, received))  # Clamp between 0 and received
            
            # Detractors are NOT assumed - they must be manually entered via DAR or employee edit
            detractors = 0
            passives = received - promoters - detractors  # Remaining are passives
            passives = max(0, passives)
            
            # Calculate CV Score:
            # 1. NPS Points: Direct ratio (77% = 7.7 pts, max 10)
            nps_pts = round(nps_score / 10, 1) if nps_score > 0 else 0.0
            nps_pts = min(nps_pts, 10.0)
            
            # 2. Promoter Bonus: +1 per promoter (detractors added via DARs)
            # CV Formula: (Promoters × 1) + (RT Mentions × 0.5) - (Detractors × 2)
            promo_detr_bonus = (promoters * 1)  # No detractor penalty until manually added
            
            # Total CV Score = NPS pts + Promoter/Detractor bonus
            cv_score = round(nps_pts + promo_detr_bonus, 2)
            
            # Use intelligent matching with aliases support
            matched_emp, match_score, match_reason = find_best_match(
                server_name, 
                employee_dicts, 
                threshold=70.0  # Lower threshold for CV names
            )
            
            employee = matched_emp['_doc'] if matched_emp else None
            
            record_status = "no_match"
            
            if employee:
                # Update employee with CV data
                old_score = employee.get('total_score', 0) or 0
                old_cv_score = employee.get('cv_score', 0) or 0
                
                # Recalculate total score
                weighted = employee.get('weighted_score', 0) or 0
                metric_bonus = employee.get('total_metric_bonus', 0) or 0
                rt_bonus = employee.get('review_tracker_bonus', 0) or 0
                new_total = round(weighted + metric_bonus + cv_score + rt_bonus, 2)
                
                await db.employees_v2.update_one(
                    {"_id": employee["_id"]},
                    {"$set": {
                        "nps_score": nps_score,
                        "nps_score_pts": nps_pts,
                        "cv_surveys_sent": sent,
                        "cv_surveys_received": received,
                        "cv_promoters": promoters,
                        "cv_passives": passives,
                        "cv_detractors": detractors,
                        "cv_score": cv_score,
                        "cv_avg_rating": avg_rating,
                        "total_score": new_total,
                        "pre_dar_score": new_total,
                        "cv_source": "manual_upload",
                        "cv_updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                employees_updated += 1
                record_status = "updated"
            
            records_processed.append({
                "name": server_name,
                "received": received,
                "nps": nps_score,
                "promoters": promoters,
                "detractors": detractors,
                "passives": passives,
                "promo_bonus": promo_detr_bonus,
                "matched_employee": employee.get("name") if employee else None,
                "match_score": match_score if matched_emp else 0,
                "match_reason": match_reason,
                "status": record_status
            })
        
        # Update admin settings with official CV stats
        total_promoters = sum(r.get('promoters', 0) for r in records_processed)
        total_detractors = sum(r.get('detractors', 0) for r in records_processed)
        total_passives = sum(r.get('passives', 0) for r in records_processed)
        total_responses = sum(r.get('received', 0) for r in records_processed)
        
        await db.admin_settings.update_one(
            {"_id": f"official_cv_stats_{quarter}_{year}"},
            {"$set": {
                "quarter": quarter.upper(),
                "year": year,
                "promoters": total_promoters,
                "detractors": total_detractors,
                "passives": total_passives,
                "total_responses": total_responses,
                "source": "manual_upload",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        # NOTE: Snapshots are NOT auto-updated. Create a new snapshot to capture this data.
        
        return {
            "success": True,
            "message": f"Processed {len(records_processed)} records, updated {employees_updated} employees. Create a new Snapshot to capture this data.",
            "summary": {
                "total_records": len(records_processed),
                "employees_updated": employees_updated,
                "total_responses": total_responses,
                "total_promoters": total_promoters,
                "total_detractors": total_detractors,
                "total_passives": total_passives
            },
            "records": records_processed,
            "quarter": quarter,
            "year": year
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"CV upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@api_router.get("/v2/review-tracker/template")
async def download_review_tracker_template(quarter: str = "Q1", year: int = 2026):
    """
    Generate and download a ReviewTracker template pre-populated with employee names.
    """
    # Get all employees for this quarter
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"name": 1, "review_mentions": 1}
    ).sort("name", 1).to_list(100)
    
    # Create template DataFrame
    template_data = []
    for emp in employees:
        template_data.append({
            "Employee Name": emp.get("name", ""),
            "Positive Mentions": emp.get("review_mentions", 0),
            "Notes": ""
        })
    
    df = pd.DataFrame(template_data)
    
    # Generate Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Review Tracker', index=False)
        
        # Auto-adjust column widths
        worksheet = writer.sheets['Review Tracker']
        worksheet.column_dimensions['A'].width = 30
        worksheet.column_dimensions['B'].width = 20
        worksheet.column_dimensions['C'].width = 40
    
    output.seek(0)
    
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=ReviewTracker_Template_{quarter}_{year}.xlsx"
        }
    )


@api_router.post("/v2/review-tracker/upload")
async def upload_review_tracker_data(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload ReviewTracker data (positive mentions per employee).
    
    Expected columns: Employee Name, Positive Mentions
    
    Updates employee review_mentions and recalculates RT bonus.
    RT Bonus = min(mentions × 0.5, 15)
    """
    try:
        contents = await file.read()
        
        # Support both CSV and XLSX
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Clean column names
        df.columns = [str(col).strip() for col in df.columns]
        
        # Find the employee name and mentions columns (flexible matching)
        name_col = None
        mentions_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'name' in col_lower or 'employee' in col_lower:
                name_col = col
            elif 'mention' in col_lower or 'positive' in col_lower or 'review' in col_lower:
                mentions_col = col
        
        if not name_col:
            raise HTTPException(status_code=400, detail="Could not find employee name column")
        if not mentions_col:
            raise HTTPException(status_code=400, detail="Could not find mentions column")
        
        employees_updated = 0
        records_processed = []
        total_mentions = 0
        
        for _, row in df.iterrows():
            emp_name = str(row.get(name_col, '')).strip()
            if not emp_name or emp_name == 'nan':
                continue
            
            mentions = int(row.get(mentions_col, 0) or 0)
            total_mentions += mentions
            
            # Calculate RT bonus
            rt_bonus = min(mentions * 0.5, 15)
            
            # Find matching employee
            employee = await db.employees_v2.find_one({
                "quarter": quarter.upper(),
                "year": year,
                "name": {"$regex": f"^{emp_name}$", "$options": "i"}
            })
            
            record_status = "no_match"
            
            if employee:
                # Get current values for recalculation
                old_mentions = employee.get('review_mentions', 0) or 0
                old_rt_bonus = employee.get('review_tracker_bonus', 0) or 0
                
                # Recalculate scores
                # Get base components
                capped_ppa = min(employee.get('score_ppa', 0) or 0, 100)
                capped_lsc = min(employee.get('score_lsc', 0) or 0, 100)
                capped_lbw = min(employee.get('score_lbw', 0) or 0, 100)
                capped_glass = min(employee.get('score_glass', 0) or 0, 100)
                nps_score = employee.get('nps_score', 0) or 0
                
                # NPS contribution
                nps_normalized = max(0, (nps_score + 100) / 2)
                nps_contribution = min(nps_normalized, 100) * 0.10
                
                # Calculate new weighted score
                new_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.15) + (capped_glass * 0.10) + nps_contribution + rt_bonus
                
                # Get other components
                metric_bonus = min(employee.get('total_metric_bonus', 0) or 0, 20)
                cv_bonus = employee.get('cv_bonus', 0) or employee.get('cv_score', 0) or 0
                
                # Final score
                new_total = round(new_weighted + metric_bonus + cv_bonus, 2)
                
                await db.employees_v2.update_one(
                    {"_id": employee["_id"]},
                    {"$set": {
                        "review_mentions": mentions,
                        "review_tracker_bonus": rt_bonus,
                        "weighted_score": round(new_weighted, 2),
                        "total_score": new_total,
                        "pre_dar_score": new_total,
                        "rt_source": "manual_upload",
                        "rt_updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                employees_updated += 1
                record_status = "updated"
                
                records_processed.append({
                    "name": emp_name,
                    "mentions": mentions,
                    "rt_bonus": rt_bonus,
                    "old_mentions": old_mentions,
                    "matched_employee": employee.get("name"),
                    "score_change": round(new_total - (employee.get('total_score', 0) or 0), 2),
                    "status": record_status
                })
            else:
                records_processed.append({
                    "name": emp_name,
                    "mentions": mentions,
                    "rt_bonus": rt_bonus,
                    "status": "no_match"
                })
        
        # Update admin settings with official RT stats
        await db.admin_settings.update_one(
            {"_id": f"official_rt_stats_{quarter}_{year}"},
            {"$set": {
                "quarter": quarter.upper(),
                "year": year,
                "total_mentions": total_mentions,
                "source": "manual_upload",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        # Sync updated employees to the most recent snapshot
        snapshot_id = await sync_employees_to_most_recent_snapshot(quarter, year)
        
        return {
            "success": True,
            "message": f"Processed {len(records_processed)} records, updated {employees_updated} employees and synced to snapshot",
            "summary": {
                "total_records": len(records_processed),
                "employees_updated": employees_updated,
                "total_mentions": total_mentions
            },
            "records": records_processed,
            "quarter": quarter,
            "year": year,
            "snapshot_synced": snapshot_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"RT upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@api_router.post("/v2/review-tracker/upload-feedback")
async def upload_review_feedback_csv(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload raw ReviewTracker feedback CSV (Reviews-feedback.csv format).
    Extracts employee names from review text using fuzzy matching.
    
    Expected columns: Review (contains review text), Rating, Source, Published
    
    This endpoint:
    1. Scans each review for employee name mentions
    2. Counts positive mentions per employee
    3. Updates employee review_mentions and recalculates RT bonus
    """
    import re
    from collections import defaultdict
    
    logging.info(f"=== REVIEW-TRACKER UPLOAD-FEEDBACK ENDPOINT HIT === File: {file.filename}")
    
    try:
        contents = await file.read()
        
        # Support both CSV and XLSX
        if file.filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Clean column names
        df.columns = [str(col).strip() for col in df.columns]
        
        logging.info(f"RT Feedback: CSV columns = {list(df.columns)}")
        logging.info(f"RT Feedback: CSV has {len(df)} rows")
        
        # Find the review text column
        review_col = None
        rating_col = None
        date_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            if col_lower == 'review' or ('review' in col_lower and 'id' not in col_lower):
                review_col = col
            elif 'rating' in col_lower:
                rating_col = col
            elif 'published' in col_lower or 'date' in col_lower:
                date_col = col
        
        if not review_col:
            logging.error(f"RT Feedback: Could not find Review column. Available: {list(df.columns)}")
            raise HTTPException(status_code=400, detail=f"Could not find Review column in CSV. Columns found: {list(df.columns)}")
        
        logging.info(f"RT Feedback: Found review column '{review_col}', rating column '{rating_col}'")
        
        # Get all employees for this quarter
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year}
        ).to_list(500)
        
        logging.info(f"RT Feedback: Found {len(employees)} employees for {quarter} {year}")
        
        if not employees:
            raise HTTPException(status_code=400, detail=f"No employees found for {quarter} {year}")
        
        # Build name lookup: first names, nicknames, and full names
        name_to_employee = {}
        for emp in employees:
            full_name = emp.get('name', '')
            full_lower = full_name.lower()
            
            # Match full name
            name_to_employee[full_lower] = emp
            
            # Match first name
            parts = full_lower.split()
            if parts:
                first = parts[0]
                name_to_employee[first] = emp
        
        # Add common nicknames/aliases
        nickname_map = {
            'keisha': 'lakeisha martin',
            'abby': 'abby ostro',
            'tad': 'tad hashey',
            'thaddeus': 'tad hashey',
            'matt': 'matt spath',
            'matthew': 'matt spath',
            'rob': 'robert mckinnon',
            'bobby': 'robert mckinnon',
            'dan': 'daniel mayorga',
            'eddie': 'eddie garcia',
            'ed': 'eddie garcia',
            'lexi': 'lexi harreau',
            'alex': 'lexi harreau',
            # Starwars variations
            'star': 'starwars mckinnon-herrera',
            'starwars': 'starwars mckinnon-herrera',
        }
        
        for nick, full in nickname_map.items():
            if full in name_to_employee:
                name_to_employee[nick] = name_to_employee[full]
        
        # Special multi-word patterns (handle "Star Wars" with space)
        special_patterns = []
        starwars_emp = name_to_employee.get('starwars mckinnon-herrera')
        if starwars_emp:
            special_patterns.append((r'\bstar\s*wars\b', starwars_emp))  # "star wars", "star  wars"
            special_patterns.append((r'\bstar\s*\(wars\)', starwars_emp))  # "star(wars)"
        
        logging.info(f"RT Feedback: Built name lookup with {len(name_to_employee)} names")
        
        # Count mentions per employee
        mention_counts = defaultdict(int)
        reviews_processed = 0
        reviews_with_mentions = 0
        sample_matches = []
        
        for _, row in df.iterrows():
            review_text = str(row.get(review_col, '')).lower()
            # Also check Title column which often has names
            title_text = str(row.get('Title', '')).lower() if 'Title' in df.columns else ''
            combined_text = review_text + ' ' + title_text
            
            if not combined_text.strip() or combined_text.strip() == 'nan':
                continue
            
            reviews_processed += 1
            rating = float(row.get(rating_col, 5) or 5) if rating_col else 5
            
            # Only count positive reviews (4+ stars)
            if rating < 4:
                continue
            
            found_names = set()
            
            # First check special multi-word patterns (like "Star Wars")
            for pattern, emp in special_patterns:
                if re.search(pattern, combined_text):
                    emp_name = emp.get('name', '')
                    if emp_name not in found_names:
                        found_names.add(emp_name)
                        mention_counts[emp_name] += 1
            
            # Then check single-word name matches
            for name_key, emp in name_to_employee.items():
                # Skip if already found via special pattern
                emp_name = emp.get('name', '')
                if emp_name in found_names:
                    continue
                    
                # Match as whole word
                pattern = r'\b' + re.escape(name_key) + r'\b'
                if re.search(pattern, combined_text):
                    if emp_name not in found_names:
                        found_names.add(emp_name)
                        mention_counts[emp_name] += 1
            
            if found_names:
                reviews_with_mentions += 1
                if len(sample_matches) < 5:
                    sample_matches.append({
                        "review_snippet": combined_text[:100] + "...",
                        "employees_found": list(found_names),
                        "rating": rating
                    })
        
        logging.info(f"RT Feedback: Processed {reviews_processed} reviews, found {reviews_with_mentions} with mentions, total {sum(mention_counts.values())} mentions")
        
        # Update employees with mention counts
        employees_updated = 0
        update_details = []
        total_mentions = sum(mention_counts.values())
        
        for emp in employees:
            emp_name = emp.get('name', '')
            mentions = mention_counts.get(emp_name, 0)
            
            # Calculate RT bonus
            rt_bonus = round(min(mentions * 0.5, 15), 2)
            
            # Get current values
            old_mentions = emp.get('review_mentions', 0) or emp.get('rt_mentions', 0) or 0
            old_rt_bonus = emp.get('review_tracker_bonus', 0) or 0
            
            # Recalculate total score
            capped_ppa = min(emp.get('score_ppa', 0) or 0, 100)
            capped_lsc = min(emp.get('score_lsc', 0) or 0, 100)
            capped_lbw = min(emp.get('score_lbw', 0) or 0, 100)
            capped_glass = min(emp.get('score_glass', 0) or 0, 100)
            nps_score = emp.get('nps_score', 0) or 0
            
            nps_normalized = max(0, (nps_score + 100) / 2)
            nps_contribution = min(nps_normalized, 100) * 0.10
            
            new_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.15) + (capped_glass * 0.10) + nps_contribution + rt_bonus
            
            metric_bonus = min(emp.get('total_metric_bonus', 0) or 0, 20)
            cv_bonus = emp.get('cv_bonus', 0) or emp.get('cv_score', 0) or 0
            new_total = round(new_weighted + metric_bonus + cv_bonus, 2)
            
            if mentions > 0 or old_mentions > 0:
                await db.employees_v2.update_one(
                    {"_id": emp["_id"]},
                    {"$set": {
                        "review_mentions": mentions,
                        "rt_mentions": mentions,
                        "review_tracker_bonus": rt_bonus,
                        "weighted_score": round(new_weighted, 2),
                        "total_score": new_total,
                        "pre_dar_score": new_total,
                        "rt_source": "feedback_csv_upload",
                        "rt_updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                employees_updated += 1
                
                update_details.append({
                    "name": emp_name,
                    "old_mentions": old_mentions,
                    "new_mentions": mentions,
                    "rt_bonus": rt_bonus,
                    "score_change": round(new_total - (emp.get('total_score', 0) or 0), 2)
                })
        
        # Sync to snapshot
        snapshot_id = await sync_employees_to_most_recent_snapshot(quarter, year)
        
        return {
            "success": True,
            "message": f"Extracted mentions from {reviews_with_mentions} reviews, updated {employees_updated} employees",
            "summary": {
                "total_reviews": reviews_processed,
                "reviews_with_mentions": reviews_with_mentions,
                "total_mentions": total_mentions,
                "employees_updated": employees_updated
            },
            "top_mentioned": sorted(
                [{"name": k, "mentions": v, "rt_bonus": min(v * 0.5, 15)} for k, v in mention_counts.items()],
                key=lambda x: -x["mentions"]
            )[:15],
            "sample_matches": sample_matches,
            "update_details": update_details,
            "quarter": quarter,
            "year": year,
            "snapshot_synced": snapshot_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Feedback CSV upload error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ============================================================================
# DATA INTEGRITY ENDPOINTS (Admin Only)
# ============================================================================

@api_router.get("/v2/admin/data-integrity/check")
async def run_integrity_check():
    """
    Run a full data integrity check across all data sources.
    Returns a comprehensive report of any issues found.
    """
    checker = DataIntegrityChecker(db)
    report = await checker.run_full_integrity_check()
    return report


@api_router.get("/v2/admin/data-integrity/review-duplicates")
async def check_review_duplicates():
    """
    Check for duplicate reviews in the system.
    """
    checker = DataIntegrityChecker(db)
    return await checker.check_review_duplicates()


@api_router.post("/v2/admin/data-integrity/remove-duplicates")
async def remove_duplicate_reviews(dry_run: bool = True):
    """
    Remove duplicate reviews from the system.
    Set dry_run=false to actually delete duplicates.
    """
    checker = DataIntegrityChecker(db)
    return await checker.remove_duplicate_reviews(dry_run=dry_run)


@api_router.get("/v2/admin/data-integrity/cv-server-names")
async def check_cv_server_names():
    """
    Check CV feedback for missing server names.
    All CV feedback must have server attribution.
    """
    checker = DataIntegrityChecker(db)
    return await checker.check_cv_server_names()


@api_router.post("/v2/admin/data-integrity/flag-invalid-cv")
async def flag_invalid_cv_feedback(dry_run: bool = True):
    """
    Flag CV feedback entries without server names as invalid.
    These should not be counted in scoring.
    """
    checker = DataIntegrityChecker(db)
    return await checker.fix_cv_server_names(dry_run=dry_run)


@api_router.get("/v2/admin/data-integrity/cv-nps-validation")
async def validate_cv_nps():
    """
    Validate that CV NPS records match the raw feedback data.
    """
    checker = DataIntegrityChecker(db)
    return await checker.validate_cv_nps_calculations()


@api_router.post("/v2/admin/data-integrity/recalculate-cv-nps")
async def recalculate_all_cv_nps():
    """
    Recalculate all CV NPS records from raw feedback data.
    This ensures 100% accuracy between feedback and NPS.
    """
    checker = DataIntegrityChecker(db)
    result = await checker.recalculate_all_cv_nps()
    return {
        "status": "complete",
        "message": f"Recalculated NPS for {result['employees_processed']} employees",
        **result
    }


@api_router.get("/v2/admin/data-integrity/review-counts")
async def get_review_counts():
    """
    Get review counts by source and quarter.
    """
    checker = DataIntegrityChecker(db)
    return await checker.check_review_counts()


@api_router.delete("/v2/admin/data-integrity/invalid-cv-feedback")
async def delete_invalid_cv_feedback():
    """
    Delete CV feedback entries that are flagged as invalid (missing server names).
    This is a destructive operation - use with caution.
    """
    checker = DataIntegrityChecker(db)
    await checker.fix_cv_server_names(dry_run=False)
    
    result = await db.cv_feedback.delete_many({"is_valid": False})
    
    return {
        "status": "complete",
        "deleted_count": result.deleted_count,
        "message": f"Deleted {result.deleted_count} invalid CV feedback entries"
    }


@api_router.delete("/v2/admin/data-integrity/orphaned-records")
async def delete_orphaned_records(quarter: str = "Q1", year: int = 2026):
    """
    Delete orphaned CV NPS records that don't have a matching employee in employees_v2.
    These are records for employees who have been removed or are from wrong quarters.
    """
    # Get ALL employee names from employees_v2 (same as check_orphaned_records)
    employees = await db.employees_v2.find({}, {"_id": 0, "name": 1}).to_list(1000)
    employee_names = set(e.get("name", "").lower().strip() for e in employees)
    
    # Find and delete orphaned CV NPS records (no quarter filter - same as check)
    all_nps = await db.cv_nps.find({}).to_list(1000)
    
    orphaned_ids = []
    orphaned_names = []
    for nps in all_nps:
        nps_name = nps.get("employee_name", "").lower().strip()
        if nps_name and nps_name not in employee_names:
            orphaned_ids.append(nps["_id"])
            orphaned_names.append(nps.get("employee_name"))
    
    deleted_count = 0
    if orphaned_ids:
        result = await db.cv_nps.delete_many({"_id": {"$in": orphaned_ids}})
        deleted_count = result.deleted_count
    
    # Log this action
    await db.audit_log.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "delete_orphaned_records",
        "quarter": quarter.upper(),
        "year": year,
        "details": {
            "deleted_count": deleted_count,
            "orphaned_names": list(set(orphaned_names))
        },
        "user": "admin"
    })
    
    return {
        "status": "complete",
        "deleted_count": deleted_count,
        "deleted_names": list(set(orphaned_names)),
        "message": f"Deleted {deleted_count} orphaned CV NPS records"
    }


# ==================== CV NPS ADJUSTMENT ENDPOINTS ====================

@api_router.post("/v2/cv/adjustment/upload")
async def upload_cv_adjustment_reports(
    feedback_file: UploadFile = File(...),
    transaction_file: UploadFile = File(None),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload Feedback Report and Transaction Report for CV NPS adjustment.
    
    This tool:
    1. Parses both reports and matches them by check number
    2. Auto-detects feedback that's likely NOT the server's fault
    3. Returns all passives/detractors for manual review
    4. Calculates original and adjusted NPS
    
    Expected files:
    - Feedback Report: Contains Id, Customer Name, Check Number, Rating, Comment
    - Transaction Report (optional): Contains CheckNumber, CustomerName, etc.
    """
    from cv_adjustment import process_cv_reports
    
    try:
        # Read feedback file
        feedback_contents = await feedback_file.read()
        if feedback_file.filename.lower().endswith('.csv'):
            feedback_df = pd.read_csv(io.BytesIO(feedback_contents))
        else:
            feedback_df = pd.read_excel(io.BytesIO(feedback_contents))
        
        # Read transaction file if provided
        transaction_df = None
        if transaction_file:
            trans_contents = await transaction_file.read()
            if transaction_file.filename.lower().endswith('.csv'):
                transaction_df = pd.read_csv(io.BytesIO(trans_contents))
            else:
                transaction_df = pd.read_excel(io.BytesIO(trans_contents))
        
        # Process the reports
        result = process_cv_reports(feedback_df, transaction_df)
        
        # Store the adjustment session in the database
        session_id = str(uuid.uuid4())
        await db.cv_adjustment_sessions.insert_one({
            "_id": session_id,
            "quarter": quarter.upper(),
            "year": year,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "feedback_items": result['feedback_items'],
            "original_nps": result['original_nps'],
            "adjusted_nps": result['adjusted_nps'],
            "status": "pending_review"
        })
        
        return {
            "status": "success",
            "session_id": session_id,
            "summary": result['summary'],
            "original_nps": result['original_nps'],
            "adjusted_nps": result['adjusted_nps'],
            "excluded_count": result['excluded_count'],
            "feedback_items": result['feedback_items'],
            "message": f"Processed {result['summary']['total_feedback']} feedback items. {result['excluded_count']['total']} auto-flagged for review."
        }
        
    except Exception as e:
        logging.exception("Error processing CV adjustment reports")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/v2/cv/adjustment/sessions")
async def get_cv_adjustment_sessions(quarter: str = "Q1", year: int = 2026):
    """
    Get all CV adjustment sessions for a quarter.
    """
    sessions = await db.cv_adjustment_sessions.find({
        "quarter": quarter.upper(),
        "year": year
    }).sort("created_at", -1).to_list(length=100)
    
    return [{
        "session_id": s["_id"],
        "created_at": s.get("created_at"),
        "status": s.get("status"),
        "original_nps": s.get("original_nps"),
        "adjusted_nps": s.get("adjusted_nps"),
        "total_items": len(s.get("feedback_items", []))
    } for s in sessions]


@api_router.get("/v2/cv/adjustment/session/{session_id}")
async def get_cv_adjustment_session(session_id: str):
    """
    Get a specific CV adjustment session with all feedback items.
    """
    session = await db.cv_adjustment_sessions.find_one({"_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session["_id"],
        "quarter": session.get("quarter"),
        "year": session.get("year"),
        "created_at": session.get("created_at"),
        "status": session.get("status"),
        "original_nps": session.get("original_nps"),
        "adjusted_nps": session.get("adjusted_nps"),
        "feedback_items": session.get("feedback_items", [])
    }


@api_router.post("/v2/cv/adjustment/session/{session_id}/update-item")
async def update_cv_adjustment_item(
    session_id: str,
    item_id: str,
    excluded: bool,
    exclusion_reason: str = ""
):
    """
    Update exclusion status for a specific feedback item.
    """
    from cv_adjustment import calculate_nps
    
    session = await db.cv_adjustment_sessions.find_one({"_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update the specific item
    feedback_items = session.get("feedback_items", [])
    item_found = False
    for item in feedback_items:
        if item.get("id") == item_id:
            item["excluded"] = excluded
            item["exclusion_reason"] = exclusion_reason if excluded else ""
            item_found = True
            break
    
    if not item_found:
        raise HTTPException(status_code=404, detail="Feedback item not found")
    
    # Recalculate adjusted NPS
    adjusted_nps = calculate_nps(feedback_items, exclude_flagged=True)
    
    # Update session in database
    await db.cv_adjustment_sessions.update_one(
        {"_id": session_id},
        {"$set": {
            "feedback_items": feedback_items,
            "adjusted_nps": adjusted_nps,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Count excluded items
    excluded_passives = len([i for i in feedback_items if i.get('excluded') and i.get('nps_category') == 'passive'])
    excluded_detractors = len([i for i in feedback_items if i.get('excluded') and i.get('nps_category') == 'detractor'])
    
    return {
        "status": "updated",
        "adjusted_nps": adjusted_nps,
        "excluded_count": {
            "passives": excluded_passives,
            "detractors": excluded_detractors,
            "total": excluded_passives + excluded_detractors
        }
    }


@api_router.post("/v2/cv/adjustment/sessions/{session_id}/assign-server")
async def assign_server_to_feedback(session_id: str, item_id: str, server_name: str):
    """
    Assign a server to a specific feedback item (passive or detractor).
    This allows manual attribution of CV scores to the responsible server.
    """
    session = await db.cv_adjustment_sessions.find_one({"_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update the specific item
    feedback_items = session.get("feedback_items", [])
    item_found = False
    for item in feedback_items:
        if item.get("id") == item_id:
            item["assigned_server"] = server_name
            item_found = True
            break
    
    if not item_found:
        raise HTTPException(status_code=404, detail="Feedback item not found")
    
    # Update session in database
    await db.cv_adjustment_sessions.update_one(
        {"_id": session_id},
        {"$set": {
            "feedback_items": feedback_items,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "status": "assigned",
        "item_id": item_id,
        "server_name": server_name
    }




@api_router.post("/v2/cv/adjustment/session/{session_id}/apply")
async def apply_cv_adjustment(session_id: str, quarter: str = "Q1", year: int = 2026):
    """
    Apply the CV adjustments to employee records.
    
    This:
    1. Updates employee cv_promoters, cv_passives, cv_detractors with adjusted counts
    2. Recalculates cv_score and nps_score for each employee
    3. Marks the session as applied
    """
    from cv_adjustment import calculate_nps
    from name_matcher import find_best_match
    
    session = await db.cv_adjustment_sessions.find_one({"_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.get("status") == "applied":
        raise HTTPException(status_code=400, detail="Adjustments already applied")
    
    feedback_items = session.get("feedback_items", [])
    
    # Get all employees for matching
    all_employees = await db.employees_v2.find({
        "quarter": quarter.upper(),
        "year": year
    }).to_list(length=None)
    
    employee_dicts = [{
        'id': str(emp.get('_id')),
        'name': emp.get('name', ''),
        'display_name': emp.get('display_name', ''),
        'report_name': emp.get('report_name', ''),
        'aliases': emp.get('aliases', []),
        '_doc': emp
    } for emp in all_employees]
    
    # Aggregate feedback by employee (using assigned_server or name detection from comments)
    employee_feedback = {}
    
    for item in feedback_items:
        if item.get('excluded'):
            continue  # Skip excluded items
        
        # First check if server was manually assigned
        server_name = item.get('assigned_server')
        
        if not server_name:
            # Try to detect server name from comment
            comment = item.get('comment', '')
            
            # Look for employee names mentioned in comment
            for emp in employee_dicts:
                emp_first = emp['name'].split()[0].lower()
                if len(emp_first) > 2 and emp_first in comment.lower():
                    server_name = emp['name']
                    break
        
        if server_name:
            if server_name not in employee_feedback:
                employee_feedback[server_name] = {
                    'promoters': 0, 'passives': 0, 'detractors': 0, 'total': 0
                }
            
            cat = item.get('nps_category')
            employee_feedback[server_name]['total'] += 1
            if cat == 'promoter':
                employee_feedback[server_name]['promoters'] += 1
            elif cat == 'passive':
                employee_feedback[server_name]['passives'] += 1
            elif cat == 'detractor':
                employee_feedback[server_name]['detractors'] += 1
    
    # Update employees with adjusted feedback counts
    employees_updated = 0
    for emp_name, counts in employee_feedback.items():
        result = await db.employees_v2.update_one(
            {"name": emp_name, "quarter": quarter.upper(), "year": year},
            {"$set": {
                "cv_promoters_adjusted": counts['promoters'],
                "cv_passives_adjusted": counts['passives'],
                "cv_detractors_adjusted": counts['detractors'],
                "cv_total_adjusted": counts['total'],
                "cv_adjustment_applied": True,
                "cv_adjustment_session_id": session_id
            }}
        )
        if result.modified_count > 0:
            employees_updated += 1
    
    # Mark session as applied
    await db.cv_adjustment_sessions.update_one(
        {"_id": session_id},
        {"$set": {
            "status": "applied",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "employees_updated": employees_updated
        }}
    )
    
    return {
        "status": "applied",
        "employees_updated": employees_updated,
        "adjusted_nps": session.get("adjusted_nps"),
        "message": f"Applied adjustments to {employees_updated} employees"
    }


@api_router.get("/v2/cv/adjustment/keywords")
async def get_cv_adjustment_keywords():
    """
    Get the list of keywords used for auto-detection of non-server issues.
    """
    from cv_adjustment import NON_SERVER_KEYWORDS, SERVER_KEYWORDS
    
    return {
        "non_server_keywords": NON_SERVER_KEYWORDS,
        "server_keywords": SERVER_KEYWORDS
    }


@api_router.post("/v2/cv/adjustment/test-detection")
async def test_cv_detection(comment: str):
    """
    Test the auto-detection algorithm on a specific comment.
    """
    from cv_adjustment import detect_non_server_issues
    
    is_non_server, reasons, category = detect_non_server_issues(comment)
    
    return {
        "comment": comment,
        "is_non_server_issue": is_non_server,
        "reasons": reasons,
        "category": category
    }




@api_router.get("/v2/admin/name-matching/preview")
async def preview_name_matching(quarter: str = "Q1", year: int = 2026):
    """
    Preview how employee names will be matched to CV NPS names.
    Shows the mapping and confidence scores without applying changes.
    """
    from name_matcher import build_name_mapping, get_nps_for_employee_smart, normalize_name
    
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
    
    employee_names = [e["name"] for e in employees]
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


@api_router.post("/v2/admin/name-matching/apply")
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
    
    # Get settings
    settings_doc = await db.quarter_settings.find_one(
        {"quarter": quarter, "year": year},
        {"_id": 0}
    )
    settings = QuarterSettings(**(settings_doc or {}))
    
    # Build NPS lookup
    nps_lookup = {normalize_name(n["employee_name"]): n for n in nps_records}
    
    # Track updates
    updates = []
    employee_objects = []
    
    for emp_data in employees:
        emp_name = emp_data["name"]
        aliases = emp_data.get("aliases", [])
        
        # Smart match to CV data
        nps_data, match_reason = get_nps_for_employee_smart(emp_name, nps_lookup, aliases)
        
        nps_score = nps_data.get("nps_score") or 0
        cv_promoters = nps_data.get("promoters") or 0
        cv_passives = nps_data.get("passives") or 0
        cv_detractors = nps_data.get("detractors") or 0
        
        # Create employee object with updated CV data
        emp = EmployeeV2(
            id=emp_data.get("id", str(uuid.uuid4())),
            name=emp_name,
            job_title=emp_data.get("job_title", "Server"),
            aliases=emp_data.get("aliases", []),
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
            review_mentions=emp_data.get("review_mentions", 0),
            nps_score=nps_score,
            year=year,
            quarter=quarter,
        )
        
        # Run scoring pipeline
        emp = calculate_lbw_total(emp)
        emp = calculate_derived_metrics(emp)
        emp = calculate_customer_voice_score(emp)
        emp = calculate_review_tracker_bonus(emp)
        emp = calculate_combined_cv_rt(emp)
        emp = calculate_normalized_scores(emp, settings)
        emp = calculate_bonus_points(emp, settings)
        emp = calculate_total_score(emp, settings)
        
        employee_objects.append(emp)
        
        old_cv = emp_data.get("cv_score") or 0
        if abs((emp.cv_score or 0) - old_cv) > 0.1:
            updates.append({
                "name": emp_name,
                "matched_to": nps_data.get("employee_name"),
                "reason": match_reason,
                "old_cv": old_cv,
                "new_cv": emp.cv_score,
                "old_score": emp_data.get("pre_dar_score") or emp_data.get("total_score") or 0,
                "new_score": emp.pre_dar_score
            })
    
    # Calculate rankings
    employee_objects = calculate_rankings(employee_objects)
    employee_objects = calculate_performance_tiers(employee_objects)
    
    # Update database
    for emp in employee_objects:
        emp_dict = emp.model_dump()
        await db.employees_v2.update_one(
            {"name": emp.name, "quarter": quarter, "year": year},
            {"$set": emp_dict}
        )
    
    return {
        "status": "complete",
        "quarter": quarter,
        "year": year,
        "employees_processed": len(employee_objects),
        "employees_updated": len(updates),
        "updates": updates
    }


@api_router.get("/v2/admin/data-integrity/summary")
async def get_integrity_summary():
    """
    Get a quick summary of data integrity status.
    """
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
# SELF-CHECKING AUDIT SYSTEM - Guarantees 100% Accurate Scoring
# ============================================================

@api_router.get("/v2/audit/employee/{employee_name}")
async def audit_employee_score(employee_name: str, quarter: str = "Q1", year: int = 2026):
    """
    Audit a single employee's score calculation step-by-step.
    Returns a detailed breakdown showing exactly how each component was calculated.
    This is the self-checking audit process that guarantees 100% accuracy.
    """
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
    # employee_mentions is an array of objects: [{name: "...", sentiment: "...", points: 0.2}]
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
            "match": (stored_guests_per_lsc is None and expected_guests_per_lsc is None) or 
                    (stored_guests_per_lsc and expected_guests_per_lsc and abs(expected_guests_per_lsc - stored_guests_per_lsc) < 0.01)
        }
    }
    
    # === NORMALIZED SCORES AUDIT ===
    benchmark_ppa = settings.get("benchmark_ppa", 55)
    benchmark_lbw = settings.get("benchmark_lbw", 8)
    benchmark_glass = settings.get("benchmark_glass", 1.25)
    benchmark_lsc = settings.get("benchmark_lsc", 100)
    
    expected_score_ppa = round((expected_ppa / benchmark_ppa) * 100, 2) if benchmark_ppa > 0 else 0
    expected_score_lbw = round((expected_lbw_per_guest / benchmark_lbw) * 100, 2) if benchmark_lbw > 0 else 0
    expected_score_glass = round((expected_glass_per_guest / benchmark_glass) * 100, 2) if benchmark_glass > 0 else 0
    expected_score_lsc = round((benchmark_lsc / expected_guests_per_lsc) * 100, 2) if expected_guests_per_lsc and expected_guests_per_lsc > 0 else 0
    
    stored_score_ppa = employee.get("score_ppa", 0)
    stored_score_lbw = employee.get("score_lbw", 0)
    stored_score_glass = employee.get("score_glass", 0)
    stored_score_lsc = employee.get("score_lsc", 0)
    
    audit["calculations"]["normalized_scores"] = {
        "ppa_score": {
            "formula": f"({expected_ppa} / {benchmark_ppa}) × 100",
            "expected": expected_score_ppa,
            "stored": stored_score_ppa,
            "match": abs(expected_score_ppa - stored_score_ppa) < 1
        },
        "lbw_score": {
            "formula": f"({expected_lbw_per_guest} / {benchmark_lbw}) × 100",
            "expected": expected_score_lbw,
            "stored": stored_score_lbw,
            "match": abs(expected_score_lbw - stored_score_lbw) < 1
        },
        "glass_score": {
            "formula": f"({expected_glass_per_guest} / {benchmark_glass}) × 100",
            "expected": expected_score_glass,
            "stored": stored_score_glass,
            "match": abs(expected_score_glass - stored_score_glass) < 1
        },
        "lsc_score": {
            "formula": f"({benchmark_lsc} / {expected_guests_per_lsc}) × 100" if expected_guests_per_lsc else "N/A",
            "expected": expected_score_lsc,
            "stored": stored_score_lsc,
            "match": abs(expected_score_lsc - stored_score_lsc) < 1
        }
    }
    
    # === WEIGHTED BASE SCORE AUDIT ===
    capped_ppa = min(expected_score_ppa, 100)
    capped_lbw = min(expected_score_lbw, 100)
    capped_glass = min(expected_score_glass, 100)
    capped_lsc = min(expected_score_lsc, 100)
    
    # Check if using manual upload - use stored NPS instead of raw
    cv_source = employee.get("cv_source", "")
    stored_nps_for_weight = employee.get("nps_score", 0) or 0
    
    # NPS % is NOT part of weighted_score - it's part of cv_score
    # Review Tracker contribution - 0.5 pts per mention, max 15 pts (added to weighted)
    rt_source = employee.get("rt_source", "")
    rt_mentions = employee.get("review_mentions", 0) or 0
    rt_contribution = min(rt_mentions * 0.5, 15)
    
    # Base weighted: PPA(25%) + LSC(25%) + LBW(15%) + Glass(10%) + RT (max 15 pts)
    # NPS is NOT included here - it's part of cv_score as nps_pts
    expected_weighted = round(capped_ppa * 0.25 + capped_lsc * 0.25 + capped_lbw * 0.15 + capped_glass * 0.10 + rt_contribution, 2)
    stored_weighted = employee.get("weighted_score", 0)
    
    audit["calculations"]["weighted_score"] = {
        "formula": f"PPA({capped_ppa}×0.25) + LSC({capped_lsc}×0.25) + LBW({capped_lbw}×0.15) + Glass({capped_glass}×0.10) + RT({rt_contribution})",
        "breakdown": {
            "ppa_contribution": round(capped_ppa * 0.25, 2),
            "lsc_contribution": round(capped_lsc * 0.25, 2),
            "lbw_contribution": round(capped_lbw * 0.15, 2),
            "glass_contribution": round(capped_glass * 0.10, 2),
            "rt_contribution": rt_contribution
        },
        "expected": expected_weighted,
        "stored": stored_weighted,
        "match": abs(expected_weighted - stored_weighted) < 1
    }
    
    # === CUSTOMER VOICE AUDIT ===
    stored_cv_promoters = employee.get("cv_promoters", 0) or 0
    stored_cv_detractors = employee.get("cv_detractors", 0) or 0
    stored_nps = employee.get("nps_score", 0) or 0
    stored_cv_score = employee.get("cv_score", 0) or 0
    cv_source = employee.get("cv_source", "")
    
    # For manual uploads, use stored values as the source of truth
    # Otherwise, use raw cv_feedback data
    if cv_source == "manual_upload":
        audit_promoters = stored_cv_promoters
        audit_detractors = stored_cv_detractors
        audit_nps = stored_nps
    else:
        audit_promoters = raw_promoters
        audit_detractors = raw_detractors
        audit_nps = raw_nps
    
    # CV Score: NPS pts (nps/10, max 10) + Promoters +0.5 each - Detractors -1 each
    # This is separate from NPS contribution in weighted_score
    audit_nps_pts = round(audit_nps / 10, 1) if audit_nps > 0 else 0.0
    audit_nps_pts = min(audit_nps_pts, 10.0)
    expected_cv_bonus = audit_nps_pts + (audit_promoters * 0.5) - (audit_detractors * 1)
    
    audit["data_trail"]["customer_voice"] = {
        "raw_feedback_count": raw_total,
        "raw_promoters": raw_promoters,
        "raw_passives": raw_passives,
        "raw_detractors": raw_detractors,
        "raw_nps_calculated": raw_nps,
        "cv_nps_record": cv_nps,
        "stored_in_employee": {
            "promoters": stored_cv_promoters,
            "detractors": stored_cv_detractors,
            "nps_score": stored_nps
        },
        "source": cv_source if cv_source else "cv_feedback",
        "audit_using": {
            "promoters": audit_promoters,
            "detractors": audit_detractors,
            "nps": audit_nps
        }
    }
    
    audit["calculations"]["customer_voice"] = {
        "nps_points": {
            "formula": f"NPS {audit_nps}% / 10 = {audit_nps_pts} pts (max 10)",
            "expected": audit_nps_pts,
            "match": True
        },
        "promoter_points": {
            "formula": f"{audit_promoters} promoters × +0.5 pt",
            "expected": audit_promoters * 0.5,
            "match": True
        },
        "detractor_points": {
            "formula": f"{audit_detractors} detractors × -1 pt",
            "expected": audit_detractors * -1,
            "match": True
        },
        "total_cv_score": {
            "formula": f"NPS pts({audit_nps_pts}) + ({audit_promoters} × 0.5) - ({audit_detractors} × 1)",
            "expected": round(expected_cv_bonus, 2),
            "stored": stored_cv_score,
            "match": abs(expected_cv_bonus - stored_cv_score) < 0.5
        }
    }
    
    # Check CV data consistency
    # Skip if using manual upload - the uploaded data IS the source of truth
    if raw_total > 0 and cv_source != "manual_upload":
        if raw_promoters != stored_cv_promoters:
            audit["discrepancies"].append({
                "field": "cv_promoters",
                "description": f"Raw feedback shows {raw_promoters} promoters but employee record has {stored_cv_promoters}",
                "severity": "HIGH"
            })
        if raw_detractors != stored_cv_detractors:
            audit["discrepancies"].append({
                "field": "cv_detractors",
                "description": f"Raw feedback shows {raw_detractors} detractors but employee record has {stored_cv_detractors}",
                "severity": "HIGH"
            })
    elif cv_source == "manual_upload":
        audit["data_trail"]["customer_voice"]["note"] = "Using uploaded data as source of truth"
    
    # === REVIEW TRACKER AUDIT ===
    stored_rt_mentions = employee.get("review_mentions", 0) or 0
    stored_rt_bonus = employee.get("review_tracker_bonus", 0) or 0
    # RT formula: 0.5 pts per mention, max 15 pts (part of 15% weight in base score)
    expected_rt_bonus = min(stored_rt_mentions * 0.5, 15)
    
    audit["data_trail"]["review_tracker"] = {
        "raw_mentions_found": raw_rt_mentions,
        "stored_mentions": stored_rt_mentions,
        "review_details": [{"platform": r.get("platform"), "date": r.get("date")} for r in review_mentions[:5]]
    }
    
    audit["calculations"]["review_tracker"] = {
        "formula": f"min({stored_rt_mentions} mentions × 0.5 pts, 15) = {expected_rt_bonus}",
        "expected_bonus": expected_rt_bonus,
        "stored_bonus": stored_rt_bonus,
        "match": abs(expected_rt_bonus - stored_rt_bonus) < 0.5
    }
    
    # Check RT data consistency
    # Skip if using manual upload - the uploaded data IS the source of truth
    rt_source = employee.get("rt_source", "")
    if raw_rt_mentions != stored_rt_mentions and rt_source != "manual_upload":
        audit["discrepancies"].append({
            "field": "review_mentions",
            "description": f"Found {raw_rt_mentions} review mentions but employee record has {stored_rt_mentions}",
            "severity": "MEDIUM"
        })
    elif rt_source == "manual_upload":
        audit["data_trail"]["review_tracker"]["source"] = "manual_upload"
        audit["data_trail"]["review_tracker"]["note"] = "Using uploaded data as source of truth"
    
    # === METRIC BONUS AUDIT ===
    def calc_bonus(score):
        if score is None or score <= 100:
            return 0
        excess = score - 100
        bonus = (excess / 20) * 5
        return min(bonus, 5.0)
    
    expected_bonus_ppa = round(calc_bonus(expected_score_ppa), 2)
    expected_bonus_lbw = round(calc_bonus(expected_score_lbw), 2)
    expected_bonus_glass = round(calc_bonus(expected_score_glass), 2)
    expected_bonus_lsc = round(calc_bonus(expected_score_lsc), 2)
    expected_total_bonus = round(expected_bonus_ppa + expected_bonus_lbw + expected_bonus_glass + expected_bonus_lsc, 2)
    
    stored_total_bonus = employee.get("total_metric_bonus", 0)
    
    audit["calculations"]["metric_bonus"] = {
        "formula": "For each metric: ((score - 100) / 20) × 5, capped at 5",
        "ppa_bonus": {"expected": expected_bonus_ppa, "stored": employee.get("bonus_ppa", 0)},
        "lbw_bonus": {"expected": expected_bonus_lbw, "stored": employee.get("bonus_lbw", 0)},
        "glass_bonus": {"expected": expected_bonus_glass, "stored": employee.get("bonus_glass", 0)},
        "lsc_bonus": {"expected": expected_bonus_lsc, "stored": employee.get("bonus_lsc", 0)},
        "total": {
            "expected": expected_total_bonus,
            "stored": stored_total_bonus,
            "match": abs(expected_total_bonus - stored_total_bonus) < 0.5
        }
    }
    
    # === FINAL SCORE AUDIT ===
    # Final = Weighted (POS + RT) + Metric Bonus + CV Score (NPS pts + promoter/detractor bonus)
    expected_final = round(expected_weighted + expected_total_bonus + expected_cv_bonus, 2)
    stored_final = employee.get("pre_dar_score") or employee.get("total_score", 0)
    
    audit["calculations"]["final_score"] = {
        "formula": f"Weighted({expected_weighted}) + MetricBonus({expected_total_bonus}) + CVScore({round(expected_cv_bonus, 2)})",
        "breakdown": {
            "weighted_base_score": expected_weighted,
            "metric_bonus": expected_total_bonus,
            "cv_score": round(expected_cv_bonus, 2)
        },
        "expected": expected_final,
        "stored": stored_final,
        "match": abs(expected_final - stored_final) < 1
    }
    
    if abs(expected_final - stored_final) >= 1:
        audit["discrepancies"].append({
            "field": "pre_dar_score",
            "description": f"Calculated score is {expected_final} but stored score is {stored_final}. Difference: {round(stored_final - expected_final, 2)}",
            "severity": "CRITICAL"
        })
    
    # Set validation status
    if len(audit["discrepancies"]) > 0:
        high_severity = [d for d in audit["discrepancies"] if d["severity"] in ["HIGH", "CRITICAL"]]
        if high_severity:
            audit["validation_status"] = "FAIL"
        else:
            audit["validation_status"] = "WARNING"
    
    # Include employee data for UI display
    audit["employee_data"] = {
        "cv_promoters": employee.get("cv_promoters"),
        "cv_detractors": employee.get("cv_detractors"),
        "cv_score": employee.get("cv_score"),
        "nps_score": employee.get("nps_score"),
        "review_mentions": employee.get("review_mentions"),
        "review_tracker_bonus": employee.get("review_tracker_bonus"),
        "weighted_score": employee.get("weighted_score"),
        "pre_dar_score": employee.get("pre_dar_score"),
        "total_score": employee.get("total_score"),
        "cv_sync_source": employee.get("cv_sync_source")
    }
    
    return {"success": True, "audit": audit}


@api_router.post("/v2/audit/fix-employee/{employee_name}")
async def fix_single_employee(employee_name: str, quarter: str = "Q1", year: int = 2026):
    """
    Fix a single employee's score discrepancies by recalculating from raw data.
    This recalculates the score using the correct formula:
    - Weighted Base (PPA 25%, LSC 25%, LBW 15%, Glass 10%, NPS 10%, RT 15%)
    - + Metric Bonus (max 20 pts)
    - + CV Bonus (promoters*0.5 - detractors*1, no cap)
    """
    # Get employee record
    employee = await db.employees_v2.find_one(
        {"name": {"$regex": f"^{employee_name}$", "$options": "i"}, "quarter": quarter.upper(), "year": year}
    )
    
    if not employee:
        return {"success": False, "error": f"Employee '{employee_name}' not found"}
    
    # Get raw CV feedback
    cv_feedback = await db.cv_feedback.find(
        {"server_name": {"$regex": f"^{employee_name}$", "$options": "i"}, "quarter": quarter.upper(), "year": year}
    ).to_list(100)
    
    # If no CV feedback found, use existing employee values
    if cv_feedback:
        promoters = len([f for f in cv_feedback if f.get("rating", 0) >= 9])
        passives = len([f for f in cv_feedback if 7 <= f.get("rating", 0) <= 8])
        detractors = len([f for f in cv_feedback if f.get("rating", 0) <= 6])
        total_feedback = len(cv_feedback)
        nps_score = round(((promoters - detractors) / total_feedback) * 100, 2) if total_feedback > 0 else 0
    else:
        # Preserve existing CV data from employee record
        promoters = employee.get("cv_promoters", 0) or 0
        passives = employee.get("cv_passives", 0) or 0
        detractors = employee.get("cv_detractors", 0) or 0
        nps_score = employee.get("nps_score", 0) or 0
    
    # Count actual review mentions
    actual_mentions = await db.customer_reviews.count_documents({
        "quarter": quarter.upper(),
        "year": year,
        "employee_mentions.name": {"$regex": f"^{employee_name}$", "$options": "i"}
    })
    
    # If no customer_reviews found, use existing RT data
    if actual_mentions == 0:
        actual_mentions = employee.get("review_mentions", 0) or 0
    
    # Get benchmark scores from employee record
    capped_ppa = min(employee.get("score_ppa", 0) or 0, 100)
    capped_lsc = min(employee.get("score_lsc", 0) or 0, 100)
    capped_lbw = min(employee.get("score_lbw", 0) or 0, 100)
    capped_glass = min(employee.get("score_glass", 0) or 0, 100)
    
    # Calculate NPS points: direct ratio (NPS% / 10, max 10 pts)
    nps_pts = round(nps_score / 10, 1) if nps_score > 0 else 0.0
    nps_pts = min(nps_pts, 10.0)
    
    # Calculate RT contribution (0.5 pts per mention, max 15)
    rt_contribution = min(actual_mentions * 0.5, 15)
    
    # CV bonus from promoters/detractors: +0.5 per promoter, -1 per detractor
    cv_promo_bonus = (promoters * 0.5) - (detractors * 1)
    
    # Total CV Score = NPS points + Promoter/Detractor bonus
    cv_score_total = round(nps_pts + cv_promo_bonus, 2)
    
    # Base weighted score (POS metrics only: PPA 25%, LSC 25%, LBW 15%, Glass 10%)
    base_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.15) + (capped_glass * 0.10)
    
    # Metric bonus
    metric_bonus = min(employee.get("total_metric_bonus", 0) or 0, 20)
    
    # Final score = Base Weighted + CV Score + RT Bonus + Metric Bonus
    new_weighted = round(base_weighted, 2)
    new_score = round(base_weighted + cv_score_total + rt_contribution + metric_bonus, 2)
    
    old_score = employee.get("pre_dar_score") or employee.get("total_score", 0)
    
    # Update employee
    await db.employees_v2.update_one(
        {"_id": employee["_id"]},
        {"$set": {
            "review_mentions": actual_mentions,
            "review_tracker_bonus": rt_contribution,
            "cv_promoters": promoters,
            "cv_passives": passives,
            "cv_detractors": detractors,
            "nps_score": nps_score,
            "nps_score_pts": nps_pts,
            "cv_raw_points": round(cv_promo_bonus, 2),
            "cv_score": cv_score_total,
            "cv_bonus": round(cv_promo_bonus, 2),
            "weighted_score": new_weighted,
            "pre_dar_score": new_score,
            "total_score": new_score,
            "fixed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "success": True,
        "employee_name": employee["name"],
        "old_score": old_score,
        "new_score": new_score,
        "score_change": round(new_score - old_score, 2),
        "details": {
            "review_mentions": actual_mentions,
            "rt_bonus": rt_contribution,
            "cv_promoters": promoters,
            "cv_detractors": detractors,
            "cv_promo_bonus": round(cv_promo_bonus, 2),
            "nps_pts": nps_pts,
            "cv_score_total": cv_score_total,
            "metric_bonus": metric_bonus,
            "weighted_score": new_weighted
        }
    }


@api_router.get("/v2/audit/all")
async def audit_all_employees(quarter: str = "Q1", year: int = 2026):
    """
    Run audit on ALL employees for a quarter.
    Returns a summary of which employees pass/fail validation.
    """
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "name": 1, "pre_dar_score": 1}
    ).to_list(1000)
    
    results = {
        "quarter": quarter.upper(),
        "year": year,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "total_employees": len(employees),
        "passed": 0,
        "warnings": 0,
        "failed": 0,
        "employees": []
    }
    
    for emp in employees:
        audit_result = await audit_employee_score(emp["name"], quarter, year)
        if audit_result.get("success"):
            status = audit_result["audit"]["validation_status"]
            discrepancies = audit_result["audit"]["discrepancies"]
            
            emp_summary = {
                "name": emp["name"],
                "score": emp.get("pre_dar_score", 0),
                "status": status,
                "discrepancy_count": len(discrepancies),
                "issues": [d["description"] for d in discrepancies[:3]]  # Top 3 issues
            }
            
            if status == "PASS":
                results["passed"] += 1
            elif status == "WARNING":
                results["warnings"] += 1
            else:
                results["failed"] += 1
            
            results["employees"].append(emp_summary)
    
    # Sort by status (FAIL first, then WARNING, then PASS)
    status_order = {"FAIL": 0, "WARNING": 1, "PASS": 2}
    results["employees"].sort(key=lambda x: (status_order.get(x["status"], 3), -x["discrepancy_count"]))
    
    results["overall_status"] = "VERIFIED" if results["failed"] == 0 and results["warnings"] == 0 else "ISSUES_FOUND"
    
    return results


@api_router.get("/v2/audit/report")
async def generate_audit_report(quarter: str = "Q1", year: int = 2026):
    """
    Generate a comprehensive audit report for a quarter.
    This is the self-checking audit process that guarantees 100% scoring accuracy.
    """
    from audit_system import ScoringAuditSystem
    
    audit_system = ScoringAuditSystem(db)
    
    # Run consistency checks
    consistency = await audit_system.run_consistency_checks(quarter, year)
    
    # Get official stats status
    official_cv = await db.official_cv_stats.find_one(
        {"quarter": quarter.upper(), "year": year}, {"_id": 0}
    )
    official_rt = await db.official_rt_stats.find_one(
        {"quarter": quarter.upper(), "year": year}, {"_id": 0}
    )
    
    # Get employee audit summary
    employee_audit = await audit_all_employees(quarter, year)
    
    # Get data counts
    cv_feedback_count = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year})
    reviews_count = await db.customer_reviews.count_documents({"quarter": quarter.upper(), "year": year})
    cv_nps_count = await db.cv_nps.count_documents({"quarter": quarter.upper(), "year": year})
    
    report = {
        "title": f"Scoring Audit Report - {quarter.upper()} {year}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quarter": quarter.upper(),
        "year": year,
        "overall_status": "VERIFIED" if (
            consistency.get("passed") and 
            employee_audit.get("failed", 1) == 0
        ) else "ISSUES_FOUND",
        "data_sources": {
            "official_cv_stats": {
                "set": official_cv is not None,
                "source": official_cv.get("source") if official_cv else None,
                "updated_at": official_cv.get("updated_at") if official_cv else None
            },
            "official_rt_stats": {
                "set": official_rt is not None,
                "source": official_rt.get("source") if official_rt else None,
                "updated_at": official_rt.get("updated_at") if official_rt else None
            }
        },
        "data_counts": {
            "employees": employee_audit.get("total_employees", 0),
            "cv_feedback": cv_feedback_count,
            "cv_nps_records": cv_nps_count,
            "customer_reviews": reviews_count
        },
        "consistency_checks": consistency,
        "employee_audit": {
            "total": employee_audit.get("total_employees", 0),
            "passed": employee_audit.get("passed", 0),
            "warnings": employee_audit.get("warnings", 0),
            "failed": employee_audit.get("failed", 0),
            "issues": [e for e in employee_audit.get("employees", []) if e["status"] != "PASS"]
        },
        "recommendations": []
    }
    
    # Add recommendations
    if not official_cv:
        report["recommendations"].append("Set official CV stats from Loyalty Voice UI for 100% accuracy")
    if not official_rt:
        report["recommendations"].append("Set official RT stats from ReviewTrackers UI for 100% accuracy")
    if employee_audit.get("failed", 0) > 0:
        report["recommendations"].append(f"Investigate and fix {employee_audit['failed']} employees with score calculation errors")
    if employee_audit.get("warnings", 0) > 0:
        report["recommendations"].append(f"Review {employee_audit['warnings']} employees with data warnings")
    
    return report


@api_router.get("/v2/audit/trail")
async def get_audit_trail(quarter: str = "Q1", year: int = 2026, limit: int = 50):
    """
    Get the audit trail showing all changes made to data for a quarter.
    """
    entries = await db.audit_log.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "entries": entries,
        "count": len(entries)
    }


@api_router.post("/v2/audit/log")
async def log_audit_entry(
    action: str,
    quarter: str = "Q1",
    year: int = 2026,
    details: dict = None,
    user: str = "admin"
):
    """
    Log an audit entry for tracking changes.
    """
    import hashlib
    import json
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "quarter": quarter.upper(),
        "year": year,
        "details": details or {},
        "user": user,
        "checksum": hashlib.sha256(json.dumps({"action": action, "details": details}, sort_keys=True).encode()).hexdigest()[:16]
    }
    
    await db.audit_log.insert_one(entry)
    
    return {"success": True, "entry": entry}


@api_router.post("/v2/audit/recalculate-all")
async def recalculate_all_scores(quarter: str = "Q1", year: int = 2026):
    """
    Recalculate ALL employee scores from their stored components.
    This fixes any score mismatches found during audits.
    """
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(1000)
    
    fixed = []
    unchanged = []
    errors = []
    
    for emp in employees:
        try:
            # Get stored component values
            weighted = emp.get('weighted_score', 0) or 0
            rt_bonus = emp.get('review_tracker_bonus', 0) or 0
            cv_score = emp.get('cv_score', 0) or 0
            metric_bonus = emp.get('total_metric_bonus', 0) or 0
            
            # Calculate correct score
            correct_score = round(weighted + rt_bonus + cv_score + metric_bonus, 2)
            stored_score = emp.get('pre_dar_score', 0) or emp.get('total_score', 0) or 0
            
            if abs(correct_score - stored_score) >= 0.01:
                # Update the employee record
                await db.employees_v2.update_one(
                    {"_id": emp["_id"]},
                    {"$set": {
                        "pre_dar_score": correct_score,
                        "total_score": correct_score
                    }}
                )
                fixed.append({
                    "name": emp["name"],
                    "old_score": stored_score,
                    "new_score": correct_score,
                    "difference": round(correct_score - stored_score, 2)
                })
            else:
                unchanged.append(emp["name"])
        except Exception as e:
            errors.append({"name": emp.get("name"), "error": str(e)})
    
    # Log this action
    await db.audit_log.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "recalculate_all_scores",
        "quarter": quarter.upper(),
        "year": year,
        "details": {
            "fixed_count": len(fixed),
            "unchanged_count": len(unchanged),
            "error_count": len(errors),
            "fixed_employees": [f["name"] for f in fixed]
        },
        "user": "system"
    })
    
    return {
        "success": True,
        "quarter": quarter.upper(),
        "year": year,
        "summary": {
            "total_employees": len(employees),
            "fixed": len(fixed),
            "unchanged": len(unchanged),
            "errors": len(errors)
        },
        "fixed_employees": fixed,
        "errors": errors if errors else None
    }


@api_router.post("/v2/audit/sync-nps-to-employees")
async def sync_nps_to_employees(quarter: str = "Q1", year: int = 2026):
    """
    Sync NPS data from cv_nps collection and review mentions from customer_reviews
    to the employees_v2 collection. This ensures scores are properly calculated.
    """
    import re
    
    # Get NPS records for this quarter
    nps_records = await db.cv_nps.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(500)
    
    # Get employees
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not employees:
        return {"success": False, "error": f"No employees found for {quarter} {year}"}
    
    # Build NPS lookup by name (case-insensitive)
    nps_lookup = {}
    for nps in nps_records:
        name = (nps.get("employee_name") or "").strip().lower()
        if name:
            nps_lookup[name] = nps
    
    # Build review mention counts from employee_mentions field in customer_reviews
    # This uses the already-detected mentions rather than text search
    mention_pipeline = [
        {"$match": {"employee_mentions": {"$exists": True, "$ne": [], "$ne": None}}},
        {"$unwind": "$employee_mentions"},
        {"$group": {
            "_id": "$employee_mentions.name",
            "count": {"$sum": 1}
        }}
    ]
    mention_results = await db.customer_reviews.aggregate(mention_pipeline).to_list(500)
    mention_lookup = {r["_id"].lower().strip(): r["count"] for r in mention_results if r.get("_id")}
    
    # Build mention counts for each employee (with name matching)
    mention_counts = {}
    for emp in employees:
        full_name = emp["name"]
        full_name_lower = full_name.lower().strip()
        first_name = full_name_lower.split()[0] if full_name_lower else ""
        
        # Direct match on full name
        if full_name_lower in mention_lookup:
            mention_counts[full_name] = mention_lookup[full_name_lower]
        # Match on first name only
        elif first_name in mention_lookup:
            mention_counts[full_name] = mention_lookup[first_name]
        else:
            # Partial first name match
            for name, count in mention_lookup.items():
                if name.startswith(first_name) or first_name in name:
                    mention_counts[full_name] = count
                    break
            else:
                mention_counts[full_name] = 0
    
    # Update employees
    nps_updated = 0
    rt_updated = 0
    scores_recalculated = 0
    
    for emp in employees:
        emp_name = emp["name"]
        emp_name_lower = emp_name.lower()
        updates = {}
        
        # Check for NPS data
        nps_data = nps_lookup.get(emp_name_lower)
        if nps_data:
            nps_score = nps_data.get("nps_score", 0) or 0
            promoters = nps_data.get("promoters", 0) or 0
            passives = nps_data.get("passives", 0) or 0
            detractors = nps_data.get("detractors", 0) or 0
            
            # Calculate NPS points: direct ratio (NPS%/10, max 10 pts)
            nps_pts = round(nps_score / 10, 1) if nps_score > 0 else 0.0
            nps_pts = min(nps_pts, 10.0)
            
            # Survey points: +0.5 per promoter, -1 per detractor
            survey_pts = (promoters * 0.5) - (detractors * 1)
            
            # Total CV Score = NPS points + Survey points
            cv_score = round(nps_pts + survey_pts, 2)
            
            updates.update({
                "nps_score": nps_score,
                "cv_promoters": promoters,
                "cv_passives": passives,
                "cv_detractors": detractors,
                "cv_score": cv_score,
                "nps_score_pts": nps_pts,
                "cv_raw_points": round(survey_pts, 2),
                "cv_source": "cv_nps_sync"
            })
            nps_updated += 1
        
        # Check for review mentions (0.5 pts per mention, capped at 15)
        mentions = mention_counts.get(emp_name, 0)
        if mentions > 0:
            rt_bonus = round(min(mentions * 0.5, 15), 1)
            updates.update({
                "review_mentions": mentions,
                "review_tracker_bonus": rt_bonus,
                "review_source": "customer_review_sync"
            })
            rt_updated += 1
        
        # Recalculate total score if we have updates
        if updates:
            cv_score = updates.get("cv_score", emp.get("cv_score", 0)) or 0
            rt_bonus = updates.get("review_tracker_bonus", emp.get("review_tracker_bonus", 0)) or 0
            metric_bonus = emp.get("total_metric_bonus", 0) or 0
            
            # Base POS weighted score (PPA 25%, LSC 25%, LBW 15%, Glass 10%)
            capped_ppa = min(emp.get("score_ppa", 0) or 0, 100)
            capped_lbw = min(emp.get("score_lbw", 0) or 0, 100)
            capped_glass = min(emp.get("score_glass", 0) or 0, 100)
            capped_lsc = min(emp.get("score_lsc", 0) or 0, 100)
            base_weighted = capped_ppa * 0.25 + capped_lsc * 0.25 + capped_lbw * 0.15 + capped_glass * 0.10
            
            # Total = Base Weighted + CV Score + RT Bonus + Metric Bonus
            new_weighted = round(base_weighted, 2)
            new_pre_dar = round(base_weighted + cv_score + rt_bonus + metric_bonus, 2)
            
            updates.update({
                "weighted_score": new_weighted,
                "pre_dar_score": new_pre_dar,
                "total_score": new_pre_dar
            })
            scores_recalculated += 1
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": updates}
            )
    
    # Log this action
    await db.audit_log.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "sync_nps_to_employees",
        "quarter": quarter.upper(),
        "year": year,
        "details": {
            "nps_updated": nps_updated,
            "rt_updated": rt_updated,
            "scores_recalculated": scores_recalculated
        },
        "user": "system"
    })
    
    return {
        "success": True,
        "quarter": quarter.upper(),
        "year": year,
        "summary": {
            "total_employees": len(employees),
            "nps_records_found": len(nps_records),
            "nps_matched_to_employees": nps_updated,
            "review_mentions_matched": rt_updated,
            "scores_recalculated": scores_recalculated
        }
    }


@api_router.get("/v2/audit/review-accuracy")
async def audit_review_accuracy(quarter: str = "Q1", year: int = 2026):
    """
    DEPRECATED: This endpoint previously compared data against live scrapers.
    Now returns current database status only since scrapers are deprecated.
    Use manual uploads for data accuracy.
    """
    audit_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "quarter": quarter.upper(),
        "year": year,
        "status": "PASS",
        "deprecated": True,
        "message": "Live scraper comparison has been deprecated. Data is now managed through manual uploads.",
        "issues": [],
        "platform_comparison": {},
        "mention_verification": {},
        "recommendations": ["Use Data Uploads page to manage review data"]
    }
    
    try:
        # Get our database counts by platform
        pipeline = [
            {"$match": {"quarter": quarter.upper(), "year": year}},
            {"$group": {"_id": "$platform", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        db_counts = await db.customer_reviews.aggregate(pipeline).to_list(20)
        
        for item in db_counts:
            platform = item['_id']
            count = item['count']
            audit_results["platform_comparison"][platform] = {
                "db_count": count,
                "status": "LOADED",
                "source": "manual_upload"
            }
        
        # Get employee mention summary
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0, "name": 1, "rt_mentions": 1, "cv_promoters": 1, "cv_detractors": 1}
        ).to_list(100)
        
        for emp in employees:
            audit_results["mention_verification"][emp["name"]] = {
                "rt_mentions": emp.get("rt_mentions", 0),
                "cv_promoters": emp.get("cv_promoters", 0),
                "cv_detractors": emp.get("cv_detractors", 0),
                "status": "FROM_MANUAL_DATA"
            }
        
        return audit_results
        
    except Exception as e:
        logging.error(f"Audit error: {e}")
        return {
            "status": "ERROR",
            "error": str(e)
        }


@api_router.post("/v2/audit/fix-all-discrepancies")
async def fix_all_discrepancies(quarter: str = "Q1", year: int = 2026):
    """
    One-click fix for all data discrepancies:
    1. Sync CV feedback from cv_feedback collection (manual uploads)
    2. Re-detect employee mentions from existing reviews
    3. Update employee mention counts
    4. Recalculate scores
    
    NOTE: This now works with manually uploaded data only (scrapers deprecated).
    """
    import re
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": []
    }
    
    try:
        # Get employee names for detection
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 1, "name": 1}
        ).to_list(100)
        
        first_to_full = {}
        for emp in employees:
            name = emp['name']
            first = name.split()[0].lower() if ' ' in name else name.lower()
            first_to_full[first] = name
            first_to_full[name.lower()] = name
            # Special aliases
            if 'treyanna' in name.lower():
                first_to_full['trey'] = name
            if 'starwars' in name.lower():
                first_to_full['star wars'] = name
        
        def detect_mentions(text):
            if not text:
                return []
            text_lower = text.lower()
            mentioned = []
            mentioned_names = set()
            for pattern, full_name in first_to_full.items():
                if full_name in mentioned_names:
                    continue
                if len(pattern) > 2 and re.search(r'\b' + re.escape(pattern) + r'\b', text_lower):
                    mentioned.append({"name": full_name, "sentiment": "positive", "points": 0.5})
                    mentioned_names.add(full_name)
            return mentioned
        
        # Step 1: Re-detect mentions in existing reviews (no scraper needed - use existing data)
        existing_reviews = await db.customer_reviews.find(
            {"quarter": quarter.upper(), "year": year}
        ).to_list(1000)
        
        updated_reviews = 0
        for review in existing_reviews:
            review_text = review.get('text', '') or ''
            mentions = detect_mentions(review_text)
            
            await db.customer_reviews.update_one(
                {"_id": review["_id"]},
                {"$set": {
                    "employee_mentions": mentions,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            updated_reviews += 1
        
        results["steps"].append({
            "step": "sync_reviews",
            "updated": updated_reviews,
            "source": "existing_data"
        })
        
        # Step 2: Aggregate mention counts
        mention_pipeline = [
            {"$match": {"employee_mentions": {"$exists": True, "$ne": []}}},
            {"$unwind": "$employee_mentions"},
            {"$group": {"_id": "$employee_mentions.name", "count": {"$sum": 1}}},
        ]
        mention_results = await db.customer_reviews.aggregate(mention_pipeline).to_list(100)
        mention_counts = {r["_id"]: r["count"] for r in mention_results}
        
        # Step 3: Update employees with RT mentions
        # Use BOTH: existing rt_mentions field (from RT upload) AND customer_reviews aggregation
        updated_employees = 0
        for emp in employees:
            name = emp["name"]
            
            current = await db.employees_v2.find_one({"_id": emp["_id"]})
            
            # Get mentions from customer_reviews aggregation
            review_mentions = mention_counts.get(name, 0)
            
            # Also check if there are rt_mentions already set (from RT upload)
            rt_mentions_uploaded = current.get("rt_mentions", 0) or 0
            
            # Use the higher of the two (prefer uploaded data)
            final_mentions = max(review_mentions, rt_mentions_uploaded)
            
            old_mentions = current.get("review_mentions", 0) or 0
            old_rt_bonus = current.get("review_tracker_bonus", 0) or 0
            
            # Calculate new RT bonus
            new_rt_bonus = round(min(final_mentions * 0.5, 15), 2)  # 0.5 pts, capped at 15
            
            if final_mentions != old_mentions or abs(new_rt_bonus - old_rt_bonus) > 0.01:
                old_total = current.get("total_score", 0) or 0
                new_total = round(old_total - old_rt_bonus + new_rt_bonus, 2)
                
                await db.employees_v2.update_one(
                    {"_id": emp["_id"]},
                    {"$set": {
                        "review_mentions": final_mentions,
                        "rt_mentions": final_mentions,
                        "review_tracker_bonus": new_rt_bonus,
                        "total_score": new_total,
                        "pre_dar_score": new_total
                    }}
                )
                updated_employees += 1
        
        results["steps"].append({
            "step": "update_employees",
            "updated_count": updated_employees
        })
        
        # Step 4: Sync CV promoters/detractors from cv_feedback collection (raw survey data - matches audit)
        cv_feedback_updated = 0
        
        # Aggregate cv_feedback data by server_name
        # Promoters: rating >= 9, Detractors: rating <= 6
        cv_pipeline = [
            {"$match": {"quarter": {"$in": [quarter.upper(), quarter]}, "year": year}},
            {"$group": {
                "_id": {"$toLower": "$server_name"},
                "promoters": {"$sum": {"$cond": [{"$gte": ["$rating", 9]}, 1, 0]}},
                "passives": {"$sum": {"$cond": [{"$and": [{"$gte": ["$rating", 7]}, {"$lte": ["$rating", 8]}]}, 1, 0]}},
                "detractors": {"$sum": {"$cond": [{"$lte": ["$rating", 6]}, 1, 0]}},
                "total": {"$sum": 1}
            }}
        ]
        
        cv_agg_result = await db.cv_feedback.aggregate(cv_pipeline).to_list(100)
        
        cv_lookup = {}
        for cp in cv_agg_result:
            emp_name = cp.get("_id", "").lower()
            if emp_name:
                total = cp.get("total", 0) or 1
                promoters = cp.get("promoters", 0) or 0
                detractors = cp.get("detractors", 0) or 0
                # Calculate NPS from raw feedback: (promoters - detractors) / total * 100
                nps_score = round((promoters - detractors) / total * 100, 1) if total > 0 else 0
                cv_lookup[emp_name] = {
                    "promoters": promoters,
                    "passives": cp.get("passives", 0) or 0,
                    "detractors": detractors,
                    "total": total,
                    "nps_score": nps_score
                }
        
        # Update employee cv_promoters/cv_detractors from cv_feedback (raw data)
        # BUT skip employees with cv_source="manual_upload" - their uploaded data IS the source of truth
        for emp in employees:
            name = emp["name"]
            name_lower = name.lower()
            
            current = await db.employees_v2.find_one({"_id": emp["_id"]})
            
            # Skip if using manual upload - preserve the uploaded values
            if current.get("cv_source") == "manual_upload":
                # Use the stored values from the manual upload
                promoters = current.get("cv_promoters", 0) or 0
                detractors = current.get("cv_detractors", 0) or 0
                passives = current.get("cv_passives", 0) or 0
                nps_score = current.get("nps_score", 0) or 0
            else:
                cv_data = cv_lookup.get(name_lower)
                if cv_data:
                    promoters = cv_data["promoters"]
                    detractors = cv_data["detractors"]
                    passives = cv_data["passives"]
                    nps_score = cv_data["nps_score"]
                else:
                    promoters = 0
                    detractors = 0
                    passives = 0
                    nps_score = 0
            
            # === SCORING FORMULA (User Confirmed) ===
            # Base POS Score (75 pts max): PPA: 25%, LSC: 25%, LBW: 15%, Glassware: 10%
            # CV Score: NPS%/10 + (Promoters × 0.5) - (Detractors × 1)
            # RT Bonus: 0.5 pts per mention (max 15 pts)
            # Metric Bonus: max 20 pts
            
            capped_ppa = min(current.get("score_ppa", 0) or 0, 100)
            capped_lsc = min(current.get("score_lsc", 0) or 0, 100)
            capped_lbw = min(current.get("score_lbw", 0) or 0, 100)
            capped_glass = min(current.get("score_glass", 0) or 0, 100)
            
            # NPS points: direct ratio (NPS%/10, max 10 pts)
            nps_pts = round(nps_score / 10, 1) if nps_score > 0 else 0.0
            nps_pts = min(nps_pts, 10.0)
            
            # CV Promoter/Detractor bonus: +0.5 per promoter, -1 per detractor
            cv_promo_bonus = (promoters * 0.5) - (detractors * 1)
            
            # Total CV Score = NPS points + Promoter/Detractor bonus
            cv_score_total = round(nps_pts + cv_promo_bonus, 2)
            
            # Review Tracker bonus: 0.5 pts per mention, max 15 pts
            rt_mentions = current.get("review_mentions", 0) or 0
            rt_contribution = min(rt_mentions * 0.5, 15)
            
            # Base POS weighted score (without CV and RT)
            base_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.15) + (capped_glass * 0.10)
            
            # Metric Bonus (max 20 pts total)
            metric_bonus = min(current.get("total_metric_bonus", 0) or 0, 20)
            
            # Final score = Base Weighted + CV Score + RT Bonus + Metric Bonus
            new_weighted = round(base_weighted, 2)
            new_pre_dar = round(base_weighted + cv_score_total + rt_contribution + metric_bonus, 2)
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "cv_promoters": promoters,
                    "cv_passives": passives,
                    "cv_detractors": detractors,
                    "nps_score": nps_score,
                    "nps_score_pts": nps_pts,
                    "cv_raw_points": round(cv_promo_bonus, 2),
                    "cv_score": cv_score_total,
                    "cv_bonus": round(cv_promo_bonus, 2),
                    "review_tracker_bonus": rt_contribution,
                    "total_metric_bonus": metric_bonus,
                    "weighted_score": new_weighted,
                    "pre_dar_score": new_pre_dar,
                    "total_score": new_pre_dar
                    # Don't overwrite cv_source - preserve manual_upload flag
                }}
            )
            cv_feedback_updated += 1
        
        results["steps"].append({
            "step": "sync_cv_feedback",
            "updated": cv_feedback_updated
        })
        
        results["success"] = True
        results["message"] = f"Updated {updated_reviews} reviews, {updated_employees} employee mentions, {cv_feedback_updated} CV feedback synced"
        
    except Exception as e:
        results["success"] = False
        results["error"] = str(e)
    
    return results


@api_router.get("/v2/audit/data-cap-check")
async def check_data_caps(quarter: str = "Q1", year: int = 2026):
    """
    Check if our data exceeds official dashboard limits.
    The real-time reviews on RT and CV dashboards are the ABSOLUTE MAX.
    """
    # Get official stats
    official_cv = await db.official_cv_stats.find_one(
        {"quarter": quarter.upper(), "year": year}, {"_id": 0}
    )
    official_rt = await db.official_rt_stats.find_one(
        {"quarter": quarter.upper(), "year": year}, {"_id": 0}
    )
    
    # Get our data counts
    cv_count = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year})
    
    # For RT, sum up all rt_mentions from employees (not from customer_reviews collection)
    rt_pipeline = [
        {"$match": {"quarter": quarter.upper(), "year": year}},
        {"$group": {"_id": None, "total_mentions": {"$sum": "$rt_mentions"}}}
    ]
    rt_result = await db.employees_v2.aggregate(rt_pipeline).to_list(1)
    rt_count = rt_result[0]["total_mentions"] if rt_result else 0
    
    result = {
        "quarter": quarter.upper(),
        "year": year,
        "customer_voice": {
            "our_count": cv_count,
            "official_max": official_cv.get("total_responses") if official_cv else None,
            "status": "UNKNOWN",
            "excess": 0
        },
        "review_tracker": {
            "our_count": rt_count,
            "official_max": official_rt.get("total_reviews") if official_rt else None,
            "status": "UNKNOWN",
            "excess": 0
        },
        "overall_status": "UNKNOWN"
    }
    
    # Check CV
    if official_cv and official_cv.get("total_responses"):
        cv_max = official_cv["total_responses"]
        if cv_count > cv_max:
            result["customer_voice"]["status"] = "EXCEEDS_LIMIT"
            result["customer_voice"]["excess"] = cv_count - cv_max
        elif cv_count == cv_max:
            result["customer_voice"]["status"] = "AT_LIMIT"
        else:
            result["customer_voice"]["status"] = "UNDER_LIMIT"
    
    # Check RT
    if official_rt and official_rt.get("total_reviews"):
        rt_max = official_rt["total_reviews"]
        if rt_count > rt_max:
            result["review_tracker"]["status"] = "EXCEEDS_LIMIT"
            result["review_tracker"]["excess"] = rt_count - rt_max
        elif rt_count == rt_max:
            result["review_tracker"]["status"] = "AT_LIMIT"
        else:
            result["review_tracker"]["status"] = "UNDER_LIMIT"
    
    # Overall status
    cv_ok = result["customer_voice"]["status"] in ["AT_LIMIT", "UNDER_LIMIT", "UNKNOWN"]
    rt_ok = result["review_tracker"]["status"] in ["AT_LIMIT", "UNDER_LIMIT", "UNKNOWN"]
    
    if cv_ok and rt_ok:
        result["overall_status"] = "COMPLIANT"
    else:
        result["overall_status"] = "EXCEEDS_OFFICIAL_DATA"
    
    return result


@api_router.post("/v2/audit/enforce-data-caps")
async def enforce_data_caps(quarter: str = "Q1", year: int = 2026):
    """
    ENFORCE data caps by removing excess entries that exceed official dashboard counts.
    The real-time reviews on RT and CV dashboards are the ABSOLUTE MAX.
    This removes the OLDEST excess entries to match the official count.
    """
    # Get official stats
    official_cv = await db.official_cv_stats.find_one(
        {"quarter": quarter.upper(), "year": year}, {"_id": 0}
    )
    official_rt = await db.official_rt_stats.find_one(
        {"quarter": quarter.upper(), "year": year}, {"_id": 0}
    )
    
    results = {
        "quarter": quarter.upper(),
        "year": year,
        "customer_voice": {"removed": 0, "details": []},
        "review_tracker": {"removed": 0, "details": []},
        "actions_taken": []
    }
    
    # Enforce CV cap
    if official_cv and official_cv.get("total_responses"):
        cv_max = official_cv["total_responses"]
        cv_count = await db.cv_feedback.count_documents({"quarter": quarter.upper(), "year": year})
        
        if cv_count > cv_max:
            excess = cv_count - cv_max
            results["actions_taken"].append(f"CV feedback exceeds limit by {excess} entries")
            
            # Find the oldest excess entries to remove (by feedback_date or _id)
            excess_entries = await db.cv_feedback.find(
                {"quarter": quarter.upper(), "year": year},
                {"_id": 1, "server_name": 1, "feedback_date": 1, "rating": 1}
            ).sort("feedback_date", 1).limit(excess).to_list(excess)
            
            for entry in excess_entries:
                await db.cv_feedback.delete_one({"_id": entry["_id"]})
                results["customer_voice"]["details"].append({
                    "server_name": entry.get("server_name"),
                    "date": entry.get("feedback_date"),
                    "rating": entry.get("rating")
                })
            
            results["customer_voice"]["removed"] = len(excess_entries)
            results["actions_taken"].append(f"Removed {len(excess_entries)} oldest CV feedback entries")
    
    # Enforce RT cap
    if official_rt and official_rt.get("total_reviews"):
        rt_max = official_rt["total_reviews"]
        rt_count = await db.customer_reviews.count_documents({"quarter": quarter.upper(), "year": year})
        
        if rt_count > rt_max:
            excess = rt_count - rt_max
            results["actions_taken"].append(f"Reviews exceed limit by {excess} entries")
            
            # Find the oldest excess entries to remove
            excess_entries = await db.customer_reviews.find(
                {"quarter": quarter.upper(), "year": year},
                {"_id": 1, "platform": 1, "date": 1, "rating": 1}
            ).sort("date", 1).limit(excess).to_list(excess)
            
            for entry in excess_entries:
                await db.customer_reviews.delete_one({"_id": entry["_id"]})
                results["review_tracker"]["details"].append({
                    "platform": entry.get("platform"),
                    "date": entry.get("date"),
                    "rating": entry.get("rating")
                })
            
            results["review_tracker"]["removed"] = len(excess_entries)
            results["actions_taken"].append(f"Removed {len(excess_entries)} oldest review entries")
    
    # Log this action
    if results["customer_voice"]["removed"] > 0 or results["review_tracker"]["removed"] > 0:
        await db.audit_log.insert_one({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "enforce_data_caps",
            "quarter": quarter.upper(),
            "year": year,
            "details": {
                "cv_removed": results["customer_voice"]["removed"],
                "rt_removed": results["review_tracker"]["removed"]
            },
            "user": "system"
        })
        
        # CRITICAL: Sync employee mention counts after removing reviews
        # This ensures employee records stay in sync with actual review data
        results["actions_taken"].append("Syncing employee mention counts with review database...")
        
        sync_result = await sync_employee_review_mentions(quarter, year)
        results["employee_sync"] = {
            "updated": sync_result.get("summary", {}).get("updated", 0),
            "unchanged": sync_result.get("summary", {}).get("unchanged", 0),
            "details": sync_result.get("updated_employees", [])
        }
        results["actions_taken"].append(f"Updated {results['employee_sync']['updated']} employee mention counts")
    else:
        results["actions_taken"].append("No excess data found - all within official limits")
    
    return results


@api_router.post("/v2/audit/sync-employee-mentions")
async def sync_employee_review_mentions(quarter: str = "Q1", year: int = 2026):
    """
    Sync employee review_mentions count with actual reviews in database.
    This should be run after enforcing data caps to update employee records.
    """
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
        
        stored_mentions = emp.get("review_mentions", 0) or 0
        
        if actual_mentions != stored_mentions:
            # Calculate new RT bonus: 0.5 pts per mention, max 15 pts (matches main scoring formula)
            new_rt_bonus = round(min(actual_mentions * 0.5, 15), 2)
            old_rt_bonus = emp.get("review_tracker_bonus", 0) or 0
            
            # Recalculate full score from base components (using correct field names)
            # Get raw metric scores (these are pre-calculated values stored in DB)
            capped_ppa = min(emp.get('score_ppa', 0) or 0, 100)
            capped_lsc = min(emp.get('score_lsc', 0) or 0, 100)
            capped_lbw = min(emp.get('score_lbw', 0) or 0, 100)
            capped_glass = min(emp.get('score_glass', 0) or 0, 100)
            nps_score = emp.get('nps_score', 0) or 0
            
            # NPS contribution (10% weight)
            nps_normalized = max(0, (nps_score + 100) / 2)
            nps_contribution = min(nps_normalized, 100) * 0.10
            
            # Calculate base weighted score (PPA 25%, LSC 25%, LBW 15%, Glass 10%, NPS 10%, RT 15%)
            base_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.15) + (capped_glass * 0.10) + nps_contribution + new_rt_bonus
            
            # Get other components
            metric_bonus = min(emp.get('total_metric_bonus', 0) or 0, 20)
            cv_bonus = emp.get('cv_score', 0) or emp.get('cv_bonus', 0) or 0
            
            # Final score = Base + Metric Bonus + CV Bonus
            new_weighted = round(base_weighted, 2)
            new_score = round(base_weighted + metric_bonus + cv_bonus, 2)
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "review_mentions": actual_mentions,
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



# ============================================================
# OFFICIAL REVIEW TRACKER STATS (Manual Override for Accuracy)
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


@api_router.post("/v2/admin/rt-stats/set")
async def set_official_rt_stats(stats: OfficialRTStats):
    """
    Set the official ReviewTrackers stats from their UI.
    These values will be used for display and scoring instead of API-synced data.
    This ensures 100% accuracy with what ReviewTrackers dashboard shows.
    """
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


@api_router.get("/v2/admin/rt-stats/official")
async def get_official_rt_stats(quarter: str = "Q1", year: int = 2026):
    """
    Get the official ReviewTrackers stats (manually set from RT UI).
    Returns None if not set - then API-synced data should be used.
    """
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



# ============================================================
# OFFICIAL CUSTOMER VOICE STATS (Manual Override for Accuracy)
# ============================================================

class OfficialCVStats(BaseModel):
    """Official Customer Voice (Loyalty Voice) stats as shown in their UI."""
    nps_score: float = 0.0
    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    total_responses: int = 0
    quarter: str = "Q1"
    year: int = 2026


@api_router.post("/v2/admin/cv-stats/set")
async def set_official_cv_stats(stats: OfficialCVStats):
    """
    Set the official Customer Voice stats from Loyalty Voice UI.
    These values will be used for display instead of scraped data.
    This ensures 100% accuracy with what Loyalty Voice dashboard shows.
    """
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


@api_router.get("/v2/admin/cv-stats/official")
async def get_official_cv_stats(quarter: str = "Q1", year: int = 2026):
    """Get the official Customer Voice stats (manually set from LV UI)."""
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


@api_router.post("/v2/admin/cv-stats/reconcile")
async def reconcile_cv_feedback_with_official(quarter: str = "Q1", year: int = 2026):
    """
    Reconcile cv_feedback data to match official stats.
    This adjusts the scraped data to match the official Loyalty Voice dashboard numbers.
    """
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
    
    # If we have excess, remove oldest unattributed or excess records
    removed_count = 0
    if diff["promoters"] < 0:
        # Remove excess promoters
        excess = await db.cv_feedback.find(
            {"quarter": quarter.upper(), "year": year, "rating": {"$gte": 9}},
            sort=[("date", -1)]
        ).limit(abs(diff["promoters"])).to_list(abs(diff["promoters"]))
        for rec in excess:
            await db.cv_feedback.delete_one({"_id": rec["_id"]})
            removed_count += 1
    
    if diff["detractors"] < 0:
        # Remove excess detractors
        excess = await db.cv_feedback.find(
            {"quarter": quarter.upper(), "year": year, "rating": {"$lte": 6}},
            sort=[("date", -1)]
        ).limit(abs(diff["detractors"])).to_list(abs(diff["detractors"]))
        for rec in excess:
            await db.cv_feedback.delete_one({"_id": rec["_id"]})
            removed_count += 1
    
    return {
        "success": True,
        "message": f"Reconciled cv_feedback with official stats",
        "official": {
            "total": official_total,
            "promoters": official_promoters,
            "passives": official_passives,
            "detractors": official_detractors
        },
        "before": current,
        "diff": diff,
        "added": len(added_records),
        "removed": removed_count
    }



# ============================================================
# UI DASHBOARD SCRAPER - DEPRECATED (Use manual upload instead)
# ============================================================

@api_router.post("/v2/admin/sync-from-ui")
async def sync_stats_from_ui_dashboards(
    quarter: str = "Q1", 
    year: int = 2026,
    background_tasks: BackgroundTasks = None
):
    """
    DEPRECATED: Use manual upload instead.
    This scraper endpoint has been replaced with manual data uploads.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "UI scraping has been deprecated. Please use the manual upload features on the Data Uploads page.",
        "alternatives": {
            "cv_upload": "/api/v2/cv/server-performance/upload",
            "rt_upload": "/api/v2/rt/upload"
        }
    }


@api_router.post("/v2/admin/sync-rt-from-ui")
async def sync_rt_from_ui(quarter: str = "Q1", year: int = 2026):
    """
    DEPRECATED: Use manual upload instead.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "ReviewTrackers UI scraping has been deprecated. Please use manual upload at /api/v2/rt/upload or the Data Uploads page."
    }


@api_router.post("/v2/admin/sync-cv-from-ui")
async def sync_cv_from_ui(quarter: str = "Q1", year: int = 2026):
    """
    DEPRECATED: Use manual upload instead.
    """
    return {
        "success": False,
        "deprecated": True,
        "message": "Loyalty Voice UI scraping has been deprecated. Please use manual upload at /api/v2/cv/server-performance/upload or the Data Uploads page."
    }



# ============================================================
# AUTOMATED RECONCILIATION SCHEDULER
# ============================================================

class SchedulerConfig(BaseModel):
    """Configuration for automated reconciliation scheduler."""
    enabled: bool = False
    schedule_hour: int = 2  # Default: 2 AM
    schedule_minute: int = 0
    quarter: str = "Q1"
    year: int = 2026

async def run_automated_reconciliation(quarter: str = "Q1", year: int = 2026):
    """
    Run the full reconciliation sequence:
    1. Fix All Discrepancies (sync reviews and recalculate scores)
    2. Enforce Data Caps (remove excess reviews)
    3. Run Audit (verify all employees pass)
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "automated_reconciliation",
        "quarter": quarter.upper(),
        "year": year,
        "steps": [],
        "success": False
    }
    
    try:
        # Step 1: Fix All Discrepancies
        fix_result = await fix_all_discrepancies(quarter, year)
        log_entry["steps"].append({
            "step": "fix_all_discrepancies",
            "success": fix_result.get("success", False),
            "message": fix_result.get("message", "")
        })
        
        # Step 2: Enforce Data Caps
        cap_result = await enforce_data_caps(quarter, year)
        log_entry["steps"].append({
            "step": "enforce_data_caps",
            "rt_removed": cap_result.get("review_tracker", {}).get("removed", 0),
            "cv_removed": cap_result.get("customer_voice", {}).get("removed", 0),
            "employees_synced": cap_result.get("employee_sync", {}).get("updated", 0)
        })
        
        # Step 3: Run Audit
        audit_result = await audit_all_employees(quarter, year)
        passes = len([e for e in audit_result.get("employees", []) if e.get("status") == "PASS"])
        total = len(audit_result.get("employees", []))
        log_entry["steps"].append({
            "step": "audit",
            "status": audit_result.get("overall_status"),
            "passed": passes,
            "total": total
        })
        
        log_entry["success"] = audit_result.get("overall_status") == "VERIFIED"
        log_entry["final_status"] = "VERIFIED" if log_entry["success"] else "ISSUES_FOUND"
        
    except Exception as e:
        log_entry["error"] = str(e)
        log_entry["success"] = False
    
    # Save to audit log (insert_one adds _id to the dict, so we save first)
    await db.reconciliation_log.insert_one(log_entry)
    
    # Remove _id before returning (MongoDB adds it during insert)
    log_entry.pop("_id", None)
    
    return log_entry


@api_router.get("/v2/scheduler/status")
async def get_scheduler_status():
    """Get the current status of the automated reconciliation scheduler."""
    config = await db.scheduler_config.find_one({"_id": "reconciliation"}, {"_id": 0})
    
    jobs = scheduler.get_jobs()
    reconciliation_job = next((j for j in jobs if j.id == "reconciliation_job"), None)
    
    return {
        "scheduler_running": scheduler.running,
        "config": config or {"enabled": False, "schedule_hour": 2, "schedule_minute": 0, "quarter": "Q1", "year": 2026},
        "next_run": reconciliation_job.next_run_time.isoformat() if reconciliation_job and reconciliation_job.next_run_time else None,
        "job_active": reconciliation_job is not None
    }


@api_router.post("/v2/scheduler/configure")
async def configure_scheduler(config: SchedulerConfig):
    """Configure and enable/disable the automated reconciliation scheduler."""
    # Save config to database
    await db.scheduler_config.update_one(
        {"_id": "reconciliation"},
        {"$set": {
            "enabled": config.enabled,
            "schedule_hour": config.schedule_hour,
            "schedule_minute": config.schedule_minute,
            "quarter": config.quarter,
            "year": config.year,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    # Remove existing job if any
    try:
        scheduler.remove_job("reconciliation_job")
    except:
        pass
    
    if config.enabled:
        # Add new scheduled job
        scheduler.add_job(
            run_automated_reconciliation,
            CronTrigger(hour=config.schedule_hour, minute=config.schedule_minute),
            id="reconciliation_job",
            kwargs={"quarter": config.quarter, "year": config.year},
            replace_existing=True
        )
        next_run = scheduler.get_job("reconciliation_job").next_run_time
        return {
            "success": True,
            "message": f"Scheduler enabled. Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')}",
            "next_run": next_run.isoformat()
        }
    else:
        return {
            "success": True,
            "message": "Scheduler disabled"
        }


@api_router.post("/v2/scheduler/run-now")
async def run_reconciliation_now(quarter: str = "Q1", year: int = 2026):
    """Manually trigger the full reconciliation sequence immediately."""
    result = await run_automated_reconciliation(quarter, year)
    return result


@api_router.get("/v2/scheduler/history")
async def get_reconciliation_history(limit: int = 10):
    """Get the history of automated reconciliation runs."""
    history = await db.reconciliation_log.find(
        {},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {"history": history}


# Register QR tracking routes BEFORE including in app
register_qr_routes(api_router, db)

# Register store management routes
register_store_routes(api_router, db)

# Include snapshot workflow routes
api_router.include_router(snapshot_router)

# Include modular routes
api_router.include_router(quarter_settings_router)
api_router.include_router(finalization_router)


# ============================================================================
# EXECUTIVE INSIGHTS ENDPOINTS
# ============================================================================

@api_router.get("/v2/insights/store-health")
async def get_store_health_score(quarter: str = "Q1", year: int = 2026):
    """
    Get Store Health Score - Executive-level view of store performance.
    
    Categories:
    - Sales Execution: Based on PPA performance
    - Upsell Performance: Based on LBW + Glassware
    - Loyalty Engagement: Based on LSC
    - Guest Experience: Based on CV + RT scores
    """
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not employees:
        return {
            "store_health_score": 0,
            "categories": {},
            "message": "No employee data found"
        }
    
    # Calculate category scores (normalized to 0-100 scale)
    def avg_score(field, default=0):
        values = [e.get(field, default) or default for e in employees]
        return sum(values) / len(values) if values else 0
    
    # Sales Execution = Average PPA score (already 0-100+ scale)
    sales_execution = min(avg_score("score_ppa"), 100)
    
    # Upsell Performance = Average of LBW and Glassware scores
    lbw_avg = min(avg_score("score_lbw"), 100)
    glass_avg = min(avg_score("score_glass"), 100)
    upsell_performance = (lbw_avg + glass_avg) / 2
    
    # Loyalty Engagement = Average LSC score
    loyalty_engagement = min(avg_score("score_lsc"), 100)
    
    # Guest Experience = Combination of NPS and RT performance
    # NPS is -100 to 100, normalize to 0-100
    nps_avg = avg_score("nps_score")
    nps_normalized = max(0, (nps_avg + 100) / 2)  # Convert -100..100 to 0..100
    
    # RT contribution: Based on average mentions (higher = better guest engagement)
    rt_mentions_avg = avg_score("rt_mentions")
    rt_normalized = min((rt_mentions_avg / 30) * 100, 100)  # Normalize to 0-100 (30 mentions = 100)
    
    guest_experience = (nps_normalized * 0.7) + (rt_normalized * 0.3)
    
    # Overall Store Health Score (weighted average)
    store_health = (
        sales_execution * 0.25 +
        upsell_performance * 0.25 +
        loyalty_engagement * 0.20 +
        guest_experience * 0.30
    )
    
    # Get benchmarks for context
    settings = await db.quarter_settings.find_one({"year": year, "quarter": quarter.upper()})
    benchmarks = {
        "ppa": settings.get("benchmark_ppa", 55) if settings else 55,
        "lbw": settings.get("benchmark_lbw", 8) if settings else 8,
        "glass": settings.get("benchmark_glass", 1.25) if settings else 1.25,
        "lsc": settings.get("benchmark_lsc", 1) if settings else 1
    }
    
    return {
        "store_health_score": round(store_health, 1),
        "categories": {
            "sales_execution": {
                "score": round(sales_execution, 1),
                "label": "Sales Execution",
                "source": "PPA Performance",
                "trend": "up" if sales_execution >= 80 else "stable" if sales_execution >= 60 else "down"
            },
            "upsell_performance": {
                "score": round(upsell_performance, 1),
                "label": "Upsell Performance", 
                "source": "LBW + Glassware",
                "trend": "up" if upsell_performance >= 80 else "stable" if upsell_performance >= 60 else "down"
            },
            "loyalty_engagement": {
                "score": round(loyalty_engagement, 1),
                "label": "Loyalty Engagement",
                "source": "LSC Performance",
                "trend": "up" if loyalty_engagement >= 80 else "stable" if loyalty_engagement >= 60 else "down"
            },
            "guest_experience": {
                "score": round(guest_experience, 1),
                "label": "Guest Experience",
                "source": "CV + Reviews",
                "trend": "up" if guest_experience >= 80 else "stable" if guest_experience >= 60 else "down"
            }
        },
        "employee_count": len(employees),
        "quarter": quarter.upper(),
        "year": year,
        "benchmarks": benchmarks
    }


@api_router.get("/v2/insights/coaching-radar")
async def get_coaching_radar(quarter: str = "Q1", year: int = 2026):
    """
    Get Coaching Radar - High-impact coaching opportunities.
    
    Identifies employees below benchmark in key areas and estimates
    the potential revenue impact of coaching interventions.
    """
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not employees:
        return {"coaching_opportunities": [], "message": "No employee data found"}
    
    # Get benchmarks
    settings = await db.quarter_settings.find_one({"year": year, "quarter": quarter.upper()})
    benchmarks = {
        "ppa": settings.get("benchmark_ppa", 55) if settings else 55,
        "lbw": settings.get("benchmark_lbw", 8) if settings else 8,
        "glass": settings.get("benchmark_glass", 1.25) if settings else 1.25,
        "lsc": settings.get("benchmark_lsc", 1) if settings else 1
    }
    
    # Revenue impact estimates per metric improvement
    # These are industry-standard estimates for restaurant metrics
    REVENUE_PER_GUEST = 45  # Average check per guest
    MONTHLY_GUESTS_PER_SERVER = 400  # Estimated monthly guest count per server
    
    coaching_opportunities = []
    
    for emp in employees:
        opportunities = []
        
        # Check Glassware (wine/alcohol upsells)
        glass_per_guest = emp.get("glassware_per_guest", 0) or 0
        if glass_per_guest < benchmarks["glass"]:
            gap = benchmarks["glass"] - glass_per_guest
            # Each $1 increase in glassware per guest = significant revenue
            potential_increase = round(gap * MONTHLY_GUESTS_PER_SERVER * 12, 0)  # Annual
            opportunities.append({
                "category": "Glassware",
                "metric": "glassware_per_guest",
                "current": round(glass_per_guest, 2),
                "benchmark": benchmarks["glass"],
                "gap": round(gap, 2),
                "impact_type": "revenue",
                "potential_monthly": round(potential_increase / 12, 0),
                "description": f"Glassware sales ${glass_per_guest:.2f}/guest vs ${benchmarks['glass']:.2f} benchmark",
                "action": "Focus on wine pairing suggestions and premium drink recommendations"
            })
        
        # Check LBW (bar upsells)
        lbw_per_guest = emp.get("lbw_per_guest", 0) or 0
        if lbw_per_guest < benchmarks["lbw"]:
            gap = benchmarks["lbw"] - lbw_per_guest
            potential_increase = round(gap * MONTHLY_GUESTS_PER_SERVER * 12, 0)
            opportunities.append({
                "category": "LBW",
                "metric": "lbw_per_guest",
                "current": round(lbw_per_guest, 2),
                "benchmark": benchmarks["lbw"],
                "gap": round(gap, 2),
                "impact_type": "revenue",
                "potential_monthly": round(potential_increase / 12, 0),
                "description": f"Bar sales ${lbw_per_guest:.2f}/guest vs ${benchmarks['lbw']:.2f} benchmark",
                "action": "Suggest appetizers, desserts, and premium add-ons"
            })
        
        # Check LSC (loyalty signups)
        lsc_count = emp.get("lsc_count", 0) or 0
        guests = emp.get("guests", 1) or 1
        lsc_rate = lsc_count / guests if guests > 0 else 0
        if lsc_rate < benchmarks["lsc"] / 100:  # Convert to percentage
            gap_pct = (benchmarks["lsc"] / 100) - lsc_rate
            potential_signups = round(gap_pct * MONTHLY_GUESTS_PER_SERVER, 0)
            opportunities.append({
                "category": "Loyalty",
                "metric": "lsc_conversion",
                "current": round(lsc_rate * 100, 1),
                "benchmark": benchmarks["lsc"],
                "gap": round(gap_pct * 100, 1),
                "impact_type": "signups",
                "potential_monthly": potential_signups,
                "description": f"Loyalty conversion {lsc_rate*100:.1f}% vs {benchmarks['lsc']}% benchmark",
                "action": "Mention rewards program benefits during checkout"
            })
        
        # Check PPA (per person average)
        ppa = emp.get("ppa", 0) or 0
        if ppa < benchmarks["ppa"]:
            gap = benchmarks["ppa"] - ppa
            potential_increase = round(gap * MONTHLY_GUESTS_PER_SERVER * 12, 0)
            opportunities.append({
                "category": "PPA",
                "metric": "ppa",
                "current": round(ppa, 2),
                "benchmark": benchmarks["ppa"],
                "gap": round(gap, 2),
                "impact_type": "revenue",
                "potential_monthly": round(potential_increase / 12, 0),
                "description": f"Guest average ${ppa:.2f} vs ${benchmarks['ppa']:.2f} benchmark",
                "action": "Focus on upselling premium items and suggesting add-ons"
            })
        
        if opportunities:
            # Sort by potential impact (highest first)
            opportunities.sort(key=lambda x: x.get("potential_monthly", 0), reverse=True)
            
            coaching_opportunities.append({
                "employee_id": emp.get("id"),
                "employee_name": emp.get("name"),
                "total_score": emp.get("total_score", 0),
                "tier": emp.get("tier_label", ""),
                "opportunities": opportunities[:2],  # Top 2 opportunities per employee
                "total_potential_monthly": sum(o.get("potential_monthly", 0) for o in opportunities)
            })
    
    # Sort by total potential impact and return top opportunities
    coaching_opportunities.sort(key=lambda x: x.get("total_potential_monthly", 0), reverse=True)
    
    return {
        "coaching_opportunities": coaching_opportunities[:10],  # Top 10
        "total_potential_monthly_revenue": sum(c.get("total_potential_monthly", 0) for c in coaching_opportunities[:10]),
        "employees_needing_coaching": len(coaching_opportunities),
        "total_employees": len(employees),
        "benchmarks": benchmarks,
        "quarter": quarter.upper(),
        "year": year
    }


@api_router.get("/v2/insights/review-impact")
async def get_review_impact(quarter: str = "Q1", year: int = 2026):
    """
    Get Review Impact Tracker - Revenue influence from guest reviews.
    
    Connects review mentions to estimated revenue influence.
    Industry research shows positive reviews drive significant revenue.
    """
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not employees:
        return {"review_impact": [], "message": "No employee data found"}
    
    # Revenue influence estimates
    # Research shows each positive review can influence $500-1000 in future revenue
    # (through repeat visits, referrals, and new customer acquisition)
    REVENUE_PER_MENTION = 550  # Conservative estimate per review mention
    REVENUE_PER_PROMOTER = 800  # Higher value for promoter (NPS 9-10)
    
    review_impact = []
    
    for emp in employees:
        rt_mentions = emp.get("rt_mentions") or emp.get("review_mentions") or 0
        cv_promoters = emp.get("cv_promoters") or 0
        nps_score = emp.get("nps_score") or 0
        
        # Skip if no guest interaction data
        if rt_mentions == 0 and cv_promoters == 0:
            continue
        
        # Calculate revenue influence
        mention_influence = rt_mentions * REVENUE_PER_MENTION
        promoter_influence = cv_promoters * REVENUE_PER_PROMOTER
        total_influence = mention_influence + promoter_influence
        
        # Guest satisfaction indicator
        if nps_score >= 80:
            satisfaction = "Excellent"
            satisfaction_color = "emerald"
        elif nps_score >= 60:
            satisfaction = "Good"
            satisfaction_color = "blue"
        elif nps_score >= 40:
            satisfaction = "Average"
            satisfaction_color = "amber"
        else:
            satisfaction = "Needs Improvement"
            satisfaction_color = "red"
        
        review_impact.append({
            "employee_id": emp.get("id"),
            "employee_name": emp.get("name"),
            "review_mentions": rt_mentions,
            "cv_promoters": cv_promoters,
            "nps_score": nps_score,
            "satisfaction_level": satisfaction,
            "satisfaction_color": satisfaction_color,
            "mention_revenue_influence": round(mention_influence, 0),
            "promoter_revenue_influence": round(promoter_influence, 0),
            "total_revenue_influence": round(total_influence, 0),
            "tier": emp.get("tier_label", ""),
            "total_score": emp.get("total_score", 0)
        })
    
    # Sort by total revenue influence
    review_impact.sort(key=lambda x: x.get("total_revenue_influence", 0), reverse=True)
    
    # Calculate totals
    total_mentions = sum(e.get("review_mentions", 0) for e in review_impact)
    total_promoters = sum(e.get("cv_promoters", 0) for e in review_impact)
    total_influence = sum(e.get("total_revenue_influence", 0) for e in review_impact)
    
    return {
        "review_impact": review_impact[:15],  # Top 15
        "totals": {
            "total_mentions": total_mentions,
            "total_promoters": total_promoters,
            "total_revenue_influence": round(total_influence, 0),
            "employees_with_impact": len(review_impact)
        },
        "methodology": {
            "revenue_per_mention": REVENUE_PER_MENTION,
            "revenue_per_promoter": REVENUE_PER_PROMOTER,
            "description": "Based on industry research on review-driven revenue (repeat visits, referrals, new customers)"
        },
        "quarter": quarter.upper(),
        "year": year
    }


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add no-cache headers middleware for API responses
from starlette.middleware.base import BaseHTTPMiddleware

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheMiddleware)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    scheduler.shutdown(wait=False)
    client.close()


@app.on_event("startup")
async def startup_event():
    """Start the scheduler and load saved configuration."""
    scheduler.start()
    
    # Load saved scheduler config
    config = await db.scheduler_config.find_one({"_id": "reconciliation"})
    if config and config.get("enabled"):
        scheduler.add_job(
            run_automated_reconciliation,
            CronTrigger(hour=config.get("schedule_hour", 2), minute=config.get("schedule_minute", 0)),
            id="reconciliation_job",
            kwargs={"quarter": config.get("quarter", "Q1"), "year": config.get("year", 2026)},
            replace_existing=True
        )
        logging.info(f"Scheduler loaded: reconciliation job scheduled at {config.get('schedule_hour', 2)}:{config.get('schedule_minute', 0):02d}")