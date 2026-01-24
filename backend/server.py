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
    
    kpi_data = [
        ["Metric", "Score", "Peer Rank", "Performance Level"],
        ["PPA (Per Person Average)", format_currency_for_prompt(employee.ppa), peer_rankings['ppa'], get_performance_level(employee.ppa)],
        ["GPG (Glassware $ Per Guest)", format_currency_for_prompt(employee.gpg), peer_rankings['gpg'], get_performance_level(employee.gpg)],
        ["PPLBW (Per Person Liquor Beer Wine)", format_currency_for_prompt(employee.pplbw), peer_rankings['pplbw'], get_performance_level(employee.pplbw)],
        ["LSC Ratio (Landry's Select Card)", format_lsc_ratio(employee.lsc_ratio), peer_rankings['lsc_ratio'], get_performance_level(employee.lsc_ratio)],
        ["Metric Bonus Points", str(employee.metric_bonus_points or 'N/A'), peer_rankings['metric_bonus'], get_performance_level(employee.metric_bonus_points)],
        ["Cumulative Score", str(employee.cumulative_score or 'N/A'), peer_rankings['cumulative'], get_performance_level(employee.cumulative_score)]
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

    # replicate frontend analytics calculation (thirds, LSC inverse)
    metrics = ["ppa", "gpg", "pplbw", "lsc_ratio", "metric_bonus_points", "cumulative_score"]
    analytics: Dict[str, Dict[str, Any]] = {}

    for metric in metrics:
        values = [e.get(metric) for e in employees]
        valid_values = [v for v in values if v is not None and isinstance(v, (int, float))]

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
                "benchmarkValue": KPI_DEFINITIONS.get(metric, {}).get("benchmark", 0),
            }
            continue

        sorted_vals = sorted(valid_values, reverse=(metric != "lsc_ratio"))
        top_third_index = int(len(sorted_vals) * (1 / 3))
        bottom_third_index = int(len(sorted_vals) * (2 / 3))

        high_threshold = sorted_vals[top_third_index] if top_third_index < len(sorted_vals) else sorted_vals[-1]
        low_threshold = sorted_vals[bottom_third_index] if bottom_third_index < len(sorted_vals) else sorted_vals[-1]

        high = medium = low = above_benchmark = 0
        benchmark_val = KPI_DEFINITIONS.get(metric, {}).get("benchmark", 0)
        avg = sum(valid_values) / len(valid_values)

        for v in valid_values:
            if metric == "lsc_ratio":
                # inverse (lower is better)
                if v <= high_threshold:
                    high += 1
                elif v <= low_threshold:
                    medium += 1
                else:
                    low += 1

                benchmark_denominator = round(1 / benchmark_val) if benchmark_val else 0
                if benchmark_denominator and v <= benchmark_denominator:
                    above_benchmark += 1
            else:
                if v >= high_threshold:
                    high += 1
                elif v >= low_threshold:
                    medium += 1
                else:
                    low += 1

                if benchmark_val and v >= benchmark_val:
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