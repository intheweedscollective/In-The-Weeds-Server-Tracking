"""
Upload Jobs Router
Handles chunked file uploads and background processing jobs.
Jobs are stored in MongoDB for persistence across restarts.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import asyncio
import uuid
import base64
import logging

logger = logging.getLogger(__name__)

upload_jobs_router = APIRouter(prefix="/v2/upload-jobs", tags=["Upload Jobs"])

def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# ============================================================================
# JOB STATUS MANAGEMENT
# ============================================================================

async def create_job(job_type: str, filename: str, total_size: int = 0, metadata: dict = None) -> str:
    """Create a new job in MongoDB and return job_id."""
    db = get_db()
    job_id = str(uuid.uuid4())
    
    job_doc = {
        "job_id": job_id,
        "job_type": job_type,  # "pdf_parse", "xlsx_parse", "csv_import", etc.
        "filename": filename,
        "total_size": total_size,
        "status": "pending",  # pending, uploading, processing, completed, failed
        "progress": 0,
        "chunks_received": 0,
        "total_chunks": 0,
        "file_data": None,  # Will store base64 encoded file
        "result": None,
        "error": None,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "completed_at": None
    }
    
    await db.upload_jobs.insert_one(job_doc)
    logger.info(f"Created job {job_id} for {job_type}: {filename}")
    return job_id


async def update_job_status(job_id: str, status: str, progress: int = None, 
                           result: dict = None, error: str = None):
    """Update job status in MongoDB."""
    db = get_db()
    
    update = {
        "status": status,
        "updated_at": datetime.now(timezone.utc)
    }
    
    if progress is not None:
        update["progress"] = progress
    if result is not None:
        update["result"] = result
    if error is not None:
        update["error"] = error
    if status in ["completed", "failed"]:
        update["completed_at"] = datetime.now(timezone.utc)
    
    await db.upload_jobs.update_one(
        {"job_id": job_id},
        {"$set": update}
    )


async def get_job(job_id: str) -> dict:
    """Get job from MongoDB."""
    db = get_db()
    job = await db.upload_jobs.find_one({"job_id": job_id}, {"_id": 0, "file_data": 0})
    return job


# ============================================================================
# CHUNKED UPLOAD ENDPOINTS
# ============================================================================

@upload_jobs_router.post("/init")
async def init_upload(
    filename: str = Form(...),
    file_type: str = Form(...),  # pdf, xlsx, csv
    total_size: int = Form(...),
    total_chunks: int = Form(...),
    quarter: str = Form("Q1"),
    year: int = Form(2026)
):
    """
    Initialize a chunked upload. Returns a job_id for subsequent chunk uploads.
    
    This endpoint returns immediately, allowing large files to be uploaded
    in chunks without timing out.
    """
    if file_type not in ["pdf", "xlsx", "csv", "image"]:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
    
    if total_size > 100 * 1024 * 1024:  # 100MB max
        raise HTTPException(status_code=400, detail="File too large. Maximum 100MB")
    
    job_id = await create_job(
        job_type=f"{file_type}_parse",
        filename=filename,
        total_size=total_size,
        metadata={
            "quarter": quarter.upper(),
            "year": year,
            "total_chunks": total_chunks
        }
    )
    
    # Update with total chunks
    db = get_db()
    await db.upload_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"total_chunks": total_chunks, "status": "uploading"}}
    )
    
    return {
        "success": True,
        "job_id": job_id,
        "message": f"Upload initialized. Send {total_chunks} chunks to /api/v2/upload-jobs/{job_id}/chunk"
    }


@upload_jobs_router.post("/direct")
async def direct_upload(
    file: UploadFile = File(...),
    quarter: str = Form("Q1"),
    year: int = Form(2026)
):
    """
    Direct file upload with immediate background processing.
    Returns job_id immediately - poll /api/v2/upload-jobs/{job_id} for results.
    
    This is the recommended endpoint for production use as it:
    1. Returns immediately (no timeout)
    2. Streams file to avoid memory issues
    3. Processes in background
    4. Stores job status in MongoDB (persists across restarts)
    """
    # Determine file type
    filename = file.filename or "unknown"
    content_type = file.content_type or ""
    
    if filename.lower().endswith('.pdf') or content_type == "application/pdf":
        file_type = "pdf"
    elif filename.lower().endswith(('.xlsx', '.xls')) or 'spreadsheet' in content_type:
        file_type = "xlsx"
    elif filename.lower().endswith('.csv') or content_type == "text/csv":
        file_type = "csv"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")
    
    # Read file in chunks to avoid memory issues
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    file_data = bytearray()
    total_read = 0
    max_size = 100 * 1024 * 1024  # 100MB max
    
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_size:
            raise HTTPException(status_code=400, detail="File too large. Maximum 100MB")
        file_data.extend(chunk)
    
    # Create job
    job_id = await create_job(
        job_type=f"{file_type}_parse",
        filename=filename,
        total_size=len(file_data),
        metadata={
            "quarter": quarter.upper(),
            "year": year
        }
    )
    
    db = get_db()
    await db.upload_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "processing", "progress": 10}}
    )
    
    # Start background processing
    asyncio.create_task(process_direct_upload(job_id, bytes(file_data), file_type))
    
    return {
        "success": True,
        "job_id": job_id,
        "status": "processing",
        "message": f"File uploaded. Processing started. Poll /api/v2/upload-jobs/{job_id} for results."
    }


async def process_direct_upload(job_id: str, file_bytes: bytes, file_type: str):
    """Process a directly uploaded file."""
    db = get_db()
    
    try:
        job = await db.upload_jobs.find_one({"job_id": job_id})
        if not job:
            return
        
        metadata = job.get("metadata", {})
        
        await update_job_status(job_id, "processing", progress=30)
        
        if file_type == "pdf":
            result = await process_pdf_job(file_bytes, metadata, job_id)
        elif file_type == "xlsx":
            result = await process_xlsx_job(file_bytes, metadata, job_id)
        elif file_type == "csv":
            result = await process_csv_job(file_bytes, metadata, job_id)
        else:
            result = {"error": f"Unknown file type: {file_type}"}
        
        if result.get("error") and not result.get("success"):
            await update_job_status(job_id, "failed", progress=100, error=result["error"])
        else:
            await update_job_status(job_id, "completed", progress=100, result=result)
        
        logger.info(f"Direct upload job {job_id} completed")
        
    except Exception as e:
        logger.error(f"Error processing direct upload {job_id}: {e}")
        await update_job_status(job_id, "failed", error=str(e))




@upload_jobs_router.post("/{job_id}/chunk")
async def upload_chunk(
    job_id: str,
    chunk_index: int = Form(...),
    chunk_data: str = Form(...)  # Base64 encoded chunk
):
    """
    Upload a single chunk of a file. 
    Chunks are assembled in order on the server.
    """
    db = get_db()
    
    job = await db.upload_jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] not in ["uploading", "pending"]:
        raise HTTPException(status_code=400, detail=f"Job is not accepting chunks. Status: {job['status']}")
    
    # Store chunk in a separate collection for assembly
    await db.upload_chunks.update_one(
        {"job_id": job_id, "chunk_index": chunk_index},
        {"$set": {
            "job_id": job_id,
            "chunk_index": chunk_index,
            "data": chunk_data,
            "received_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    
    # Update chunks received count
    chunks_count = await db.upload_chunks.count_documents({"job_id": job_id})
    total_chunks = job.get("total_chunks", 1)
    progress = int((chunks_count / total_chunks) * 50)  # Upload is 50% of total progress
    
    await db.upload_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "chunks_received": chunks_count,
            "progress": progress,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    # Check if all chunks received
    if chunks_count >= total_chunks:
        # Start processing in background
        asyncio.create_task(assemble_and_process(job_id))
    
    return {
        "success": True,
        "chunks_received": chunks_count,
        "total_chunks": total_chunks,
        "progress": progress
    }


@upload_jobs_router.get("/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of an upload/processing job."""
    job = await get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "filename": job.get("filename"),
        "job_type": job.get("job_type"),
        "result": job.get("result") if job["status"] == "completed" else None,
        "error": job.get("error") if job["status"] == "failed" else None,
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at")
    }


@upload_jobs_router.delete("/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a pending or uploading job and clean up chunks."""
    db = get_db()
    
    job = await db.upload_jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] in ["completed", "failed"]:
        # Just clean up
        pass
    
    # Delete chunks
    await db.upload_chunks.delete_many({"job_id": job_id})
    
    # Update job status
    await db.upload_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc)}}
    )
    
    return {"success": True, "message": "Job cancelled"}


# ============================================================================
# BACKGROUND PROCESSING
# ============================================================================

async def assemble_and_process(job_id: str):
    """Assemble chunks and process the file in background."""
    db = get_db()
    
    try:
        job = await db.upload_jobs.find_one({"job_id": job_id})
        if not job:
            return
        
        await update_job_status(job_id, "processing", progress=50)
        
        # Get all chunks in order
        chunks = await db.upload_chunks.find(
            {"job_id": job_id}
        ).sort("chunk_index", 1).to_list(1000)
        
        if not chunks:
            await update_job_status(job_id, "failed", error="No chunks found")
            return
        
        # Assemble file from chunks
        file_data_b64 = "".join(chunk["data"] for chunk in chunks)
        file_bytes = base64.b64decode(file_data_b64)
        
        logger.info(f"Assembled file for job {job_id}: {len(file_bytes)} bytes")
        
        # Clean up chunks immediately to save space
        await db.upload_chunks.delete_many({"job_id": job_id})
        
        await update_job_status(job_id, "processing", progress=60)
        
        # Process based on job type
        job_type = job.get("job_type", "")
        metadata = job.get("metadata", {})
        
        if job_type == "pdf_parse":
            result = await process_pdf_job(file_bytes, metadata, job_id)
        elif job_type == "xlsx_parse":
            result = await process_xlsx_job(file_bytes, metadata, job_id)
        elif job_type == "csv_parse":
            result = await process_csv_job(file_bytes, metadata, job_id)
        else:
            result = {"error": f"Unknown job type: {job_type}"}
        
        if result.get("error"):
            await update_job_status(job_id, "failed", progress=100, error=result["error"])
        else:
            await update_job_status(job_id, "completed", progress=100, result=result)
        
        logger.info(f"Job {job_id} completed")
        
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}")
        await update_job_status(job_id, "failed", error=str(e))


async def process_pdf_job(file_bytes: bytes, metadata: dict, job_id: str) -> dict:
    """Process a PDF file for POS data extraction."""
    import math
    import os
    from pos_ocr import extract_pos_data_from_pdf, validate_extracted_data

    # DEBUG: persist raw PDF bytes for offline parser debugging.
    # Controlled by env var so it can be disabled in production.
    if os.environ.get("POS_DEBUG_DUMP", "0") == "1":
        try:
            os.makedirs("/tmp/pos_debug", exist_ok=True)
            dump_path = f"/tmp/pos_debug/{job_id}.pdf"
            with open(dump_path, "wb") as f:
                f.write(file_bytes)
            logger.info(f"[POS_DEBUG] Dumped {len(file_bytes)} bytes to {dump_path}")
        except Exception as dump_err:
            logger.warning(f"[POS_DEBUG] Failed to dump PDF: {dump_err}")
    
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
        await update_job_status(job_id, "processing", progress=65)

        # Try the deterministic native PDF parser FIRST. It works on any
        # digitally-generated POS report and is dramatically more accurate
        # than the AI OCR pipeline for those (no hallucinations, no kerning
        # mistakes). Falls back to AI OCR only when the PDF is image-only or
        # the native parser yields no usable data.
        raw_data: dict[str, Any]
        used_native = False
        try:
            from native_pos_parser import (
                extract_pos_data_from_pdf_bytes_native,
                is_pdf_native_extractable,
            )
            if is_pdf_native_extractable(file_bytes):
                native = extract_pos_data_from_pdf_bytes_native(file_bytes)
                if native.get("success") and native.get("employees"):
                    # Re-shape into the dict the legacy validator expects.
                    # The validator reads top-level fields, NOT _raw, so we
                    # put metric fields at the top level too.
                    raw_data = {
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
                    used_native = True
                    logger.info(
                        f"Native PDF parser extracted {len(native['employees'])} employees"
                    )
        except Exception as e:
            logger.warning(f"Native parser failed, falling back to AI OCR: {e}")

        # AI OCR fallback (image-only PDFs or native parser failed)
        if not used_native:
            raw_data = await extract_pos_data_from_pdf(file_bytes)

        await update_job_status(job_id, "processing", progress=80)
        
        if "error" in raw_data and not raw_data.get("employees"):
            return {
                "success": False,
                "error": raw_data.get("error", "Failed to extract data from PDF"),
                "employees": []
            }
        
        # Validate and clean
        validated_data = validate_extracted_data(raw_data)
        
        if not validated_data.get("employees"):
            return {
                "success": False,
                "error": "No employee data could be extracted from the PDF",
                "employees": []
            }
        
        await update_job_status(job_id, "processing", progress=90)
        
        # Format employees
        formatted_employees = []
        for emp in validated_data.get("employees", []):
            raw_data_fields = emp.get("_raw", {})
            
            guest_count = safe_int(emp.get("guest_count", 0))
            net_sales = safe_float(emp.get("net_sales", 0))
            ppa = safe_float(emp.get("ppa", 0))
            if (not ppa or ppa == 0) and guest_count > 0 and net_sales > 0:
                ppa = round(net_sales / guest_count, 2)
            
            liquor_sales = safe_float(raw_data_fields.get("liquor_sales", 0))
            beer_sales = safe_float(raw_data_fields.get("beer_sales", 0))
            wine_sales = safe_float(raw_data_fields.get("wine_sales", 0))
            lbw_total = liquor_sales + beer_sales + wine_sales

            formatted_employees.append({
                "name": str(emp.get("name", "Unknown") or "Unknown"),
                "guest_count": guest_count,
                "net_sales": net_sales,
                "ppa": ppa,
                "food_sales": safe_float(raw_data_fields.get("food_sales", 0)),
                "liquor_sales": liquor_sales,
                "beer_sales": beer_sales,
                "wine_sales": wine_sales,
                "lbw_total": lbw_total,
                "bar_glassware_sales": safe_float(raw_data_fields.get("bar_glassware_sales", 0) or emp.get("bar_glassware_sales", 0)),
                "loyalty_sales": safe_float(raw_data_fields.get("loyalty_sales", 0) or emp.get("loyalty_sales", 0)),
            })
        
        return {
            "success": True,
            "employees": formatted_employees,
            "total_extracted": len(formatted_employees),
            "extraction_notes": validated_data.get("extraction_notes", "")
        }
        
    except Exception as e:
        logger.error(f"PDF processing error: {e}")
        return {"success": False, "error": str(e), "employees": []}


async def process_xlsx_job(file_bytes: bytes, metadata: dict, job_id: str) -> dict:
    """Process an XLSX file for POS data extraction."""
    from pos_ocr import extract_pos_data_from_xlsx, validate_extracted_data

    def safe_float(val, default=0):
        try:
            if val is None:
                return default
            f = float(val)
            import math
            if math.isnan(f) or math.isinf(f):
                return default
            return f
        except (TypeError, ValueError):
            return default

    try:
        await update_job_status(job_id, "processing", progress=70)
        
        raw_data = await extract_pos_data_from_xlsx(file_bytes)
        
        await update_job_status(job_id, "processing", progress=85)
        
        if "error" in raw_data and not raw_data.get("employees"):
            return {
                "success": False,
                "error": raw_data.get("error"),
                "employees": []
            }
        
        validated_data = validate_extracted_data(raw_data)

        # Flatten _raw fields to top-level and compute lbw_total so the preview
        # UI (which displays emp.lbw_total / emp.liquor_sales etc.) works.
        flattened = []
        for emp in validated_data.get("employees", []):
            raw = emp.get("_raw", {}) or {}
            liquor = safe_float(raw.get("liquor_sales", 0) or emp.get("liquor_sales", 0))
            beer = safe_float(raw.get("beer_sales", 0) or emp.get("beer_sales", 0))
            wine = safe_float(raw.get("wine_sales", 0) or emp.get("wine_sales", 0))
            flat = dict(emp)
            flat["liquor_sales"] = liquor
            flat["beer_sales"] = beer
            flat["wine_sales"] = wine
            flat["lbw_total"] = liquor + beer + wine
            flat["food_sales"] = safe_float(raw.get("food_sales", 0) or emp.get("food_sales", 0))
            flat["bar_glassware_sales"] = safe_float(
                raw.get("bar_glassware_sales", 0) or emp.get("bar_glassware_sales", 0)
            )
            flattened.append(flat)

        return {
            "success": True,
            "employees": flattened,
            "total_extracted": len(flattened),
            "extraction_notes": validated_data.get("extraction_notes", "")
        }
        
    except Exception as e:
        logger.error(f"XLSX processing error: {e}")
        return {"success": False, "error": str(e), "employees": []}


async def process_csv_job(file_bytes: bytes, metadata: dict, job_id: str) -> dict:
    """Process a CSV file (e.g., ReviewTracker export)."""
    import csv
    import io
    
    try:
        await update_job_status(job_id, "processing", progress=70)
        
        # Decode and parse CSV
        content = file_bytes.decode('utf-8-sig')  # Handle BOM
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        
        await update_job_status(job_id, "processing", progress=90)
        
        return {
            "success": True,
            "rows": rows,
            "total_rows": len(rows),
            "columns": reader.fieldnames if hasattr(reader, 'fieldnames') else []
        }
        
    except Exception as e:
        logger.error(f"CSV processing error: {e}")
        return {"success": False, "error": str(e), "rows": []}


# ============================================================================
# CLEANUP
# ============================================================================

@upload_jobs_router.post("/cleanup")
async def cleanup_old_jobs(days: int = 7):
    """Clean up jobs older than specified days."""
    db = get_db()
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Delete old jobs
    result = await db.upload_jobs.delete_many({
        "created_at": {"$lt": cutoff}
    })
    
    # Delete orphaned chunks
    job_ids = await db.upload_jobs.distinct("job_id")
    chunk_result = await db.upload_chunks.delete_many({
        "job_id": {"$nin": job_ids}
    })
    
    return {
        "deleted_jobs": result.deleted_count,
        "deleted_chunks": chunk_result.deleted_count
    }
