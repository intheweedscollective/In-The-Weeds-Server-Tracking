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
POS_EXTRACTION_PROMPT = """You are an expert at extracting employee performance data from restaurant POS (Point of Sale) reports, specifically Aloha POS reports.

Analyze the uploaded image and extract ALL employee performance metrics you can find. Look for:

1. **Employee Names** - Server/bartender names
2. **PPA** (Per Person Average) - Dollar amount per guest
3. **LBW** (Liquor, Beer, Wine) per guest - Dollar amount
4. **Glassware per guest** - Dollar amount (wine glass sales)
5. **Guest Count** - Total number of guests served
6. **Net Sales** - Total sales amount
7. **LSC** (Labor Sales Check) or Guests per LSC
8. **Tips** - If available
9. **Hours Worked** - If available

IMPORTANT INSTRUCTIONS:
- Extract data for EVERY employee visible in the report
- Use the exact names as shown (first name or full name)
- If a value is not visible or unclear, use null
- Numbers should be extracted as floats without $ signs
- Be thorough - scan the entire image for all data tables

Return the data as a JSON object with this exact structure:
{
  "report_date": "YYYY-MM-DD or null if not visible",
  "report_type": "daily/weekly/bi-weekly/unknown",
  "employees": [
    {
      "name": "Employee Name",
      "ppa": 45.50,
      "lbw_per_guest": 8.25,
      "glassware_per_guest": 1.50,
      "guest_count": 120,
      "net_sales": 5460.00,
      "guests_per_lsc": 85,
      "tips": 650.00,
      "hours": 32.5
    }
  ],
  "extraction_notes": "Any notes about data quality or missing information"
}

If you cannot extract any meaningful data, return:
{
  "error": "Description of why extraction failed",
  "employees": []
}

Return ONLY valid JSON, no markdown formatting or explanation."""


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
        
        # Create image content
        image_content = ImageContent(image_base64=image_base64)
        
        # Send message with image
        user_message = UserMessage(
            text="Please extract all employee performance data from this POS report image. Return the data as JSON.",
            image_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
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
            
        validated_emp = {
            "name": str(emp.get("name", "")).strip(),
            "ppa": _safe_float(emp.get("ppa")),
            "lbw_per_guest": _safe_float(emp.get("lbw_per_guest")),
            "glassware_per_guest": _safe_float(emp.get("glassware_per_guest")),
            "guest_count": _safe_int(emp.get("guest_count")),
            "net_sales": _safe_float(emp.get("net_sales")),
            "guests_per_lsc": _safe_float(emp.get("guests_per_lsc")),
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
