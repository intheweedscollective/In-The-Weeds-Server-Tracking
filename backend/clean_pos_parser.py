"""
Clean POS Report Parser

Parses a simplified POS report format where each employee block contains:
- Employee Name (column B)
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


def parse_clean_pos_report(file_content: bytes, filename: str = "") -> Dict[str, Any]:
    """
    Parse a cleaned POS report XLSX file.
    
    Expected format per employee block:
    Row: Employee Name
    Row: (blank or header)
    Row: "Net Sls" header
    Row: Food | value
    Row: Liquor | value  
    Row: Beer | value
    Row: Wine | value
    Row: Loyalty | value
    Row: Bar Glassware | value
    Row: Totals | value
    Row: Total Guests | value
    
    Returns a dict with employee data list and parsing stats.
    """
    
    result = {
        "success": False,
        "employees": [],
        "errors": [],
        "stats": {
            "total_rows": 0,
            "employees_found": 0,
            "total_guests_sum": 0,
            "total_sales_sum": 0
        }
    }
    
    try:
        # Read Excel file
        df = pd.read_excel(BytesIO(file_content), header=None)
        result["stats"]["total_rows"] = len(df)
        
        # Convert to list for easier processing
        rows = df.values.tolist()
        
        employees = []
        current_employee = None
        
        i = 0
        while i < len(rows):
            row = rows[i]
            
            # Get first non-empty cell in row
            first_cell = None
            first_cell_col = None
            for col_idx, cell in enumerate(row):
                if pd.notna(cell) and str(cell).strip():
                    first_cell = str(cell).strip()
                    first_cell_col = col_idx
                    break
            
            if not first_cell:
                i += 1
                continue
            
            # Check if this is an employee name (not a known field)
            known_fields = [
                'net sls', 'food', 'liquor', 'beer', 'wine', 'loyalty', 
                'bar glassware', 'totals', 'total guests', 'net sales',
                'bar glass', 'glassware'
            ]
            
            is_known_field = any(
                kf in first_cell.lower() 
                for kf in known_fields
            )
            
            # Check if it looks like an employee name (letters, possibly with spaces)
            looks_like_name = (
                not is_known_field and 
                re.match(r'^[A-Za-z][A-Za-z\s\-\.\']+$', first_cell) and
                len(first_cell) > 2
            )
            
            if looks_like_name:
                # Save previous employee if exists
                if current_employee and current_employee.get("name"):
                    employees.append(current_employee)
                
                # Start new employee
                current_employee = {
                    "name": first_cell,
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
                i += 1
                continue
            
            # If we have a current employee, look for their data
            if current_employee:
                field_lower = first_cell.lower()
                
                # Get the value from the next column with data
                value = 0
                for col_idx in range(first_cell_col + 1, len(row)):
                    cell_val = row[col_idx]
                    if pd.notna(cell_val):
                        try:
                            # Clean and parse number
                            val_str = str(cell_val).replace(',', '').replace('$', '').strip()
                            value = float(val_str)
                            break
                        except (ValueError, TypeError):
                            continue
                
                # Map to field
                if 'food' in field_lower and 'total' not in field_lower:
                    current_employee["food"] = value
                elif 'liquor' in field_lower:
                    current_employee["liquor"] = value
                elif 'beer' in field_lower:
                    current_employee["beer"] = value
                elif 'wine' in field_lower:
                    current_employee["wine"] = value
                elif 'loyalty' in field_lower:
                    current_employee["loyalty"] = value
                elif 'glassware' in field_lower or 'bar glass' in field_lower:
                    current_employee["bar_glassware"] = value
                elif field_lower == 'totals' or field_lower == 'total':
                    current_employee["totals"] = value
                    current_employee["net_sales"] = value
                elif 'total guests' in field_lower or field_lower == 'guests':
                    current_employee["total_guests"] = int(value)
            
            i += 1
        
        # Don't forget the last employee
        if current_employee and current_employee.get("name"):
            employees.append(current_employee)
        
        # Calculate stats
        total_guests = sum(e.get("total_guests", 0) for e in employees)
        total_sales = sum(e.get("totals", 0) or e.get("net_sales", 0) for e in employees)
        
        result["success"] = True
        result["employees"] = employees
        result["stats"]["employees_found"] = len(employees)
        result["stats"]["total_guests_sum"] = total_guests
        result["stats"]["total_sales_sum"] = round(total_sales, 2)
        
    except Exception as e:
        result["success"] = False
        result["errors"].append(f"Parse error: {str(e)}")
    
    return result


def parse_multi_employee_clean_report(file_content: bytes) -> Dict[str, Any]:
    """
    Parse a clean report that may have multiple employees in sequence.
    Each employee block is separated by their name appearing.
    """
    return parse_clean_pos_report(file_content)


# Test function
if __name__ == "__main__":
    # Test with sample data structure
    sample = """
    Kitti Xavier
    
    Net Sls
    Food    40810.98
    Liquor  4590.00
    Beer    2755.00
    Wine    260
    Loyalty 750
    Bar Glassware   1145.00
    Totals  50310.98
    Total Guests    975
    """
    print("Parser module loaded successfully")
