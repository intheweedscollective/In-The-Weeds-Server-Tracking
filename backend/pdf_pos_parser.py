"""
PDF POS Report Parser for Bubba Gump Server Sales Reports

This parser handles scanned PDF reports in the format:
- Multiple pages, one per employee
- Each page contains:
  - Employee name
  - Sales by Category table (Food, Liquor, Beer, Wine, etc.)
  - Guest counts (Num Guests section)

Uses pdfplumber for text extraction with fallback to PyMuPDF for complex scans.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_number(val: str) -> float:
    """
    Clean a number value from OCR'd text.
    Handles common OCR errors:
    - Spaces in numbers: "5 018.84" -> 5018.84
    - Multiple decimals: "3.911.00" -> 3911.00
    - Commas vs periods: "1,234.56" -> 1234.56
    """
    if not val or val.strip() == '':
        return 0.0
    
    val_str = str(val).strip()
    
    # Remove all spaces
    val_str = val_str.replace(' ', '')
    
    # Handle multiple decimal points (OCR error): "3.911.00" -> "3911.00"
    period_count = val_str.count('.')
    if period_count > 1:
        parts = val_str.split('.')
        # Keep only the last decimal part
        val_str = ''.join(parts[:-1]) + '.' + parts[-1]
    
    # Remove commas
    val_str = val_str.replace(',', '')
    
    # Remove any non-numeric characters except decimal point
    val_str = re.sub(r'[^\d.]', '', val_str)
    
    try:
        result = float(val_str) if val_str else 0.0
        return result
    except (ValueError, TypeError):
        return 0.0


def extract_employee_name(text: str) -> Optional[str]:
    """
    Extract employee name from a page of the POS report.
    The name typically appears on line 5-6 after 'Printedby: BGLVEDC'.
    Format: Employee names are the only lines that are JUST proper names.
    """
    lines = text.split('\n')
    
    # Known non-name keywords - must match as whole words or be significant parts
    skip_keywords = {
        'server', 'sales', 'bubba', 'gump', 'bglv', 'vegas', '337', '3717',
        'printed', 'page', 'grs', 'net', 'tax', 'category', 'food', 'liquor', 
        'beer', 'wine', 'retail', 'loyalty', 'glassware', 'guests', 'shift', 
        'tip', 'reduction', 'report', 'avg', 'check', 'blvd', 'paradise', 
        'totals', 'lessvoidscomps', 'netsls', 'grssls', 'addchgs', 'ordercharges'
    }
    
    # Look for employee name - typically lines 4-8
    for line in lines[3:10]:
        line = line.strip()
        
        # Skip empty or short lines
        if len(line) < 4 or len(line) > 50:
            continue
        
        # Skip lines that are mostly numbers
        alpha_chars = sum(1 for c in line if c.isalpha())
        if alpha_chars < len(line) * 0.6:
            continue
        
        line_lower = line.lower()
        
        # Tokenize the line into words
        words = re.split(r'[\s\-]+', line_lower)
        words = [w for w in words if len(w) > 1]
        
        # Skip if any word matches a keyword exactly
        if any(word in skip_keywords for word in words):
            continue
        
        # Skip lines with specific patterns
        if any(x in line_lower for x in ['01/01', '03/20', '2026', '89109', 'printedby']):
            continue
        
        # Must have at least one uppercase letter (proper name)
        if not any(c.isupper() for c in line):
            continue
        
        # Should look like a name (letters, spaces, hyphens, apostrophes)
        valid_chars = sum(1 for c in line if c.isalpha() or c in " -'")
        if valid_chars < len(line) * 0.85:
            continue
        
        # Looks like a name - clean it up
        # Fix OCR space issues (e.g., "Jose PlancarteVilla" -> "Jose Plancarte Villa")
        # Add space before capital letters in the middle of a word
        cleaned_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', line)
        
        logger.info(f"Found employee name: {cleaned_name}")
        return cleaned_name
    
    return None


def extract_sales_data(text: str) -> Dict[str, float]:
    """
    Extract sales data from the SALES BY CATEGORY section.
    The format is: CategoryName NetSls Taxes Vd/Sur/Ord GrsSls CheckAvg GuestAvg
    We want the first number (NetSls).
    
    Handles OCR errors like:
    - Missing decimal points: "51,373183" should be "51,373.83"
    - Small numbers: "696.50"
    
    Returns dict with food, liquor, beer, wine, glassware, loyalty values.
    """
    data = {
        'food': 0.0,
        'liquor': 0.0,
        'beer': 0.0,
        'wine': 0.0,
        'glassware': 0.0,
        'loyalty': 0.0
    }
    
    lines = text.split('\n')
    
    # Category names to look for (case-insensitive)
    categories = {
        'food': 'food',
        'liquor': 'liquor',
        'beer': 'beer',
        'wine': 'wine',
        'barglassware': 'glassware',
        'bar glassware': 'glassware',
        'loyalty': 'loyalty',
        'loyany': 'loyalty',   # OCR error
        'loyaity': 'loyalty',  # OCR error
        'loyahy': 'loyalty',   # OCR error - 'lt' read as 'h'
        'loyaiy': 'loyalty',   # OCR error
        'loyalhy': 'loyalty',  # OCR error
        'ioyalty': 'loyalty',  # OCR error - 'L' read as 'I'
        'loyaltv': 'loyalty',  # OCR error - 'y' read as 'v'
    }
    
    for line in lines:
        line_lower = line.lower().strip()
        
        for search_term, data_key in categories.items():
            if line_lower.startswith(search_term):
                # Remove the category name from the line
                rest_of_line = line[len(search_term):].strip()
                
                # Case 1: Standard format with decimal - "5,018.84" or "696.50"
                match = re.search(r'^[\s]*([\d,]+\.\d{2})\b', rest_of_line)
                if match:
                    data[data_key] = clean_number(match.group(1))
                    logger.debug(f"Found {data_key}: {data[data_key]} (standard format)")
                    break
                
                # Case 2: OCR merged numbers - "51,373183" should be "51,373.83"
                # Pattern: XX,XXX followed by extra digits where LAST 2 are cents
                # The extra digits before the last 2 are garbage from next column
                
                # First try 2,3 pattern (values 10,000-99,999)
                match = re.search(r'^[\s]*(\d{2},\d{3})(\d+)', rest_of_line)
                if match:
                    base = match.group(1).replace(',', '')  # e.g., "51373"
                    extra = match.group(2)  # e.g., "183"
                    
                    if len(extra) >= 2:
                        cents = extra[-2:]  # LAST 2 digits are cents
                        value = float(f"{base}.{cents}")
                        if 10000 < value < 200000:
                            data[data_key] = value
                            logger.debug(f"Found {data_key}: {data[data_key]} (OCR fix 2,3)")
                            break
                
                # Try 1,3 pattern (values 1,000-9,999)
                match = re.search(r'^[\s]*(\d{1},\d{3})(\d+)', rest_of_line)
                if match:
                    base = match.group(1).replace(',', '')
                    extra = match.group(2)
                    if len(extra) >= 2:
                        cents = extra[-2:]
                        value = float(f"{base}.{cents}")
                        if 1000 < value < 10000:
                            data[data_key] = value
                            logger.debug(f"Found {data_key}: {data[data_key]} (OCR fix 1,3)")
                            break
                
                # Try 3,3 pattern (values 100,000-999,999)
                match = re.search(r'^[\s]*(\d{3},\d{3})(\d+)', rest_of_line)
                if match:
                    base = match.group(1).replace(',', '')
                    extra = match.group(2)
                    if len(extra) >= 2:
                        cents = extra[-2:]
                        value = float(f"{base}.{cents}")
                        if 100000 < value < 1000000:
                            data[data_key] = value
                            logger.debug(f"Found {data_key}: {data[data_key]} (OCR fix 3,3)")
                            break
                
                # Case 3: Simple number without comma (small values) - might be "0.00" or "175.00"
                match = re.search(r'^[\s]*(\d+\.\d{2})\b', rest_of_line)
                if match:
                    data[data_key] = clean_number(match.group(1))
                    logger.debug(f"Found {data_key}: {data[data_key]} (simple decimal)")
                    break
                
                # Case 4: Just digits with potential OCR issues
                match = re.search(r'^[\s]*(\d+)', rest_of_line)
                if match:
                    num_str = match.group(1)
                    if len(num_str) >= 4:
                        # Insert decimal 2 from end
                        value = float(num_str[:-2] + '.' + num_str[-2:])
                        data[data_key] = value
                        logger.debug(f"Found {data_key}: {data[data_key]} (inferred decimal)")
                    else:
                        data[data_key] = float(num_str)
                    break
                
                break
    
    return data


def extract_guest_count(text: str) -> int:
    """
    Extract total guest count from the Num Guests section.
    Looks for 'Total Guests' followed by a number.
    Handles OCR errors where 'O' is mistaken for '0' and 'l' for '1'.
    """
    lines = text.split('\n')
    
    for line in lines:
        if 'total' in line.lower() and 'guest' in line.lower():
            # Found the Total Guests line
            # Extract everything after "Total Guests"
            match = re.search(r'Total\s*Guests\s*(.+)', line, re.IGNORECASE)
            if match:
                num_part = match.group(1).strip()
                # Clean up OCR errors: O->0, l->1, I->1
                num_part = num_part.replace('O', '0').replace('o', '0')
                num_part = num_part.replace('l', '1').replace('I', '1')
                # Remove any non-digit characters
                num_part = re.sub(r'[^\d]', '', num_part)
                
                if num_part:
                    try:
                        count = int(num_part)
                        logger.debug(f"Found Total Guests: {count} from line: {line}")
                        return count
                    except ValueError:
                        pass
    
    return 0


def parse_pdf_page(page_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single page of the POS report.
    Returns employee data dict or None if invalid.
    """
    # Extract employee name
    name = extract_employee_name(page_text)
    if not name:
        logger.warning("Could not find employee name on page")
        return None
    
    # Extract sales data
    sales = extract_sales_data(page_text)
    
    # Extract guest count
    guests = extract_guest_count(page_text)
    
    # Calculate derived values
    lbw = sales['liquor'] + sales['beer'] + sales['wine']
    net_sales = sales['food'] + lbw
    
    employee = {
        'name': name,
        'food': sales['food'],
        'liquor': sales['liquor'],
        'beer': sales['beer'],
        'wine': sales['wine'],
        'lbw': lbw,
        'net_sales': net_sales,
        'glassware': sales['glassware'],
        'loyalty_sales': sales['loyalty'],
        'guests': guests
    }
    
    logger.info(f"Parsed: {name} - Net Sales: ${net_sales:,.2f}, LBW: ${lbw:,.2f}, Guests: {guests}")
    return employee


def parse_pos_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a complete POS report PDF file.
    Uses pdfplumber as primary, PyMuPDF as fallback.
    
    Returns list of employee dictionaries with their sales data.
    """
    logger.info(f"Parsing PDF: {file_path}")
    employees = []
    seen_names = set()
    
    # Try pdfplumber first
    try:
        import pdfplumber
        
        with pdfplumber.open(file_path) as pdf:
            logger.info(f"PDF has {len(pdf.pages)} pages")
            
            for page_num, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if not text:
                        continue
                    
                    employee = parse_pdf_page(text)
                    if employee and employee['name'] not in seen_names:
                        seen_names.add(employee['name'])
                        employees.append(employee)
                        
                except Exception as e:
                    logger.warning(f"Error parsing page {page_num}: {e}")
                    continue
        
        if employees:
            logger.info(f"Parsed {len(employees)} employees using pdfplumber")
            return employees
            
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}, trying PyMuPDF")
    
    # Fallback to PyMuPDF
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(file_path)
        logger.info(f"PDF has {len(doc)} pages (PyMuPDF)")
        
        for page_num in range(len(doc)):
            try:
                page = doc[page_num]
                text = page.get_text()
                if not text:
                    continue
                
                employee = parse_pdf_page(text)
                if employee and employee['name'] not in seen_names:
                    seen_names.add(employee['name'])
                    employees.append(employee)
                    
            except Exception as e:
                logger.warning(f"Error parsing page {page_num}: {e}")
                continue
        
        doc.close()
        
    except Exception as e:
        logger.error(f"Both PDF parsers failed: {e}")
    
    logger.info(f"Parsed {len(employees)} employees total")
    return employees


def is_pos_pdf_format(file_path: str) -> bool:
    """
    Check if the PDF file is in POS report format.
    """
    try:
        import pdfplumber
        
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) == 0:
                return False
            
            # Check first page for POS markers
            text = pdf.pages[0].extract_text()
            if not text:
                return False
            
            text_lower = text.lower()
            markers = ['server sales', 'sales by category', 'total guests', 'bubba gump', 'bglv']
            found = sum(1 for m in markers if m in text_lower)
            
            return found >= 2
            
    except Exception as e:
        logger.error(f"Error checking PDF format: {e}")
        return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if is_pos_pdf_format(file_path):
            print("File is a POS report PDF")
            employees = parse_pos_pdf(file_path)
            print(f"\nExtracted {len(employees)} employees:")
            for i, emp in enumerate(employees, 1):
                print(f"{i}. {emp['name']}: Net=${emp['net_sales']:,.2f}, LBW=${emp['lbw']:,.2f}, Guests={emp['guests']}")
        else:
            print("File is NOT a POS report PDF")
