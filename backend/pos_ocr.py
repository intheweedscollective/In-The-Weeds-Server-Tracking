"""
POS Report OCR Module
Extracts employee performance data from uploaded POS report images using AI vision.
"""

import os
import base64
import json
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# System prompt for extracting POS data
POS_EXTRACTION_PROMPT = """You are an expert at extracting employee performance data from Aloha POS Server Sales Detail Reports.

REPORT STRUCTURE - Server Sales Detail Report:
- Employee name at the TOP of the page
- Table with columns: Category | Qty Sold | Gross Sls | Net Sls | Void | Comp | Promo | Emp Disc
- Categories include: Food, Liquor, Beer, Wine, Bar Glassware, Loyalty, etc.
- Summary section at bottom with "Total Guests"

CRITICAL: Extract values from the "Net Sls" column ONLY (not Gross Sls).

DATA TO EXTRACT:
1. **Employee Name** - At top of page (e.g., "Terrance Kott", "Kitti Smith")
2. **Total Guests** - From summary section at bottom (number of guests served)
3. **Net Sales by Category** - From the "Net Sls" column for each row:
   - **Food** → food_sales
   - **Liquor** → liquor_sales  
   - **Beer** → beer_sales
   - **Wine** → wine_sales
   - **Bar Glassware** → bar_glassware_sales
   - **Loyalty** → loyalty_sales
   - **Total (grand total row)** → net_sales

FORMULAS (DO NOT calculate these - I will calculate them):
- PPA = net_sales / guest_count
- LBW per guest = (liquor_sales + beer_sales + wine_sales) / guest_count
- Glassware per guest = bar_glassware_sales / guest_count
- Guests per LSC = guest_count / (loyalty_sales / 25)

Return RAW extracted values - do NOT pre-calculate PPA, LBW per guest, etc.

JSON FORMAT:
{
  "report_date": "YYYY-MM-DD or null",
  "report_type": "server_sales_detail",
  "employees": [
    {
      "name": "Employee Name",
      "guest_count": 725,
      "net_sales": 38274.79,
      "food_sales": 28500.00,
      "liquor_sales": 3467.00,
      "beer_sales": 1960.00,
      "wine_sales": 238.00,
      "bar_glassware_sales": 837.00,
      "loyalty_sales": 250.00
    }
  ],
  "extraction_notes": "Any issues or notes"
}

IMPORTANT:
- Use "Net Sls" column values, NOT "Gross Sls"
- Extract numbers as-is without $ signs or commas
- If a category row doesn't exist, use null
- Do NOT calculate derived values like PPA or LBW/guest

Return ONLY valid JSON."""


async def extract_pos_data_from_image(image_base64: str, mime_type: str = "image/jpeg") -> Dict[str, Any]:
    """
    Extract employee performance data from a POS report image using AI vision.
    
    Args:
        image_base64: Base64 encoded image data
        mime_type: MIME type of the image (image/jpeg, image/png, image/webp)
    
    Returns:
        Dictionary containing extracted employee data
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY not configured", "employees": []}
    
    try:
        # Initialize chat with vision model
        chat = LlmChat(
            api_key=api_key,
            session_id=f"pos-ocr-{os.urandom(8).hex()}",
            system_message=POS_EXTRACTION_PROMPT
        ).with_model("openai", "gpt-4o")  # gpt-4o has strong vision capabilities
        
        # Create image content using ImageContent for base64 images
        image_content = ImageContent(image_base64=image_base64)
        
        # Send message with image - use file_contents parameter with ImageContent
        user_message = UserMessage(
            text="Please extract all employee performance data from this POS report image. Return the data as JSON.",
            file_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
        # Log response for debugging
        import logging
        logging.info(f"OCR Response (first 500 chars): {response[:500] if response else 'Empty response'}")
        
        if not response or not response.strip():
            return {
                "error": "AI returned empty response",
                "employees": []
            }
        
        # Parse JSON response
        # Clean up response - remove markdown code blocks if present
        cleaned_response = response.strip()
        if cleaned_response.startswith("```"):
            # Remove markdown code block
            cleaned_response = re.sub(r'^```(?:json)?\n?', '', cleaned_response)
            cleaned_response = re.sub(r'\n?```$', '', cleaned_response)
        
        try:
            data = json.loads(cleaned_response)
            return data
        except json.JSONDecodeError as e:
            return {
                "error": f"Failed to parse AI response as JSON: {str(e)}",
                "raw_response": response[:500],
                "employees": []
            }
            
    except Exception as e:
        import logging
        import traceback
        logging.error(f"OCR extraction error: {str(e)}\n{traceback.format_exc()}")
        return {
            "error": f"OCR extraction failed: {str(e)}",
            "employees": []
        }


def validate_extracted_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and clean extracted POS data.
    
    Args:
        data: Raw extracted data from OCR
    
    Returns:
        Validated and cleaned data
    """
    if "error" in data and not data.get("employees"):
        return data
    
    employees = data.get("employees", [])
    validated_employees = []
    
    for emp in employees:
        if not emp.get("name"):
            continue
        
        # Extract all sales data
        net_sales = _safe_float(emp.get("net_sales"))
        guest_count = _safe_int(emp.get("guest_count"))
        food_sales = _safe_float(emp.get("food_sales"))
        liquor_sales = _safe_float(emp.get("liquor_sales"))
        beer_sales = _safe_float(emp.get("beer_sales"))
        wine_sales = _safe_float(emp.get("wine_sales"))
        loyalty_sales = _safe_float(emp.get("loyalty_sales"))
        bar_glassware_sales = _safe_float(emp.get("bar_glassware_sales"))
        
        # Calculate LBW total if not provided but components are
        lbw_per_guest = _safe_float(emp.get("lbw_per_guest"))
        if lbw_per_guest is None and guest_count and guest_count > 0:
            lbw_total = (liquor_sales or 0) + (beer_sales or 0) + (wine_sales or 0)
            if lbw_total > 0:
                lbw_per_guest = lbw_total / guest_count
        
        # Calculate PPA if not provided
        ppa = _safe_float(emp.get("ppa"))
        if ppa is None and net_sales and guest_count and guest_count > 0:
            ppa = net_sales / guest_count
        
        # Calculate LSC count from loyalty_sales (each LSC = $25)
        # Then calculate guests_per_lsc = guest_count / lsc_count
        guests_per_lsc = _safe_float(emp.get("guests_per_lsc"))
        if guests_per_lsc is None and loyalty_sales and loyalty_sales > 0 and guest_count and guest_count > 0:
            lsc_count = loyalty_sales / 25.0  # Number of LSC cards sold
            if lsc_count > 0:
                guests_per_lsc = guest_count / lsc_count  # Guests per LSC card
        
        # Calculate glassware_per_guest from bar_glassware_sales
        # Glassware per guest = Bar Glassware sales / Guest Count
        glassware_per_guest = _safe_float(emp.get("glassware_per_guest"))
        if glassware_per_guest is None and bar_glassware_sales and guest_count and guest_count > 0:
            glassware_per_guest = bar_glassware_sales / guest_count
            
        validated_emp = {
            "name": str(emp.get("name", "")).strip(),
            "ppa": ppa,
            "lbw_per_guest": lbw_per_guest,
            "glassware_per_guest": glassware_per_guest,
            "guest_count": guest_count,
            "net_sales": net_sales,
            "guests_per_lsc": guests_per_lsc,
            "loyalty_sales": loyalty_sales,
            "tips": _safe_float(emp.get("tips")),
            "hours": _safe_float(emp.get("hours"))
        }
        
        # Only include if we have at least name and one metric
        if validated_emp["name"] and any([
            validated_emp["ppa"],
            validated_emp["lbw_per_guest"],
            validated_emp["guest_count"],
            validated_emp["net_sales"]
        ]):
            validated_employees.append(validated_emp)
    
    return {
        "report_date": data.get("report_date"),
        "report_type": data.get("report_type", "unknown"),
        "employees": validated_employees,
        "extraction_notes": data.get("extraction_notes", ""),
        "employee_count": len(validated_employees)
    }


def _safe_float(value) -> Optional[float]:
    """Safely convert value to float."""
    if value is None:
        return None
    try:
        # Handle string values with $ or commas
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
        return float(value) if value else None
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> Optional[int]:
    """Safely convert value to int."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(float(value)) if value else None
    except (ValueError, TypeError):
        return None


async def extract_pos_data_from_pdf(pdf_bytes: bytes, max_pages: int = 5) -> Dict[str, Any]:
    """
    Extract employee performance data from a PDF file.
    Converts PDF pages to images and processes each with OCR.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        max_pages: Maximum number of pages to process (default 5 to prevent timeout)
    
    Returns:
        Dictionary containing extracted employee data from all pages
    """
    import fitz  # PyMuPDF
    from io import BytesIO
    import logging
    import asyncio
    
    try:
        # Open PDF with PyMuPDF
        logging.info("Starting PDF conversion with PyMuPDF...")
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        total_pages = len(pdf_document)
        logging.info(f"PDF has {total_pages} pages")
        
        if total_pages == 0:
            return {"error": "PDF has no pages", "employees": []}
        
        # Limit pages to prevent timeout
        pages_to_process = min(total_pages, max_pages)
        if total_pages > max_pages:
            logging.warning(f"PDF has {total_pages} pages, limiting to {max_pages}")
        
        # Convert all pages to images first
        page_images = []
        for page_num in range(pages_to_process):
            page = pdf_document[page_num]
            mat = fitz.Matrix(150/72, 150/72)  # 150 DPI
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
            image_base64 = base64.b64encode(img_bytes).decode('utf-8')
            page_images.append((page_num, image_base64))
        
        pdf_document.close()
        
        # Process pages in parallel (3 at a time to avoid rate limits)
        all_employees = []
        extraction_notes = []
        report_date = None
        report_type = "unknown"
        
        async def process_page(page_num, image_base64):
            logging.info(f"Processing page {page_num + 1}/{pages_to_process}...")
            return page_num, await extract_pos_data_from_image(image_base64, "image/jpeg")
        
        # Process in batches of 3
        batch_size = 3
        for i in range(0, len(page_images), batch_size):
            batch = page_images[i:i+batch_size]
            tasks = [process_page(page_num, img) for page_num, img in batch]
            results = await asyncio.gather(*tasks)
            
            for page_num, page_data in results:
                if page_data.get("employees"):
                    all_employees.extend(page_data["employees"])
                    
                if page_data.get("report_date") and not report_date:
                    report_date = page_data["report_date"]
                    
                if page_data.get("report_type") and page_data["report_type"] != "unknown":
                    report_type = page_data["report_type"]
                    
                if page_data.get("extraction_notes"):
                    extraction_notes.append(f"Page {page_num + 1}: {page_data['extraction_notes']}")
                
                if page_data.get("error"):
                    extraction_notes.append(f"Page {page_num + 1}: {page_data['error']}")
        
        # Deduplicate employees by name (keep the one with more data)
        unique_employees = _deduplicate_employees(all_employees)
        
        # If no employees found after processing all pages, include error info
        if not unique_employees:
            return {
                "error": f"No employee data found in {pages_to_process} page(s). The PDF may not contain recognizable POS report data.",
                "extraction_notes": "; ".join(extraction_notes) if extraction_notes else "No data extracted",
                "employees": [],
                "pages_processed": pages_to_process,
                "total_pages": total_pages
            }
        
        note_suffix = ""
        if total_pages > max_pages:
            note_suffix = f" (PDF had {total_pages} pages, processed first {max_pages})"
        
        return {
            "report_date": report_date,
            "report_type": report_type,
            "employees": unique_employees,
            "extraction_notes": ("; ".join(extraction_notes) if extraction_notes else f"Processed {pages_to_process} page(s)") + note_suffix,
            "pages_processed": pages_to_process,
            "total_pages": total_pages
        }
        
    except Exception as e:
        import traceback
        import logging
        logging.error(f"PDF processing error: {str(e)}\n{traceback.format_exc()}")
        return {
            "error": f"PDF processing failed: {str(e)}",
            "employees": []
        }


def _deduplicate_employees(employees: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate employees by name, keeping the entry with more data.
    """
    seen = {}
    for emp in employees:
        name = emp.get("name", "").strip().lower()
        if not name:
            continue
            
        # Count non-null fields
        data_count = sum(1 for v in emp.values() if v is not None and v != "")
        
        if name not in seen or data_count > seen[name]["_count"]:
            emp["_count"] = data_count
            seen[name] = emp
    
    # Remove the _count field before returning
    result = []
    for emp in seen.values():
        emp.pop("_count", None)
        result.append(emp)
    
    return result
