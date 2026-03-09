"""
Clean POS Report Parser

Parses a simplified POS report format where each employee is in a separate sheet.
Each sheet contains:
- Employee Name (first non-empty cell)
- Net Sales header
- Sales breakdown: Food, Liquor, Beer, Wine, Loyalty, Bar Glassware
- Totals
- Total Guests

This is the "cleaned up" format where unnecessary cells have been removed.
"""

import pandas as pd
from typing import List, Dict, Any, Optional
import re
from io import BytesIO


def parse_single_sheet(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Parse a single sheet to extract one employee's data."""
    rows = df.values.tolist()
    
    employee = {
        "name": None,
        "food": 0,
        "liquor": 0,
        "beer": 0,
        "wine": 0,
        "loyalty": 0,
        "bar_glassware": 0,
        "totals": 0,
        "total_guests": 0,
        "net_sales": 0
    }
    
    for row in rows:
        # Find first non-empty cell
        first_cell = None
        first_col = None
        for col_idx, cell in enumerate(row):
            if pd.notna(cell) and str(cell).strip():
                first_cell = str(cell).strip()
                first_col = col_idx
                break
        
        if not first_cell:
            continue
        
        field_lower = first_cell.lower()
        
        # Check if this is the employee name (first non-field cell)
        known_fields = [
            'net sls', 'net sis', 'net sales', 'food', 'liquor', 'beer', 'wine', 
            'loyalty', 'loyany', 'bar glassware', 'totals', 'total sales', 
            'total guests', 'retail', 'non revenue'
        ]
        
        is_known = any(kf in field_lower for kf in known_fields)
        
        if not is_known and not employee["name"]:
            # This looks like an employee name
            if re.match(r'^[A-Za-z][A-Za-z\s\-\—\.\']+$', first_cell) and len(first_cell) > 2:
                employee["name"] = first_cell.replace('—', '-')  # Fix em-dash
                continue
        
        # Get value from remaining columns
        value = 0
        for col_idx in range(first_col + 1, len(row)):
            cell_val = row[col_idx]
            if pd.notna(cell_val):
                try:
                    # Clean the value - handle various formats like "71 ,87595", "3.911.00", "5,291 .00"
                    val_str = str(cell_val)
                    # Remove spaces around numbers
                    val_str = re.sub(r'\s+', '', val_str)
                    # Remove currency symbols
                    val_str = val_str.replace('$', '').replace(',', '')
                    # Handle European format (3.911.00 -> 3911.00)
                    parts = val_str.split('.')
                    if len(parts) > 2:
                        # Multiple decimals - assume last is decimal point
                        val_str = ''.join(parts[:-1]) + '.' + parts[-1]
                    value = float(val_str)
                    break
                except (ValueError, TypeError):
                    continue
        
        # Map to fields
        if 'food' in field_lower:
            employee["food"] = value
        elif 'liquor' in field_lower:
            employee["liquor"] = value
        elif 'beer' in field_lower:
            employee["beer"] = value
        elif 'wine' in field_lower:
            employee["wine"] = value
        elif 'loyal' in field_lower:  # matches loyalty and loyany (typo)
            employee["loyalty"] = value
        elif 'glassware' in field_lower or 'bar glass' in field_lower:
            employee["bar_glassware"] = value
        elif field_lower in ['totals', 'total sales']:
            employee["totals"] = value
            employee["net_sales"] = value
        elif 'total guests' in field_lower or field_lower == 'guests':
            employee["total_guests"] = int(value)
    
    # Validate - must have name and some data
    if employee["name"] and (employee["totals"] > 0 or employee["total_guests"] > 0):
        return employee
    
    return None


def parse_clean_pos_report(file_content: bytes, filename: str = "") -> Dict[str, Any]:
    """
    Parse a cleaned POS report XLSX file with multiple sheets (one per employee).
    
    Returns a dict with employee data list and parsing stats.
    """
    
    result = {
        "success": False,
        "employees": [],
        "errors": [],
        "stats": {
            "total_rows": 0,
            "total_sheets": 0,
            "employees_found": 0,
            "total_guests_sum": 0,
            "total_sales_sum": 0
        }
    }
    
    try:
        # Read Excel file - get all sheet names
        xl = pd.ExcelFile(BytesIO(file_content))
        sheet_names = xl.sheet_names
        result["stats"]["total_sheets"] = len(sheet_names)
        
        employees = []
        
        for sheet_name in sheet_names:
            try:
                df = pd.read_excel(BytesIO(file_content), sheet_name=sheet_name, header=None)
                result["stats"]["total_rows"] += len(df)
                
                emp = parse_single_sheet(df)
                if emp:
                    employees.append(emp)
            except Exception as e:
                result["errors"].append(f"Error parsing sheet {sheet_name}: {str(e)}")
        
        # Calculate stats
        total_guests = sum(e.get("total_guests", 0) for e in employees)
        total_sales = sum(e.get("totals", 0) or e.get("net_sales", 0) for e in employees)
        
        result["success"] = len(employees) > 0
        result["employees"] = employees
        result["stats"]["employees_found"] = len(employees)
        result["stats"]["total_guests_sum"] = total_guests
        result["stats"]["total_sales_sum"] = round(total_sales, 2)
        
    except Exception as e:
        result["success"] = False
        result["errors"].append(f"Parse error: {str(e)}")
    
    return result


# Test function
if __name__ == "__main__":
    print("Clean POS Parser module loaded successfully")
