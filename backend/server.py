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
from routes.yodeck_slides import yodeck_router
from routes.employees import employee_router
from routes.trends import trends_router
from routes.upload_jobs import upload_jobs_router
from routes.stores import stores_router
from routes.audit import audit_router
from routes.cv import cv_router
from routes.admin import admin_router
from routes.reviews import reviews_router
from routes.insights import insights_router
from routes.pos_upload import pos_upload_router, pdf_jobs
from routes.scheduler import scheduler_router
from routes.snapshots_legacy import register_snapshots_legacy_routes
from routes.auth import auth_router

# pdf_jobs is now imported from pos_upload module
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


# Legacy snapshots helper functions and routes moved to /app/backend/routes/snapshots_legacy.py


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
        # Recalculate derived metrics from raw data if available
        guests = emp.get('guest_count', 0) or emp.get('guests', 0) or 0
        net_sales = emp.get('net_sales', 0) or 0
        lbw_total = emp.get('lbw_total', 0) or emp.get('lbw', 0) or 0
        if lbw_total == 0:
            lbw_total = (emp.get('liquor_sales', 0) or 0) + (emp.get('beer_sales', 0) or 0) + (emp.get('wine_sales', 0) or 0)
        glassware = emp.get('bar_glassware_sales', 0) or emp.get('glassware_sales', 0) or 0
        lsc_count = emp.get('lsc_count', 0) or 0
        if lsc_count == 0 and emp.get('loyalty_sales'):
            lsc_count = int((emp.get('loyalty_sales', 0) or 0) / 25)

        # Recalculate per-guest metrics from raw data
        derived_updates = {}
        if guests > 0:
            new_ppa = round(net_sales / guests, 2) if net_sales > 0 else emp.get('ppa', 0) or 0
            new_lbw_pg = round(lbw_total / guests, 2) if lbw_total > 0 else emp.get('lbw_per_guest', 0) or 0
            new_glass_pg = round(glassware / guests, 2) if glassware > 0 else emp.get('glassware_per_guest', 0) or 0
            new_gplsc = round(guests / lsc_count, 2) if lsc_count > 0 else emp.get('guests_per_lsc', 0) or 0

            if new_ppa > 0 and abs(new_ppa - (emp.get('ppa', 0) or 0)) > 0.01:
                derived_updates['ppa'] = new_ppa
            if new_lbw_pg > 0 and abs(new_lbw_pg - (emp.get('lbw_per_guest', 0) or 0)) > 0.01:
                derived_updates['lbw_per_guest'] = new_lbw_pg
            if new_glass_pg > 0 and abs(new_glass_pg - (emp.get('glassware_per_guest', 0) or 0)) > 0.01:
                derived_updates['glassware_per_guest'] = new_glass_pg
            if new_gplsc > 0 and abs(new_gplsc - (emp.get('guests_per_lsc', 0) or 0)) > 0.01:
                derived_updates['guests_per_lsc'] = new_gplsc

            # Recalculate score fields from derived metrics
            settings_doc = await db.quarter_settings.find_one(
                {"year": year, "quarter": quarter.upper()}, {"_id": 0}
            )
            if settings_doc:
                bm_ppa = settings_doc.get('benchmark_ppa', 55) or 55
                bm_lbw = settings_doc.get('benchmark_lbw', 8) or 8
                bm_glass = settings_doc.get('benchmark_glass', 1.35) or 1.35
                bm_lsc = settings_doc.get('benchmark_lsc', 100) or 100
                ppa_val = new_ppa if 'ppa' in derived_updates else (emp.get('ppa', 0) or 0)
                lbw_val = new_lbw_pg if 'lbw_per_guest' in derived_updates else (emp.get('lbw_per_guest', 0) or 0)
                glass_val = new_glass_pg if 'glassware_per_guest' in derived_updates else (emp.get('glassware_per_guest', 0) or 0)
                gplsc_val = new_gplsc if 'guests_per_lsc' in derived_updates else (emp.get('guests_per_lsc', 0) or 0)
                
                new_score_ppa = round((ppa_val / bm_ppa) * 100, 2) if bm_ppa > 0 and ppa_val > 0 else emp.get('score_ppa', 0) or 0
                new_score_lbw = round((lbw_val / bm_lbw) * 100, 2) if bm_lbw > 0 and lbw_val > 0 else emp.get('score_lbw', 0) or 0
                new_score_glass = round((glass_val / bm_glass) * 100, 2) if bm_glass > 0 and glass_val > 0 else emp.get('score_glass', 0) or 0
                new_score_lsc = round((bm_lsc / gplsc_val) * 100, 2) if gplsc_val > 0 else emp.get('score_lsc', 0) or 0
                
                if new_score_ppa > 0:
                    derived_updates['score_ppa'] = new_score_ppa
                if new_score_lbw > 0:
                    derived_updates['score_lbw'] = new_score_lbw
                if new_score_glass > 0:
                    derived_updates['score_glass'] = new_score_glass
                if new_score_lsc > 0:
                    derived_updates['score_lsc'] = new_score_lsc

            # Apply derived updates to emp dict for subsequent score calc
            for k, v in derived_updates.items():
                emp[k] = v

        # Get raw scores (possibly updated above)
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
        rt_bonus = min(rt_mentions * 0.3, 20)
        
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
            abs(rt_bonus - old_rt_bonus) > 0.01 or
            len(derived_updates) > 0
        )
        
        if needs_update:
            update_set = {
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
            }
            update_set.update(derived_updates)
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": update_set}
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

# NOTE: Quarter Settings endpoints moved to /app/backend/routes/quarter_settings.py
# NOTE: Finalization/DAR endpoints moved to /app/backend/routes/finalization.py
# NOTE: Yodeck Slide endpoints moved to /app/backend/routes/yodeck_slides.py
# NOTE: Trends endpoints moved to /app/backend/routes/trends.py

# === DAR (Disciplinary Action Reports) Management ===

class DARUpdate(BaseModel):
    written_warnings: int = 0
    suspensions: int = 0


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



# POS OCR/PDF routes moved to /app/backend/routes/pos_upload.py

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
            
            guests = emp_data.get('guests', 0) or emp_data.get('total_guests', 0) or emp_data.get('guest_count', 0) or 0
            net_sales = emp_data.get('net_sales', 0) or emp_data.get('totals', 0) or 0
            
            # Extract individual LBW components
            liquor = emp_data.get('liquor', 0) or emp_data.get('liquor_sales', 0) or 0
            beer = emp_data.get('beer', 0) or emp_data.get('beer_sales', 0) or 0
            wine = emp_data.get('wine', 0) or emp_data.get('wine_sales', 0) or 0
            lbw = emp_data.get('lbw', 0) or 0
            
            # Always recalculate LBW from components if we have them
            if liquor > 0 or beer > 0 or wine > 0:
                lbw = liquor + beer + wine
            
            glassware = emp_data.get('glassware', 0) or emp_data.get('glassware_sales', 0) or emp_data.get('bar_glassware', 0) or emp_data.get('bar_glassware_sales', 0) or 0
            loyalty = emp_data.get('loyalty', 0) or emp_data.get('loyalty_sales', 0) or 0
            lsc_count = emp_data.get('lsc_count', 0) or 0
            
            # If lsc from loyalty sales
            if lsc_count == 0 and loyalty > 0:
                lsc_count = int(loyalty / 25)
            
            # Calculate derived metrics
            ppa = net_sales / guests if guests > 0 else 0
            lbw_per_guest = lbw / guests if guests > 0 else 0
            glassware_per_guest = glassware / guests if guests > 0 else 0
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
                rt_contribution = min(rt_mentions * 0.3, 20)
                total_metric_bonus = match.get("total_metric_bonus", 0) or 0
                
                # Recalculate weighted with RT
                weighted_with_rt = weighted_score + rt_contribution
                total_score = weighted_with_rt + cv_score + total_metric_bonus
                
                update_fields = {
                    "report_name": name,  # Update report_name to latest from POS
                    "guests": guests,
                    "guest_count": guests,
                    "net_sales": round(net_sales, 2),
                    "liquor_sales": round(liquor, 2),
                    "beer_sales": round(beer, 2),
                    "wine_sales": round(wine, 2),
                    "lbw": round(lbw, 2),
                    "lbw_total": round(lbw, 2),
                    "glassware_sales": round(glassware, 2),
                    "bar_glassware_sales": round(glassware, 2),
                    "loyalty_sales": round(loyalty, 2),
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
                    "guest_count": guests,
                    "net_sales": round(net_sales, 2),
                    "liquor_sales": round(liquor, 2),
                    "beer_sales": round(beer, 2),
                    "wine_sales": round(wine, 2),
                    "lbw": round(lbw, 2),
                    "lbw_total": round(lbw, 2),
                    "glassware_sales": round(glassware, 2),
                    "bar_glassware_sales": round(glassware, 2),
                    "loyalty_sales": round(loyalty, 2),
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
            "message": "POS data uploaded successfully",
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
    """
    List employees. Phase-2 wired through `EmployeeService` — reads from
    the canonical `employees` collection. Falls back to legacy
    `employees_v2` when canonical has no rows for the requested quarter
    (safety net while Phase-1 migration soaks in).

    Response shape is unchanged (flat list, legacy-compatible) so the
    Employees tab, slide generators, and audit page keep working.
    """
    from services.employee_service import EmployeeService
    svc = EmployeeService(db)

    actives = await svc.list_active(quarter=quarter, year=year)
    used_canonical = bool(actives)

    if not used_canonical:
        # Canonical empty for this quarter — fall back to legacy.
        legacy_query: Dict[str, Any] = {}
        if year:
            legacy_query["year"] = year
        if quarter:
            legacy_query["quarter"] = quarter.upper()
        actives = await db.employees_v2.find(legacy_query, {"_id": 0}).to_list(5000)
        if used_canonical is False:
            logging.warning(
                "GET /v2/employees: canonical empty for %s %s — fallback to legacy_v2 (%d rows)",
                quarter, year, len(actives),
            )

    # Flatten canonical shape to the legacy projection the frontend expects.
    flat: List[Dict[str, Any]] = []
    for emp in actives:
        cm = emp.get("current_metrics") or {}
        merged = {k: v for k, v in emp.items() if k != "current_metrics"}
        merged.update(cm)
        flat.append(merged)

    employees_sorted = sorted(
        flat,
        key=lambda x: x.get("pre_dar_score") or x.get("total_score") or 0,
        reverse=True,
    )
    total = len(employees_sorted)

    for i, emp in enumerate(employees_sorted):
        if isinstance(emp.get("created_at"), str):
            try:
                emp["created_at"] = datetime.fromisoformat(emp["created_at"])
            except ValueError:
                pass

        # Always surface display_name as name (First-Name-Only policy).
        if emp.get("display_name") and emp.get("display_name") != emp.get("name"):
            emp["name"] = emp["display_name"]

        # Backfill performance_tier if missing (legacy parity).
        if not emp.get("performance_tier"):
            rank = i + 1
            percentile = ((total - rank) / total) * 100 if total > 0 else 0
            if percentile >= 75:
                emp["performance_tier"] = "Top Performer"
            elif percentile >= 50:
                emp["performance_tier"] = "Above Average"
            elif percentile >= 25:
                emp["performance_tier"] = "Below Average"
            else:
                emp["performance_tier"] = "Needs Immediate Improvement"

    return employees_sorted


@api_router.get("/v2/employees/{employee_id}")
async def get_employee_v2(employee_id: str):
    """
    Get a single employee by id. Phase-2 wired through EmployeeService.
    Accepts both the canonical id and legacy_ids (so old frontend links
    keep resolving after migration).
    """
    from services.employee_service import EmployeeService
    svc = EmployeeService(db)

    emp = await svc.get_by_id(employee_id)
    if not emp:
        emp = await svc.col.find_one({"legacy_ids": employee_id}, {"_id": 0})
    if not emp:
        # Last-resort legacy fallback.
        legacy = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
        if not legacy:
            raise HTTPException(status_code=404, detail="Employee not found")
        if isinstance(legacy.get("created_at"), str):
            try:
                legacy["created_at"] = datetime.fromisoformat(legacy["created_at"])
            except ValueError:
                pass
        if legacy.get("display_name") and legacy["display_name"] != legacy.get("name"):
            legacy["name"] = legacy["display_name"]
        return legacy

    cm = emp.get("current_metrics") or {}
    flat = {k: v for k, v in emp.items() if k != "current_metrics"}
    flat.update(cm)
    if isinstance(flat.get("created_at"), str):
        try:
            flat["created_at"] = datetime.fromisoformat(flat["created_at"])
        except ValueError:
            pass
    if flat.get("display_name") and flat["display_name"] != flat.get("name"):
        flat["name"] = flat["display_name"]
    return flat


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


async def _load_snapshot_first_rankings(
    year: int,
    quarter: str,
) -> tuple[List[dict], "QuarterSettings"]:
    """
    Resolve the row set that the snapshot-PNG/PDF generators should
    render. Reads from the active snapshot's embedded `employees[]`
    first (the architectural source of truth post Phase-2B) and falls
    back to `employees_v2` only when no current snapshot exists.

    Returns (rankings, settings).
    Raises HTTPException(404) if no data exists for the quarter.
    """
    from services.employee_service import EmployeeService

    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()}, {"_id": 0}
    ) or {}
    settings = QuarterSettings(
        year=year, quarter=quarter.upper(),
        benchmark_ppa=settings_doc.get("benchmark_ppa", 55.0),
        benchmark_lbw=settings_doc.get("benchmark_lbw", 8.0),
        benchmark_glass=settings_doc.get("benchmark_glass", 1.0),
        benchmark_lsc=settings_doc.get("benchmark_lsc", 100.0),
        benchmark_cv=settings_doc.get("benchmark_cv", 5.0),
        weight_ppa=settings_doc.get("weight_ppa", 0.25),
        weight_lbw=settings_doc.get("weight_lbw", 0.20),
        weight_glass=settings_doc.get("weight_glass", 0.15),
        weight_lsc=settings_doc.get("weight_lsc", 0.25),
        weight_cv=settings_doc.get("weight_cv", 0.15),
        bonus_rate=settings_doc.get("bonus_rate", 0.2),
        bonus_cap=settings_doc.get("bonus_cap", 5.0),
        a_server_min_score=settings_doc.get("a_server_min_score", 85.0),
        b_server_min_score=settings_doc.get("b_server_min_score", 70.0),
        rt_points_per_mention=settings_doc.get("rt_points_per_mention", 0.3),
        rt_max_points=settings_doc.get("rt_max_points", 20.0),
    )

    # Snapshot-first: active snapshot is the source of truth.
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "year": year, "quarter": quarter.upper()},
        {"_id": 0},
    )
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "year": year, "quarter": quarter.upper()},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)],
        )

    if snapshot and snapshot.get("employees"):
        raw_rows = snapshot.get("employees") or []
        deleted_names = snapshot.get("deleted_names") or []
    else:
        # Defense in depth — fall back to the legacy mirror.
        raw_rows = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0},
        ).to_list(500)
        deleted_names = []

    if not raw_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No employees found for {quarter} {year}",
        )

    # Phase 2B: filter terminated/merged employees out through canonical.
    raw_rows = await EmployeeService(db).filter_active_only(
        raw_rows, snapshot_deleted_names=deleted_names,
    )

    # Recompute the three drift-prone derived fields on every row from
    # their current inputs so manual overrides on the snapshot always win
    # over stale stored scores (matches `/current-rankings` behavior).
    _rt_coef = settings.rt_points_per_mention or 0.3
    _rt_cap = settings.rt_max_points or 20.0
    for r in raw_rows:
        # RT bonus
        _m = r.get("rt_mentions") or r.get("review_mentions") or 0
        r["review_tracker_bonus"] = round(min(_m * _rt_coef, _rt_cap), 2)
        r["review_mentions"] = _m
        r["rt_mentions"] = _m
        # CV score — skip if manual override pinned this row.
        if not r.get("nps_manual_override"):
            try:
                _nps_c = max(0.0, min(float(r.get("nps_score") or 0), 100.0))
            except (TypeError, ValueError):
                _nps_c = 0.0
            _p = r.get("cv_promoters") or 0
            _d = r.get("cv_detractors") or 0
            r["nps_contribution"] = round(_nps_c / 10.0, 2)
            r["cv_raw_points"] = round(_p - 2 * _d, 2)
            r["cv_score"] = round(r["nps_contribution"] + r["cv_raw_points"], 2)
        # Metric bonus aggregate
        r["total_metric_bonus"] = round(
            (r.get("bonus_ppa") or 0)
            + (r.get("bonus_lbw") or 0)
            + (r.get("bonus_glass") or 0)
            + (r.get("bonus_lsc") or 0),
            2,
        )

    # Convert to EmployeeV2 (parser uses alt names — normalize first).
    employees: List[EmployeeV2] = []
    for emp_data in raw_rows:
        if not emp_data.get("glassware_sales") and emp_data.get("bar_glassware_sales"):
            emp_data["glassware_sales"] = emp_data["bar_glassware_sales"]
        if "guest_count" in emp_data and "guests" not in emp_data:
            emp_data["guests"] = emp_data["guest_count"]
        try:
            employees.append(EmployeeV2(**emp_data))
        except Exception:
            continue

    rankings = generate_hierarchy_rankings(employees, settings)

    # generate_hierarchy_rankings recalculates cv_score / metric_bonus
    # internally from raw inputs — re-overlay the snapshot's authoritative
    # values (incl. manual overrides) on top so the slide reflects the
    # exact numbers the dashboard / current-rankings page shows.
    raw_by_name = {(r.get("name") or "").lower(): r for r in raw_rows}
    for rank in rankings:
        src = raw_by_name.get((rank.get("name") or "").lower()) or {}
        if src.get("nps_manual_override"):
            rank["cv_score"] = src.get("cv_score", rank.get("cv_score"))
            rank["nps_score"] = src.get("nps_score", rank.get("nps_score"))
        # RT bonus and metric bonus are derived from clean inputs in both
        # paths — but copy the override flag through for slide consumers.
        if src.get("nps_manual_override"):
            rank["nps_manual_override"] = True

    return rankings, settings


@api_router.get("/v2/full-rankings/{year}/{quarter}/snapshot-png")
async def download_full_rankings_snapshot_png(year: int, quarter: str):
    """
    Download the detailed Server Performance Snapshot as a 1920×1080 PNG.

    Reads snapshot-first (matches `/current-rankings`) so manual overrides
    on the active snapshot always render correctly, with `employees_v2`
    only used as a defense-in-depth fallback when no snapshot exists.
    """
    from png_full_rankings import build_full_rankings_png

    rankings, settings = await _load_snapshot_first_rankings(year, quarter)

    png_bytes = build_full_rankings_png(
        rankings=rankings,
        quarter=quarter.upper(),
        year=year,
        thresholds={
            "a_min": settings.a_server_min_score,
            "b_min": settings.b_server_min_score,
        },
    )

    filename = f"Server_Performance_Snapshot_{quarter.upper()}_{year}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/full-rankings/{year}/{quarter}/snapshot-pdf")
async def download_full_rankings_snapshot_pdf(year: int, quarter: str):
    """
    Download the detailed Server Performance Snapshot PDF — wide-format
    document with the Bubba Gump sidebar, color-coded legend, and the
    full Rank/Name/Trend/PPA/LBW/GLASS/LSC/CV/RT/Bonus/Score table.

    Reads snapshot-first (matches `/current-rankings`) so manual overrides
    on the active snapshot always render correctly. `employees_v2` is
    only used as a fallback when no snapshot exists.
    """
    rankings, settings = await _load_snapshot_first_rankings(year, quarter)

    pdf_bytes = build_full_rankings_pdf(
        rankings=rankings,
        quarter=quarter.upper(),
        year=year,
        thresholds={
            "a_min": settings.a_server_min_score,
            "b_min": settings.b_server_min_score,
        },
    )

    filename = f"Server_Performance_Snapshot_{quarter.upper()}_{year}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/full-rankings/{year}/{quarter}/pdf")
async def download_full_rankings_pdf(year: int, quarter: str):
    """
    Download Full Rankings as a PNG slide matching the Snapshot aesthetic.
    
    Uses the snapshot_slides.py generator for the exact dark navy design with:
    - Bubba Gump logo and left sidebar
    - Color-coded performance cells (blue/green/yellow/red)
    - Metrics as percentages with visual indicators
    """
    
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
            "rt_bonus": emp.get("review_tracker_bonus", 0) or min((emp.get("rt_mentions", 0) or 0) * 0.3, 20),
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



# Yodeck slide routes moved to /app/backend/routes/yodeck_slides.py


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
        EmployeeV2
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
async def update_employee(employee_id: str, data: dict):
    """
    Update an existing employee. Accepts any fields and persists them directly.
    Recalculates scores if POS data fields are provided.
    """
    # Get existing employee - try by ID, then snapshot fallback searching name/report_name/display_name.
    # Final fallback: if a snapshot embedded record exists but no v2 record matches it
    # (orphan snapshot row from a previous partial save), CREATE a v2 record from the snap data
    # so the user's edit always succeeds — instead of 404'ing.
    import re as re_mod
    emp_doc = await db.employees_v2.find_one({"id": employee_id})
    snapshot_ctx = None  # Remember matched snapshot for precise sync later
    snap_emp_clone = None  # Used when we need to create a v2 record from snapshot data
    if not emp_doc:
        snapshot_ctx = await db.snapshot_workflow.find_one(
            {"employees.id": employee_id},
            {"employees.$": 1, "quarter": 1, "year": 1, "id": 1}
        )
        if snapshot_ctx and snapshot_ctx.get("employees"):
            snap_emp = snapshot_ctx["employees"][0]
            snap_name = snap_emp.get("name", "")
            snap_report = snap_emp.get("report_name", "") or snap_name
            snap_display = snap_emp.get("display_name", "") or snap_name
            snap_aliases = snap_emp.get("aliases") or []
            snap_quarter = (snapshot_ctx.get("quarter") or "").upper()
            snap_year = snapshot_ctx.get("year")

            # Build candidate name set: includes any aliases stored on the snap row
            candidates = {n for n in [snap_name, snap_report, snap_display] if n}
            for a in snap_aliases:
                if isinstance(a, str) and a.strip():
                    candidates.add(a.strip())

            if candidates:
                name_query = {
                    "$or": (
                        [{"name": {"$regex": f"^{re_mod.escape(n)}$", "$options": "i"}} for n in candidates] +
                        [{"report_name": {"$regex": f"^{re_mod.escape(n)}$", "$options": "i"}} for n in candidates] +
                        [{"display_name": {"$regex": f"^{re_mod.escape(n)}$", "$options": "i"}} for n in candidates] +
                        [{"aliases": {"$elemMatch": {"$regex": f"^{re_mod.escape(n)}$", "$options": "i"}}} for n in candidates]
                    )
                }
                if snap_quarter and snap_year:
                    name_query["quarter"] = snap_quarter
                    name_query["year"] = snap_year
                emp_doc = await db.employees_v2.find_one(name_query)

                # Cross-quarter fallback (very rare)
                if not emp_doc and snap_quarter:
                    fallback_query = dict(name_query)
                    fallback_query.pop("quarter", None)
                    fallback_query.pop("year", None)
                    emp_doc = await db.employees_v2.find_one(fallback_query)

            # ORPHAN ROW RECOVERY: snapshot has the employee but no v2 link
            # exists — happens when someone renames an employee in a way that
            # makes the snapshot and v2 names diverge with no overlap. Create
            # a v2 record on-the-fly from the snapshot data so the edit
            # succeeds. The snapshot sync below will keep everything aligned.
            #
            # IMPORTANT: also copy the original snapshot names into `aliases`
            # so future name-based lookups (e.g. another PUT, sync-from-employees
            # dedup, POS-upload merge) can find this record without creating
            # ANOTHER duplicate. Without this, every rename pass produced a
            # ghost row that re-appeared on the next Save Snapshot.
            if not emp_doc:
                snap_emp_clone = {k: v for k, v in snap_emp.items() if k != "_id"}
                snap_emp_clone["id"] = employee_id
                snap_emp_clone["quarter"] = snap_quarter or "Q2"
                snap_emp_clone["year"] = snap_year or 2026
                # Preserve the snapshot's old names as aliases so the user's
                # rename doesn't sever the link to the original employee.
                existing_aliases = list(snap_emp_clone.get("aliases") or [])
                for alias_name in (snap_name, snap_report, snap_display):
                    if alias_name and alias_name not in existing_aliases:
                        existing_aliases.append(alias_name)
                snap_emp_clone["aliases"] = existing_aliases
                snap_emp_clone["created_at"] = datetime.now(timezone.utc).isoformat()
                snap_emp_clone["updated_at"] = snap_emp_clone["created_at"]
                await db.employees_v2.insert_one(snap_emp_clone)
                emp_doc = snap_emp_clone

        if not emp_doc:
            raise HTTPException(status_code=404, detail="Employee not found")
    
    actual_id = emp_doc.get("id", employee_id)
    mongo_id = emp_doc.get("_id")
    
    # Build update - only include fields that were actually sent
    update_fields = {}
    for key, value in data.items():
        if key in ('_id', 'id'):
            continue
        if value is not None:
            update_fields[key] = value
    
    # If display_name is being set, always persist it
    if 'display_name' in update_fields:
        # Also preserve report_name for POS matching
        if 'report_name' not in update_fields:
            update_fields['report_name'] = emp_doc.get('report_name') or emp_doc.get('name', '')
    
    # If name is being set and no display_name provided, treat name as display_name
    if 'name' in update_fields and 'display_name' not in update_fields:
        update_fields['display_name'] = update_fields['name']
        if 'report_name' not in update_fields:
            update_fields['report_name'] = emp_doc.get('report_name') or emp_doc.get('name', '')
    
    update_fields['updated_at'] = datetime.now(timezone.utc).isoformat()

    # Mirror guests <-> guest_count so a PUT that supplies only one keeps both
    # in lockstep. Otherwise reprocess writes the stale field back over the
    # user's edit during snapshot rebuild.
    if 'guests' in update_fields and 'guest_count' not in update_fields:
        update_fields['guest_count'] = update_fields['guests']
    elif 'guest_count' in update_fields and 'guests' not in update_fields:
        update_fields['guests'] = update_fields['guest_count']

    # If the caller is editing NPS or CV stats directly, mark the row as a
    # manual override so subsequent /process passes won't redistribute
    # store-level CV data over the user's value. Cleared automatically when
    # a fresh CV upload is processed (handled in merge_snapshot_data).
    # Skip the flag if the value is unchanged from emp_doc (idempotent PUT).
    nps_override_fields = {"nps_score", "cv_promoters", "cv_passives", "cv_detractors"}
    nps_changed = any(
        k in update_fields and update_fields[k] != emp_doc.get(k)
        for k in nps_override_fields
    )
    if nps_changed:
        update_fields["nps_manual_override"] = True
    
    # Recalculate derived metrics and scores if POS data fields changed
    pos_fields = {'guests', 'guest_count', 'net_sales', 'liquor_sales', 'beer_sales', 
                  'wine_sales', 'lbw', 'glassware_sales', 'bar_glassware_sales', 
                  'loyalty_sales', 'lsc_count'}
    if pos_fields.intersection(update_fields.keys()):
        # Merge updates into emp_doc for recalculation
        merged = {**{k: v for k, v in emp_doc.items() if k != '_id'}, **update_fields}
        
        guests = merged.get('guests', 0) or merged.get('guest_count', 0) or 0
        net_sales = merged.get('net_sales', 0) or 0
        liquor = merged.get('liquor_sales', 0) or 0
        beer = merged.get('beer_sales', 0) or 0
        wine = merged.get('wine_sales', 0) or 0
        lbw = liquor + beer + wine if (liquor + beer + wine) > 0 else (merged.get('lbw', 0) or 0)
        glassware = merged.get('glassware_sales', 0) or merged.get('bar_glassware_sales', 0) or 0
        loyalty = merged.get('loyalty_sales', 0) or 0
        # Respect user-set lsc_count of 0 - don't override from loyalty_sales
        lsc_count = merged.get('lsc_count')
        if lsc_count is None:
            lsc_count = int(loyalty / 25) if loyalty > 0 else 0
        
        if guests > 0:
            update_fields['ppa'] = round(net_sales / guests, 2)
            update_fields['lbw_per_guest'] = round(lbw / guests, 2) if lbw > 0 else 0
            update_fields['glassware_per_guest'] = round(glassware / guests, 2) if glassware > 0 else 0
            update_fields['guests_per_lsc'] = round(guests / lsc_count, 2) if lsc_count > 0 else 0
        
        update_fields['lbw'] = lbw
        update_fields['lbw_total'] = lbw
        
        # Get benchmarks for scoring
        settings_doc = await db.quarter_settings.find_one(
            {"year": emp_doc.get('year', 2026), "quarter": emp_doc.get('quarter', 'Q2')},
            {"_id": 0}
        )
        if settings_doc:
            bm_ppa = settings_doc.get('benchmark_ppa', 55) or 55
            bm_lbw = settings_doc.get('benchmark_lbw', 8) or 8
            bm_glass = settings_doc.get('benchmark_glass', 1.35) or 1.35
            bm_lsc = settings_doc.get('benchmark_lsc', 100) or 100
            
            ppa_val = update_fields.get('ppa', merged.get('ppa', 0) or 0)
            lbw_pg = update_fields.get('lbw_per_guest', merged.get('lbw_per_guest', 0) or 0)
            glass_pg = update_fields.get('glassware_per_guest', merged.get('glassware_per_guest', 0) or 0)
            gplsc = update_fields.get('guests_per_lsc', merged.get('guests_per_lsc', 0) or 0)
            
            if ppa_val > 0:
                update_fields['score_ppa'] = round((ppa_val / bm_ppa) * 100, 2)
            if lbw_pg > 0:
                update_fields['score_lbw'] = round((lbw_pg / bm_lbw) * 100, 2)
            if glass_pg > 0:
                update_fields['score_glass'] = round((glass_pg / bm_glass) * 100, 2)
            if gplsc > 0:
                update_fields['score_lsc'] = round((bm_lsc / gplsc) * 100, 2)
    
    # Recalculate total score if any score fields changed
    score_fields = {'score_ppa', 'score_lbw', 'score_glass', 'score_lsc', 'cv_score',
                    'review_tracker_bonus', 'total_metric_bonus',
                    # CV inputs — editing any of these must rebuild cv_score
                    'nps_score', 'cv_promoters', 'cv_passives', 'cv_detractors'}
    if score_fields.intersection(update_fields.keys()) or pos_fields.intersection(update_fields.keys()):
        merged = {**{k: v for k, v in emp_doc.items() if k != '_id'}, **update_fields}
        settings_doc = settings_doc if 'settings_doc' in dir() else await db.quarter_settings.find_one(
            {"year": emp_doc.get('year', 2026), "quarter": emp_doc.get('quarter', 'Q2')}, {"_id": 0}
        ) or {}

        # ---- Recompute CV Score (NPS%/10 + promoters - 2*detractors) ----
        # cv_score in the new spec is the COMBINED Customer Voice value.
        # Recompute whenever the user edits NPS or promoter/detractor counts.
        cv_inputs = {'nps_score', 'cv_promoters', 'cv_passives', 'cv_detractors'}
        old_cv = emp_doc.get('cv_score') or 0
        if cv_inputs.intersection(update_fields.keys()):
            nps_val = merged.get('nps_score') or 0
            nps_norm = max(0, min(100, nps_val))
            promo = merged.get('cv_promoters') or 0
            detr = merged.get('cv_detractors') or 0
            cv_recalc = round(nps_norm * 0.10 + promo * 1 + detr * -2, 2)
            update_fields['cv_score'] = cv_recalc
            update_fields['nps_contribution'] = round(nps_norm * 0.10, 2)
            update_fields['cv_raw_points'] = round(promo * 1 + detr * -2, 2)
            merged['cv_score'] = cv_recalc

        # If ONLY CV / RT / bonus changed (no POS data), apply delta math
        # rather than rebuilding the weighted_score from scratch — the
        # snapshot pipeline caps percentages differently and a full rebuild
        # would produce a much larger number than the user expects.
        non_cv_score_fields = pos_fields | {'score_ppa', 'score_lbw', 'score_glass', 'score_lsc'}
        full_rebuild = bool(non_cv_score_fields.intersection(update_fields.keys()))

        if not full_rebuild:
            # Delta math: shift existing total_score by the difference in
            # cv_score / RT bonus / metric bonus.
            old_rt = emp_doc.get('review_tracker_bonus') or 0
            old_bonus = emp_doc.get('total_metric_bonus') or 0
            new_cv = merged.get('cv_score') or 0
            new_rt = merged.get('review_tracker_bonus') or 0
            new_bonus = merged.get('total_metric_bonus') or 0
            delta = (new_cv - old_cv) + (new_rt - old_rt) + (new_bonus - old_bonus)
            old_total = emp_doc.get('total_score') or 0
            new_total = round(old_total + delta, 2)
            update_fields['total_score'] = new_total
            update_fields['pre_dar_score'] = new_total

            # Tier label refresh based on new total
            a_min = settings_doc.get('a_server_min_score', 85)
            b_min = settings_doc.get('b_server_min_score', 70)
            job = (update_fields.get('job_title') or merged.get('job_title', '') or '').lower()
            if 'trainer' in job:
                update_fields['tier_label'] = 'Trainer'
            elif 'bartender' in job or 'bar' in job:
                update_fields['tier_label'] = 'Bartender'
            elif new_total >= a_min:
                update_fields['tier_label'] = 'A-Server'
            elif new_total >= b_min:
                update_fields['tier_label'] = 'B-Server'
            else:
                update_fields['tier_label'] = 'C-Server'

        # Legacy full-rebuild path — only when POS-data fields actually
        # changed. Caps each score at 100% (consistent with the snapshot
        # pipeline) so a server with extreme metrics like LSC=330% can't
        # inflate weighted_score beyond the documented max of
        # sum(weights) × 100.
        if full_rebuild:
            # Default to current Q2+ active model when settings are missing
            # any field. Q1 legacy used 0.25/0.15/0.10/0.25 — but those are
            # already in the QuarterSettings doc, so the .get() fallbacks
            # below should rarely be hit in practice.
            w_ppa = settings_doc.get('weight_ppa', 0.25)
            w_lbw = settings_doc.get('weight_lbw', 0.20)
            w_glass = settings_doc.get('weight_glass', 0.15)
            w_lsc = settings_doc.get('weight_lsc', 0.25)

            s_ppa = min(merged.get('score_ppa', 0) or 0, 100)
            s_lbw = min(merged.get('score_lbw', 0) or 0, 100)
            s_glass = min(merged.get('score_glass', 0) or 0, 100)
            s_lsc = min(merged.get('score_lsc', 0) or 0, 100)
            cv = merged.get('cv_score', 0) or 0
            rt = merged.get('review_tracker_bonus', 0) or 0
            bonus = merged.get('total_metric_bonus', 0) or 0

            weighted = (s_ppa * w_ppa) + (s_lbw * w_lbw) + (s_glass * w_glass) + (s_lsc * w_lsc)
            total = weighted + cv + rt + bonus
            update_fields['weighted_score'] = round(weighted, 2)
            update_fields['total_score'] = round(total, 2)
            update_fields['pre_dar_score'] = round(total, 2)

            # Tier assignment
            a_min = settings_doc.get('a_server_min_score', 85)
            b_min = settings_doc.get('b_server_min_score', 70)
            job = (update_fields.get('job_title') or merged.get('job_title', '') or '').lower()
            if 'trainer' in job:
                update_fields['tier_label'] = 'Trainer'
            elif 'bartender' in job or 'bar' in job:
                update_fields['tier_label'] = 'Bartender'
            elif total >= a_min:
                update_fields['tier_label'] = 'A-Server'
            elif total >= b_min:
                update_fields['tier_label'] = 'B-Server'
            else:
                update_fields['tier_label'] = 'C-Server'
    
    # Save to employees_v2
    await db.employees_v2.update_one(
        {"_id": mongo_id},
        {"$set": update_fields}
    )
    
    # Also update the snapshot to keep ALL fields in sync so that re-fetches
    # from /v2/snapshot-workflow/current-rankings reflect user edits.
    display = update_fields.get('display_name') or update_fields.get('name')

    # Build a complete snapshot-employee sync payload from ALL updated fields
    # (not just name/tier). Metrics edited in Employee List must persist in the
    # snapshot or users see old values on re-fetch.
    SNAP_SYNCABLE = {
        "name", "display_name", "report_name", "job_title", "tier_label",
        "guests", "guest_count", "net_sales",
        "liquor_sales", "beer_sales", "wine_sales", "lbw", "lbw_total",
        "glassware_sales", "bar_glassware_sales",
        "loyalty_sales", "lsc_count",
        "ppa", "lbw_per_guest", "glassware_per_guest", "guests_per_lsc",
        "score_ppa", "score_lbw", "score_glass", "score_lsc",
        "weighted_score", "total_score", "pre_dar_score",
        "cv_promoters", "cv_passives", "cv_detractors", "cv_score",
        "nps_score", "nps_score_pts", "nps_contribution", "cv_raw_points",
        "rt_mentions", "review_tracker_bonus",
        "total_metric_bonus", "aliases",
        "nps_manual_override",
    }
    snap_update = {}
    for k, v in update_fields.items():
        if k in SNAP_SYNCABLE:
            snap_update[f"employees.$.{k}"] = v
    # Keep name and display_name aligned in the snapshot too
    if display:
        snap_update["employees.$.name"] = display
        snap_update["employees.$.display_name"] = display

    if snap_update:
        # Prefer the snapshot_ctx quarter/year when the request originated from
        # a snapshot UUID - otherwise use the employees_v2 quarter/year.
        if snapshot_ctx:
            quarter = (snapshot_ctx.get('quarter') or emp_doc.get('quarter', 'Q2')).upper()
            year = snapshot_ctx.get('year') or emp_doc.get('year', 2026)
        else:
            quarter = (emp_doc.get('quarter') or 'Q2').upper()
            year = emp_doc.get('year', 2026)
        actual_id = emp_doc.get('id', employee_id)

        # Try BOTH IDs (employees_v2 ID and the original request ID which may
        # be a snapshot UUID). When the snapshot row was orphaned, the only
        # way to update it is by the original request ID — using actual_id
        # alone would miss it.
        updated_any = False
        for eid in {actual_id, employee_id}:
            if not eid:
                continue
            result = await db.snapshot_workflow.update_many(
                {"quarter": quarter, "year": year, "employees.id": eid},
                {"$set": snap_update}
            )
            if result.modified_count > 0:
                updated_any = True

        # Fallback: match snapshot employee by name if ID lookup didn't update
        # anything (snapshot employees often have different UUIDs). Use
        # arrayFilters to unambiguously target the right embedded element.
        if not updated_any:
            match_name = emp_doc.get('report_name') or emp_doc.get('name') or display
            if match_name:
                import re as _re
                name_pat = f"^{_re.escape(match_name)}$"
                af_snap_update = {f"employees.$[e].{k.split('.')[-1]}": v
                                  for k, v in snap_update.items()}
                await db.snapshot_workflow.update_many(
                    {"quarter": quarter, "year": year},
                    {"$set": af_snap_update},
                    array_filters=[{
                        "$or": [
                            {"e.name": {"$regex": name_pat, "$options": "i"}},
                            {"e.report_name": {"$regex": name_pat, "$options": "i"}},
                            {"e.display_name": {"$regex": name_pat, "$options": "i"}},
                        ]
                    }],
                )
    
    name = update_fields.get('display_name') or update_fields.get('name') or emp_doc.get('display_name') or emp_doc.get('name', '')
    
    return {
        "success": True,
        "message": f"Updated {name} - new score: {update_fields.get('total_score', emp_doc.get('total_score', 0))}"
    }


@api_router.put("/v2/employees/{employee_id}/manual-score")
async def update_employee_manual_score(employee_id: str, data: dict):
    """
    Manually set employee scores WITHOUT recalculation.
    Used for restoring finalized rankings from backup.
    """
    # Get existing employee
    emp_doc = await db.employees_v2.find_one({"id": employee_id}, {"_id": 0})
    if not emp_doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Fields that can be manually set
    allowed_fields = [
        'total_score', 'pre_dar_score', 'score_ppa', 'score_lbw', 'score_glass', 'score_lsc',
        'cv_score', 'review_tracker_bonus', 'total_metric_bonus', 'weighted_score',
        'bonus_ppa', 'bonus_lbw', 'bonus_glass', 'bonus_lsc'
    ]
    
    update_dict = {}
    for field in allowed_fields:
        if field in data:
            update_dict[field] = data[field]
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    # Update in employees_v2
    await db.employees_v2.update_one(
        {"id": employee_id},
        {"$set": update_dict}
    )
    
    # Also update in snapshot_workflow
    snapshot_update = {f"employees.$.{k}": v for k, v in update_dict.items()}
    await db.snapshot_workflow.update_many(
        {
            "year": emp_doc.get('year'),
            "quarter": emp_doc.get('quarter'),
            "employees.id": employee_id
        },
        {"$set": snapshot_update}
    )
    
    return {"success": True, "message": f"Manually set scores for {emp_doc.get('name')}", "updated_fields": list(update_dict.keys())}


@api_router.delete("/v2/employees/{employee_id}")
async def delete_employee(employee_id: str):
    """
    Soft-delete a single employee. Phase-2 wired through
    EmployeeService.delete_completely which handles canonical
    soft-delete + employees_v2 mirror removal + snapshot pull (by id,
    legacy_ids, AND name) + `deleted_names` blocklist write +
    employee_count recompute in one atomic flow.

    Accepts canonical id, legacy_id, OR a bare name (the name fallback
    preserves backwards-compat for any frontend code still POSTing
    `/v2/employees/<name>` directly).
    """
    import re as _re
    from services.employee_service import EmployeeService
    svc = EmployeeService(db)

    canonical = await svc.get_by_id(employee_id)
    if not canonical:
        canonical = await svc.col.find_one({"legacy_ids": employee_id}, {"_id": 0})

    if not canonical:
        # Treat employee_id as a bare name (case-insensitive) — find the
        # canonical row by name/alias and route through delete_completely.
        canonical = await svc.find_by_name_or_alias(employee_id, include_inactive=True)

    if not canonical:
        # Last-resort: only present in legacy employees_v2 (canonical
        # migration hadn't run for them yet). Mint a canonical row first
        # so all the bookkeeping below works.
        legacy = await db.employees_v2.find_one(
            {"$or": [
                {"id": employee_id},
                {"name": {"$regex": f"^{_re.escape(employee_id)}$", "$options": "i"}},
                {"display_name": {"$regex": f"^{_re.escape(employee_id)}$", "$options": "i"}},
            ]},
            {"_id": 0},
        )
        if not legacy:
            raise HTTPException(status_code=404, detail="Employee not found")
        canonical = await svc.create_employee({
            "id": legacy.get("id"),
            "name": legacy.get("name"),
            "display_name": legacy.get("display_name") or (legacy.get("name") or "").split()[0],
            "report_name": legacy.get("report_name") or legacy.get("name"),
            "job_title": legacy.get("job_title") or "Server",
        })

    result = await svc.delete_completely(canonical["id"])
    return {
        "success": True,
        "message": f"Deleted {canonical.get('name') or 'employee'}",
        **result,
    }



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


@api_router.get("/v2/admin/integrity")
async def employee_data_integrity():
    """
    Run the 9-check EmployeeValidator suite (Phase 1) and return the
    full report as JSON. Surface this on an admin page to spot drift
    before it becomes a slide-generation bug.

    Response shape mirrors `scripts/run_validation_suite.py` output:
        {
          "duplicate_canonical_ids": [...],
          "orphaned_snapshot_refs":  [...],
          "employees_missing_id":    [...],
          "blocklist_violations":    [...],
          "duplicate_active_names":  [...],
          "inactive_in_current_snap":[...],
          "metric_drift":            [...],
          "legacy_only_employees":   [...],
          "snapshot_only_employees": [...],
          "summary": {p0_issues, p1_issues, p2_issues, deploy_gate: "PASS|FAIL"}
        }
    """
    from services.validation_service import EmployeeValidator
    report = await EmployeeValidator(db).run_all()
    return report


@api_router.post("/v2/employees/cleanup/delete")
async def delete_employees_bulk(request: EmployeeCleanupRequest):
    """
    Delete multiple employees by ID.
    Routes each id through EmployeeService.delete_completely so every
    deletion does the full canonical soft-delete + snapshot pull +
    blocklist add. Phase-2 wiring of the bulk path.
    """
    if not request.employee_ids:
        raise HTTPException(status_code=400, detail="No employee IDs provided")

    from services.employee_service import EmployeeService
    svc = EmployeeService(db)

    deleted_count = 0
    errors = []

    for emp_id in request.employee_ids:
        try:
            # Resolve via canonical first, fall back to legacy_ids index.
            canonical = await svc.get_by_id(emp_id)
            if not canonical:
                canonical = await svc.col.find_one({"legacy_ids": emp_id}, {"_id": 0})

            if not canonical:
                # No canonical row — mint one from the legacy v2 doc so
                # future deletes (re-runs of this script, undo) work.
                legacy = await db.employees_v2.find_one({"id": emp_id}, {"_id": 0})
                if not legacy:
                    errors.append(f"Employee {emp_id} not found")
                    continue
                canonical = await svc.create_employee({
                    "id": legacy.get("id"),
                    "name": legacy.get("name"),
                    "display_name": legacy.get("display_name") or (legacy.get("name") or "").split()[0],
                    "report_name": legacy.get("report_name") or legacy.get("name"),
                    "job_title": legacy.get("job_title") or "Server",
                })

            res = await svc.delete_completely(canonical["id"])
            if res.get("success"):
                deleted_count += 1
            else:
                errors.append(f"Could not delete {emp_id}: {res.get('reason')}")
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
        snapshot = await db.snapshot_workflow.find_one(
            {"employees.id": employee_id},
            {"employees.$": 1}
        )
        if snapshot and snapshot.get("employees"):
            snap_name = snapshot["employees"][0].get("name", "")
            if snap_name:
                employee = await db.employees_v2.find_one({
                    "$or": [
                        {"name": {"$regex": f"^{snap_name}$", "$options": "i"}},
                        {"report_name": {"$regex": f"^{snap_name}$", "$options": "i"}},
                        {"display_name": {"$regex": f"^{snap_name}$", "$options": "i"}},
                    ]
                })
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
    cv_promoters = max(0, int(data.get("cv_promoters", 0) or 0))
    cv_detractors = max(0, int(data.get("cv_detractors", 0) or 0))
    cv_passives = max(0, int(data.get("cv_passives", 0) or 0))
    
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
            except Exception as e:
                logger.warning(f"Failed to capture score distribution chart: {e}")
            
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
            except Exception as e:
                logger.warning(f"Failed to capture top 10 chart: {e}")
            
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

# NOTE: trend_charts imports are at the top of file (line 49)


# ============================================================================
# SNAPSHOT ENDPOINTS - MOVED TO /app/backend/routes/snapshots_legacy.py
# ============================================================================
# Legacy snapshots (using db.snapshots collection) have been extracted to 
# routes/snapshots_legacy.py for better code organization.
# The snapshot_workflow routes remain in snapshot_routes.py (using db.snapshot_workflow).


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



# Admin routes moved to /app/backend/routes/admin.py


# Deprecated UI scraper endpoints removed - use manual upload instead

# Scheduler routes moved to /app/backend/routes/scheduler.py


# Register QR tracking routes BEFORE including in app
register_qr_routes(api_router, db)

# Register store management routes
register_store_routes(api_router, db)

# Include snapshot workflow routes
api_router.include_router(snapshot_router)

# Include modular routes
api_router.include_router(quarter_settings_router)
api_router.include_router(finalization_router)
api_router.include_router(yodeck_router)
api_router.include_router(employee_router)
api_router.include_router(trends_router)
api_router.include_router(upload_jobs_router)
api_router.include_router(stores_router)
api_router.include_router(audit_router)
api_router.include_router(cv_router)
api_router.include_router(admin_router)
api_router.include_router(reviews_router)
api_router.include_router(insights_router)
api_router.include_router(pos_upload_router)
api_router.include_router(scheduler_router)
api_router.include_router(auth_router)

# Register legacy snapshots routes (uses db.snapshots collection)
register_snapshots_legacy_routes(api_router, db)


# Insights routes moved to /app/backend/routes/insights.py

# Include the router in the main app
app.include_router(api_router)

# CORS configuration
# - When CORS_ORIGINS="*" (the default in preview), allow all origins. The
#   browser spec forbids `credentials=true` together with `origin=*`, so in
#   that mode we don't send the auth cookie cross-origin. That's fine for
#   preview because the frontend and backend share the same origin.
# - When CORS_ORIGINS is an explicit comma-separated allowlist, enable
#   credentials so the auth cookie travels. The default allowlist includes
#   the preview, the original Emergent-hosted production domain, the user's
#   custom production domain, and localhost.
_origins_raw = (os.environ.get("CORS_ORIGINS") or "*").strip()

if _origins_raw == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    _origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]
    if not _origins:
        _origins = [
            "https://staff-score-engine.preview.emergentagent.com",
            "https://eatery-reports.emergent.host",
            "https://intheweedscollective.com",
            "https://www.intheweedscollective.com",
            "http://localhost:3000",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
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


# ---------------------------------------------------------------------------
# AUTH GATE — protect every state-changing /api/v2/* endpoint.
#
# Read-only GETs stay public so the rankings/snapshots can be shared as a
# public link. Anything that creates, edits, or deletes data requires the
# session_token cookie set by /api/auth/session AND the user's email must
# be in the ALLOWED_ADMIN_EMAILS whitelist (see routes/auth.py).
#
# Routes explicitly EXEMPTED from the gate (in addition to all GETs):
#   • /api/auth/*          — auth flow itself
#   • /api/health, /api/   — health checks
# ---------------------------------------------------------------------------
from routes.auth import _get_session_user as _auth_get_session_user, ALLOWED_EMAILS

_AUTH_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUTH_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/api/health",
)

class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Public reads + auth flow + non-API requests pass through unchanged.
        if (
            method not in _AUTH_PROTECTED_METHODS
            or not path.startswith("/api/")
            or any(path.startswith(p) for p in _AUTH_PUBLIC_PREFIXES)
        ):
            return await call_next(request)

        # Protected: require valid session whose email is on the whitelist.
        try:
            user = await _auth_get_session_user(
                db,
                request.cookies.get("session_token"),
                request.headers.get("authorization"),
            )
        except Exception:
            user = None

        if not user:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "Sign in required to make changes."},
            )
        if not user.is_admin:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": f"{user.email} is not authorized to edit this app. Contact the owner to be added."},
            )

        return await call_next(request)


app.add_middleware(AdminAuthMiddleware)

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
    from routes.scheduler import run_automated_reconciliation
    
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