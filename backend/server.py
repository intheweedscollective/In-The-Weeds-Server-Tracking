from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
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
    generate_complete_rankings_slide,
    THEMES
)
from snapshot_slides import generate_snapshot_slide, get_available_backgrounds, BACKGROUNDS

# Import new scoring engine
from scoring_engine import (
    EmployeeV2, QuarterSettings, 
    validate_upload_columns, validate_upload_data, validate_employee_row,
    calculate_derived_metrics, calculate_normalized_scores, 
    calculate_bonus_points, calculate_total_score,
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
    Download a sample CSV template with Q1 2026 column format.
    
    IMPORTANT: LBW must NOT be a column. Use individual Liquor, Beer, Wine columns.
    LBW Total is calculated automatically: LBW = Liquor + Beer + Wine
    
    NEW: Job Title column for hierarchy-based rankings (Trainer > Bartender > Server)
    NOTE: CV Passives removed - they contribute 0 points to score
    """
    template_content = """Employee Name,Job Title,Guests,Net Sales,Liquor Sales,Beer Sales,Wine Sales,Glassware Sales,LSC Count,CV Promoters,CV Detractors,Review Mentions
John Smith,Server,450,24750,1500,1350,1200,540,5,3,1,8
Jane Doe,Bartender,520,28600,1800,1500,1380,624,9,5,0,12
Sarah Johnson,Trainer,400,22000,1200,1200,1200,480,4,2,2,5"""
    
    return Response(
        content=template_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_template_q1_2026.csv"}
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
        
        for idx, row in df.iterrows():
            try:
                # Extract core values
                name = str(row.get(mapping["name"], "")).strip()
                if not name or name == "nan":
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
                
                # Customer Voice fields (optional)
                cv_promoters = safe_int(row.get(mapping.get("cv_promoters", ""))) if mapping.get("cv_promoters") else 0
                cv_passives = safe_int(row.get(mapping.get("cv_passives", ""))) if mapping.get("cv_passives") else 0
                cv_detractors = safe_int(row.get(mapping.get("cv_detractors", ""))) if mapping.get("cv_detractors") else 0
                
                # Review Tracker field (optional)
                review_mentions = safe_int(row.get(mapping.get("review_mentions", ""))) if mapping.get("review_mentions") else 0
                
                # Legacy optional text fields
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
                emp = EmployeeV2(
                    name=name,
                    job_title=job_title,  # NEW: Job Title for hierarchy rankings
                    guests=guests,
                    net_sales=net_sales,
                    liquor_sales=liquor_sales,  # Individual input
                    beer_sales=beer_sales,      # Individual input
                    wine_sales=wine_sales,      # Individual input
                    # lbw is calculated automatically from liquor+beer+wine
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
        
        # Clear existing employees for this quarter
        await db.employees_v2.delete_many({"year": year, "quarter": quarter})
        
        # Insert scored employees
        for emp in scored_employees:
            doc = emp.model_dump()
            doc['created_at'] = doc['created_at'].isoformat()
            await db.employees_v2.insert_one(doc)
        
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
        
        # Get employee line graph for this quarter/year if available
        line_graph = await db.line_graphs.find_one(
            {
                "employee_id": employee_id,
                "quarter": review_data.quarter.upper(),
                "year": review_data.year,
                "graph_kind": "quarter",
            },
            {"_id": 0},
        )
        
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
        
        # Merge with line graph if available
        if line_graph and line_graph.get('file_data'):
            try:
                graph_pdf = _create_graph_pdf_from_image_bytes(base64.b64decode(line_graph['file_data']))
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
async def get_yodeck_top10_slide(year: int, quarter: str):
    """
    Generate Top 10 Performers slide (1920x1080 PNG).
    Shows the 10 highest scores OVERALL regardless of tier.
    Uses per-quarter theme settings.
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
    
    # Sort by total_score descending to get TOP 10 overall (not by tier)
    employees_docs.sort(key=lambda e: float(e.get("total_score", 0) or 0), reverse=True)
    
    # Add tier_label based on job_title and score for display
    a_server_min = settings.a_server_min_score or 80.1
    b_server_min = settings.b_server_min_score or 70.1
    
    for emp in employees_docs[:10]:
        job = str(emp.get("job_title", "server")).lower()
        score = float(emp.get("total_score", 0) or 0)
        
        if job == "trainer":
            emp["tier_label"] = "Trainer"
        elif job == "bartender":
            emp["tier_label"] = "Bartender"
        else:
            if score >= a_server_min:
                emp["tier_label"] = "A-Server"
            elif score >= b_server_min:
                emp["tier_label"] = "B-Server"
            else:
                emp["tier_label"] = "C-Server"
    
    rankings = employees_docs[:10]
    
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
    slide_bytes = generate_top_10_slide(
        rankings, quarter.upper(), year,
        theme=theme,
        custom_colors=custom_colors,
        custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme
    )
    
    filename = f"yodeck_top10_{quarter}_{year}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/complete-rankings")
async def get_yodeck_complete_rankings_slide(year: int, quarter: str):
    """
    Generate a complete rankings slide showing ALL employees top to bottom on one slide.
    Uses a compact multi-column layout with proper tier labels and circular progress.
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
        seasonal_theme=seasonal_theme
    )
    
    filename = f"yodeck_complete_rankings_{quarter}_{year}.png"
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
    
    # Build slide manifest
    max_per_page = 10
    slides = []
    
    # Top 10
    slides.append({
        "id": "top10",
        "name": "Top 10 Performers",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/top10",
        "pages": 1,
        "category": "primary"
    })
    
    # Complete Rankings (all employees on one slide)
    slides.append({
        "id": "complete-rankings",
        "name": "Complete Rankings",
        "description": "All team members top to bottom",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/complete-rankings",
        "employee_count": len(rankings),
        "pages": 1,
        "category": "primary"
    })
    
    # Tier slides
    for tier_key, tier_label in [
        ("trainers", "Trainer"),
        ("bartenders", "Bartender"),
        ("a-servers", "A-Server"),
        ("b-servers", "B-Server"),
        ("c-servers", "C-Server"),
    ]:
        count = tier_counts[tier_label]
        if count > 0:
            total_pages = (count + max_per_page - 1) // max_per_page
            slides.append({
                "id": tier_key,
                "name": f"{tier_label} Rankings",
                "endpoint": f"/api/v2/yodeck/{year}/{quarter}/tier/{tier_key}",
                "employee_count": count,
                "pages": total_pages,
                "category": "tier"
            })
    
    # Special slides
    slides.append({
        "id": "most-improved",
        "name": "Most Improved",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/most-improved",
        "pages": 1,
        "category": "special"
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
            "category": "special"
        })
    
    # At Risk (C-Servers) - manager only
    if tier_counts["C-Server"] > 0:
        slides.append({
            "id": "at-risk",
            "name": "Coaching Focus (Manager Only)",
            "endpoint": f"/api/v2/yodeck/{year}/{quarter}/at-risk",
            "employee_count": tier_counts["C-Server"],
            "pages": 1,
            "category": "manager"
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
async def get_yodeck_most_improved_slide(year: int, quarter: str):
    """Generate Most Improved slide - employees with biggest score increase."""
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
        seasonal_theme=seasonal_theme
    )
    
    filename = f"yodeck_most_improved_{quarter}_{year}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/promotion-watchlist")
async def get_yodeck_promotion_watchlist_slide(year: int, quarter: str):
    """Generate Promotion Watchlist slide - B-Servers close to A-Server threshold."""
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
        seasonal_theme=seasonal_theme
    )
    
    filename = f"yodeck_promotion_watchlist_{quarter}_{year}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/v2/yodeck/{year}/{quarter}/at-risk")
async def get_yodeck_at_risk_slide(year: int, quarter: str):
    """Generate At Risk / Coaching Focus slide - C-Servers needing attention. Manager only."""
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
        seasonal_theme=seasonal_theme
    )
    
    filename = f"yodeck_at_risk_{quarter}_{year}.png"
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
    """Generate Analytics PDF that matches the Analytics tab exactly, including charts."""
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak, Image as RLImage
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch
    import numpy as np
    
    employees_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    # Get settings for benchmarks
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ) or {}
    
    # Metric definitions matching the frontend
    metrics_config = {
        "ppa": {"label": "PPA", "benchmark_key": "benchmark_ppa", "default": 55.0, "higher_better": True, "format": "currency", "weight": "25%", "unit": "/guest"},
        "lbw_per_guest": {"label": "LBW/Guest", "benchmark_key": "benchmark_lbw", "default": 8.0, "higher_better": True, "format": "currency", "weight": "20%", "unit": "/guest"},
        "glassware_per_guest": {"label": "Glass/Guest", "benchmark_key": "benchmark_glass", "default": 1.25, "higher_better": True, "format": "currency", "weight": "15%", "unit": "/guest"},
        "guests_per_lsc": {"label": "Guests/LSC", "benchmark_key": "benchmark_lsc", "default": 100.0, "higher_better": False, "format": "number", "weight": "25%", "unit": " guests"},
        "cv_score": {"label": "CV Score", "benchmark_key": "benchmark_cv", "default": 5.0, "higher_better": True, "format": "number", "weight": "15%", "unit": " pts"},
    }
    
    def get_benchmark(metric_key):
        cfg = metrics_config[metric_key]
        return settings_doc.get(cfg["benchmark_key"], cfg["default"])
    
    def format_value(metric_key, value):
        if value is None:
            return "N/A"
        cfg = metrics_config[metric_key]
        if cfg["format"] == "currency":
            return f"${value:.2f}"
        return f"{value:.1f}"
    
    # Calculate analytics for each metric (matching frontend logic)
    analytics = {}
    for metric_key, cfg in metrics_config.items():
        values = [e.get(metric_key) for e in employees_docs if e.get(metric_key) is not None]
        if not values:
            continue
        
        benchmark = get_benchmark(metric_key)
        avg = sum(values) / len(values)
        min_val = min(values)
        max_val = max(values)
        
        if cfg["higher_better"]:
            high_threshold = benchmark * 1.1
            low_threshold = benchmark * 0.9
            high = sum(1 for v in values if v >= high_threshold)
            low = sum(1 for v in values if v < low_threshold)
            medium = len(values) - high - low
            meeting = sum(1 for v in values if v >= benchmark)
        else:
            high_threshold = benchmark * 0.9
            low_threshold = benchmark * 1.1
            high = sum(1 for v in values if v <= high_threshold)
            low = sum(1 for v in values if v >= low_threshold)
            medium = len(values) - high - low
            meeting = sum(1 for v in values if v <= benchmark)
        
        analytics[metric_key] = {
            "high": high, "medium": medium, "low": low,
            "meeting": meeting, "total": len(values),
            "average": avg, "min": min_val, "max": max_val,
            "benchmark": benchmark
        }
    
    # Calculate totals for summary
    total_high = sum(a["high"] for a in analytics.values())
    total_medium = sum(a["medium"] for a in analytics.values())
    total_low = sum(a["low"] for a in analytics.values())
    total_all = sum(a["total"] for a in analytics.values())
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.4*inch, bottomMargin=0.4*inch,
                          leftMargin=0.5*inch, rightMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle('title', parent=styles['Title'], fontName='Helvetica-Bold',
                                fontSize=22, textColor=rl_colors.HexColor('#1F2937'), alignment=1, spaceAfter=4)
    subtitle_style = ParagraphStyle('subtitle', parent=styles['Normal'], fontName='Helvetica',
                                   fontSize=11, textColor=rl_colors.HexColor('#6B7280'), alignment=1, spaceAfter=20)
    section_style = ParagraphStyle('section', parent=styles['Heading2'], fontName='Helvetica-Bold',
                                  fontSize=14, textColor=rl_colors.HexColor('#1F2937'), spaceBefore=16, spaceAfter=10)
    subsection_style = ParagraphStyle('subsection', parent=styles['Heading3'], fontName='Helvetica-Bold',
                                     fontSize=11, textColor=rl_colors.HexColor('#374151'), spaceBefore=10, spaceAfter=6)
    
    story = []
    
    # === TITLE ===
    story.append(Paragraph("Performance Analytics", title_style))
    story.append(Paragraph(f"{quarter} {year} • Bubba Gump Shrimp Co. • Las Vegas", subtitle_style))
    
    # === SCORE DISTRIBUTION SUMMARY (matching the 3-box layout) ===
    story.append(Paragraph("Score Distribution Summary", section_style))
    
    pct_high = round((total_high / total_all) * 100) if total_all > 0 else 0
    pct_medium = round((total_medium / total_all) * 100) if total_all > 0 else 0
    pct_low = round((total_low / total_all) * 100) if total_all > 0 else 0
    
    dist_data = [
        ["Exceeds Target", "Near Target", "Below Target"],
        [f"{pct_high}%", f"{pct_medium}%", f"{pct_low}%"],
        ["Top Performers", "On Track", "Needs Improvement"]
    ]
    
    dist_table = Table(dist_data, colWidths=[2.3*inch, 2.3*inch, 2.3*inch])
    dist_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TEXTCOLOR', (0, 0), (0, 0), rl_colors.HexColor('#166534')),
        ('TEXTCOLOR', (1, 0), (1, 0), rl_colors.HexColor('#854D0E')),
        ('TEXTCOLOR', (2, 0), (2, 0), rl_colors.HexColor('#9A3412')),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 28),
        ('TEXTCOLOR', (0, 1), (0, 1), rl_colors.HexColor('#22C55E')),
        ('TEXTCOLOR', (1, 1), (1, 1), rl_colors.HexColor('#EAB308')),
        ('TEXTCOLOR', (2, 1), (2, 1), rl_colors.HexColor('#F97316')),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica'),
        ('FONTSIZE', (0, 2), (-1, 2), 8),
        ('TEXTCOLOR', (0, 2), (-1, 2), rl_colors.HexColor('#6B7280')),
        ('BACKGROUND', (0, 0), (0, -1), rl_colors.HexColor('#F0FDF4')),
        ('BACKGROUND', (1, 0), (1, -1), rl_colors.HexColor('#FEFCE8')),
        ('BACKGROUND', (2, 0), (2, -1), rl_colors.HexColor('#FFF7ED')),
        ('BOX', (0, 0), (0, -1), 1, rl_colors.HexColor('#BBF7D0')),
        ('BOX', (1, 0), (1, -1), 1, rl_colors.HexColor('#FEF08A')),
        ('BOX', (2, 0), (2, -1), 1, rl_colors.HexColor('#FED7AA')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(dist_table)
    story.append(Spacer(1, 20))
    
    # === PERFORMANCE OVERVIEW CHARTS (matching the Analytics tab) ===
    story.append(Paragraph("Performance Overview", section_style))
    
    def create_metric_chart(metric_key, cfg, data, width=7, height=1.2):
        """Create a horizontal range chart for a metric matching the Analytics tab."""
        fig, ax = plt.subplots(figsize=(width, height))
        
        values = [e.get(metric_key) for e in employees_docs if e.get(metric_key) is not None]
        if not values:
            plt.close(fig)
            return None
        
        min_val = min(values)
        max_val = max(values)
        avg_val = sum(values) / len(values)
        benchmark = data["benchmark"]
        higher_better = cfg["higher_better"]
        
        # Calculate range with padding
        range_padding = (max_val - min_val) * 0.15 if max_val > min_val else max_val * 0.2
        chart_min = max(0, min_val - range_padding)
        chart_max = max_val + range_padding
        
        # Calculate zone thresholds
        if higher_better:
            high_threshold = benchmark * 1.1
            low_threshold = benchmark * 0.9
        else:
            high_threshold = benchmark * 0.9
            low_threshold = benchmark * 1.1
        
        # Draw gradient background zones
        ax.set_xlim(chart_min, chart_max)
        ax.set_ylim(0, 1)
        
        # Create gradient effect with zones
        if higher_better:
            # Red (left/low) -> Yellow (middle) -> Green (right/high)
            ax.axvspan(chart_min, low_threshold, alpha=0.3, color='#FEE2E2', zorder=1)
            ax.axvspan(low_threshold, high_threshold, alpha=0.3, color='#FEF9C3', zorder=1)
            ax.axvspan(high_threshold, chart_max, alpha=0.3, color='#DCFCE7', zorder=1)
        else:
            # Green (left/low) -> Yellow (middle) -> Red (right/high)
            ax.axvspan(chart_min, high_threshold, alpha=0.3, color='#DCFCE7', zorder=1)
            ax.axvspan(high_threshold, low_threshold, alpha=0.3, color='#FEF9C3', zorder=1)
            ax.axvspan(low_threshold, chart_max, alpha=0.3, color='#FEE2E2', zorder=1)
        
        # Draw the range bar (min to max)
        bar_height = 0.35
        bar_y = 0.5 - bar_height/2
        
        # Gradient bar from min to max
        gradient = np.linspace(0, 1, 100)
        for i, g in enumerate(gradient):
            x_pos = min_val + (max_val - min_val) * i / 100
            x_width = (max_val - min_val) / 100
            
            # Color based on position relative to benchmark
            if higher_better:
                if x_pos >= high_threshold:
                    color = '#22C55E'  # Green
                elif x_pos >= low_threshold:
                    color = '#EAB308'  # Yellow
                else:
                    color = '#EF4444'  # Red
            else:
                if x_pos <= high_threshold:
                    color = '#22C55E'  # Green
                elif x_pos <= low_threshold:
                    color = '#EAB308'  # Yellow
                else:
                    color = '#EF4444'  # Red
            
            ax.add_patch(plt.Rectangle((x_pos, bar_y), x_width, bar_height, 
                                       facecolor=color, edgecolor='none', alpha=0.8, zorder=2))
        
        # Draw benchmark line
        ax.axvline(x=benchmark, color='#1F2937', linestyle='--', linewidth=2, zorder=4, label='Benchmark')
        ax.annotate(f'Target: {format_value(metric_key, benchmark)}', 
                   xy=(benchmark, 0.92), fontsize=8, ha='center', color='#1F2937', fontweight='bold')
        
        # Draw average marker
        ax.plot(avg_val, 0.5, marker='D', markersize=10, color='#3B82F6', zorder=5, markeredgecolor='white', markeredgewidth=1.5)
        ax.annotate(f'Avg: {format_value(metric_key, avg_val)}', 
                   xy=(avg_val, 0.12), fontsize=8, ha='center', color='#3B82F6', fontweight='bold')
        
        # Draw min/max labels
        ax.annotate(f'Min: {format_value(metric_key, min_val)}', 
                   xy=(min_val, 0.5), fontsize=7, ha='right' if min_val > chart_min + (chart_max-chart_min)*0.1 else 'left', 
                   va='center', color='#6B7280')
        ax.annotate(f'Max: {format_value(metric_key, max_val)}', 
                   xy=(max_val, 0.5), fontsize=7, ha='left' if max_val < chart_max - (chart_max-chart_min)*0.1 else 'right',
                   va='center', color='#6B7280')
        
        # Title
        meeting_pct = round((data["meeting"] / data["total"]) * 100) if data["total"] > 0 else 0
        ax.set_title(f"{cfg['label']} ({cfg['weight']}) - {meeting_pct}% Meeting Benchmark", 
                    fontsize=10, fontweight='bold', color='#1F2937', loc='left', pad=8)
        
        # Clean up axes
        ax.set_yticks([])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='x', labelsize=7)
        
        plt.tight_layout()
        
        # Save to buffer
        chart_buffer = io.BytesIO()
        plt.savefig(chart_buffer, format='png', dpi=150, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        chart_buffer.seek(0)
        return chart_buffer
    
    # Generate and add charts for each metric
    for metric_key, cfg in metrics_config.items():
        data = analytics.get(metric_key, {})
        if not data:
            continue
        
        chart_buffer = create_metric_chart(metric_key, cfg, data)
        if chart_buffer:
            chart_img = RLImage(chart_buffer, width=6.8*inch, height=1.1*inch)
            story.append(chart_img)
            story.append(Spacer(1, 8))
    
    story.append(Spacer(1, 10))
    
    # === METRIC-BY-METRIC BREAKDOWN ===
    story.append(Paragraph("Performance by Metric", section_style))
    
    metric_header = ["Metric", "Weight", "Benchmark", "Team Avg", "Exceeds", "Near", "Below", "% Meeting"]
    metric_rows = [metric_header]
    
    for metric_key, cfg in metrics_config.items():
        data = analytics.get(metric_key, {})
        if not data:
            continue
        
        benchmark = data["benchmark"]
        avg = data["average"]
        meeting_pct = round((data["meeting"] / data["total"]) * 100) if data["total"] > 0 else 0
        
        metric_rows.append([
            cfg["label"],
            cfg["weight"],
            format_value(metric_key, benchmark),
            format_value(metric_key, avg),
            str(data["high"]),
            str(data["medium"]),
            str(data["low"]),
            f"{meeting_pct}%"
        ])
    
    metric_table = Table(metric_rows, colWidths=[1.1*inch, 0.6*inch, 0.85*inch, 0.85*inch, 0.65*inch, 0.6*inch, 0.6*inch, 0.85*inch])
    metric_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#60A5FA')),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), rl_colors.HexColor('#F9FAFB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.HexColor('#FFFFFF'), rl_colors.HexColor('#F3F4F6')]),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#E5E7EB')),
        ('TEXTCOLOR', (4, 1), (4, -1), rl_colors.HexColor('#166534')),
        ('TEXTCOLOR', (5, 1), (5, -1), rl_colors.HexColor('#854D0E')),
        ('TEXTCOLOR', (6, 1), (6, -1), rl_colors.HexColor('#DC2626')),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 20))
    
    # === TOP 10 OVERALL ===
    story.append(Paragraph("Top 10 Overall (Total Score)", section_style))
    
    # Sort by total_score descending
    sorted_by_score = sorted(employees_docs, key=lambda e: float(e.get("total_score", 0) or 0), reverse=True)[:10]
    
    top10_header = ["Rank", "Employee", "Performance Tier", "Total Score"]
    top10_rows = [top10_header]
    
    for idx, emp in enumerate(sorted_by_score, 1):
        top10_rows.append([
            f"#{idx}",
            emp.get("name", "Unknown"),
            emp.get("performance_tier", "Not Assessed"),
            f"{float(emp.get('total_score', 0) or 0):.1f}"
        ])
    
    top10_table = Table(top10_rows, colWidths=[0.6*inch, 2.2*inch, 1.8*inch, 1.2*inch])
    top10_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#60A5FA')),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.HexColor('#FFFFFF'), rl_colors.HexColor('#F3F4F6')]),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#E5E7EB')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 1), (0, -1), rl_colors.HexColor('#DC2626')),
    ]))
    story.append(top10_table)
    
    # Page break before Top 10 by Metric
    story.append(PageBreak())
    
    # === TOP 10 BY METRIC (2-column layout) ===
    story.append(Paragraph("Top 10 by Metric", section_style))
    
    def create_metric_top10_table(metric_key, cfg):
        """Create a top 10 table for a specific metric."""
        higher_better = cfg["higher_better"]
        sorted_emps = sorted(
            [e for e in employees_docs if e.get(metric_key) is not None],
            key=lambda e: float(e.get(metric_key, 0) or 0),
            reverse=higher_better
        )[:10]
        
        rows = [[f"{cfg['label']} - Top 10", "", ""]]
        rows.append(["Rank", "Employee", "Value"])
        
        for idx, emp in enumerate(sorted_emps, 1):
            rows.append([
                f"#{idx}",
                emp.get("name", "Unknown")[:15],
                format_value(metric_key, emp.get(metric_key))
            ])
        
        table = Table(rows, colWidths=[0.5*inch, 1.5*inch, 0.9*inch])
        table.setStyle(TableStyle([
            ('SPAN', (0, 0), (-1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#1F2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
            ('BACKGROUND', (0, 1), (-1, 1), rl_colors.HexColor('#60A5FA')),
            ('TEXTCOLOR', (0, 1), (-1, 1), rl_colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 2), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 2), (-1, -1), [rl_colors.HexColor('#FFFFFF'), rl_colors.HexColor('#F3F4F6')]),
            ('GRID', (0, 1), (-1, -1), 0.5, rl_colors.HexColor('#E5E7EB')),
            ('FONTNAME', (0, 2), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 2), (0, -1), rl_colors.HexColor('#DC2626')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        return table
    
    # Create pairs of metric tables (2-column layout)
    metric_keys = list(metrics_config.keys())
    for i in range(0, len(metric_keys), 2):
        left_key = metric_keys[i]
        left_table = create_metric_top10_table(left_key, metrics_config[left_key])
        
        if i + 1 < len(metric_keys):
            right_key = metric_keys[i + 1]
            right_table = create_metric_top10_table(right_key, metrics_config[right_key])
            row_table = Table([[left_table, right_table]], colWidths=[3.5*inch, 3.5*inch])
        else:
            row_table = Table([[left_table, ""]], colWidths=[3.5*inch, 3.5*inch])
        
        row_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(row_table)
        story.append(Spacer(1, 15))
    
    # === FOOTER ===
    story.append(Spacer(1, 20))
    footer_style = ParagraphStyle('footer', parent=styles['Normal'], fontSize=8, 
                                 textColor=rl_colors.HexColor('#9CA3AF'), alignment=1)
    story.append(Paragraph(f"Generated {datetime.now().strftime('%m/%d/%Y %H:%M')} • Confidential", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=analytics_{quarter}_{year}.pdf"}
    )


# ============================================================================
# TREND CHART ENDPOINTS
# ============================================================================

from trend_charts import (
    generate_employee_comparison_chart, generate_employee_change_chart,
    generate_team_comparison_chart, generate_tier_distribution_chart,
    get_previous_quarter, chart_to_base64
)


@api_router.get("/v2/trends/{year}/{quarter}/employee/{employee_id}")
async def get_employee_trend_chart(year: int, quarter: str, employee_id: str, chart_type: str = "comparison"):
    """
    Generate trend chart for an individual employee comparing current vs previous quarter.
    
    chart_type: "comparison" (bar chart) or "change" (% change chart)
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
        chart_bytes = generate_employee_comparison_chart(
            current_doc.get("name", "Employee"),
            current_doc, previous_doc,
            quarter.upper(), year
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


@api_router.get("/v2/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    """Get a specific snapshot by ID."""
    snapshot = await db.snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


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
        
        employees = []
        for idx, row in df.iterrows():
            try:
                name = str(row.get(mapping["name"], "")).strip()
                if not name or name == "nan":
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
                
                # Calculate metrics and scores
                emp = calculate_derived_metrics(emp)
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
        
        return {
            "message": "Snapshot data uploaded successfully",
            "employee_count": len(employees)
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")


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


@api_router.get("/v2/snapshots/backgrounds")
async def get_snapshot_backgrounds():
    """Get available background options for snapshots."""
    return get_available_backgrounds()


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