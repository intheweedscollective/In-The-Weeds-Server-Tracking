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

REPORT STRUCTURE:
- Employee name at TOP of the page (e.g., "Chase Winston", "Starwars Mckinnon-Herrera")
- Table with columns: Category | Qty Sold | Gross Sls | Net Sls | Void | Comp | Promo | Emp Disc | Guest Avg
- Each row is a sales category. ALWAYS look for these rows in the table:
  * Food
  * Liquor
  * Beer
  * Wine
  * Bar Glassware (may appear as "Brglswre", "Bar Glass", "Glassware")
  * Loyalty (may appear as "Loyany", "LSC", "Loyal" - this is CRITICAL, don't miss it!)
  * Totals (bottom row with summary values)
- Summary section at bottom with "Total Guests" or "Ttl Guests"

CRITICAL - LOYALTY ROW:
The Loyalty row is often near the bottom of the category table, sometimes between other rows.
- Look for ANY row containing "Loyal", "LSC", "Loyany", "Loyalty"
- The Net Sls value = number of cards × $25 (e.g., 2 cards = $50.00, 11 cards = $275.00)
- If you see Qty Sold = 2 and Net Sls = 50.00, that's the Loyalty row
- DO NOT return 0 unless you are 100% certain there is NO Loyalty row

CRITICAL - PPA (GUEST AVERAGE):
The PPA is found in the "Totals" row under the "Guest Avg" or "Guest Average" column.
- Look at the LAST column in the Totals row - this is the PPA value
- Example: If Totals row shows Guest Avg = 52.29, then ppa = 52.29
- This is the pre-calculated PPA from the register system - use this exact value
- DO NOT calculate PPA yourself - extract the Guest Avg value from the Totals row

EXTRACT THESE VALUES (use Net Sls column unless specified):
1. **name** - Employee name at top
2. **guest_count** - "Total Guests" number
3. **ppa** - CRITICAL: The "Guest Avg" value from the TOTALS row (e.g., 52.29)
4. **net_sales** - Grand Total row (sum of all categories)
5. **food_sales** - Food row
6. **liquor_sales** - Liquor row
7. **beer_sales** - Beer row
8. **wine_sales** - Wine row
9. **bar_glassware_sales** - Bar Glassware row (may also be labeled "Brglswre" or just "Glassware")
10. **loyalty_sales** - Loyalty row (CRITICAL - this row ALWAYS exists, scan the ENTIRE table for it!)

CRITICAL INSTRUCTIONS:
- The "Loyalty" row is ALWAYS present in the table, usually between other category rows
- Even if Loyalty sales are small (like $25 or $50), you MUST extract this value
- Bar Glassware row is also ALWAYS present
- DO NOT return 0 for these fields unless you have verified the row shows 0.00
- Scan ALL rows in the Sales By Category section carefully

JSON FORMAT:
{
  "report_date": "YYYY-MM-DD or null",
  "report_type": "server_sales_detail",
  "employees": [
    {
      "name": "Employee Name",
      "guest_count": 725,
      "ppa": 52.29,
      "net_sales": 38274.79,
      "food_sales": 28500.00,
      "liquor_sales": 3467.00,
      "beer_sales": 1960.00,
      "wine_sales": 238.00,
      "bar_glassware_sales": 837.00,
      "loyalty_sales": 250.00
    }
  ],
  "extraction_notes": "Describe what you found"
}

IMPORTANT:
- The Loyalty row is ALWAYS present - scan every row in the Sales By Category section
- Even small amounts ($25, $50, $100) MUST be captured from the Loyalty row
- Bar Glassware is also ALWAYS present - look for "Bar Glassware" or "Brglswre"
- Use 0 ONLY if the Net Sls column for that row literally shows 0.00 or is blank
- ALWAYS extract the ppa from the Guest Avg column in the Totals row
- Remove $ signs and commas from numbers
- Double-check that you have extracted loyalty_sales before returning

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
    import asyncio
    import logging
    
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
        
        # Add timeout to prevent hanging on slow responses (60 seconds per page)
        try:
            response = await asyncio.wait_for(
                chat.send_message(user_message),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            logging.warning("OCR request timed out after 60 seconds")
            return {
                "error": "OCR request timed out - page may be too complex",
                "employees": []
            }
        
        # Log response for debugging
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
        
        # Use PPA from report's Guest Avg column if provided
        # Only fall back to calculation if not available
        ppa = _safe_float(emp.get("ppa"))
        if ppa is None or ppa == 0:
            # Fallback: calculate PPA from net_sales / guest_count
            if net_sales and guest_count and guest_count > 0:
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
            "hours": _safe_float(emp.get("hours")),
            # Include raw extracted values for debugging
            "_raw": {
                "liquor_sales": liquor_sales,
                "beer_sales": beer_sales,
                "wine_sales": wine_sales,
                "bar_glassware_sales": bar_glassware_sales,
                "food_sales": food_sales
            }
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
    """Safely convert value to float. Handles spaces, commas, merged cells."""
    if value is None:
        return None
    try:
        val_str = str(value).strip()
        
        # If empty, return None
        if not val_str:
            return None
        
        # Remove $ signs
        val_str = val_str.replace("$", "")
        
        # Handle OCR-style errors with spaces in numbers
        # Examples: "51 ,70633" -> "51706.33", "21 962.81" -> "21962.81"
        # "67,671 .77" -> "67671.77", "67,671 .77  5,588.29" -> "67671.77"
        
        # Check if there are multiple space-separated parts
        parts = val_str.split()
        
        if len(parts) >= 2:
            raw_second = parts[1]
            first = parts[0].rstrip(',.')
            
            # If second part starts with decimal, join ONLY first two parts
            # "67,671 .77  5,588.29" -> join "67,671" + ".77" = "67,671.77"
            if raw_second.startswith('.'):
                # Join only first and second part
                val_str = first + raw_second.split()[0] if ' ' in raw_second else first + raw_second
                # Actually raw_second is already split, so it's just ".77"
                val_str = first + raw_second
            elif raw_second.startswith(','):
                # "51 ,70633" -> join first two: "51,70633"
                val_str = first + raw_second
            else:
                # Check if it looks like a broken number
                second = raw_second
                first_ends_digit = first and first[-1].isdigit()
                second_starts_digit = second and second[0].isdigit()
                
                if first_ends_digit and second_starts_digit:
                    # "21 962.81" -> "21962.81"
                    if '.' not in first and '.' in second:
                        val_str = first + second
                    elif len(first.replace(",", "")) <= 2:
                        # First part too short, join
                        val_str = first + second
                    else:
                        # First looks complete
                        val_str = first
                else:
                    val_str = first
        
        # Remove all spaces
        val_str = val_str.replace(" ", "")
        
        # Handle comma as thousand separator
        val_str = val_str.replace(",", "")
        
        # Validate it's a number
        if not val_str or not val_str.replace(".", "").replace("-", "").isdigit():
            return None
        
        num = float(val_str)
        
        # Handle case where decimal might be missing: "5170633" should be "51706.33"
        # But only if unreasonably large and no decimal
        if num > 100000 and "." not in val_str:
            val_str = val_str[:-2] + "." + val_str[-2:]
            num = float(val_str)
        
        return num
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> Optional[int]:
    """Safely convert value to int. Handles spaces in numbers like '61 5' -> 615"""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            # Remove spaces, commas, and other formatting
            value = value.replace(",", "").replace(" ", "").strip()
        return int(float(value)) if value else None
    except (ValueError, TypeError):
        return None


async def extract_pos_data_from_pdf(pdf_bytes: bytes, max_pages: int = 60) -> Dict[str, Any]:
    """
    Extract employee performance data from a PDF file.
    Converts PDF pages to images and processes each with OCR.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        max_pages: Maximum number of pages to process (default 60 for full team reports)
    
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
        
        # Convert all pages to images first - use lower DPI for faster processing
        page_images = []
        for page_num in range(pages_to_process):
            page = pdf_document[page_num]
            # Use 120 DPI for better OCR accuracy while keeping reasonable file size
            mat = fitz.Matrix(120/72, 120/72)
            pix = page.get_pixmap(matrix=mat)
            # Use JPEG with quality setting for smaller file size
            img_bytes = pix.tobytes("jpeg")
            image_base64 = base64.b64encode(img_bytes).decode('utf-8')
            page_images.append((page_num, image_base64))
        
        pdf_document.close()
        
        # Process pages in parallel (5 at a time for speed while staying under rate limits)
        all_employees = []
        extraction_notes = []
        report_date = None
        report_type = "unknown"
        
        async def process_page(page_num, image_base64):
            logging.info(f"Processing page {page_num + 1}/{pages_to_process}...")
            return page_num, await extract_pos_data_from_image(image_base64, "image/jpeg")
        
        # Process pages in batches of 3 for reliability (reduces timeout risk)
        batch_size = 3
        for i in range(0, len(page_images), batch_size):
            batch = page_images[i:i+batch_size]
            tasks = [process_page(page_num, img) for page_num, img in batch]
            
            # Add overall timeout for the batch (3 pages × 60 seconds each + buffer)
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=210.0  # 3.5 minutes per batch
                )
            except asyncio.TimeoutError:
                logging.warning(f"Batch {i//batch_size + 1} timed out, continuing with next batch...")
                extraction_notes.append(f"Batch {i//batch_size + 1} timed out")
                continue
            
            for result in results:
                # Handle exceptions from gather
                if isinstance(result, Exception):
                    logging.error(f"Page processing error: {str(result)}")
                    extraction_notes.append(f"Page error: {str(result)}")
                    continue
                    
                page_num, page_data = result
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
    Deduplicate employees by name, MERGING data from multiple extractions.
    This ensures we capture data that might be extracted from different pages.
    """
    seen = {}
    for emp in employees:
        name = emp.get("name", "").strip().lower()
        if not name:
            continue
        
        if name not in seen:
            # First time seeing this employee
            seen[name] = emp.copy()
        else:
            # Merge data - keep non-zero values from either extraction
            existing = seen[name]
            for key, value in emp.items():
                if key == "name":
                    continue
                # If the new value is better (non-null, non-zero), use it
                existing_val = existing.get(key)
                if value is not None and value != "" and value != 0:
                    if existing_val is None or existing_val == "" or existing_val == 0:
                        existing[key] = value
                    elif isinstance(value, (int, float)) and isinstance(existing_val, (int, float)):
                        # For numeric values, keep the larger non-zero value (likely more complete data)
                        if value > existing_val:
                            existing[key] = value
    
    return list(seen.values())


def extract_pos_data_from_xlsx(xlsx_bytes: bytes) -> Dict[str, Any]:
    """
    Extract employee performance data from an XLSX file.
    
    Supports TWO formats:
    1. Multi-sheet format: Each employee has their own sheet/tab
    2. Consolidated format: All employees on a single sheet (new format)
    
    Multi-sheet Structure (per sheet):
    - Row 5, Column F: Employee Name (yellow cell)
    - Row 10-37: Category rows (Food, Liquor, Beer, Wine, Bar Glassware, Loyalty, etc.)
    - Row 16 (Loyalty): Net Sales / 25 = LSC Count
    - Row 31 (Bar Glassware): Net Sales for glassware
    - Row 38: Totals row with Net Sales
    - Row 42: Total Guests
    
    Consolidated Structure (single sheet):
    - "Server Sales Page X of Y" headers with employee names
    - SALES BY CATEGORY sections
    - Total Guests per employee block
    - Loyalty $ and Loyalty Qty rows
    
    Args:
        xlsx_bytes: Raw XLSX file bytes
    
    Returns:
        Dictionary containing extracted employee data from all sheets
    """
    import openpyxl
    from io import BytesIO
    import logging
    import tempfile
    import os
    
    try:
        logging.info("Starting XLSX extraction with openpyxl...")
        workbook = openpyxl.load_workbook(BytesIO(xlsx_bytes), data_only=True)
        
        logging.info(f"XLSX has {len(workbook.sheetnames)} sheets: {workbook.sheetnames[:5]}...")
        
        # Check for "SSD Engine" / Summary format - has Master_Summary or similar sheets
        summary_sheet_names = ['Master_Summary', 'Summary', 'Parsed_Data']
        has_summary_sheet = any(sheet in workbook.sheetnames for sheet in summary_sheet_names)
        
        # Check if this is a consolidated format (few sheets OR has known summary sheet)
        is_consolidated = False
        if has_summary_sheet:
            logging.info(f"Detected summary sheet format - found one of {summary_sheet_names}")
            is_consolidated = True
        elif len(workbook.sheetnames) <= 5:
            # Check first sheet for consolidated format markers (Server Sales blocks)
            first_sheet = workbook[workbook.sheetnames[0]]
            markers_found = 0
            for row in range(1, min(100, first_sheet.max_row + 1)):
                for col in range(1, min(20, first_sheet.max_column + 1)):
                    cell_val = first_sheet.cell(row=row, column=col).value
                    if cell_val:
                        cell_str = str(cell_val).lower()
                        if 'server sales' in cell_str and 'page' in cell_str:
                            markers_found += 1
                        if markers_found >= 2:
                            is_consolidated = True
                            break
                if is_consolidated:
                    break
        
        if is_consolidated:
            logging.info("Detected CONSOLIDATED format - using specialized parser")
            workbook.close()
            
            # Use the consolidated parser from pos_report_parser
            from pos_report_parser import parse_consolidated_pos_report
            import tempfile
            
            # Save bytes to temp file for the parser
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                tmp.write(xlsx_bytes)
                tmp_path = tmp.name
            
            try:
                parsed_employees = parse_consolidated_pos_report(tmp_path)
            finally:
                os.unlink(tmp_path)
            
            if not parsed_employees:
                return {
                    "error": "No employee data found in consolidated XLSX file.",
                    "extraction_notes": "Consolidated format detected but no data extracted",
                    "employees": []
                }
            
            # Transform to expected output format
            all_employees = []
            for emp in parsed_employees:
                guest_count = emp.get('guests', 0) or 1  # Avoid division by zero
                net_sales = emp.get('net_sales', 0) or 0
                lbw_total = emp.get('lbw', 0) or 0
                glassware = emp.get('glassware', 0) or 0
                loyalty_sales = emp.get('loyalty_sales', 0) or 0
                lsc_count = emp.get('lsc_count', 0) or 0
                
                # Use extracted PPA if available, else calculate
                extracted_ppa = emp.get('ppa', 0) or 0
                if extracted_ppa and extracted_ppa > 0:
                    ppa = extracted_ppa
                else:
                    ppa = net_sales / guest_count if guest_count > 0 else 0
                
                lbw_per_guest = lbw_total / guest_count if guest_count > 0 else 0
                glassware_per_guest = glassware / guest_count if guest_count > 0 else 0
                guests_per_lsc = guest_count / lsc_count if lsc_count > 0 else None
                
                employee_data = {
                    "name": emp.get('name'),
                    "ppa": round(ppa, 2) if ppa else None,
                    "lbw_per_guest": round(lbw_per_guest, 2) if lbw_per_guest else None,
                    "glassware_per_guest": round(glassware_per_guest, 2) if glassware_per_guest else None,
                    "guest_count": guest_count,
                    "net_sales": round(net_sales, 2) if net_sales else None,
                    "guests_per_lsc": round(guests_per_lsc, 2) if guests_per_lsc else None,
                    "loyalty_sales": round(loyalty_sales, 2) if loyalty_sales else None,
                    "lsc_count": lsc_count,
                    "_raw": {
                        "food_sales": round(emp.get('food', 0), 2),
                        "liquor_sales": round(emp.get('liquor', 0), 2),
                        "beer_sales": round(emp.get('beer', 0), 2),
                        "wine_sales": round(emp.get('wine', 0), 2),
                        "bar_glassware_sales": round(glassware, 2),
                        "lbw_total": round(lbw_total, 2),
                        "lsc_count": lsc_count
                    }
                }
                all_employees.append(employee_data)
                logging.info(f"Extracted (consolidated): {emp.get('name')} - Guests: {guest_count}, Net: ${net_sales:.2f}, PPA: ${ppa:.2f}, LSC: {lsc_count}")
            
            return {
                "report_date": None,
                "report_type": "server_sales_consolidated",
                "employees": all_employees,
                "extraction_notes": f"Extracted {len(all_employees)} employees from consolidated format",
                "sheets_processed": 1,
                "employee_count": len(all_employees)
            }
        
        # Original multi-sheet processing
        logging.info("Using MULTI-SHEET format parser")
        all_employees = []
        extraction_notes = []
        report_date = None
        
        skipped_sheets = []
        
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            
            try:
                # Extract employee name - try multiple locations
                employee_name = None
                
                def is_valid_name(val):
                    """Check if a value looks like a person name (not date, number, or address)"""
                    if not val or len(val) < 3:
                        return False
                    val = str(val).strip()
                    # Reject dates (contains / or starts with digits like 01/01)
                    if '/' in val or '—' in val or '--' in val:
                        return False
                    # Reject numbers
                    if val.replace('.','').replace(',','').replace(' ','').isdigit():
                        return False
                    # Reject addresses (contains state abbreviations or zip codes)
                    if any(x in val for x in ['NV ', 'CA ', 'AZ ', '89109', '89101', '89102', '89103', '89104']):
                        return False
                    # Reject if starts with digits
                    if val[0].isdigit():
                        return False
                    return True
                
                # Primary location based on user feedback: cell N11 (row 11, column 14)
                name_cell = sheet.cell(row=11, column=14).value
                if name_cell and is_valid_name(name_cell):
                    employee_name = str(name_cell).strip()
                
                # Try H11 (row 11, column 8) - seen in some sheets
                if not employee_name:
                    name_cell = sheet.cell(row=11, column=8).value
                    if name_cell and is_valid_name(name_cell):
                        employee_name = str(name_cell).strip()
                
                # Fallback: cell F5 (row 5, column 6) - original location
                if not employee_name:
                    name_cell = sheet.cell(row=5, column=6).value
                    if name_cell and is_valid_name(name_cell):
                        employee_name = str(name_cell).strip()
                
                # Fallback: Check other common name locations (rows 4-6, 10-12 across columns D-P)
                if not employee_name:
                    for row in [11, 5, 4, 6, 10, 12]:
                        for col in range(4, 17):  # D through P
                            cell_val = sheet.cell(row=row, column=col).value
                            if cell_val and is_valid_name(cell_val):
                                employee_name = str(cell_val).strip()
                                break
                        if employee_name:
                            break
                
                # Last resort: Use sheet name if it looks like a name
                if not employee_name:
                    if sheet_name and not sheet_name.lower().startswith('sheet') and is_valid_name(sheet_name):
                        employee_name = sheet_name
                
                # Skip sheets without a valid employee name
                if not employee_name:
                    logging.warning(f"Skipping sheet '{sheet_name}': No valid employee name found")
                    skipped_sheets.append(sheet_name)
                    continue
                
                # Try to extract date from row 3 (e.g., "01/01/2026 — 03/01/2026")
                if not report_date:
                    date_cell = sheet.cell(row=3, column=6).value
                    if date_cell:
                        report_date = str(date_cell).strip()
                
                # Extract data from specific rows
                # Row numbers based on the Aloha Server Sales Detail format
                
                def get_net_sales_value(row_num) -> float:
                    """Get the Net Sales value from columns C, D, or E for a given row."""
                    if not row_num:
                        return 0.0
                    # Try columns C (3), D (4), E (5) - Net Sales might be in different columns
                    for col in [3, 4, 5]:
                        val = sheet.cell(row=row_num, column=col).value
                        parsed = _safe_float(val)
                        if parsed and parsed > 0:
                            return parsed
                    return 0.0
                
                def find_row_by_label(label: str, start_row: int = 1, end_row: int = 60) -> Optional[int]:
                    """Find a row by searching for a label in columns A, B, or C."""
                    label_lower = label.lower().replace(" ", "")  # Remove spaces for matching
                    for row in range(start_row, end_row + 1):
                        for col in range(1, 4):  # Check columns A, B, C
                            cell_val = sheet.cell(row=row, column=col).value
                            if cell_val:
                                # Remove spaces from cell value for comparison (handles "Tota ls" -> "totals")
                                cell_clean = str(cell_val).lower().replace(" ", "")
                                if label_lower in cell_clean:
                                    return row
                    return None
                
                def get_guest_avg_value(row_num) -> float:
                    """Get the Guest Average (PPA) from the Totals row - typically in columns F-L."""
                    if not row_num:
                        return 0.0
                    # Guest Avg is typically in columns F (6), G (7), H (8), or later
                    # It's usually one of the last columns with data
                    for col in range(6, 15):  # Columns F through N
                        # First, check if the header row has "Guest Avg" above this column
                        # The header is typically 2-3 rows above the Totals row
                        for header_offset in range(1, 4):
                            if row_num - header_offset > 0:
                                header_val = sheet.cell(row=row_num - header_offset, column=col).value
                                if header_val:
                                    header_str = str(header_val).lower().replace(" ", "")
                                    if "guestavg" in header_str or "gstavg" in header_str or "guest avg" in str(header_val).lower():
                                        val = sheet.cell(row=row_num, column=col).value
                                        parsed = _safe_float(val)
                                        if parsed and parsed > 0 and parsed < 500:  # PPA typically $10-$200
                                            return parsed
                    return 0.0
                
                # Find key rows by label - search entire sheet with wide ranges
                food_row = find_row_by_label("food", 1, 60)
                liquor_row = find_row_by_label("liquor", 1, 60)
                beer_row = find_row_by_label("beer", 1, 60)
                wine_row = find_row_by_label("wine", 1, 60)
                loyalty_row = find_row_by_label("loyalty", 1, 60)
                glassware_row = find_row_by_label("bar glassware", 1, 60) or find_row_by_label("glassware", 1, 60)
                totals_row = find_row_by_label("totals", 1, 60)
                
                # If totals not found, try alternative labels
                if not totals_row:
                    totals_row = find_row_by_label("total", 30, 60)  # Just "total" as fallback
                
                # Extract values - use found rows or skip if critical rows missing
                food_sales = get_net_sales_value(food_row) if food_row else 0.0
                liquor_sales = get_net_sales_value(liquor_row) if liquor_row else 0.0
                beer_sales = get_net_sales_value(beer_row) if beer_row else 0.0
                wine_sales = get_net_sales_value(wine_row) if wine_row else 0.0
                loyalty_sales = get_net_sales_value(loyalty_row) if loyalty_row else 0.0
                bar_glassware_sales = get_net_sales_value(glassware_row) if glassware_row else 0.0
                net_sales = get_net_sales_value(totals_row) if totals_row else 0.0
                
                # Extract PPA from Guest Avg column in Totals row
                extracted_ppa = get_guest_avg_value(totals_row) if totals_row else 0.0
                
                # Log if key data is missing
                if not totals_row or net_sales == 0:
                    logging.warning(f"Sheet '{sheet_name}': Could not find Totals row for {employee_name}. Food row: {food_row}, Totals row: {totals_row}")
                
                # Find "Total Guests" row - search the entire sheet
                guests_row = None
                guest_count = None
                
                # Search for "total guests" label (with space handling)
                for row in range(1, 100):
                    for col in range(1, 11):
                        cell_val = sheet.cell(row=row, column=col).value
                        if cell_val:
                            # Remove spaces for comparison (handles "Total Guests" or "TotalGuests")
                            cell_clean = str(cell_val).lower().replace(" ", "")
                            if "totalguests" in cell_clean or "totalguest" in cell_clean:
                                guests_row = row
                                # Guest count might be in the same row but different column
                                for val_col in range(1, 11):
                                    val = _safe_int(sheet.cell(row=row, column=val_col).value)
                                    if val and val > 0 and val < 100000:  # Reasonable guest count
                                        guest_count = val
                                        break
                                if guest_count:
                                    break
                    if guest_count:
                        break
                
                # If not found, try searching for "Num Guests" pattern
                if not guest_count:
                    for row in range(1, 100):
                        for col in range(1, 11):
                            cell_val = sheet.cell(row=row, column=col).value
                            if cell_val:
                                cell_clean = str(cell_val).lower().replace(" ", "")
                                if cell_clean in ['numguests', 'numguests:', 'guests', 'guestcount']:
                                    # Look in next rows for the actual count
                                    for check_row in range(row, row + 5):
                                        for val_col in range(1, 11):
                                            val = _safe_int(sheet.cell(row=check_row, column=val_col).value)
                                            if val and val > 10 and val < 100000:
                                                guest_count = val
                                                break
                                        if guest_count:
                                            break
                                if guest_count:
                                    break
                        if guest_count:
                            break
                
                # Last resort: Look for a number after "Totals" row that could be guest count
                # Pattern: Shift A value + Shift B value = Total Guests
                if not guest_count and totals_row:
                    candidates = []
                    for row in range(totals_row + 2, totals_row + 15):
                        for col in range(3, 6):  # Check columns C, D, E
                            val = _safe_int(sheet.cell(row=row, column=col).value)
                            if val and val > 30 and val < 10000:
                                label_col2 = sheet.cell(row=row, column=2).value or ""
                                label_str = str(label_col2).lower().replace(" ", "")
                                candidates.append({
                                    'row': row,
                                    'col': col,
                                    'value': val,
                                    'label': label_str,
                                    'is_total': 'total' in label_str,
                                    'is_shift': 'shift' in label_str
                                })
                    
                    # First, prefer any value with "total" label (like "Total Guests")
                    for c in candidates:
                        if c['is_total']:
                            guest_count = c['value']
                            break
                    
                    # If no "total" label, look for Shift A + Shift B = Total pattern
                    # Find pairs where value[i] + value[i+shift_b] ≈ value[i+total]
                    if not guest_count and len(candidates) >= 3:
                        for i, c in enumerate(candidates):
                            # Check if this could be a "Total" (sum of previous two)
                            if i >= 2:
                                prev_vals = [candidates[j]['value'] for j in range(max(0, i-3), i)]
                                # Check if current value equals sum of any two previous
                                for j in range(len(prev_vals)):
                                    for k in range(j+1, len(prev_vals)):
                                        if prev_vals[j] + prev_vals[k] == c['value']:
                                            guest_count = c['value']
                                            break
                                    if guest_count:
                                        break
                            if guest_count:
                                break
                    
                    # Still no guest count? Take value that appears multiple times (likely total)
                    if not guest_count and candidates:
                        value_counts = {}
                        for c in candidates:
                            v = c['value']
                            value_counts[v] = value_counts.get(v, 0) + 1
                        # Find values that appear more than once
                        for v, count in sorted(value_counts.items(), key=lambda x: (-x[1], -x[0])):
                            if count > 1 and v > 100:
                                guest_count = v
                                break
                    
                    # Last fallback: take the largest reasonable value (but not comps which are usually < 1000)
                    if not guest_count and candidates:
                        # Filter to likely guest counts (100-3000 typical range)
                        guest_candidates = [c for c in candidates if 100 < c['value'] < 3000]
                        if guest_candidates:
                            guest_candidates.sort(key=lambda x: x['value'], reverse=True)
                            guest_count = guest_candidates[0]['value']
                
                # If still no guest count, log more details and skip
                if not guest_count or guest_count <= 0:
                    logging.warning(f"Sheet '{sheet_name}': No valid guest count for {employee_name}. Searched rows 1-100.")
                    # Log cells from various areas for debugging
                    debug_info = []
                    # Check around common areas
                    for r in [42, 43, 44, 50, 51, 52, 60, 61, 62]:
                        for c in range(1, 6):
                            v = sheet.cell(row=r, column=c).value
                            if v:
                                debug_info.append(f"R{r}C{c}={v}")
                    if debug_info:
                        logging.warning(f"  Sample cells: {', '.join(debug_info[:15])}")
                    extraction_notes.append(f"{employee_name}: Missing guest count")
                    continue
                
                # Calculate derived values
                # PPA = Use extracted Guest Avg if available, else calculate from Net Sales / Guests
                if extracted_ppa and extracted_ppa > 0:
                    ppa = extracted_ppa
                else:
                    ppa = net_sales / guest_count if guest_count > 0 else None
                
                # LBW Total = Liquor + Beer + Wine
                lbw_total = liquor_sales + beer_sales + wine_sales
                lbw_per_guest = lbw_total / guest_count if guest_count > 0 else None
                
                # Glassware per guest
                glassware_per_guest = bar_glassware_sales / guest_count if guest_count > 0 else None
                
                # LSC Count = Loyalty$ / 25 (each LSC card = $25)
                # Guests per LSC = Guest Count / LSC Count
                lsc_count = loyalty_sales / 25.0 if loyalty_sales > 0 else 0
                guests_per_lsc = guest_count / lsc_count if lsc_count > 0 else None
                
                employee_data = {
                    "name": employee_name,
                    "ppa": round(ppa, 2) if ppa else None,
                    "lbw_per_guest": round(lbw_per_guest, 2) if lbw_per_guest else None,
                    "glassware_per_guest": round(glassware_per_guest, 2) if glassware_per_guest else None,
                    "guest_count": guest_count,
                    "net_sales": round(net_sales, 2) if net_sales else None,
                    "guests_per_lsc": round(guests_per_lsc, 2) if guests_per_lsc else None,
                    "loyalty_sales": round(loyalty_sales, 2) if loyalty_sales else None,
                    "_raw": {
                        "food_sales": round(food_sales, 2),
                        "liquor_sales": round(liquor_sales, 2),
                        "beer_sales": round(beer_sales, 2),
                        "wine_sales": round(wine_sales, 2),
                        "bar_glassware_sales": round(bar_glassware_sales, 2),
                        "lbw_total": round(lbw_total, 2),
                        "lsc_count": round(lsc_count, 2)
                    }
                }
                
                all_employees.append(employee_data)
                ppa_str = f"${ppa:.2f}" if ppa else "$0.00"
                logging.info(f"Extracted: {employee_name} - Guests: {guest_count}, Net Sales: ${net_sales:.2f}, PPA: {ppa_str}")
                
            except Exception as sheet_error:
                logging.warning(f"Error processing sheet '{sheet_name}': {str(sheet_error)}")
                extraction_notes.append(f"Sheet '{sheet_name}': {str(sheet_error)}")
                continue
        
        workbook.close()
        
        if not all_employees:
            return {
                "error": "No employee data found in XLSX file. Ensure each sheet has employee name in cell F5 and valid sales data.",
                "extraction_notes": "; ".join(extraction_notes) if extraction_notes else "No valid sheets found",
                "employees": []
            }
        
        return {
            "report_date": report_date,
            "report_type": "server_sales_detail",
            "employees": all_employees,
            "extraction_notes": f"Extracted {len(all_employees)} employees from {len(workbook.sheetnames)} sheets" + (f". Issues: {'; '.join(extraction_notes)}" if extraction_notes else ""),
            "sheets_processed": len(workbook.sheetnames),
            "employee_count": len(all_employees)
        }
        
    except Exception as e:
        import traceback
        import logging
        logging.error(f"XLSX processing error: {str(e)}\n{traceback.format_exc()}")
        return {
            "error": f"XLSX processing failed: {str(e)}",
            "employees": []
        }
