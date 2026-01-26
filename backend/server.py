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
from pdf_top_performers import build_top_performers_pdf
from pdf_analytics import build_analytics_pdf
from pdf_full_rankings import build_full_rankings_pdf

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

KPI_DEFINITIONS = {
    "ppa": {"name": "Per Person Average (PPA)", "format": "currency", "benchmark": 55.0},
    "gpg": {"name": "Glassware $ Per Guest (GPG)", "format": "currency", "benchmark": 1.0},
    "pplbw": {"name": "Per Person Liquor Beer Wine (PPLBW)", "format": "currency", "benchmark": 8.0},
    "lsc_ratio": {"name": "Landry's Select Card Ratio (LSC)", "format": "ratio", "benchmark": 0.01},
    "metric_bonus_points": {"name": "Metric Bonus Points", "format": "number", "benchmark": 5},
    "cumulative_score": {"name": "Cumulative Score", "format": "number", "benchmark": 80},
}


# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Define Models
class Employee(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    position: str
    ppa: Optional[float] = None
    gpg: Optional[float] = None 
    pplbw: Optional[float] = None
    lsc_ratio: Optional[float] = None
    metric_bonus_points: Optional[float] = None
    cumulative_score: Optional[float] = None
    overall_rank: Optional[str] = None
    ranking: Optional[str] = None
    performance_tier: Optional[str] = None
    additional_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EmployeeCreate(BaseModel):
    name: str
    position: str
    ppa: Optional[float] = None
    gpg: Optional[float] = None
    pplbw: Optional[float] = None
    lsc_ratio: Optional[float] = None
    metric_bonus_points: Optional[float] = None
    cumulative_score: Optional[float] = None
    overall_rank: Optional[str] = None
    ranking: Optional[str] = None
    performance_tier: Optional[str] = None
    additional_data: Dict[str, Any] = Field(default_factory=dict)

class Review(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    employee_name: str
    review_content: str
    quarter: str
    year: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReviewCreate(BaseModel):
    quarter: str = "Q4"
    year: int = 2024


class ReviewResponse(BaseModel):
    success: bool
    review_id: Optional[str] = None
    message: str
    pdf_base64: Optional[str] = None

class LineGraph(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    quarter: str
    year: int
    graph_kind: str = "quarter"  # quarter | ytd
    filename: str
    content_type: str
    file_data: str  # base64 encoded file bytes
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LineGraphUpload(BaseModel):
    quarter: str = "Q4"
    year: int = 2024
    success: bool
    review_id: Optional[str] = None
    message: str
    pdf_base64: Optional[str] = None

# Helper function to generate review content
# Helper functions
def format_overall_rank(rank_value):
    """Convert overall rank to proper string format"""
    if rank_value is None or pd.isna(rank_value):
        return None
    
    # If it's already a string like "9 of 26", return as is
    if isinstance(rank_value, str):
        if ' of ' in rank_value:
            return rank_value
        # If it's just a number as string, convert it
        try:
            rank_num = int(rank_value)
            return f"{rank_num} of 26"
        except ValueError:
            return str(rank_value)
    
    # If it's a number, convert to "X of 26" format
    if isinstance(rank_value, (int, float)):
        return f"{int(rank_value)} of 26"
    
    return str(rank_value)

def format_currency_for_prompt(value):
    """Format currency for GPT prompt"""
    if value is None:
        return 'N/A'
    return f"${float(value):.2f}"

def format_lsc_ratio(value):
    """Format LSC ratio as '1 in xxx'"""
    if value is None or value == 0:
        return 'N/A'
    try:
        # The value is already the denominator (e.g., 34 means "1 in 34")
        ratio = round(float(value))
        return f"1 in {ratio}"
    except (ValueError, ZeroDivisionError):
        return 'N/A'

async def generate_review_content(employee: Employee, quarter: str, year: int) -> str:
    try:
        # Initialize LLM Chat
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            raise ValueError("EMERGENT_LLM_KEY not found in environment variables")
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"review_{employee.id}_{quarter}_{year}",
            system_message="You are an expert HR professional specializing in creating comprehensive quarterly employee reviews for restaurant staff. Your reviews should be professional, human-like, and HR-defensible while maintaining a positive and constructive tone."
        ).with_model("openai", "gpt-5.2")
        
        # Extract peer rankings from additional data
        peer_rankings = {
            'ppa': employee.additional_data.get('ppa rank vs peers', 'N/A'),
            'gpg': employee.additional_data.get('gpg vs peers', 'N/A'),
            'pplbw': employee.additional_data.get('pplbw vs peers', 'N/A'),
            'lsc_ratio': employee.additional_data.get('lsc ratio vs peers', 'N/A'),
            'metric_bonus': employee.additional_data.get('metric bonus points vs peers', 'N/A'),
            'cumulative': employee.additional_data.get('cummulative score vs peers', 'N/A')
        }

        # Per-metric tiers (Top Performer / Meets Expectations / Below Expectations / Needs Immediate Improvement)
        metric_tiers = employee.additional_data.get("metric_tiers", {}) or {}
        tiers_text = (
            f"TIERS BY METRIC (from spreadsheet):\n"
            f"- PPA Tier: {metric_tiers.get('ppa', 'N/A')}\n"
            f"- GPG Tier: {metric_tiers.get('gpg', 'N/A')}\n"
            f"- PPLBW Tier: {metric_tiers.get('pplbw', 'N/A')}\n"
            f"- LSC Ratio Tier: {metric_tiers.get('lsc_ratio', 'N/A')}\n"
            f"- Metric Bonus Tier: {metric_tiers.get('metric_bonus_points', 'N/A')}\n"
            f"- Cumulative Score Tier: {metric_tiers.get('cumulative_score', 'N/A')}\n"
        )

        # IMPORTANT: Use these tiers as the source of truth. Do NOT invent tiers.
        # If a tier is N/A, omit that metric tier from narrative rather than guessing.

        
        # Create detailed prompt
        prompt = f"""
Create a concise quarterly review for {employee.name}, a {employee.position} at Bubba Gump Shrimp Co.

PERFORMANCE METRICS WITH PEER RANKINGS:
- PPA (Per Person Average): {format_currency_for_prompt(employee.ppa)} - Ranked {peer_rankings['ppa']} (Benchmark: $55.00)
- GPG (Glassware $ Per Guest): {format_currency_for_prompt(employee.gpg)} - Ranked {peer_rankings['gpg']} (Benchmark: $1.00)
- PPLBW (Per Person Liquor Beer Wine): {format_currency_for_prompt(employee.pplbw)} - Ranked {peer_rankings['pplbw']} (Benchmark: $8.00)
- LSC Ratio (Landry's Select Card): {format_lsc_ratio(employee.lsc_ratio)} - Ranked {peer_rankings['lsc_ratio']} (Benchmark: 1 in 100)
- Metric Bonus Points: {employee.metric_bonus_points or 'N/A'} - Ranked {peer_rankings['metric_bonus']} (Exceeds benchmarks)
- Cumulative Score: {employee.cumulative_score or 'N/A'} - Ranked {peer_rankings['cumulative']} (Final grade)

OVERALL RANKING: {employee.overall_rank or 'N/A'} | POSITION LEVEL: {employee.ranking or 'N/A'}

{tiers_text}
REVIEW REQUIREMENTS:
1. Write EXACTLY 2 paragraphs - no more, no less
2. First paragraph: Performance highlights and peer ranking context
3. Second paragraph: Areas for growth and next quarter goals
4. Be conversational, HR-defensible, and maintain Bubba Gump's friendly culture
5. Reference specific KPIs and peer rankings to provide context
6. Total length: 150-250 words maximum

PLEASE DO NOT include any headers, titles, or formatting markers. Just provide exactly 2 paragraphs of review content.
"""
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        return response
        
    except Exception as e:
        logging.error(f"Error generating review content: {str(e)}")
        return f"Unable to generate personalized review at this time. Please contact HR for manual review processing. Employee: {employee.name}, Position: {employee.position}"

# Helper function to generate PDF
def generate_pdf(employee: Employee, review_content: str, quarter: str, year: int, line_graph=None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.4*inch, bottomMargin=0.4*inch,
                          leftMargin=0.6*inch, rightMargin=0.6*inch)
    
    # Create custom styles optimized for single page
    styles = getSampleStyleSheet()
    
    # Compact styles for single page layout
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
    
    # Build PDF content optimized for single page
    story = []
    
    try:
        # Download and add logo
        logo_url = "https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png"
        response = requests.get(logo_url)
        logo_buffer = BytesIO(response.content)
        
        # Create logo image - increased size (~30%) but still fits single page
        logo_img = Image(logo_buffer, width=0.78*inch, height=0.78*inch)
        logo_img.hAlign = 'CENTER'
        story.append(logo_img)
        story.append(Spacer(1, 3))
    except Exception:
        # If logo fails to load, continue without it
        pass
    
    # Header section with compact branding
    story.append(Paragraph("🦐 BUBBA GUMP SHRIMP CO. 🦐", title_style))
    story.append(Paragraph("Restaurant & Market • Las Vegas", subtitle_style))
    story.append(Spacer(1, 7))
    
    # Review title
    story.append(Paragraph(f"QUARTERLY PERFORMANCE REVIEW - {quarter} {year}", header_style))
    story.append(Spacer(1, 8))
    
    # Compact employee info section
    emp_info_data = [
        ["Employee:", employee.name, "Position:", employee.position],
        ["Review Period:", f"{quarter} {year}", "Overall Rank:", employee.overall_rank or 'N/A'],
        ["Ranking Level:", employee.ranking or 'N/A', "Date Generated:", datetime.now().strftime("%m/%d/%Y")]
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
    
    # KPI Performance Metrics with Peer Rankings
    story.append(Paragraph("KEY PERFORMANCE INDICATORS & PEER RANKINGS", header_style))
    
    # Extract peer rankings
    peer_rankings = {
        'ppa': employee.additional_data.get('ppa rank vs peers', 'N/A'),
        'gpg': employee.additional_data.get('gpg vs peers', 'N/A'), 
        'pplbw': employee.additional_data.get('pplbw vs peers', 'N/A'),
        'lsc_ratio': employee.additional_data.get('lsc ratio vs peers', 'N/A'),
        'metric_bonus': employee.additional_data.get('metric bonus points vs peers', 'N/A'),
        'cumulative': employee.additional_data.get('cummulative score vs peers', 'N/A')
    }
    
    # Performance tier labels from spreadsheet (preferred, per user). Fallback to computed level if missing.
    metric_tiers = employee.additional_data.get("metric_tiers", {}) or {}

    def tier_or_fallback(metric_key: str, fallback_value):
        tier = metric_tiers.get(metric_key)
        return tier if tier else get_performance_level(fallback_value)

    kpi_data = [
        ["Metric", "Score", "Peer Rank", "Tier"],
        ["PPA (Per Person Average)", format_currency_for_prompt(employee.ppa), peer_rankings['ppa'], tier_or_fallback('ppa', employee.ppa)],
        ["GPG (Glassware $ Per Guest)", format_currency_for_prompt(employee.gpg), peer_rankings['gpg'], tier_or_fallback('gpg', employee.gpg)],
        ["PPLBW (Per Person Liquor Beer Wine)", format_currency_for_prompt(employee.pplbw), peer_rankings['pplbw'], tier_or_fallback('pplbw', employee.pplbw)],
        ["LSC Ratio (Landry's Select Card)", format_lsc_ratio(employee.lsc_ratio), peer_rankings['lsc_ratio'], tier_or_fallback('lsc_ratio', employee.lsc_ratio)],
        ["Metric Bonus Points", str(employee.metric_bonus_points or 'N/A'), peer_rankings['metric_bonus'], tier_or_fallback('metric_bonus_points', employee.metric_bonus_points)],
        ["Cumulative Score", str(employee.cumulative_score or 'N/A'), peer_rankings['cumulative'], tier_or_fallback('cumulative_score', employee.cumulative_score)]
    ]
    
    # Match the full content width (A4: 595.27pt; margins: 0.6"+0.6" => 86.4pt)
    # Available width ≈ 508.9pt = 7.07 inches
    kpi_table = Table(kpi_data, colWidths=[2.75*inch, 1.15*inch, 1.05*inch, 2.12*inch])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#005B96')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFFFFF')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F9F9F9'), colors.white])
    ]))
    
    story.append(kpi_table)
    story.append(Spacer(1, 10))
    
    # Compact review content section
    story.append(Paragraph("PERFORMANCE REVIEW", header_style))
    
    # Split review content into paragraphs and format compactly
    paragraphs = [p.strip() for p in review_content.split('\n\n') if p.strip()]
    for paragraph in paragraphs:
        story.append(Paragraph(paragraph, body_style))
    
    story.append(Spacer(1, 14))
    
    # Compact signature section
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
    
    # Compact footer
    story.append(Spacer(1, 10))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#005B96'),
        alignment=TA_CENTER
    )
    story.append(Paragraph("🦐 Bubba Gump Shrimp Co. • Confidential Employee Review • Generated by Performance Management System 🦐", footer_style))
    
    # Line graph PDFs/images are appended as page 2 via pypdf in generate_employee_review.
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()



def _create_graph_pdf_from_image_bytes(image_bytes: bytes) -> bytes:
    """Create a 1-page PDF that contains the given image (png/jpg) scaled to fit."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    story: List[Any] = []
    story.append(Spacer(1, 12))
    story.append(Image(BytesIO(image_bytes), width=6.8 * inch, height=9.2 * inch))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _merge_review_with_graph(review_pdf: bytes, graph_doc: Dict[str, Any]) -> bytes:
    """Append the uploaded graph (PDF or image) as page 2+ without distorting its native page size."""
    if not graph_doc or not graph_doc.get("file_data"):
        return review_pdf

    graph_bytes = base64.b64decode(graph_doc["file_data"])
    is_pdf = (
        graph_doc.get("content_type") == "application/pdf"
        or (graph_doc.get("filename") or "").lower().endswith(".pdf")
    )

    if not is_pdf:
        graph_bytes = _create_graph_pdf_from_image_bytes(graph_bytes)

    writer = PdfWriter()

    review_reader = PdfReader(BytesIO(review_pdf))
    for page in review_reader.pages:
        writer.add_page(page)

    graph_reader = PdfReader(BytesIO(graph_bytes))
    for page in graph_reader.pages:
        writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.getvalue()

def get_performance_level(score):
    """Helper function to determine performance level based on score"""
    if score is None:
        return "Not Assessed"
    try:
        score = float(score)
        if score >= 90:
            return "Excellent"
        elif score >= 80:
            return "Above Average"
        elif score >= 70:
            return "Satisfactory"
        elif score >= 60:
            return "Needs Improvement"
        else:
            return "Below Expectations"
    except (ValueError, TypeError):
        return "Not Assessed"


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

@api_router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only Excel files are allowed")
    
    try:
        # Read Excel file
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Clean column names (remove extra spaces, convert to lowercase)
        df.columns = df.columns.str.strip().str.lower()
        
        employees_added = 0
        for _, row in df.iterrows():
            # Create employee object with flexible column mapping - try multiple column name variations
            employee_data = {
                'name': row.get('name', row.get('employee_name', row.get('employee', 'Unknown'))),
                'position': row.get('position', row.get('job_title', row.get('title', 'Staff'))),
                'ppa': row.get('ppa', None),
                'gpg': row.get('gpg', None),
                'pplbw': row.get('pplbw', None),
                'lsc_ratio': row.get('lsc_ratio', row.get('lsc ratio', None)),
                'metric_bonus_points': row.get('metric_bonus_points', row.get('metric bonus points', row.get('bonus_points', row.get('bonus points', None)))),
                'cumulative_score': row.get('cumulative_score', row.get('cumulative score', row.get('cummulative_score', row.get('cummulative score', row.get('total_score', row.get('total score', None)))))),
                'overall_rank': format_overall_rank(row.get('overall_rank', row.get('overall rank', None))),
                'ranking': str(row.get('ranking', row.get('rank', ''))) if pd.notna(row.get('ranking', row.get('rank', None))) else None,
                'performance_tier': str(row.get('performance_tier', row.get('performance tier', ''))) if pd.notna(row.get('performance_tier', row.get('performance tier', None))) else None
            }
            
            # Add any additional columns to additional_data
            additional_data = {}

            # Per-metric tiers
            metric_tiers = {}
            for metric_key, candidates in TIER_COLUMN_MAP.items():
                metric_tiers[metric_key] = _first_non_empty(row, candidates)
            additional_data["metric_tiers"] = metric_tiers

            for col in df.columns:
                if col not in ['name', 'employee_name', 'employee', 'position', 'job_title', 'title', 'ppa', 'gpg', 'pplbw', 'lsc_ratio', 'lsc ratio', 'bonus_points', 'bonus points', 'metric_bonus_points', 'metric bonus points', 'total_score', 'total score', 'cumulative_score', 'cumulative score', 'cummulative_score', 'cummulative score', 'overall_rank', 'overall rank', 'ranking', 'rank', 'performance_tier', 'performance tier',
                               'ppa tier', 'pplbw tier', 'lsc ratio tier', 'lsc_ratio tier', 'gpg tier', 'metirc bonus tier', 'metric bonus tier', 'metric bonus points tier', 'cummulative score tier', 'cumulative score tier']:
                    additional_data[col] = str(row[col]) if pd.notna(row[col]) else None
            
            employee_data['additional_data'] = additional_data
            
            # Create employee object
            employee = Employee(**employee_data)
            
            # Convert to dict and serialize datetime
            doc = employee.model_dump()
            doc['created_at'] = doc['created_at'].isoformat()
            
            # Insert into database
            await db.employees.insert_one(doc)
            employees_added += 1
        
        return {
            "success": True,
            "message": f"Successfully processed {employees_added} employees",
            "employees_count": employees_added
        }
        
    except Exception as e:
        logging.error(f"Error processing Excel file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@api_router.get("/employees", response_model=List[Employee])
async def get_employees():
    employees = await db.employees.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for emp in employees:
        if isinstance(emp['created_at'], str):
            emp['created_at'] = datetime.fromisoformat(emp['created_at'])
    
    return employees

@api_router.get("/employees/{employee_id}", response_model=Employee)
async def get_employee(employee_id: str):
    employee = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if isinstance(employee['created_at'], str):
        employee['created_at'] = datetime.fromisoformat(employee['created_at'])
    
    return employee

@api_router.post("/employees/{employee_id}/generate-review", response_model=ReviewResponse)
async def generate_employee_review(employee_id: str, review_data: ReviewCreate):
    # Get employee
    employee_doc = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not employee_doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Convert to Employee object
    if isinstance(employee_doc['created_at'], str):
        employee_doc['created_at'] = datetime.fromisoformat(employee_doc['created_at'])
    
    employee = Employee(**employee_doc)
    
    try:
        # Generate review content
        review_content = await generate_review_content(employee, review_data.quarter, review_data.year)
        
        # Get employee line graph for this quarter/year if available
        line_graph = await db.line_graphs.find_one(
            {
                "employee_id": employee_id,
                "quarter": review_data.quarter,
                "year": review_data.year,
                "graph_kind": "quarter",
            },
            {"_id": 0},
        )
        
        # Create review record
        review = Review(
            employee_id=employee_id,
            employee_name=employee.name,
            review_content=review_content,
            quarter=review_data.quarter,
            year=review_data.year
        )
        
        # Save review to database
        review_doc = review.model_dump()
        review_doc['created_at'] = review_doc['created_at'].isoformat()
        await db.reviews.insert_one(review_doc)
        
        # Generate base (single-page) review PDF, then append graph PDF (page 2) if present
        base_pdf = generate_pdf(employee, review_content, review_data.quarter, review_data.year, None)
        merged_pdf = _merge_review_with_graph(base_pdf, line_graph) if line_graph else base_pdf
        pdf_base64 = base64.b64encode(merged_pdf).decode('utf-8')
        
        return ReviewResponse(
            success=True,
            review_id=review.id,
            message="Review generated successfully",
            pdf_base64=pdf_base64
        )
        
    except Exception as e:
        logging.error(f"Error generating review: {str(e)}")
        return ReviewResponse(
            success=False,
            message=f"Error generating review: {str(e)}"
        )

@api_router.get("/reviews", response_model=List[Review])
async def get_reviews():
    reviews = await db.reviews.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for review in reviews:
        if isinstance(review['created_at'], str):
            review['created_at'] = datetime.fromisoformat(review['created_at'])
    
    return reviews

@api_router.post("/line-graphs")
async def upload_line_graph(
    quarter: str,
    year: int,
    employee_id: str,
    graph_kind: str = "quarter",
    file: UploadFile = File(...),
):
    filename_lower = (file.filename or "").lower()
    content_type_lower = (file.content_type or "").lower()

    allowed_content_types = {"image/png", "image/jpeg", "application/pdf"}
    allowed_extensions = (".png", ".jpg", ".jpeg", ".pdf")

    # iOS/Safari sometimes uploads images with no extension; prefer content-type check.
    if not (
        content_type_lower in allowed_content_types
        or filename_lower.endswith(allowed_extensions)
    ):
        raise HTTPException(
            status_code=400,
            detail="Only image files (PNG, JPG) or PDF files are allowed",
        )

    if graph_kind not in {"quarter", "ytd"}:
        raise HTTPException(status_code=400, detail="graph_kind must be 'quarter' or 'ytd'")

    try:
        contents = await file.read()
        file_base64 = base64.b64encode(contents).decode("utf-8")

        line_graph = LineGraph(
            employee_id=employee_id,
            quarter=quarter,
            year=year,
            graph_kind=graph_kind,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            file_data=file_base64,
        )

        graph_doc = line_graph.model_dump()
        graph_doc["created_at"] = graph_doc["created_at"].isoformat()

        # One graph per employee per period per kind
        await db.line_graphs.delete_many(
            {
                "employee_id": employee_id,
                "quarter": quarter,
                "year": year,
                "graph_kind": graph_kind,
            }
        )

        await db.line_graphs.insert_one(graph_doc)

        return {
            "success": True,
            "message": f"Line graph uploaded for {employee_id} ({quarter} {year}, {graph_kind})",
            "graph_id": line_graph.id,
        }

    except Exception as e:
        logging.error(f"Error uploading line graph: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading graph: {str(e)}")

@api_router.get("/line-graphs")
async def get_line_graphs(employee_id: Optional[str] = None):
    query: Dict[str, Any] = {}
    if employee_id:
        query["employee_id"] = employee_id

    graphs = await db.line_graphs.find(query, {"_id": 0}).to_list(200)
    
    # Convert ISO string timestamps back to datetime objects
    for graph in graphs:
        if isinstance(graph['created_at'], str):
            graph['created_at'] = datetime.fromisoformat(graph['created_at'])
    
    return graphs

@api_router.get("/line-graphs/{employee_id}/{quarter}/{year}")
async def get_line_graph(employee_id: str, quarter: str, year: int, graph_kind: str = "quarter"):
    graph = await db.line_graphs.find_one(
        {"employee_id": employee_id, "quarter": quarter, "year": year, "graph_kind": graph_kind},
        {"_id": 0},
    )
    if not graph:
        raise HTTPException(status_code=404, detail="Line graph not found for this period")
    
    if isinstance(graph['created_at'], str):
        graph['created_at'] = datetime.fromisoformat(graph['created_at'])
    
    return graph

@api_router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: str):
    result = await db.employees.delete_one({"id": employee_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"success": True, "message": "Employee deleted successfully"}

@api_router.delete("/employees")
async def clear_all_employees():
    result = await db.employees.delete_many({})
    return {
        "success": True,
        "message": f"Cleared {result.deleted_count} employees",
        "deleted_count": result.deleted_count,
    }


@api_router.get("/top-performers/pdf")

@api_router.get("/analytics/pdf")
async def analytics_pdf():
    employees = await db.employees.find({}, {"_id": 0}).to_list(5000)

    # Benchmark-relative buckets (10% above = High, 10% below = Low, otherwise Medium)
    metrics = ["ppa", "gpg", "pplbw", "lsc_ratio", "metric_bonus_points", "cumulative_score"]
    analytics: Dict[str, Dict[str, Any]] = {}

    for metric in metrics:
        values = [e.get(metric) for e in employees]
        valid_values = [v for v in values if v is not None and isinstance(v, (int, float))]

        benchmark_val = KPI_DEFINITIONS.get(metric, {}).get("benchmark", 0)

        if not valid_values:
            analytics[metric] = {
                "high": 0,
                "medium": 0,
                "low": 0,
                "benchmark": 0,
                "average": 0,
                "total": 0,
                "highThreshold": 0,
                "lowThreshold": 0,
                "benchmarkValue": benchmark_val,
            }
            continue

        avg = sum(valid_values) / len(valid_values)

        high = medium = low = above_benchmark = 0

        if metric == "lsc_ratio":
            benchmark_denominator = round(1 / benchmark_val) if benchmark_val else 0
            high_threshold = round(benchmark_denominator * 0.9) if benchmark_denominator else 0
            low_threshold = round(benchmark_denominator * 1.1) if benchmark_denominator else 0

            for v in valid_values:
                if v <= high_threshold:
                    high += 1
                elif v >= low_threshold:
                    low += 1
                else:
                    medium += 1

                if benchmark_denominator and v <= benchmark_denominator:
                    above_benchmark += 1

            analytics[metric] = {
                "high": high,
                "medium": medium,
                "low": low,
                "benchmark": above_benchmark,
                "average": avg,
                "total": len(valid_values),
                "highThreshold": high_threshold,
                "lowThreshold": low_threshold,
                "benchmarkValue": benchmark_val,
            }
            continue

        # Normal metrics
        if benchmark_val:
            high_threshold = benchmark_val * 1.1
            low_threshold = benchmark_val * 0.9

            for v in valid_values:
                if v >= high_threshold:
                    high += 1
                elif v < low_threshold:
                    low += 1
                else:
                    medium += 1

                if v >= benchmark_val:
                    above_benchmark += 1
        else:
            # No benchmark defined
            medium = len(valid_values)
            high_threshold = 0
            low_threshold = 0

        analytics[metric] = {
            "high": high,
            "medium": medium,
            "low": low,
            "benchmark": above_benchmark,
            "average": avg,
            "total": len(valid_values),
            "highThreshold": high_threshold,
            "lowThreshold": low_threshold,
            "benchmarkValue": benchmark_val,
        }

    pdf_bytes = build_analytics_pdf(analytics, KPI_DEFINITIONS)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=analytics_report.pdf"},
    )

async def top_performers_pdf():
    employees = await db.employees.find({}, {"_id": 0}).to_list(5000)
    pdf_bytes = build_top_performers_pdf(employees, KPI_DEFINITIONS)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=top_performers_report.pdf"},
    )


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
    """Update quarter settings (only if not locked)"""
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()}, 
        {"_id": 0}
    )
    if not settings:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    if settings.get("is_locked"):
        raise HTTPException(
            status_code=403, 
            detail=f"Settings for {quarter} {year} are locked. Scores have already been generated."
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
    """
    template_content = """Employee Name,Job Title,Guests,Net Sales,Liquor Sales,Beer Sales,Wine Sales,Glassware Sales,LSC Count,CV Promoters,CV Passives,CV Detractors,Review Mentions
John Smith,Server,450,24750,1500,1350,1200,540,5,3,2,1,8
Jane Doe,Bartender,520,28600,1800,1500,1380,624,9,5,1,0,12
Sarah Johnson,Trainer,400,22000,1200,1200,1200,480,4,2,3,2,5"""
    
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
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
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
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Validate columns
        column_validation = validate_upload_columns(list(df.columns))
        
        if not column_validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns: {', '.join(column_validation['missing'])}"
            )
        
        mapping = column_validation["mapping"]
        employees = []
        
        for idx, row in df.iterrows():
            try:
                # Extract core values
                name = str(row.get(mapping["name"], "")).strip()
                guests = int(row.get(mapping["guests"], 0))
                net_sales = float(row.get(mapping["net_sales"], 0))
                
                # Job Title (optional) - for hierarchy-based rankings
                job_title = "Server"  # Default
                if mapping.get("job_title"):
                    val = row.get(mapping["job_title"])
                    if not pd.isna(val) and str(val).strip():
                        job_title = str(val).strip()
                
                # Individual alcohol sales (required) - LBW calculated automatically
                liquor_val = row.get(mapping["liquor_sales"])
                beer_val = row.get(mapping["beer_sales"])
                wine_val = row.get(mapping["wine_sales"])
                
                # Treat missing/blank as zero
                liquor_sales = float(liquor_val) if not pd.isna(liquor_val) else 0.0
                beer_sales = float(beer_val) if not pd.isna(beer_val) else 0.0
                wine_sales = float(wine_val) if not pd.isna(wine_val) else 0.0
                
                glassware_sales = float(row.get(mapping["glassware_sales"], 0))
                lsc_count = int(row.get(mapping["lsc_count"], 0))
                
                if guests <= 0:
                    logging.warning(f"Row {idx + 2}: Skipping {name} - guests must be > 0")
                    continue
                
                # Customer Voice fields (optional)
                cv_promoters = 0
                cv_passives = 0
                cv_detractors = 0
                
                if mapping.get("cv_promoters"):
                    val = row.get(mapping["cv_promoters"])
                    if not pd.isna(val):
                        cv_promoters = int(val)
                
                if mapping.get("cv_passives"):
                    val = row.get(mapping["cv_passives"])
                    if not pd.isna(val):
                        cv_passives = int(val)
                
                if mapping.get("cv_detractors"):
                    val = row.get(mapping["cv_detractors"])
                    if not pd.isna(val):
                        cv_detractors = int(val)
                
                # Review Tracker field (optional)
                review_mentions = 0
                if mapping.get("review_mentions"):
                    val = row.get(mapping["review_mentions"])
                    if not pd.isna(val):
                        review_mentions = int(val)
                
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