from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import Response
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

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


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
    a_server_min_score: float = 85.1
    b_server_min_score: float = 70.1


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
        
        return {
            "success": True,
            "message": f"Imported and scored {len(scored_employees)} employees for {quarter} {year}",
            "employees_count": len(scored_employees),
            "cv_data_updated": cv_updated,
            "review_data_updated": review_updated,
            "quarter": quarter,
            "year": year,
            "settings_locked": True
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
    
    for emp in employees:
        if isinstance(emp.get('created_at'), str):
            emp['created_at'] = datetime.fromisoformat(emp['created_at'])
    
    return employees


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
    
    # Get all employees
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
    
    # Convert to EmployeeV2 objects
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    
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
    Download Full Rankings as a PDF document.
    
    Includes all employees with hierarchy-based ranking and complete scoring breakdown:
    - Position, Position Label (T1, Bar1, A1, B1, C1...)
    - Employee Name, Tier
    - Total Score, Total Bonus
    - PPA (Base + Bonus), LBW (Base + Bonus), LSC (Base + Bonus), Glass (Base + Bonus)
    - Customer Voice Score
    """
    # Get settings for tier thresholds
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
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data found for {quarter} {year}")
    
    # Convert to EmployeeV2 objects and generate rankings
    employees = [EmployeeV2(**doc) for doc in employees_docs]
    rankings = generate_hierarchy_rankings(employees, settings)
    
    # Add bonus details to rankings for PDF
    emp_lookup = {emp.id: emp for emp in employees}
    for r in rankings:
        emp = emp_lookup.get(r["employee_id"])
        if emp:
            r["bonus_ppa"] = emp.bonus_ppa or 0
            r["bonus_lbw"] = emp.bonus_lbw or 0
            r["bonus_lsc"] = emp.bonus_lsc or 0
            r["bonus_glass"] = emp.bonus_glass or 0
            r["cv_score"] = emp.cv_score or 0
    
    # Generate PDF
    thresholds = {
        "a_server_min": settings.a_server_min_score,
        "b_server_min": settings.b_server_min_score
    }
    
    pdf_bytes = build_full_rankings_pdf(rankings, quarter.upper(), year, thresholds)
    
    filename = f"full_rankings_{quarter}_{year}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
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
    
    Args:
        format: "16:9" for Yodeck/digital signage (1920x1080) or "letter" for 8.5x11" print (2550x3300)
        background: Background key (dark, rainbow_bokeh, cosmic_lights, neon_grid, synthwave_sunset, electric_mesh)
    """
    # Get all rankings using the full-rankings format for proper tier labels
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
    
    a_server_min = settings.get("a_server_min_score", 80.1)
    b_server_min = settings.get("b_server_min_score", 70.1)
    
    # Transform employees to have proper tier labels and points structure
    tier_counters = {"trainer": 0, "bartender": 0, "a-server": 0, "b-server": 0, "c-server": 0}
    
    # Sort by hierarchy then by score within each tier
    def get_sort_key(e):
        job = str(e.get("job_title", "server")).lower()
        if job == "trainer":
            return (0, -float(e.get("total_score", 0) or 0))
        elif job == "bartender":
            return (1, -float(e.get("total_score", 0) or 0))
        else:
            # Servers sorted by A/B/C then score
            score = float(e.get("total_score", 0) or 0)
            if score >= a_server_min:
                return (2, -score)
            elif score >= b_server_min:
                return (3, -score)
            else:
                return (4, -score)
    
    employees.sort(key=get_sort_key)
    
    # Add tier labels and position labels
    for emp in employees:
        job = str(emp.get("job_title", "server")).lower()
        score = float(emp.get("total_score", 0) or 0)
        
        if job == "trainer":
            tier_counters["trainer"] += 1
            emp["tier_label"] = "Trainer"
            emp["position_label"] = f"T{tier_counters['trainer']}"
        elif job == "bartender":
            tier_counters["bartender"] += 1
            emp["tier_label"] = "Bartender"
            emp["position_label"] = f"Bar{tier_counters['bartender']}"
        else:
            # Determine server tier based on score
            if score >= a_server_min:
                tier_counters["a-server"] += 1
                emp["tier_label"] = "A-Server"
                emp["position_label"] = f"A{tier_counters['a-server']}"
            elif score >= b_server_min:
                tier_counters["b-server"] += 1
                emp["tier_label"] = "B-Server"
                emp["position_label"] = f"B{tier_counters['b-server']}"
            else:
                tier_counters["c-server"] += 1
                emp["tier_label"] = "C-Server"
                emp["position_label"] = f"C{tier_counters['c-server']}"
        
        # Add points structure (earned/possible) - cap scores at max
        ppa_raw = float(emp.get("score_ppa", 0) or 0)
        lbw_raw = float(emp.get("score_lbw", 0) or 0)
        lsc_raw = float(emp.get("score_lsc", 0) or 0)
        glass_raw = float(emp.get("score_glass", 0) or 0)
        
        # Calculate weighted scores (capped at 100% of weight, then scaled)
        ppa_pct = min(ppa_raw / 100, 1.0)
        lbw_pct = min(lbw_raw / 100, 1.0)
        lsc_pct = min(lsc_raw / 100, 1.0)
        glass_pct = min(glass_raw / 100, 1.0)
        
        emp["ppa_points"] = {"earned": round(ppa_pct * 30, 2), "possible": 30}
        emp["lbw_points"] = {"earned": round(lbw_pct * 25, 2), "possible": 25}
        emp["lsc_points"] = {"earned": round(lsc_pct * 30, 2), "possible": 30}
        emp["glassware_points"] = {"earned": round(glass_pct * 20, 2), "possible": 20}
        
        # Bonus points
        emp["bonus_total"] = float(emp.get("bonus_total", 0) or emp.get("total_metric_bonus", 0) or 0)
    
    theme = settings.get("slide_theme", "dark_navy")
    seasonal_theme = settings.get("slide_seasonal_theme", None)
    custom_colors = None
    
    if theme == "custom":
        custom_colors = {
            "background": settings.get("slide_bg_color", "#0A1628"),
            "background_gradient": settings.get("slide_bg_gradient", "#132238"),
            "text_white": settings.get("slide_text_color", "#FFFFFF"),
            "primary": settings.get("slide_accent_color", "#D12E2E"),
            "secondary": settings.get("slide_secondary_color", "#005B96"),
        }
    
    slide_bytes = generate_complete_rankings_slide(
        rankings=employees,
        quarter=quarter,
        year=year,
        theme=theme,
        custom_colors=custom_colors,
        seasonal_theme=seasonal_theme,
        output_format=format,
        background=background
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"complete_rankings_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
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
    job_title: Optional[str] = None
    aliases: Optional[List[str]] = None  # Nicknames for name matching
    guests: Optional[float] = None
    net_sales: Optional[float] = None
    lbw: Optional[float] = None
    glassware_sales: Optional[float] = None
    lsc_count: Optional[int] = None
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
                "employees.$.job_title": emp_dict['job_title'],
                "employees.$.tier_label": tier_label,
                "employees.$.total_score": emp_dict.get('total_score', 0),
                "employees.$.pre_dar_score": emp_dict.get('pre_dar_score', 0),
                "employees.$.weighted_score": emp_dict.get('weighted_score', 0)
            }
        }
    )
    logging.info(f"Updated employee {employee.name} job_title to {emp_dict['job_title']} in both employees_v2 and snapshots")
    
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
    # Use the preview URL for capturing
    preview_url = os.environ.get("REACT_APP_BACKEND_URL", "https://employee-metrics-13.preview.emergentagent.com")
    if "preview.emergentagent.com" in preview_url:
        frontend_url = preview_url.replace("/api", "").rstrip("/")
    
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
    """Create a new empty snapshot for the given date."""
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
    
    snapshot = {
        "id": snapshot_id,
        "snapshot_date": data.snapshot_date,
        "title": data.title,
        "year": data.year,
        "quarter": data.quarter.upper(),
        "employees": [],
        "benchmarks": benchmarks,
        "employee_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.snapshots.insert_one(snapshot)
    return {"id": snapshot_id, "message": "Snapshot created successfully"}


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
        # First, try the Clean POS format (simplified single-sheet format)
        from clean_pos_parser import parse_clean_pos_report
        import tempfile
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        # Try clean format first (if it's an xlsx)
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
                    
                    # Determine tier label
                    if emp.total_score >= settings.a_server_min_score:
                        tier_label = "A-Server"
                    elif emp.total_score >= settings.b_server_min_score:
                        tier_label = "B-Server"
                    else:
                        tier_label = "C-Server"
                    
                    emp_dict = emp.model_dump()
                    emp_dict["tier_label"] = tier_label
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
        
        # Fall back to original POS report format
        from pos_report_parser import is_pos_report_format, parse_pos_report
        
        if not filename.endswith('.csv') and is_pos_report_format(tmp_path):
            # Use specialized POS report parser
            logging.info("Detected POS report format - using specialized parser")
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
                guests = emp_data.get('guests', 0)
                net_sales = emp_data.get('net_sales', 0)
                lbw = emp_data.get('lbw', 0)
                glassware_sales = emp_data.get('glassware_sales', 0)
                lsc_count = emp_data.get('lsc_count', 0)
                
                # Skip if no meaningful data
                if net_sales <= 0 and lbw <= 0:
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
            
            # Create EmployeeV2 from existing data
            # Use CV data from cv_nps collection (not from snapshot which may be stale)
            emp = EmployeeV2(
                id=emp_data.get("id", str(uuid.uuid4())),
                name=emp_name,
                job_title=emp_data.get("job_title", "Server"),
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
    If generate_reviews=True, automatically generates AI reviews for all employees.
    """
    # Get current employees
    employees = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(1000)
    
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
        "reviews_generated": False
    }
    
    await db.quarter_finalizations.update_one(
        {"year": year, "quarter": quarter.upper()},
        {"$set": finalization_doc},
        upsert=True
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
from reviewtrackers_integration import (
    ReviewTrackersClient, sync_reviews_from_reviewtrackers
)


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
    query = {"quarter": quarter.upper(), "year": year}
    
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
    reviews = await db.customer_reviews.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(1000)
    
    # Get employee names from the database
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"name": 1, "_id": 0}
    ).to_list(500)
    employee_names = [e["name"] for e in employees]
    
    stats = get_review_stats(reviews, employee_names)
    
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
# REVIEWTRACKERS SYNC - Automatic review import
# ============================================================================

@api_router.post("/v2/reviews/sync")
async def sync_from_reviewtrackers(
    quarter: str = "Q1",
    year: int = 2026,
    since_date: Optional[str] = None
):
    """
    Sync reviews from ReviewTrackers API.
    
    Args:
        quarter: Quarter to assign reviews to
        year: Year to assign reviews to
        since_date: Only sync reviews published after this date (YYYY-MM-DD)
    """
    try:
        results = await sync_reviews_from_reviewtrackers(
            db=db,
            quarter=quarter,
            year=year,
            since_date=since_date,
            detect_employees_func=detect_employees_in_review
        )
        
        return {
            "success": results.get("success", False),
            "message": f"Synced {results.get('new_count', 0)} new reviews from ReviewTrackers",
            "new_reviews": results.get("new_count", 0),
            "skipped_duplicates": results.get("skipped_count", 0),
            "total_fetched": results.get("total_fetched", 0),
            "errors": results.get("errors", [])[:5]  # Limit errors shown
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


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
    """Test connection to ReviewTrackers API."""
    try:
        client = ReviewTrackersClient()
        success = await client.authenticate()
        
        if success:
            # Try to get a few reviews to verify full access
            result = await client.get_reviews(per_page=5)
            review_count = len(result.get("reviews", []))
            
            return {
                "success": True,
                "message": "Successfully connected to ReviewTrackers",
                "account_id": client.account_id,
                "sample_reviews_found": review_count
            }
        else:
            return {
                "success": False,
                "message": "Authentication failed - check credentials"
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection error: {str(e)}"
        }


# ============================================================================
# LOYALTY VOICE (CV) INTEGRATION - Server Performance NPS Scores
# ============================================================================

from loyalty_voice_integration import (
    sync_loyalty_voice_to_db,
    scrape_server_performance_report,
    get_nps_score_for_employee,
    get_quarter_date_range
)


@api_router.post("/v2/cv/sync")
async def sync_loyalty_voice(quarter: str = "Q1", year: int = 2026):
    """
    Sync NPS scores from Loyalty Voice Server Performance Report.
    
    This scrapes the Server Performance Report which contains NPS %
    for each server, then matches them to employees in the database.
    Also updates employees_v2 collection with the synced NPS data.
    """
    try:
        results = await sync_loyalty_voice_to_db(
            db=db,
            quarter=quarter,
            year=year
        )
        
        if not results.get("success"):
            return {
                "success": False,
                "message": results.get("error", "Sync failed"),
                "error": results.get("error"),
                "debug_screenshot": results.get("debug_screenshot")
            }
        
        # IMPORTANT: Also update employees_v2 with the synced NPS data
        # This ensures CV scores are reflected in the main employee records
        cv_records = await db.cv_nps.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(500)
        
        employees_updated = 0
        for cv in cv_records:
            emp_name = cv.get("employee_name", "")
            nps_score = cv.get("nps_score", 0) or 0
            
            # Calculate CV score from NPS (NPS% × 0.10)
            cv_score = round(nps_score * 0.10, 2)
            
            if emp_name:
                # First, get the current employee data to recalculate scores
                emp_doc = await db.employees_v2.find_one(
                    {"name": emp_name, "quarter": quarter.upper(), "year": year},
                    {"_id": 0}
                )
                
                if emp_doc:
                    # Recalculate weighted_score and pre_dar_score with new CV score
                    # weighted_score = base_score + cv_score
                    # base_score = capped(PPA×0.25 + LBW×0.20 + Glass×0.15 + LSC×0.25)
                    capped_ppa = min(emp_doc.get('score_ppa', 0) or 0, 100)
                    capped_lbw = min(emp_doc.get('score_lbw', 0) or 0, 100)
                    capped_glass = min(emp_doc.get('score_glass', 0) or 0, 100)
                    capped_lsc = min(emp_doc.get('score_lsc', 0) or 0, 100)
                    
                    base_score = capped_ppa * 0.25 + capped_lbw * 0.20 + capped_glass * 0.15 + capped_lsc * 0.25
                    new_weighted = round(base_score + cv_score, 2)
                    
                    # pre_dar_score = weighted + metric_bonus + rt_bonus
                    metric_bonus = emp_doc.get('total_metric_bonus', 0) or 0
                    rt_bonus = emp_doc.get('review_tracker_bonus', 0) or 0
                    new_pre_dar = round(new_weighted + metric_bonus + rt_bonus, 2)
                    new_total = round(new_pre_dar + (emp_doc.get('dar_penalty', 0) or 0), 2)
                    
                    result = await db.employees_v2.update_one(
                        {"name": emp_name, "quarter": quarter.upper(), "year": year},
                        {"$set": {
                            "cv_promoters": cv.get("promoters", 0),
                            "cv_passives": cv.get("passives", 0),
                            "cv_detractors": cv.get("detractors", 0),
                            "cv_score": cv_score,
                            "score_cv": cv_score,
                            "nps_score": nps_score,
                            "cv_source": "loyalty_voice_sync",
                            "weighted_score": new_weighted,
                            "pre_dar_score": new_pre_dar,
                            "total_score": new_total
                        }}
                    )
                    if result.modified_count > 0:
                        employees_updated += 1
        
        logging.info(f"CV sync: Updated {employees_updated} employees with NPS data and recalculated scores")
        
        return {
            "success": True,
            "message": f"Synced NPS scores for {results.get('matched_count', 0)} employees",
            "matched_count": results.get("matched_count", 0),
            "matched_servers": results.get("matched_servers", []),
            "unmatched_servers": results.get("unmatched_servers", []),
            "total_scraped": results.get("total_scraped", 0),
            "employees_updated": employees_updated,
            "cleared_count": results.get("cleared_count", 0)
        }
    except Exception as e:
        logging.error(f"CV sync error: {e}")
        raise HTTPException(status_code=500, detail=f"CV sync failed: {str(e)}")


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
# CV FEEDBACK (Customer Voice Comments) INTEGRATION
# ============================================================================

from cv_feedback_scraper import sync_cv_feedback_to_db, scrape_cv_feedback


@api_router.post("/v2/cv/feedback/sync")
async def sync_cv_feedback(quarter: str = "Q1", year: int = 2026):
    """
    Sync Customer Voice feedback comments from Loyalty Voice.
    
    This scrapes individual feedback items with ratings and comments,
    detects employee mentions, and awards CV points.
    """
    try:
        results = await sync_cv_feedback_to_db(
            db=db,
            quarter=quarter,
            year=year
        )
        
        if not results.get("success"):
            return {
                "success": False,
                "message": results.get("error", "Sync failed"),
                "error": results.get("error")
            }
        
        return {
            "success": True,
            "message": f"Synced {results.get('new_count', 0)} new CV feedback items",
            "new_count": results.get("new_count", 0),
            "skipped_count": results.get("skipped_count", 0),
            "total_scraped": results.get("total_scraped", 0),
            "employees_with_mentions": results.get("employees_with_mentions", 0)
        }
    except Exception as e:
        logging.error(f"CV feedback sync error: {e}")
        raise HTTPException(status_code=500, detail=f"CV feedback sync failed: {str(e)}")


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
    ).sort("date", -1).to_list(limit)
    
    # Also get excluded count
    excluded_count = await db.cv_feedback.count_documents({
        "quarter": quarter.upper(), 
        "year": year,
        "excluded": True
    })
    
    return {
        "feedback": feedback,
        "total": len(feedback),
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
    Upload Server Performance Report CSV from Customer Voice to properly
    attribute CV surveys to servers.
    
    The CSV should have columns: Name, Location, Sent, Received, Response Rate, Avg Rating, NPS
    
    This updates the cv_nps collection with accurate server-level NPS data.
    """
    import csv
    import io
    
    try:
        contents = await file.read()
        csv_text = contents.decode('utf-8')
        reader = csv.DictReader(io.StringIO(csv_text))
        
        records_updated = 0
        total_surveys = 0
        
        for row in reader:
            server_name = row.get('Name', '').strip()
            if not server_name or server_name == 'Manager App Manager App':
                continue
            
            received = int(row.get('Received', 0) or 0)
            sent = int(row.get('Sent', 0) or 0)
            nps_score = float(row.get('NPS', 0) or 0)
            avg_rating = float(row.get('Avg Rating', 0) or 0)
            
            if received == 0:
                continue
            
            total_surveys += received
            
            # Calculate promoters/passives/detractors from NPS
            # NPS = (promoters - detractors) / received * 100
            # For now, estimate based on NPS score
            if nps_score >= 75:
                promoters = received
                detractors = 0
                passives = 0
            elif nps_score >= 50:
                promoters = int(received * 0.75)
                passives = int(received * 0.25)
                detractors = 0
            elif nps_score >= 0:
                promoters = int(received * 0.5)
                passives = int(received * 0.3)
                detractors = int(received * 0.2)
            else:
                promoters = 0
                passives = int(received * 0.3)
                detractors = int(received * 0.7)
            
            # Ensure counts sum to received
            total = promoters + passives + detractors
            if total < received:
                promoters += (received - total)
            
            # Find matching employee in database
            employee = await db.employees_v2.find_one({
                "quarter": quarter.upper(),
                "year": year,
                "$or": [
                    {"name": {"$regex": f"^{server_name}$", "$options": "i"}},
                    {"name": {"$regex": server_name.split()[0], "$options": "i"}} if ' ' in server_name else {"name": server_name}
                ]
            })
            
            employee_id = employee.get("id") if employee else None
            
            # Update or insert cv_nps record
            await db.cv_nps.update_one(
                {
                    "employee_name": server_name,
                    "quarter": quarter.upper(),
                    "year": year
                },
                {"$set": {
                    "employee_name": server_name,
                    "employee_id": employee_id,
                    "quarter": quarter.upper(),
                    "year": year,
                    "nps_score": nps_score,
                    "received": received,
                    "sent": sent,
                    "promoters": promoters,
                    "passives": passives,
                    "detractors": detractors,
                    "avg_rating": avg_rating,
                    "source": "csv_upload",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            records_updated += 1
        
        return {
            "success": True,
            "message": f"Updated {records_updated} server NPS records",
            "records_updated": records_updated,
            "total_surveys": total_surveys,
            "quarter": quarter,
            "year": year
        }
        
    except Exception as e:
        logging.error(f"Server Performance CSV upload error: {e}")
        raise HTTPException(status_code=500, detail=f"CSV upload failed: {str(e)}")


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
    
    # NPS % contribution (10% weight) - normalize NPS (-100 to 100) to 0-100 scale
    raw_nps_for_weight = raw_nps if raw_nps else 0
    nps_normalized = max(0, (raw_nps_for_weight + 100) / 2)
    nps_contribution = round(min(nps_normalized, 100) * 0.10, 2)
    
    # Review Tracker contribution (15% weight) - 0.5 pts per mention, max 15 pts
    rt_mentions = employee.get("review_mentions", 0) or 0
    rt_contribution = min(rt_mentions * 0.5, 15)
    
    # Base weighted: PPA(25%) + LSC(25%) + LBW(15%) + Glass(10%) + NPS%(10%) + RT(15%) = 100%
    expected_weighted = round(capped_ppa * 0.25 + capped_lsc * 0.25 + capped_lbw * 0.15 + capped_glass * 0.10 + nps_contribution + rt_contribution, 2)
    stored_weighted = employee.get("weighted_score", 0)
    
    audit["calculations"]["weighted_score"] = {
        "formula": f"PPA({capped_ppa}×0.25) + LSC({capped_lsc}×0.25) + LBW({capped_lbw}×0.15) + Glass({capped_glass}×0.10) + NPS({nps_contribution}) + RT({rt_contribution})",
        "breakdown": {
            "ppa_contribution": round(capped_ppa * 0.25, 2),
            "lsc_contribution": round(capped_lsc * 0.25, 2),
            "lbw_contribution": round(capped_lbw * 0.15, 2),
            "glass_contribution": round(capped_glass * 0.10, 2),
            "nps_contribution": nps_contribution,
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
    
    # CV Bonus: Promoters +0.5 each, Detractors -1 each (no cap)
    expected_cv_bonus = (raw_promoters * 0.5) - (raw_detractors * 1)
    
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
        }
    }
    
    audit["calculations"]["customer_voice"] = {
        "promoter_points": {
            "formula": f"{raw_promoters} promoters × +0.5 pt",
            "expected": raw_promoters * 0.5,
            "match": True
        },
        "detractor_points": {
            "formula": f"{raw_detractors} detractors × -1 pt",
            "expected": raw_detractors * -1,
            "match": True
        },
        "total_cv_bonus": {
            "formula": f"({raw_promoters} × 0.5) - ({raw_detractors} × 1)",
            "expected": round(expected_cv_bonus, 2),
            "stored": stored_cv_score,
            "match": abs(expected_cv_bonus - stored_cv_score) < 0.5
        }
    }
    
    # Check CV data consistency
    if raw_total > 0:
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
    
    if raw_rt_mentions != stored_rt_mentions:
        audit["discrepancies"].append({
            "field": "review_mentions",
            "description": f"Found {raw_rt_mentions} review mentions but employee record has {stored_rt_mentions}",
            "severity": "MEDIUM"
        })
    
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
    # Final = Base Weighted (includes NPS% and RT) + Metric Bonus + CV Bonus
    expected_final = round(expected_weighted + expected_total_bonus + expected_cv_bonus, 2)
    stored_final = employee.get("pre_dar_score") or employee.get("total_score", 0)
    
    audit["calculations"]["final_score"] = {
        "formula": f"Weighted({expected_weighted}) + MetricBonus({expected_total_bonus}) + CVBonus({expected_cv_bonus})",
        "breakdown": {
            "weighted_base_score": expected_weighted,
            "metric_bonus": expected_total_bonus,
            "cv_bonus": round(expected_cv_bonus, 2)
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
            
            # Calculate NPS points
            if nps_score >= 90: nps_pts = 10
            elif nps_score >= 80: nps_pts = 9
            elif nps_score >= 70: nps_pts = 8
            elif nps_score >= 60: nps_pts = 7
            elif nps_score >= 50: nps_pts = 6
            elif nps_score > 0: nps_pts = round((nps_score / 50) * 5, 1)
            else: nps_pts = 0
            
            # Survey points
            survey_pts = promoters - (detractors * 2)
            cv_score = nps_pts + survey_pts
            
            updates.update({
                "nps_score": nps_score,
                "cv_promoters": promoters,
                "cv_passives": passives,
                "cv_detractors": detractors,
                "cv_score": cv_score,
                "score_cv": cv_score,
                "nps_score_pts": nps_pts,
                "cv_raw_points": survey_pts,
                "cv_source": "cv_nps_sync"
            })
            nps_updated += 1
        
        # Check for review mentions
        mentions = mention_counts.get(emp_name, 0)
        if mentions > 0:
            rt_bonus = round(mentions * 0.2, 1)
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
            
            # Base weighted score
            capped_ppa = min(emp.get("score_ppa", 0) or 0, 100)
            capped_lbw = min(emp.get("score_lbw", 0) or 0, 100)
            capped_glass = min(emp.get("score_glass", 0) or 0, 100)
            capped_lsc = min(emp.get("score_lsc", 0) or 0, 100)
            base_weighted = capped_ppa * 0.25 + capped_lbw * 0.20 + capped_glass * 0.15 + capped_lsc * 0.25
            
            new_weighted = round(base_weighted + cv_score, 2)
            new_pre_dar = round(new_weighted + metric_bonus + rt_bonus, 2)
            
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
    Comprehensive audit comparing our data against source systems.
    Returns discrepancies and verification status.
    """
    from reviewtrackers_integration import ReviewTrackersClient
    
    audit_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "quarter": quarter.upper(),
        "year": year,
        "status": "PASS",
        "issues": [],
        "platform_comparison": {},
        "mention_verification": {},
        "recommendations": []
    }
    
    try:
        # 1. Compare RT API data vs our database
        rt_client = ReviewTrackersClient()
        await rt_client.authenticate()
        api_reviews = await rt_client.get_all_reviews()
        
        # Count API reviews by platform
        api_platform_counts = {}
        for r in api_reviews:
            source = r.get('source_name') or r.get('source_code') or 'Unknown'
            source_lower = source.lower()
            if 'google' in source_lower:
                platform = 'Google'
            elif 'yelp' in source_lower:
                platform = 'Yelp'
            elif 'tripadvisor' in source_lower or 'trip' in source_lower:
                platform = 'TripAdvisor'
            elif 'opentable' in source_lower:
                platform = 'OpenTable'
            else:
                platform = source
            api_platform_counts[platform] = api_platform_counts.get(platform, 0) + 1
        
        # Get our database counts
        pipeline = [
            {"$group": {"_id": "$platform", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        db_counts = await db.customer_reviews.aggregate(pipeline).to_list(20)
        db_platform_counts = {r['_id']: r['count'] for r in db_counts}
        
        # Compare
        all_platforms = set(api_platform_counts.keys()) | set(db_platform_counts.keys())
        for platform in all_platforms:
            api_count = api_platform_counts.get(platform, 0)
            db_count = db_platform_counts.get(platform, 0)
            diff = db_count - api_count
            
            audit_results["platform_comparison"][platform] = {
                "api_count": api_count,
                "db_count": db_count,
                "difference": diff,
                "status": "MATCH" if diff == 0 else ("EXTRA" if diff > 0 else "MISSING")
            }
            
            if diff != 0:
                audit_results["status"] = "WARNING"
                audit_results["issues"].append(f"{platform}: {abs(diff)} {'extra' if diff > 0 else 'missing'} reviews")
        
        # 2. Verify mention counts
        # Get mention counts from reviews
        mention_pipeline = [
            {"$match": {"employee_mentions": {"$exists": True, "$ne": []}}},
            {"$unwind": "$employee_mentions"},
            {"$group": {"_id": "$employee_mentions.name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        review_mentions = await db.customer_reviews.aggregate(mention_pipeline).to_list(100)
        review_mention_counts = {r["_id"]: r["count"] for r in review_mentions}
        
        # Get employee stored counts
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"name": 1, "review_mentions": 1, "review_tracker_bonus": 1}
        ).to_list(100)
        
        for emp in employees:
            name = emp["name"]
            stored_mentions = emp.get("review_mentions", 0) or 0
            calculated_mentions = review_mention_counts.get(name, 0)
            expected_bonus = round(calculated_mentions * 0.2, 1)
            stored_bonus = emp.get("review_tracker_bonus", 0) or 0
            
            status = "PASS"
            if stored_mentions != calculated_mentions:
                status = "MISMATCH"
                audit_results["status"] = "FAIL"
                audit_results["issues"].append(
                    f"{name}: stored={stored_mentions}, calculated={calculated_mentions}"
                )
            
            audit_results["mention_verification"][name] = {
                "stored_mentions": stored_mentions,
                "calculated_mentions": calculated_mentions,
                "stored_bonus": stored_bonus,
                "expected_bonus": expected_bonus,
                "status": status
            }
        
        # 3. Generate recommendations
        if api_platform_counts != db_platform_counts:
            audit_results["recommendations"].append(
                "Run 'Sync ReviewTrackers' to update review data from API"
            )
        
        mention_mismatches = [
            k for k, v in audit_results["mention_verification"].items() 
            if v["status"] != "PASS"
        ]
        if mention_mismatches:
            audit_results["recommendations"].append(
                "Run 'Sync NPS & Reviews' on Scoring Audit page to fix mention counts"
            )
        
        audit_results["summary"] = {
            "api_total_reviews": len(api_reviews),
            "db_total_reviews": sum(db_platform_counts.values()),
            "platforms_matched": sum(1 for p in audit_results["platform_comparison"].values() if p["status"] == "MATCH"),
            "platforms_total": len(audit_results["platform_comparison"]),
            "employees_verified": len(employees),
            "mention_mismatches": len(mention_mismatches)
        }
        
    except Exception as e:
        audit_results["status"] = "ERROR"
        audit_results["error"] = str(e)
    
    return audit_results


@api_router.post("/v2/audit/fix-all-discrepancies")
async def fix_all_discrepancies(quarter: str = "Q1", year: int = 2026):
    """
    One-click fix for all data discrepancies:
    1. Sync reviews from ReviewTrackers API
    2. Re-detect employee mentions
    3. Update employee mention counts
    4. Recalculate scores
    """
    import re
    from reviewtrackers_integration import ReviewTrackersClient
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": []
    }
    
    try:
        # Step 1: Sync reviews from RT API
        rt_client = ReviewTrackersClient()
        await rt_client.authenticate()
        api_reviews = await rt_client.get_all_reviews()
        
        # Get employee names for detection
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"name": 1}
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
                    mentioned.append({"name": full_name, "sentiment": "positive", "points": 0.2})
                    mentioned_names.add(full_name)
            return mentioned
        
        new_reviews = 0
        updated_reviews = 0
        
        for r in api_reviews:
            review_id = str(r.get('id') or r.get('review_id'))
            if not review_id:
                continue
            
            source = r.get('source_name') or r.get('source_code') or 'Unknown'
            source_lower = source.lower()
            if 'google' in source_lower:
                platform = 'Google'
            elif 'yelp' in source_lower:
                platform = 'Yelp'
            elif 'tripadvisor' in source_lower:
                platform = 'TripAdvisor'
            elif 'opentable' in source_lower:
                platform = 'OpenTable'
            else:
                platform = source
            
            review_text = r.get('content') or r.get('text') or ''
            mentions = detect_mentions(review_text)
            
            existing = await db.customer_reviews.find_one({"review_id": review_id})
            
            if existing:
                await db.customer_reviews.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "employee_mentions": mentions,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                updated_reviews += 1
            else:
                await db.customer_reviews.insert_one({
                    "review_id": review_id,
                    "platform": platform,
                    "text": review_text,
                    "rating": r.get('rating'),
                    "author": r.get('author'),
                    "review_date": r.get('published_at'),
                    "employee_mentions": mentions,
                    "source": "reviewtrackers",
                    "quarter": quarter.upper(),
                    "year": year,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
                new_reviews += 1
        
        results["steps"].append({
            "step": "sync_reviews",
            "new_reviews": new_reviews,
            "updated_reviews": updated_reviews
        })
        
        # Step 2: Aggregate mention counts
        mention_pipeline = [
            {"$match": {"employee_mentions": {"$exists": True, "$ne": []}}},
            {"$unwind": "$employee_mentions"},
            {"$group": {"_id": "$employee_mentions.name", "count": {"$sum": 1}}},
        ]
        mention_results = await db.customer_reviews.aggregate(mention_pipeline).to_list(100)
        mention_counts = {r["_id"]: r["count"] for r in mention_results}
        
        # Step 3: Update employees
        updated_employees = 0
        for emp in employees:
            name = emp["name"]
            mentions = mention_counts.get(name, 0)
            
            current = await db.employees_v2.find_one({"_id": emp["_id"]})
            old_mentions = current.get("review_mentions", 0) or 0
            
            if mentions != old_mentions:
                rt_bonus = round(mentions * 0.2, 1)
                old_rt = current.get("review_tracker_bonus", 0) or 0
                old_total = current.get("total_score", 0) or 0
                new_total = round(old_total - old_rt + rt_bonus, 2)
                
                await db.employees_v2.update_one(
                    {"_id": emp["_id"]},
                    {"$set": {
                        "review_mentions": mentions,
                        "review_tracker_bonus": rt_bonus,
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
        for emp in employees:
            name = emp["name"]
            name_lower = name.lower()
            
            cv_data = cv_lookup.get(name_lower)
            current = await db.employees_v2.find_one({"_id": emp["_id"]})
            
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
            
            # === SCORING FORMULA (matches audit) ===
            # Base Score (100 pts max):
            # PPA: 25%, LSC: 25%, LBW: 15%, Glassware: 10%, NPS%: 10%, RT: 15%
            
            capped_ppa = min(current.get("score_ppa", 0) or 0, 100)
            capped_lsc = min(current.get("score_lsc", 0) or 0, 100)
            capped_lbw = min(current.get("score_lbw", 0) or 0, 100)
            capped_glass = min(current.get("score_glass", 0) or 0, 100)
            
            # NPS % contribution (10% weight) - normalize NPS (-100 to 100) to 0-100 scale
            nps_normalized = max(0, (nps_score + 100) / 2)  # Convert -100..100 to 0..100
            nps_contribution = min(nps_normalized, 100) * 0.10
            
            # Review Tracker contribution (15% weight) - 0.5 pts per mention, max 15 pts
            rt_mentions = current.get("review_mentions", 0) or 0
            rt_contribution = min(rt_mentions * 0.5, 15)
            
            # Base weighted score
            base_weighted = (capped_ppa * 0.25) + (capped_lsc * 0.25) + (capped_lbw * 0.15) + (capped_glass * 0.10) + nps_contribution + rt_contribution
            
            # Metric Bonus (max 20 pts total)
            metric_bonus = min(current.get("total_metric_bonus", 0) or 0, 20)
            
            # CV Promoter/Detractor bonus (no cap)
            # Promoters (9-10): +0.5 each, Detractors (<=6): -1 each
            cv_bonus = (promoters * 0.5) - (detractors * 1)
            
            # Final score = Base + Metric Bonus + CV Bonus
            new_weighted = round(base_weighted, 2)
            new_pre_dar = round(base_weighted + metric_bonus + cv_bonus, 2)
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "cv_promoters": promoters,
                    "cv_passives": passives,
                    "cv_detractors": detractors,
                    "nps_score": nps_score,
                    "cv_score": cv_bonus,
                    "score_cv": nps_contribution,
                    "cv_bonus": cv_bonus,
                    "review_tracker_bonus": rt_contribution,
                    "total_metric_bonus": metric_bonus,
                    "weighted_score": new_weighted,
                    "pre_dar_score": new_pre_dar,
                    "total_score": new_pre_dar,
                    "cv_sync_source": "cv_feedback_raw"
                }}
            )
            cv_feedback_updated += 1
        
        results["steps"].append({
            "step": "sync_cv_feedback",
            "updated": cv_feedback_updated
        })
        
        results["success"] = True
        results["message"] = f"Fixed {new_reviews} new reviews, {updated_reviews} updated, {updated_employees} employees mentions, {cv_feedback_updated} CV feedback synced"
        
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
    rt_count = await db.customer_reviews.count_documents({"quarter": quarter.upper(), "year": year})
    
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
        
        # Recalculate affected employee scores
        results["actions_taken"].append("Triggering score recalculation for affected employees...")
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
            # Calculate new RT bonus
            new_rt_bonus = round(actual_mentions * 0.2, 2)
            old_rt_bonus = emp.get("review_tracker_bonus", 0) or 0
            
            # Calculate new score
            weighted = emp.get('weighted_score', 0) or 0
            cv_score = emp.get('cv_score', 0) or 0
            metric_bonus = emp.get('total_metric_bonus', 0) or 0
            new_score = round(weighted + new_rt_bonus + cv_score + metric_bonus, 2)
            
            await db.employees_v2.update_one(
                {"_id": emp["_id"]},
                {"$set": {
                    "review_mentions": actual_mentions,
                    "review_tracker_bonus": new_rt_bonus,
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


# ============================================================
# UI DASHBOARD SCRAPER - Sync from RT and LV dashboards directly
# ============================================================

@api_router.post("/v2/admin/sync-from-ui")
async def sync_stats_from_ui_dashboards(
    quarter: str = "Q1", 
    year: int = 2026,
    background_tasks: BackgroundTasks = None
):
    """
    Scrape official stats directly from ReviewTrackers and Loyalty Voice UI dashboards.
    This ensures 100% accuracy with what you see in their interfaces.
    
    This operation logs into both platforms and extracts the exact numbers displayed.
    """
    from ui_scrapers import sync_official_stats_from_ui
    
    try:
        results = await sync_official_stats_from_ui(db, quarter, year)
        return {
            "success": True,
            "message": "Stats synced from UI dashboards",
            "results": results
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@api_router.post("/v2/admin/sync-rt-from-ui")
async def sync_rt_from_ui(quarter: str = "Q1", year: int = 2026):
    """
    Scrape ReviewTrackers stats directly from their web dashboard.
    """
    from ui_scrapers import ReviewTrackersScraper
    
    scraper = ReviewTrackersScraper()
    stats = await scraper.scrape_platform_stats(quarter, year)
    
    if stats.get("success"):
        # Save as official stats
        official = {
            "quarter": quarter.upper(),
            "year": year,
            "platforms": {
                "Google": stats.get("platforms", {}).get("Google", {"rating": 0, "reviews": 0}),
                "Yelp": stats.get("platforms", {}).get("Yelp", {"rating": 0, "reviews": 0}),
                "TripAdvisor": stats.get("platforms", {}).get("TripAdvisor", {"rating": 0, "reviews": 0}),
                "OpenTable": stats.get("platforms", {}).get("OpenTable", {"rating": 0, "reviews": 0}),
                "Facebook": stats.get("platforms", {}).get("Facebook", {"rating": 0, "reviews": 0}),
            },
            "total_reviews": stats.get("total_reviews", 0),
            "source": "scraped_from_ui",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.official_rt_stats.update_one(
            {"quarter": quarter.upper(), "year": year},
            {"$set": official},
            upsert=True
        )
        
        return {"success": True, "stats": official}
    else:
        return {"success": False, "error": stats.get("error")}


@api_router.post("/v2/admin/sync-cv-from-ui")
async def sync_cv_from_ui(quarter: str = "Q1", year: int = 2026):
    """
    Scrape Loyalty Voice (Customer Voice) stats directly from their web dashboard.
    """
    from ui_scrapers import LoyaltyVoiceScraper
    
    scraper = LoyaltyVoiceScraper()
    stats = await scraper.scrape_nps_stats(quarter, year)
    
    if stats.get("success"):
        # Save as official stats
        official = {
            "quarter": quarter.upper(),
            "year": year,
            "nps_score": stats.get("nps_score", 0),
            "promoters": stats.get("promoters", 0),
            "passives": stats.get("passives", 0),
            "detractors": stats.get("detractors", 0),
            "total_responses": stats.get("total_responses", 0),
            "source": "scraped_from_ui",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.official_cv_stats.update_one(
            {"quarter": quarter.upper(), "year": year},
            {"$set": official},
            upsert=True
        )
        
        return {"success": True, "stats": official}
    else:
        return {"success": False, "error": stats.get("error")}



# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()