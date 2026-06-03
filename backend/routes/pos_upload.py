"""
POS Upload Routes - All POS data upload and parsing endpoints.

Includes:
- POS OCR extraction (image-based)
- POS PDF parsing (scanned documents)
- Unified POS data upload (XLSX/CSV)
- File validation
- Employee data upload (V2 scoring engine)
"""

import asyncio
import base64
import io
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from scoring_engine import QuarterSettings, EmployeeV2, run_full_scoring, validate_upload_columns, validate_upload_data
from services.employee_v2_writer import upsert_employee_v2


def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# Router
pos_upload_router = APIRouter(tags=["POS Upload"])

# In-memory job storage for background PDF processing
pdf_jobs: Dict[str, Dict] = {}


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

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


class ParsedEmployeeData(BaseModel):
    employees: List[Dict[str, Any]]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_float(val, default=0):
    """Safely convert to float, handling NaN and None."""
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
    """Safely convert to int, handling NaN and None."""
    if val is None:
        return default
    try:
        result = float(val)
        if math.isnan(result) or math.isinf(result):
            return default
        return int(result)
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


# ---------------------------------------------------------------------------
# NATIVE-FIRST PDF EXTRACTION (shared)
# ---------------------------------------------------------------------------
#
# Every PDF-handling POS upload route MUST go through `extract_pos_pdf_native_first`
# so all three routes share the same precedence rule: try the deterministic
# native parser first, fall back to AI OCR only if the PDF is image-only or
# native extraction yields no usable rows. This mirrors how upload_jobs.py
# already works and prevents regression on digitally-generated POS reports.

# How loosely "food + liquor + beer + wine ≈ net_sales" is enforced. POS
# reports almost always include comps / discounts / dessert / NA bev /
# misc adjustments in the net_sales line that aren't accounted for in
# the four category columns, so we have to tolerate non-trivial drift.
# The fail threshold is set high enough that only obviously broken
# extractions (missing column, swapped columns, decimal lost) trip it.
SALES_RECONCILIATION_TOLERANCE_PCT = 0.15  # 15%
SALES_RECONCILIATION_MIN_NET = 50.0        # Skip the check below this — rounding noise dominates.


def _validate_sales_reconciliation(emp: Dict[str, Any]) -> Optional[str]:
    """
    Return a reject-reason string if this employee's category sales
    don't approximately sum to net_sales. Returns `None` if the row
    passes (or if there's not enough signal to judge).
    """
    net = safe_float(emp.get("net_sales") or 0)
    food = safe_float(emp.get("food_sales") or 0)
    liquor = safe_float(emp.get("liquor_sales") or 0)
    beer = safe_float(emp.get("beer_sales") or 0)
    wine = safe_float(emp.get("wine_sales") or 0)

    if net < SALES_RECONCILIATION_MIN_NET:
        return None
    cat_sum = food + liquor + beer + wine
    if cat_sum <= 0:
        # No category breakdown extracted — can't judge. POS report
        # might just be a summary; let it through.
        return None
    diff_pct = abs(cat_sum - net) / net
    if diff_pct <= SALES_RECONCILIATION_TOLERANCE_PCT:
        return None
    return (
        f"Category sales (${cat_sum:,.2f}) drift {diff_pct*100:.1f}% "
        f"vs net sales (${net:,.2f}). Likely an extraction error — "
        f"check for swapped columns, missed column, or lost decimal."
    )


def _filter_reconcilable_employees(
    employees: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Split a list of extracted employees into kept + rejected based on
    cross-field validation. Returns a dict with both lists so the
    caller can decide whether to fail loudly or just surface warnings.
    """
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for emp in employees:
        reason = _validate_sales_reconciliation(emp)
        if reason:
            rejected.append({
                "name": emp.get("name") or "Unknown",
                "net_sales": safe_float(emp.get("net_sales") or 0),
                "reason": reason,
            })
        else:
            kept.append(emp)
    return {"kept": kept, "rejected": rejected}


async def extract_pos_pdf_native_first(file_bytes: bytes) -> Dict[str, Any]:
    """
    Native PDF parser first, AI OCR fallback. Returns the same
    legacy-shaped dict the validator expects:
      { "employees": [ {... per-employee fields ...} ],
        "extraction_notes": "...",
        "extraction_method": "native_pdf" | "ai_ocr",
        "error": str? }
    Falls through to AI OCR if the native parser fails / returns 0 rows.
    """
    from pos_ocr import extract_pos_data_from_pdf  # AI OCR fallback

    # 1) Try the deterministic native parser.
    try:
        from native_pos_parser import (
            extract_pos_data_from_pdf_bytes_native,
            is_pdf_native_extractable,
        )
        if is_pdf_native_extractable(file_bytes):
            native = extract_pos_data_from_pdf_bytes_native(file_bytes)
            if native.get("success") and native.get("employees"):
                logging.info(
                    f"Native PDF parser extracted {len(native['employees'])} employees"
                )
                return {
                    "employees": [
                        {
                            "name": e["name"],
                            "guest_count": e["guest_count"],
                            "net_sales": e["net_sales"],
                            "ppa": e["ppa"],
                            "food_sales": e["food_sales"],
                            "liquor_sales": e["liquor_sales"],
                            "beer_sales": e["beer_sales"],
                            "wine_sales": e["wine_sales"],
                            "bar_glassware_sales": e["bar_glassware_sales"],
                            "loyalty_sales": e["loyalty_sales"],
                        }
                        for e in native["employees"]
                    ],
                    "extraction_notes": native.get("extraction_notes", ""),
                    "extraction_method": "native_pdf",
                }
    except Exception as e:
        logging.warning(f"Native parser failed, falling back to AI OCR: {e}")

    # 2) Fall back to AI OCR.
    raw = await extract_pos_data_from_pdf(file_bytes)
    raw["extraction_method"] = "ai_ocr"
    return raw


# ============================================================================
# POS REPORT OCR ENDPOINTS
# ============================================================================

@pos_upload_router.post("/v2/pos-ocr/extract", response_model=POSOCRResponse)
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


@pos_upload_router.post("/v2/pos-ocr/upload")
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
            # Native PDF parser first, AI OCR fallback. Mirrors upload_jobs.py.
            raw_data = await extract_pos_pdf_native_first(contents)
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

        # Cross-field validation: category sales should ≈ net sales.
        # Rows that fail get rejected so they never reach the snapshot.
        # Native parser rows almost always pass; OCR rows fail here when
        # the AI swapped a column or missed a decimal point.
        if is_pdf or not is_xlsx:
            reconciled = _filter_reconcilable_employees(
                validated_data.get("employees", [])
            )
            if reconciled["rejected"]:
                logging.warning(
                    f"POS upload: rejected {len(reconciled['rejected'])} row(s) "
                    f"that failed sales reconciliation: "
                    f"{[r['name'] for r in reconciled['rejected']]}"
                )
            validated_data["employees"] = reconciled["kept"]
            validated_data["rejected_rows"] = reconciled["rejected"]
            if not reconciled["kept"] and reconciled["rejected"]:
                return {
                    "success": False,
                    "error": (
                        f"All {len(reconciled['rejected'])} extracted row(s) "
                        f"failed cross-field validation (category sales did "
                        f"not reconcile with net sales). The extraction is "
                        f"unreliable — please re-upload or contact support."
                    ),
                    "rejected_rows": reconciled["rejected"],
                    "extraction_notes": validated_data.get("extraction_notes"),
                }

        return {
            "success": True,
            "filename": file.filename,
            "file_type": "pdf" if is_pdf else "image",
            "pages_processed": raw_data.get("pages_processed", 1),
            "extraction_method": raw_data.get("extraction_method", "ai_ocr"),
            "report_date": validated_data.get("report_date"),
            "report_type": validated_data.get("report_type"),
            "employees": validated_data.get("employees", []),
            "employee_count": validated_data.get("employee_count", 0),
            "rejected_rows": validated_data.get("rejected_rows", []),
            "extraction_notes": validated_data.get("extraction_notes")
        }
        
    except Exception as e:
        logging.error(f"POS file upload failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}"
        )


# ============================================================================
# SCANNED PDF PARSER ENDPOINTS
# ============================================================================

@pos_upload_router.post("/v2/pos-pdf/test")
async def test_pdf_endpoint(file: UploadFile = File(...)):
    """Simple test endpoint to check if PDF upload works at all"""
    contents = await file.read()
    return {
        "success": True,
        "filename": file.filename,
        "size": len(contents),
        "content_type": file.content_type
    }


@pos_upload_router.post("/v2/pos-pdf/parse")
async def parse_pos_pdf_scan(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    Parse a scanned POS report PDF using AI-powered OCR extraction.
    Returns a job_id immediately - poll /v2/pos-pdf/job/{job_id} for results.
    """
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
    from pos_ocr import extract_pos_data_from_pdf, validate_extracted_data
    import asyncio
    
    try:
        logging.info(f"Background PDF processing started for job {job_id}")
        
        # Update status to processing
        pdf_jobs[job_id] = {
            **pdf_jobs[job_id],
            "status": "processing",
            "progress": 5,
            "message": "Starting PDF processing..."
        }
        
        # Native PDF parser first, AI OCR fallback (mirrors upload_jobs.py).
        # No overall timeout - let it run as long as needed
        raw_data = await extract_pos_pdf_native_first(contents)

        # Update progress
        pdf_jobs[job_id] = {
            **pdf_jobs[job_id],
            "progress": 90,
            "message": "Validating extracted data..."
        }

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

        # Cross-field validation — reject rows whose category sales
        # don't reconcile with net sales (extraction error indicator).
        reconciled = _filter_reconcilable_employees(
            validated_data.get("employees", [])
        )
        validated_data["employees"] = reconciled["kept"]
        rejected_rows = reconciled["rejected"]
        if rejected_rows:
            logging.warning(
                f"PDF job {job_id}: rejected {len(rejected_rows)} row(s) "
                f"failing sales reconciliation: "
                f"{[r['name'] for r in rejected_rows]}"
            )
        if not validated_data["employees"] and rejected_rows:
            pdf_jobs[job_id] = {
                **pdf_jobs[job_id],
                "status": "completed",
                "progress": 100,
                "result": {
                    "success": False,
                    "error": (
                        f"All {len(rejected_rows)} extracted row(s) failed "
                        "cross-field validation. The extraction is unreliable."
                    ),
                    "employees": [],
                    "rejected_rows": rejected_rows,
                    "extraction_notes": validated_data.get("extraction_notes", ""),
                },
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
                "extraction_method": raw_data.get("extraction_method", "ai_ocr"),
                "rejected_rows": rejected_rows,
                "employees": formatted_employees,
                "extraction_notes": (
                    f"{raw_data.get('extraction_method', 'ai_ocr')} extracted "
                    f"{len(formatted_employees)} employees"
                    + (f", rejected {len(rejected_rows)} for failing cross-field validation"
                       if rejected_rows else "")
                    + f". {validated_data.get('extraction_notes', '')}"
                )
            }
        }
        logging.info(f"Background PDF processing completed for job {job_id}: {len(formatted_employees)} employees ({raw_data.get('extraction_method', 'ai_ocr')})")
        
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


@pos_upload_router.get("/v2/pos-pdf/job/{job_id}")
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


@pos_upload_router.post("/v2/pos-pdf/import-parsed")
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
    from server import fix_all_employee_scores
    
    quarter = quarter.upper()
    employees_data = data.employees
    
    if not employees_data:
        raise HTTPException(status_code=400, detail="No employee data provided")
    
    # Check quarter settings
    settings_doc = await get_db().quarter_settings.find_one(
        {"year": year, "quarter": quarter},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(
            status_code=400,
            detail=f"Quarter settings must exist for {quarter} {year}. Go to Settings first."
        )
    
    # Get existing employees for matching
    existing_employees = await get_db().employees_v2.find({
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
                
                await get_db().employees_v2.update_one(
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
                await upsert_employee_v2(get_db(), new_employee)
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


@pos_upload_router.post("/v2/pos-pdf/import")
async def import_pos_pdf_data(
    file: UploadFile = File(...),
    quarter: str = "Q1",
    year: int = 2026
):
    """
    Parse and import scanned POS PDF data into the employee database.
    Uses the native PDF parser as the primary extraction method, with
    AI OCR as a fallback only if native parsing fails or the PDF is
    image-only (mirrors upload_jobs.py).

    This endpoint:
    1. Parses the PDF (native first, AI OCR fallback)
    2. Validates that each row's category sales (food + liquor + beer
       + wine) approximately sum to its net sales — rejects rows that
       fail this check
    3. Matches employees using fuzzy name matching
    4. Updates existing employees or creates new ones
    5. Recalculates all scores
    """
    from pos_ocr import validate_extracted_data
    from rapidfuzz import fuzz, process
    from server import fix_all_employee_scores
    
    quarter = quarter.upper()
    
    # Check quarter settings
    settings_doc = await get_db().quarter_settings.find_one(
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
        logging.info(f"Processing PDF import: {file.filename}, size: {len(contents)} bytes")

        # Native PDF parser first, AI OCR fallback (mirrors upload_jobs.py).
        raw_data = await extract_pos_pdf_native_first(contents)

        if "error" in raw_data and not raw_data.get("employees"):
            raise HTTPException(status_code=400, detail=raw_data.get("error", "No employee data found in PDF"))

        # Validate and clean extracted data
        validated_data = validate_extracted_data(raw_data)

        if not validated_data.get("employees"):
            raise HTTPException(status_code=400, detail="No employee data could be extracted from PDF")

        # Cross-field validation — reject rows where category sales don't
        # reconcile with net sales. This stops bad imports cold instead of
        # silently flushing garbage into the snapshot.
        reconciled = _filter_reconcilable_employees(
            validated_data.get("employees", [])
        )
        rejected_rows = reconciled["rejected"]
        if rejected_rows:
            logging.warning(
                f"PDF import: rejected {len(rejected_rows)} row(s) failing "
                f"sales reconciliation: {[r['name'] for r in rejected_rows]}"
            )
        validated_data["employees"] = reconciled["kept"]
        if not validated_data["employees"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"All {len(rejected_rows)} extracted row(s) failed "
                    f"cross-field validation (category sales did not "
                    f"reconcile with net sales). Aborted to avoid "
                    f"importing unreliable data. Rejected: "
                    f"{[r['name'] for r in rejected_rows[:5]]}"
                ),
            )
        
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
        existing_employees = await get_db().employees_v2.find({
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
                    # Update existing employee with raw + derived metrics
                    guests = emp_data['guests']
                    net_sales = emp_data['net_sales']
                    lbw = emp_data['lbw']
                    glassware = emp_data['glassware']
                    loyalty = emp_data.get('loyalty_sales', 0)
                    lsc_count = int(loyalty / 25) if loyalty > 0 else 0
                    
                    # Calculate derived per-guest metrics
                    ppa = round(net_sales / guests, 2) if guests > 0 else 0
                    lbw_per_guest = round(lbw / guests, 2) if guests > 0 else 0
                    glass_per_guest = round(glassware / guests, 2) if guests > 0 else 0
                    guests_per_lsc = round(guests / lsc_count, 2) if lsc_count > 0 else 0
                    
                    update_data = {
                        "guest_count": guests,
                        "guests": guests,
                        "net_sales": net_sales,
                        "food_sales": emp_data['food'],
                        "liquor_sales": emp_data['liquor'],
                        "beer_sales": emp_data['beer'],
                        "wine_sales": emp_data['wine'],
                        "lbw_total": lbw,
                        "lbw": lbw,
                        "bar_glassware_sales": glassware,
                        "glassware_sales": glassware,
                        "loyalty_sales": loyalty,
                        "lsc_count": lsc_count,
                        "ppa": ppa,
                        "lbw_per_guest": lbw_per_guest,
                        "glassware_per_guest": glass_per_guest,
                        "guests_per_lsc": guests_per_lsc,
                        "updated_at": datetime.now(timezone.utc)
                    }
                    
                    await get_db().employees_v2.update_one(
                        {"id": matched_id},
                        {"$set": update_data}
                    )
                    results["matched"].append({"name": emp_name, "id": matched_id})
                else:
                    # Create new employee with raw + derived metrics
                    new_id = str(uuid.uuid4())
                    guests = emp_data['guests']
                    net_sales = emp_data['net_sales']
                    lbw = emp_data['lbw']
                    glassware = emp_data['glassware']
                    loyalty = emp_data.get('loyalty_sales', 0)
                    lsc_count = int(loyalty / 25) if loyalty > 0 else 0
                    
                    ppa = round(net_sales / guests, 2) if guests > 0 else 0
                    lbw_per_guest = round(lbw / guests, 2) if guests > 0 else 0
                    glass_per_guest = round(glassware / guests, 2) if guests > 0 else 0
                    guests_per_lsc = round(guests / lsc_count, 2) if lsc_count > 0 else 0
                    
                    new_employee = {
                        "id": new_id,
                        "name": emp_name,
                        "display_name": emp_name,
                        "report_name": emp_name,
                        "aliases": [],
                        "quarter": quarter,
                        "year": year,
                        "guest_count": guests,
                        "guests": guests,
                        "net_sales": net_sales,
                        "food_sales": emp_data['food'],
                        "liquor_sales": emp_data['liquor'],
                        "beer_sales": emp_data['beer'],
                        "wine_sales": emp_data['wine'],
                        "lbw_total": lbw,
                        "lbw": lbw,
                        "bar_glassware_sales": glassware,
                        "glassware_sales": glassware,
                        "loyalty_sales": loyalty,
                        "lsc_count": lsc_count,
                        "ppa": ppa,
                        "lbw_per_guest": lbw_per_guest,
                        "glassware_per_guest": glass_per_guest,
                        "guests_per_lsc": guests_per_lsc,
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    await upsert_employee_v2(get_db(), new_employee)
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
            "rejected_rows": rejected_rows,
            "extraction_method": raw_data.get("extraction_method", "ai_ocr"),
            "details": results,
            "extraction_notes": (
                f"{raw_data.get('extraction_method', 'ai_ocr')} processed "
                f"{raw_data.get('pages_processed', 'N/A')} pages"
                + (f", rejected {len(rejected_rows)} row(s) for failing "
                   "cross-field validation" if rejected_rows else "")
            ),
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"PDF import error: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
