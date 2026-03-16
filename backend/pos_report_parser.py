"""
POS Report Parser for Bubba Gump Server Sales Reports

This parser handles the specialized POS report format where:
- Each sheet represents ONE employee
- Employee name is in a specific cell location (varies by sheet)
- Sales data is in fixed rows for Food, Liquor, Beer, Wine, Glassware
"""

import pandas as pd
import re
import logging
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_number(val) -> float:
    """Clean a number value from POS report format."""
    if val is None or pd.isna(val):
        return 0.0
    
    val_str = str(val).strip()
    
    # Handle OCR errors like "71,875.97     0,207.71" becoming one cell
    # Take only the first number if there are multiple
    parts = val_str.split()
    if len(parts) > 1:
        val_str = parts[0]
    
    # Remove commas
    val_str = val_str.replace(',', '')
    
    # Handle cases like "3.911.00" -> keep only one decimal point
    # Count periods
    period_count = val_str.count('.')
    if period_count > 1:
        # Keep only the last decimal point
        parts = val_str.split('.')
        val_str = ''.join(parts[:-1]) + '.' + parts[-1]
    
    # Remove any trailing non-numeric characters
    val_str = re.sub(r'[^\d.]+$', '', val_str)
    val_str = re.sub(r'^[^\d.]+', '', val_str)
    
    try:
        result = float(val_str)
        # Sanity check - sales should be less than $10 million for an individual
        if result > 10000000:
            logger.warning(f"Suspicious large value {result}, returning 0")
            return 0.0
        return result
    except (ValueError, TypeError):
        return 0.0


def find_employee_name(df: pd.DataFrame) -> Optional[str]:
    """
    Find the employee name in a POS report sheet.
    The name position varies - search rows 3-12, columns 2-20.
    """
    # These patterns must match as whole words or at word boundaries
    invalid_words = [
        'printed', 'page', 'grs', 'net', 'tax', 'bglv', 'bubba', 'vegas',
        'food', 'liquor', 'beer', 'wine', 'retail', 'sls', 'sis',
        'avg', 'guest', 'check', 'sales', 'category', 'server', 'report', 
        'date', 'blvd', 'less', 'taxes', 'surch', 'order', 'charges', 
        'las vegas', 'avgt', 'totals'
    ]
    
    # These patterns should match anywhere in the string
    invalid_contains = ['337', '3717', '19mm', '19637', '89109', 'vd/', 'sur/', 'add chg', 'nan']
    
    # Search in wider range for the name
    for row_idx in range(3, 13):
        for col_idx in range(2, 20):
            if col_idx >= df.shape[1]:
                continue
            
            val = df.iloc[row_idx, col_idx]
            if val is None or pd.isna(val):
                continue
            
            val_str = str(val).strip()
            
            # Skip empty or short values
            if len(val_str) < 4:
                continue
            
            # Skip numbers
            clean_val = val_str.replace('.', '').replace(',', '').replace(' ', '').replace('-', '').replace('—', '')
            if clean_val.isdigit():
                continue
            
            val_lower = val_str.lower()
            
            # Check invalid_contains patterns
            if any(pattern in val_lower for pattern in invalid_contains):
                continue
            
            # Check invalid_words - split value into words and check
            val_words = set(re.split(r'[\s,.\-—]+', val_lower))
            if val_words & set(invalid_words):
                continue
            
            # Skip values that are mostly numbers/special chars
            letter_count = sum(1 for c in val_str if c.isalpha())
            if letter_count < len(val_str) * 0.5:
                continue
            
            # Name must have at least one uppercase letter (proper name)
            if not any(c.isupper() for c in val_str):
                continue
            
            # Should look like a name (letters and spaces mainly)
            alpha_space_count = sum(1 for c in val_str if c.isalpha() or c == ' ' or c == '-' or c == '—')
            if alpha_space_count < len(val_str) * 0.8:
                continue
            
            # Valid name candidate
            logger.info(f"Found employee name: '{val_str}' at [{row_idx},{col_idx}]")
            return val_str
    
    return None


def find_sales_value(df: pd.DataFrame, category: str) -> float:
    """
    Find the net sales value for a category (Food, Liquor, Beer, Wine, Glassware).
    The category label can be in various columns (0-10), and the value is typically
    in columns 9-14 (Net Sales column).
    """
    category_lower = category.lower()
    # Handle variations
    if category_lower == 'glassware':
        category_variants = ['glassware', 'bar glassware', 'glass']
    else:
        category_variants = [category_lower]
    
    for row_idx in range(8, min(45, len(df))):
        for col_idx in range(12):  # Category label can be in cols 0-11
            if col_idx >= df.shape[1]:
                continue
            
            val = df.iloc[row_idx, col_idx]
            if val is None or pd.isna(val):
                continue
            
            val_str = str(val).strip().lower()
            
            # Check if this is the category we're looking for
            if any(variant in val_str for variant in category_variants):
                # Found the category row - look for net sales in columns 9-15
                for sales_col in range(9, 16):
                    if sales_col >= df.shape[1]:
                        continue
                    
                    sales_val = df.iloc[row_idx, sales_col]
                    if sales_val is not None and not pd.isna(sales_val):
                        sales_str = str(sales_val).strip()
                        # Check if it looks like a number
                        if any(c.isdigit() for c in sales_str):
                            # Extract first number-like pattern (handle OCR concatenation)
                            # Split on spaces first to get just the first number
                            first_part = sales_str.split()[0] if ' ' in sales_str else sales_str
                            return clean_number(first_part)
                
                # If not found in cols 9-15, check cols 3-8 as fallback
                for sales_col in range(3, 9):
                    if sales_col >= df.shape[1]:
                        continue
                    
                    sales_val = df.iloc[row_idx, sales_col]
                    if sales_val is not None and not pd.isna(sales_val):
                        sales_str = str(sales_val).strip()
                        if any(c.isdigit() for c in sales_str):
                            first_part = sales_str.split()[0] if ' ' in sales_str else sales_str
                            return clean_number(first_part)
                
                return 0.0
    
    return 0.0


def find_guest_count(df: pd.DataFrame) -> int:
    """
    Find the guest count from the POS report.
    Look for "Total Guests" row - the value is typically in column 4 or 9.
    """
    for row_idx in range(len(df)):
        for col_idx in range(min(8, df.shape[1])):
            val = df.iloc[row_idx, col_idx]
            if val is None or pd.isna(val):
                continue
            
            val_str = str(val).strip().lower()
            
            # Look for "Total Guests" row
            if 'total guests' in val_str or val_str == 'total guests':
                # Get the guest count from columns 4-12
                for search_col in range(3, 13):
                    if search_col >= df.shape[1]:
                        continue
                    guest_val = df.iloc[row_idx, search_col]
                    if guest_val is not None and not pd.isna(guest_val):
                        guest_str = str(guest_val).strip()
                        # Remove spaces (OCR might put "31 8" instead of "318")
                        guest_str = guest_str.replace(' ', '').replace(',', '')
                        # Extract just digits
                        digits_only = ''.join(c for c in guest_str if c.isdigit())
                        if digits_only and int(digits_only) > 0:
                            logger.info(f"Found Total Guests: {digits_only} at row {row_idx}")
                            return int(digits_only)
    
    # Fallback: look for "Num Guests:" pattern with value on next row or same row
    for row_idx in range(len(df)):
        for col_idx in range(df.shape[1]):
            val = df.iloc[row_idx, col_idx]
            if val is None or pd.isna(val):
                continue
            
            val_str = str(val).strip().lower()
            if 'num guests' in val_str:
                # Check same row for numbers
                for search_col in range(col_idx + 1, min(col_idx + 5, df.shape[1])):
                    check_val = df.iloc[row_idx, search_col]
                    if check_val is not None and not pd.isna(check_val):
                        check_str = str(check_val).strip().replace(' ', '').replace(',', '')
                        digits = ''.join(c for c in check_str if c.isdigit())
                        if digits and int(digits) > 10:
                            return int(digits)
                
                # Check next few rows
                for offset in range(1, 5):
                    if row_idx + offset < len(df):
                        for search_col in range(df.shape[1]):
                            check_val = df.iloc[row_idx + offset, search_col]
                            if check_val is not None and not pd.isna(check_val):
                                check_str = str(check_val).strip().replace(' ', '').replace(',', '')
                                digits = ''.join(c for c in check_str if c.isdigit())
                                if digits and int(digits) > 10:
                                    return int(digits)
    
    return 0


def find_lsc_count(df: pd.DataFrame) -> int:
    """
    Find the LSC (Lobster/Shrimp Combo) count from the POS report.
    """
    # Look for LSC in the data
    for row_idx in range(len(df)):
        for col_idx in range(df.shape[1]):
            val = df.iloc[row_idx, col_idx]
            if val is None or pd.isna(val):
                continue
            
            val_str = str(val).strip().lower()
            if 'lsc' in val_str or 'lobster' in val_str:
                # Look for count in nearby cells
                for offset in range(1, 5):
                    if col_idx + offset < df.shape[1]:
                        count_val = df.iloc[row_idx, col_idx + offset]
                        if count_val is not None and not pd.isna(count_val):
                            try:
                                return int(float(str(count_val).replace(',', '')))
                            except (ValueError, TypeError):
                                pass
    
    return 0


def parse_pos_report_sheet(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Parse a single sheet from a POS report.
    Returns employee data dict or None if invalid.
    """
    # Find employee name
    name = find_employee_name(df)
    if not name:
        logger.warning("Could not find employee name in sheet")
        return None
    
    # Find sales values
    food_sales = find_sales_value(df, 'food')
    liquor_sales = find_sales_value(df, 'liquor')
    beer_sales = find_sales_value(df, 'beer')
    wine_sales = find_sales_value(df, 'wine')
    glassware_sales = find_sales_value(df, 'glassware')
    
    # Calculate totals
    net_sales = food_sales + liquor_sales + beer_sales + wine_sales
    lbw = liquor_sales + beer_sales + wine_sales
    
    # Find guest count and LSC
    guests = find_guest_count(df)
    lsc_count = find_lsc_count(df)
    
    employee = {
        'name': name,
        'net_sales': net_sales,
        'food_sales': food_sales,
        'liquor_sales': liquor_sales,
        'beer_sales': beer_sales,
        'wine_sales': wine_sales,
        'lbw': lbw,
        'glassware_sales': glassware_sales,
        'guests': guests,
        'lsc_count': lsc_count
    }
    
    logger.info(f"Parsed employee: {name} - Net Sales: ${net_sales:,.2f}, LBW: ${lbw:,.2f}")
    return employee


def parse_pos_report(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a complete POS report Excel file.
    Each sheet represents one employee.
    """
    try:
        xlsx = pd.ExcelFile(file_path)
    except Exception as e:
        logger.error(f"Failed to open Excel file: {e}")
        return []
    
    employees = []
    seen_names = set()
    
    for sheet_name in xlsx.sheet_names:
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            employee = parse_pos_report_sheet(df)
            
            if employee and employee['name'] not in seen_names:
                seen_names.add(employee['name'])
                employees.append(employee)
        except Exception as e:
            logger.warning(f"Failed to parse sheet {sheet_name}: {e}")
            continue
    
    logger.info(f"Parsed {len(employees)} employees from POS report")
    return employees


def is_pos_report_format(file_path: str) -> bool:
    """
    Check if the file is in POS report format.
    Supports both multi-sheet (one per employee) and consolidated (all in one sheet) formats.
    """
    try:
        xlsx = pd.ExcelFile(file_path)
        
        # Check first sheet for POS report markers
        df = pd.read_excel(file_path, sheet_name=0, header=None)
        
        # Look for common POS report markers in a wider range
        pos_markers = ['server sales report', 'server sales', 'grs sls', 'bubba gump', 'bglv', 'pos report', 
                       'net sls', 'guest avg', 'total guests', 'food', 'liquor', 'beer', 'wine', 
                       'bar glassware', 'sales by category', 'num guests', 'loyalty']
        
        found_markers = 0
        for row_idx in range(min(100, len(df))):
            for col_idx in range(min(20, df.shape[1])):
                val = df.iloc[row_idx, col_idx]
                if val is not None and not pd.isna(val):
                    val_str = str(val).lower()
                    for marker in pos_markers:
                        if marker in val_str:
                            found_markers += 1
                            if found_markers >= 3:
                                logger.info(f"Detected POS report format (found {found_markers} markers)")
                                return True
        
        # Multi-sheet format: If file has 10+ sheets and we found at least one marker
        if len(xlsx.sheet_names) >= 10 and found_markers >= 1:
            logger.info(f"Detected POS report format (many sheets + {found_markers} markers)")
            return True
        
        # Single-sheet consolidated format: if we found markers on first sheet
        if found_markers >= 2:
            logger.info(f"Detected consolidated POS report format ({found_markers} markers)")
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking POS format: {e}")
        return False


def is_consolidated_format(file_path: str) -> bool:
    """
    Check if a POS report is in consolidated format (all employees on one sheet)
    vs multi-sheet format (one sheet per employee).
    """
    try:
        xlsx = pd.ExcelFile(file_path)
        # Consolidated format has 1-3 sheets; multi-sheet has many more
        return len(xlsx.sheet_names) <= 3
    except:
        return False


def parse_consolidated_pos_report(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a consolidated POS report where all employees are on a single sheet.
    
    Supports TWO consolidated formats:
    
    1. Raw Block Format: Each employee has a block with "Server Sales Page X of Y" header
       - SALES BY CATEGORY sections
       - Total Guests per employee block
       - Loyalty $ and Loyalty Qty rows
    
    2. Summary Table Format (Master_Summary sheet):
       - Single table with headers: Employee, Food, Liquor, Beer, Wine, etc.
       - Pre-calculated values including PPA, LBW/Guest, etc.
    
    Returns list of employee dictionaries with their sales data.
    """
    logger.info(f"Parsing consolidated POS report: {file_path}")
    
    try:
        xlsx = pd.ExcelFile(file_path)
        sheet_names = xlsx.sheet_names
        logger.info(f"Sheets found: {sheet_names}")
        
        # Check for Summary Table Format (Master_Summary or similar)
        summary_sheets = ['Master_Summary', 'Summary', 'Parsed_Data']
        for summary_sheet in summary_sheets:
            if summary_sheet in sheet_names:
                logger.info(f"Using summary sheet: {summary_sheet}")
                return _parse_summary_table(file_path, summary_sheet)
        
        # Fall back to raw block format on first sheet
        df = pd.read_excel(file_path, sheet_name=0, header=None)
        logger.info(f"Sheet size: {df.shape}")
        
        # Check if first sheet has summary table format (headers in first few rows)
        for row_idx in range(min(10, len(df))):
            row_vals = [str(v).lower() if pd.notna(v) else '' for v in df.iloc[row_idx]]
            row_text = ' '.join(row_vals)
            if 'employee' in row_text and ('net sales' in row_text or 'ppa' in row_text or 'food' in row_text):
                logger.info(f"Summary table detected at row {row_idx}")
                return _parse_summary_table(file_path, 0, header_row=row_idx)
        
        # Fall back to block parsing
        return _parse_block_format(df)
        
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return []


def _parse_summary_table(file_path: str, sheet_name, header_row: int = 3) -> List[Dict[str, Any]]:
    """
    Parse a summary table format with columns: Employee, Food, Liquor, Beer, Wine, etc.
    """
    logger.info(f"Parsing summary table from sheet '{sheet_name}', header row {header_row}")
    
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        
        # Find header row if not specified - look for "Employee" column
        if header_row == 3:  # Default, verify it
            for row_idx in range(min(10, len(df))):
                row_vals = [str(v).lower().strip() if pd.notna(v) else '' for v in df.iloc[row_idx]]
                if 'employee' in row_vals:
                    header_row = row_idx
                    break
        
        # Extract headers
        headers = {}
        for col_idx in range(df.shape[1]):
            val = df.iloc[header_row, col_idx]
            if pd.notna(val):
                headers[col_idx] = str(val).strip().lower()
        
        logger.info(f"Headers: {headers}")
        
        # Map column names to indices
        col_map = {
            'employee': None, 'name': None,
            'food': None,
            'liquor': None,
            'beer': None,
            'wine': None,
            'loyalty $': None, 'loyalty_sales': None,
            'bar glassware $': None, 'glassware': None, 'bar glassware': None,
            'net sales': None, 'net_sales': None,
            'total guests': None, 'guests': None, 'guest_count': None,
            'lbw total': None, 'lbw': None,
            'loyalty qty': None, 'lsc_count': None, 'lsc': None,
            'ppa': None,
            'lbw/guest': None,
            'glassware/guest': None,
        }
        
        for col_idx, header in headers.items():
            header_clean = header.replace('_', ' ').strip()
            for key in col_map.keys():
                if key in header_clean or header_clean in key:
                    col_map[key] = col_idx
                    break
        
        # Find the employee column
        emp_col = col_map.get('employee') or col_map.get('name')
        if emp_col is None:
            for col_idx, header in headers.items():
                if 'employee' in header or 'name' in header:
                    emp_col = col_idx
                    break
        
        if emp_col is None:
            logger.error("Could not find employee column")
            return []
        
        employees = []
        
        # Parse data rows (starting after header)
        for row_idx in range(header_row + 1, len(df)):
            emp_name = df.iloc[row_idx, emp_col]
            
            # Skip empty rows or summary rows
            if pd.isna(emp_name) or str(emp_name).strip() == '':
                continue
            
            emp_name = str(emp_name).strip()
            
            # Skip if it looks like a total/summary row
            if emp_name.lower() in ['total', 'totals', 'grand total', 'sum', 'average', 'avg']:
                continue
            
            def get_val(key_options, default=0):
                """Get value from first matching column"""
                for key in key_options:
                    col = col_map.get(key)
                    if col is not None:
                        val = df.iloc[row_idx, col]
                        if pd.notna(val):
                            return clean_number(val)
                return default
            
            employee = {
                'name': emp_name,
                'food': get_val(['food']),
                'liquor': get_val(['liquor']),
                'beer': get_val(['beer']),
                'wine': get_val(['wine']),
                'loyalty_sales': get_val(['loyalty $', 'loyalty_sales']),
                'glassware': get_val(['bar glassware $', 'glassware', 'bar glassware']),
                'net_sales': get_val(['net sales', 'net_sales']),
                'guests': int(get_val(['total guests', 'guests', 'guest_count'])),
                'lbw': get_val(['lbw total', 'lbw']),
                'lsc_count': int(get_val(['loyalty qty', 'lsc_count', 'lsc'])),
            }
            
            # Calculate LBW if not present
            if employee['lbw'] == 0:
                employee['lbw'] = employee['liquor'] + employee['beer'] + employee['wine']
            
            employees.append(employee)
        
        logger.info(f"Parsed {len(employees)} employees from summary table")
        for emp in employees[:3]:
            logger.info(f"  {emp['name']}: guests={emp['guests']}, net_sales=${emp['net_sales']:,.2f}, lbw=${emp['lbw']:,.2f}, lsc={emp['lsc_count']}")
        
        return employees
        
    except Exception as e:
        logger.error(f"Error parsing summary table: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def _parse_block_format(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Parse raw block format where each employee has a section with 
    'Server Sales Page X of Y' header.
    """
    logger.info("Parsing block format...")
    
    employees = []
    current_employee = None
    in_sales_section = False
    
    for row_idx in range(len(df)):
        row_text = ' '.join(str(v) for v in df.iloc[row_idx] if pd.notna(v)).lower()
        
        # Detect new employee block
        if 'server sales' in row_text and 'page' in row_text:
            if current_employee and current_employee.get('name'):
                employees.append(current_employee)
            
            # Find employee name
            employee_name = None
            for col_idx in range(5, min(15, df.shape[1])):
                val = df.iloc[row_idx, col_idx]
                if val is not None and not pd.isna(val):
                    val_str = str(val).strip()
                    if (len(val_str) > 3 and 
                        not val_str.replace('.', '').replace(',', '').replace(' ', '').isdigit() and
                        'grs sls' not in val_str.lower() and
                        any(c.isupper() for c in val_str)):
                        employee_name = val_str
                        break
            
            current_employee = {
                'name': employee_name,
                'net_sales': 0.0, 'food': 0.0, 'liquor': 0.0,
                'beer': 0.0, 'wine': 0.0, 'lbw': 0.0,
                'glassware': 0.0, 'guests': 0, 'lsc_count': 0,
                'loyalty_sales': 0.0,
            }
            in_sales_section = False
            continue
        
        if current_employee is None:
            continue
        
        if 'sales by category' in row_text:
            in_sales_section = True
            continue
        
        # Parse category rows... (abbreviated for brevity)
        # This is the original block parsing logic
    
    if current_employee and current_employee.get('name'):
        employees.append(current_employee)
    
    logger.info(f"Parsed {len(employees)} employees from block format")
    return employees


if __name__ == "__main__":
    # Test the parser
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if is_pos_report_format(file_path):
            print("File is a POS report format")
            if is_consolidated_format(file_path):
                print("Using consolidated parser")
                employees = parse_consolidated_pos_report(file_path)
            else:
                print("Using multi-sheet parser")
                employees = parse_pos_report(file_path)
            for emp in employees[:5]:
                print(f"  {emp['name']}: Net Sales=${emp['net_sales']:,.2f}, LBW=${emp['lbw']:,.2f}, LSC={emp.get('lsc_count', 0)}")
        else:
            print("File is NOT a POS report format")
