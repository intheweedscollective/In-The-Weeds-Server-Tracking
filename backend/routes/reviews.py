"""
Reviews Routes Module
Customer Reviews, Review Tracker, and Platform Stats management.
Extracted from server.py for better maintainability.
"""

from fastapi import APIRouter, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
import io
import logging

logger = logging.getLogger(__name__)

reviews_router = APIRouter(prefix="/v2", tags=["Reviews"])

def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# Import review_tracker utilities
from review_tracker import (
    PLATFORMS, POINTS_PER_POSITIVE_MENTION,
    generate_review_hash, detect_employees_in_review,
    calculate_review_points_for_employee, get_review_stats
)


# ============================================================
# PYDANTIC MODELS
# ============================================================

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


# ============================================================
# QUARTERLY REVIEWS (Generated Performance Reviews)
# ============================================================

@reviews_router.get("/reviews/quarterly/{year}/{quarter}")
async def get_quarterly_reviews(year: int, quarter: str):
    """Get all generated quarterly reviews for a quarter."""
    db = get_db()
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


@reviews_router.get("/reviews/quarterly/{year}/{quarter}/{employee_id}")
async def get_employee_quarterly_review(year: int, quarter: str, employee_id: str):
    """Get a specific employee's quarterly review with PDF."""
    db = get_db()
    review = await db.reviews_v2.find_one(
        {"year": year, "quarter": quarter.upper(), "employee_id": employee_id},
        {"_id": 0}
    )
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found for this employee")
    
    return review


# ============================================================
# REVIEW PLATFORMS & STATS
# ============================================================

@reviews_router.get("/reviews/platforms")
async def get_review_platforms():
    """Get list of supported review platforms."""
    return {
        "platforms": PLATFORMS,
        "points_per_mention": POINTS_PER_POSITIVE_MENTION
    }


@reviews_router.get("/reviews/platform-stats")
async def get_platform_stats(quarter: str = "Q1", year: int = 2026):
    """Get QTD stats for each review platform.
    Uses official RT stats if set (for 100% accuracy with RT dashboard),
    otherwise falls back to API-synced data.
    """
    db = get_db()
    
    # Check for official RT stats (manually set from RT UI)
    official_stats = await db.official_rt_stats.find_one(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if official_stats:
        return {
            "source": "official_rt_stats",
            "google": official_stats.get("platforms", {}).get("Google", {"reviews": 0, "rating": 0}),
            "yelp": official_stats.get("platforms", {}).get("Yelp", {"reviews": 0, "rating": 0}),
            "facebook": official_stats.get("platforms", {}).get("Facebook", {"reviews": 0, "rating": 0}),
            "tripadvisor": official_stats.get("platforms", {}).get("TripAdvisor", {"reviews": 0, "rating": 0}),
            "opentable": official_stats.get("platforms", {}).get("OpenTable", {"reviews": 0, "rating": 0}),
            "total_reviews": official_stats.get("total_reviews", 0),
            "updated_at": official_stats.get("updated_at"),
            "note": "Using official RT stats (manually set for 100% accuracy)"
        }
    
    # Fall back to aggregating from customer_reviews collection
    pipeline = [
        {"$match": {"quarter": quarter.upper(), "year": year}},
        {"$group": {
            "_id": "$platform",
            "count": {"$sum": 1},
            "avg_rating": {"$avg": "$rating"}
        }}
    ]
    
    results = await db.customer_reviews.aggregate(pipeline).to_list(10)
    
    platform_stats = {}
    for r in results:
        platform_stats[r["_id"].lower() if r["_id"] else "unknown"] = {
            "count": r["count"],
            "avg_rating": round(r["avg_rating"], 1) if r["avg_rating"] else 0
        }
    
    return {
        "source": "api_synced",
        "google": platform_stats.get("google", {"count": 0, "avg_rating": 0}),
        "yelp": platform_stats.get("yelp", {"count": 0, "avg_rating": 0}),
        "facebook": platform_stats.get("facebook", {"count": 0, "avg_rating": 0}),
        "tripadvisor": platform_stats.get("tripadvisor", {"count": 0, "avg_rating": 0}),
        "opentable": platform_stats.get("opentable", {"count": 0, "avg_rating": 0}),
        "all_platforms": platform_stats,
        "note": "Using API-synced data. Set official RT stats via /v2/admin/rt-stats/set for 100% accuracy."
    }


# ============================================================
# CUSTOMER REVIEWS CRUD
# ============================================================

@reviews_router.get("/reviews")
async def get_reviews(
    quarter: str = "Q1",
    year: int = 2026,
    platform: Optional[str] = None,
    employee_name: Optional[str] = None
):
    """Get all reviews with optional filters."""
    db = get_db()
    
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


@reviews_router.get("/reviews/stats")
async def get_review_stats_endpoint(quarter: str = "Q1", year: int = 2026):
    """Get review statistics including employee mention counts and points."""
    db = get_db()
    
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
    # populate the stats from employee records.
    # Per-quarter coefficients so historical quarters keep their original
    # bonus rule. ALWAYS recompute from current mentions — never trust a
    # stored review_tracker_bonus (it drifts when new RT data lands).
    qs_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0, "rt_points_per_mention": 1, "rt_max_points": 1},
    ) or {}
    _rt_coef = qs_doc.get("rt_points_per_mention", 0.3) or 0.3
    _rt_cap  = qs_doc.get("rt_max_points", 20.0) or 20.0
    if len(reviews) == 0:
        total_mentions = 0
        for emp in employees:
            mentions = emp.get("rt_mentions") or emp.get("review_mentions") or 0
            points = round(min(mentions * _rt_coef, _rt_cap), 2)
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


@reviews_router.post("/reviews")
async def create_review(review: CustomerReviewCreate):
    """Create a new customer review with AI-powered employee detection."""
    db = get_db()
    
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
    
    # Update employee RT mention counts from this review
    for mention in employee_mentions:
        emp_name = mention.get("employee_name", "")
        if emp_name:
            # Increment mention count
            emp = await db.employees_v2.find_one({
                "$or": [
                    {"name": {"$regex": f"^{emp_name}$", "$options": "i"}},
                    {"display_name": {"$regex": f"^{emp_name}$", "$options": "i"}},
                ],
                "quarter": review.quarter.upper(),
                "year": review.year
            })
            if emp:
                current_mentions = (emp.get("rt_mentions") or 0) + 1
                rt_bonus = min(current_mentions * 0.3, 20)
                await db.employees_v2.update_one(
                    {"_id": emp["_id"]},
                    {"$set": {
                        "rt_mentions": current_mentions,
                        "review_mentions": current_mentions,
                        "review_tracker_bonus": rt_bonus,
                        "rt_updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
    
    # Remove MongoDB _id before returning
    review_doc.pop("_id", None)
    
    return {
        "success": True,
        "review": review_doc,
        "detected_employees": len(employee_mentions),
        "message": f"Review added. Detected {len(employee_mentions)} employee mention(s)."
    }


@reviews_router.post("/reviews/detect")
async def detect_employees_endpoint(
    review_text: str,
    quarter: str = "Q1",
    year: int = 2026
):
    """Preview employee detection without saving the review."""
    db = get_db()
    
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


@reviews_router.get("/reviews/{review_id}")
async def get_review(review_id: str):
    """Get a specific review by ID."""
    db = get_db()
    review = await db.customer_reviews.find_one({"id": review_id}, {"_id": 0})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@reviews_router.put("/reviews/{review_id}/mentions")
async def update_review_mentions(review_id: str, update: EmployeeMentionUpdate):
    """Update employee mentions for a review (manual correction)."""
    db = get_db()
    
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


@reviews_router.delete("/reviews/{review_id}")
async def delete_review(review_id: str):
    """Delete a review."""
    db = get_db()
    result = await db.customer_reviews.delete_one({"id": review_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return {"success": True, "message": "Review deleted"}


@reviews_router.get("/reviews/employee/{employee_name}/points")
async def get_employee_review_points(
    employee_name: str,
    quarter: str = "Q1",
    year: int = 2026
):
    """Get total review points for a specific employee."""
    db = get_db()
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


# ============================================================
# REVIEW TRACKER TEMPLATE & UPLOAD
# ============================================================

@reviews_router.get("/rt/template")
async def download_rt_template():
    """
    Download the Review Tracker upload template (XLSX).
    Template has columns: Employee Name, Mentions
    Automatically includes all employees from the most recent snapshot.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    
    db = get_db()
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
        "3. Each mention = +0.3 points (capped at 20 pts) — Q2+ rule",
        "",
        "Scoring Color Thresholds:",
        "  0 mentions = 0 pts (Red)",
        "  1-9 mentions = 0.3-2.7 pts (Yellow)",
        "  10-19 mentions = 3.0-5.7 pts (Green)",
        "  20+ mentions = 6.0-20 pts (Blue, capped at 20)",
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


@reviews_router.get("/reviews/sync/status")
async def get_review_sync_status(quarter: str = "Q1", year: int = 2026):
    """
    Get the status of review data synchronization.
    Returns info about manual uploads and data sources.
    """
    db = get_db()
    
    # Count reviews in database
    review_count = await db.customer_reviews.count_documents({
        "quarter": quarter.upper(),
        "year": year
    })
    
    # Check for official RT stats
    official_stats = await db.official_rt_stats.find_one(
        {"quarter": quarter.upper(), "year": year}
    )
    
    # Get employee RT mention stats
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "name": 1, "rt_mentions": 1, "review_tracker_bonus": 1}
    ).to_list(500)
    
    employees_with_mentions = len([e for e in employees if (e.get("rt_mentions") or 0) > 0])
    total_mentions = sum(e.get("rt_mentions", 0) or 0 for e in employees)
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "review_count": review_count,
        "official_rt_stats_set": official_stats is not None,
        "official_rt_stats_updated_at": official_stats.get("updated_at") if official_stats else None,
        "employees_with_mentions": employees_with_mentions,
        "total_mentions": total_mentions,
        "data_sources": {
            "manual_upload": employees_with_mentions > 0,
            "official_stats": official_stats is not None,
            "api_reviews": review_count > 0
        },
        "recommendation": (
            "Data is complete via manual upload" if employees_with_mentions > 0
            else "Upload RT data via /v2/rt/upload or set official stats via /v2/admin/rt-stats/set"
        )
    }



@reviews_router.post("/review-tracker/upload-feedback")
async def upload_review_tracker_feedback(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Upload ReviewTracker feedback CSV/XLSX.
    Scans review text for employee name mentions and updates RT scores.
    """
    import pandas as pd
    
    db = get_db()
    quarter = quarter.upper()
    
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="File must be Excel (.xlsx, .xls) or CSV (.csv)")
    
    try:
        contents = await file.read()
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Normalize columns
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        
        # Map common column names
        col_mapping = {}
        for col in df.columns:
            cl = col.lower()
            # Skip ID columns
            if cl.endswith('_id') or cl == 'id':
                continue
            if cl == 'review' or cl == 'review_text' or any(x in cl for x in ['comment', 'feedback', 'body']):
                if 'review_text' not in col_mapping.values():
                    col_mapping[col] = 'review_text'
            elif any(x in cl for x in ['rating', 'score', 'star']):
                if 'rating' not in col_mapping.values():
                    col_mapping[col] = 'rating'
            elif cl == 'published' or cl == 'date' or any(x in cl for x in ['created', 'posted']):
                if 'date' not in col_mapping.values():
                    col_mapping[col] = 'date'
            elif any(x in cl for x in ['source', 'platform', 'site']):
                if 'platform' not in col_mapping.values():
                    col_mapping[col] = 'platform'
        df = df.rename(columns=col_mapping)
        
        # Get all employees for name matching
        employees = await db.employees_v2.find(
            {"quarter": quarter, "year": year},
            {"_id": 0, "id": 1, "name": 1, "display_name": 1, "report_name": 1, "aliases": 1}
        ).to_list(200)
        
        if not employees:
            raise HTTPException(status_code=404, detail=f"No employees found for {quarter} {year}")
        
        # Build name list for matching
        employee_names = {}
        for emp in employees:
            emp_id = emp.get("id")
            for field in ["name", "display_name", "report_name"]:
                n = (emp.get(field) or "").strip()
                if n:
                    employee_names[n.lower()] = emp_id
                    # Also add first name
                    first = n.split()[0].lower()
                    if len(first) > 2 and first not in employee_names:
                        employee_names[first] = emp_id
            for alias in emp.get("aliases", []):
                if alias:
                    employee_names[alias.lower()] = emp_id
        
        # Scan reviews for employee mentions
        mention_counts = {}  # emp_id -> count
        reviews_with_mentions = 0
        total_reviews = 0
        
        review_col = 'review_text' if 'review_text' in df.columns else None
        if not review_col:
            # Try to find any text column
            for col in df.columns:
                if df[col].dtype == 'object':
                    avg_len = df[col].astype(str).str.len().mean()
                    if avg_len > 30:  # likely a text column
                        review_col = col
                        break
        
        if not review_col:
            raise HTTPException(status_code=400, detail=f"Could not find review text column. Columns found: {', '.join(df.columns)}")
        
        for _, row in df.iterrows():
            text = str(row.get(review_col, '') or '').lower()
            # Fall back to original_content if review is empty
            if (not text or text == 'nan') and 'original_content' in df.columns:
                text = str(row.get('original_content', '') or '').lower()
            # Also check title column for short mentions
            if (not text or text == 'nan') and 'title' in df.columns:
                text = str(row.get('title', '') or '').lower()
            if not text or text == 'nan':
                continue
            total_reviews += 1
            
            found_in_review = False
            for emp_name, emp_id in employee_names.items():
                if emp_name in text:
                    mention_counts[emp_id] = mention_counts.get(emp_id, 0) + 1
                    found_in_review = True
            
            if found_in_review:
                reviews_with_mentions += 1
        
        # Update employee records with mention counts
        employees_updated = 0
        for emp_id, mentions in mention_counts.items():
            rt_bonus = min(mentions * 0.3, 20)
            result = await db.employees_v2.update_one(
                {"id": emp_id, "quarter": quarter, "year": year},
                {"$set": {
                    "rt_mentions": mentions,
                    "review_mentions": mentions,
                    "review_tracker_bonus": rt_bonus,
                    "rt_source": "feedback_csv_upload",
                    "rt_updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            if result.modified_count > 0:
                employees_updated += 1
        
        return {
            "success": True,
            "summary": {
                "total_reviews": total_reviews,
                "reviews_with_mentions": reviews_with_mentions,
                "total_mentions": sum(mention_counts.values()),
                "employees_updated": employees_updated,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RT upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@reviews_router.post("/review-tracker/bulk-import")
async def bulk_import_rt_mentions(
    data: dict,
    quarter: str = "Q2",
    year: int = 2026
):
    """
    Bulk import ReviewTracker mention counts directly to employees.
    Accepts: {"mentions": [{"name": "Employee Name", "count": 36}, ...]}
    Or: {"mentions": {"Employee Name": 36, "Another Name": 21, ...}}
    """
    db = get_db()
    quarter = quarter.upper()
    
    mentions_data = data.get("mentions", [])
    if not mentions_data:
        raise HTTPException(status_code=400, detail="No mention data provided. Expected: {mentions: [{name, count}, ...]} or {mentions: {name: count, ...}}")
    
    # Normalize to list of {name, count}
    if isinstance(mentions_data, dict):
        mentions_list = [{"name": k, "count": v} for k, v in mentions_data.items()]
    elif isinstance(mentions_data, list):
        mentions_list = mentions_data
    else:
        raise HTTPException(status_code=400, detail="mentions must be a list or dict")
    
    # Get all employees for matching
    employees = await db.employees_v2.find(
        {"quarter": quarter, "year": year}
    ).to_list(200)
    
    if not employees:
        raise HTTPException(status_code=404, detail=f"No employees found for {quarter} {year}. Upload POS data first.")
    
    # Build name lookup
    emp_lookup = {}
    for emp in employees:
        for field in ["name", "display_name", "report_name"]:
            n = (emp.get(field) or "").strip().lower()
            if n:
                emp_lookup[n] = emp
                first = n.split()[0]
                if len(first) > 2 and first not in emp_lookup:
                    emp_lookup[first] = emp
        for alias in emp.get("aliases", []):
            if alias:
                emp_lookup[alias.lower()] = emp
    
    updated = []
    not_found = []
    
    for item in mentions_list:
        name = (item.get("name") or "").strip()
        count = int(item.get("count", 0) or 0)
        
        if not name or count == 0:
            continue
        
        # Try matching
        match = None
        name_lower = name.lower()
        
        # Exact match
        match = emp_lookup.get(name_lower)
        
        # First name match
        if not match:
            first = name_lower.split()[0]
            if len(first) > 2:
                match = emp_lookup.get(first)
        
        # Parenthetical name match (e.g., "Thaddeus (Tad) Hashey" -> try "tad")
        if not match:
            import re
            paren = re.search(r'\(([^)]+)\)', name)
            if paren:
                nickname = paren.group(1).strip().lower()
                match = emp_lookup.get(nickname)
        
        # Last name match
        if not match:
            parts = name_lower.split()
            if len(parts) > 1:
                last = parts[-1]
                for key, emp in emp_lookup.items():
                    if last in key:
                        match = emp
                        break
        
        if match:
            rt_bonus = min(count * 0.5, 15)
            await db.employees_v2.update_one(
                {"_id": match["_id"]},
                {"$set": {
                    "rt_mentions": count,
                    "review_mentions": count,
                    "review_tracker_bonus": rt_bonus,
                    "rt_source": "bulk_import",
                    "rt_updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            updated.append({
                "input_name": name,
                "matched_to": match.get("display_name") or match.get("name"),
                "mentions": count,
                "bonus": rt_bonus
            })
        else:
            not_found.append(name)
    
    return {
        "success": True,
        "quarter": quarter,
        "year": year,
        "updated_count": len(updated),
        "not_found_count": len(not_found),
        "updated": updated,
        "not_found": not_found
    }
