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
    
    # Remove common OCR errors and formatting
    val_str = val_str.replace(',', '').replace(' ', '').replace('.', '', val_str.count('.') - 1)
    
    # Handle cases like "3.911.00" -> "3911.00"
    parts = val_str.split('.')
    if len(parts) > 2:
        # Keep only the last decimal
        val_str = ''.join(parts[:-1]) + '.' + parts[-1]
    
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0


def find_employee_name(df: pd.DataFrame) -> Optional[str]:
    """
    Find the employee name in a POS report sheet.
    The name is typically in rows 5-7, columns 4-8.
    """
    invalid_patterns = [
        'printed', 'page', 'grs', 'net', 'tax', 'bglv', 'bubba', 'vegas',
        'food', 'liquor', 'beer', 'wine', 'retail', 'nan', 'sls', 'sis',
        'avg', 'guest', 'check', 'sales', 'category', 'vd/', 'sur/', 'add',
        'chg', 'server', 'report', 'date', 'blvd', '337', '3717', 'less',
        'taxes', 'surch', 'order', 'charges', '19mm', '19637', 'nv'
    ]
    
    # Search in likely locations for the name
    for row_idx in range(3, 10):
        for col_idx in range(2, 10):
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
            clean_val = val_str.replace('.', '').replace(',', '').replace(' ', '').replace('-', '')
            if clean_val.isdigit():
                continue
            
            # Skip values with invalid patterns
            val_lower = val_str.lower()
            if any(pattern in val_lower for pattern in invalid_patterns):
                continue
            
            # Skip values that are mostly numbers/special chars
            letter_count = sum(1 for c in val_str if c.isalpha())
            if letter_count < len(val_str) * 0.6:
                continue
            
            # Name must have at least one space (first + last name) or be a single word name
            # But should look like a proper name
            if not any(c.isupper() for c in val_str):
                continue
            
            # Valid name candidate
            logger.info(f"Found employee name: '{val_str}' at [{row_idx},{col_idx}]")
            return val_str
    
    return None


def find_sales_value(df: pd.DataFrame, category: str) -> float:
    """
    Find the net sales value for a category (Food, Liquor, Beer, Wine, Glassware).
    """
    for row_idx in range(8, min(25, len(df))):
        for col_idx in range(3):
            if col_idx >= df.shape[1]:
                continue
            
            val = df.iloc[row_idx, col_idx]
            if val is None or pd.isna(val):
                continue
            
            val_str = str(val).strip().lower()
            if val_str == category.lower():
                # Found the category row - look for net sales in columns 3-5
                for sales_col in range(3, 7):
                    if sales_col >= df.shape[1]:
                        continue
                    
                    sales_val = df.iloc[row_idx, sales_col]
                    if sales_val is not None and not pd.isna(sales_val):
                        sales_str = str(sales_val).strip()
                        # Check if it looks like a number
                        if any(c.isdigit() for c in sales_str):
                            # Extract first number-like pattern
                            match = re.search(r'[\d,]+\.?\d*', sales_str.replace(' ', ''))
                            if match:
                                return clean_number(match.group())
                
                return 0.0
    
    return 0.0


def find_guest_count(df: pd.DataFrame) -> int:
    """
    Find the guest count from the POS report.
    Usually in the header area or near "Guest Avg." row.
    """
    # Look for "Guest" related values
    for row_idx in range(len(df)):
        for col_idx in range(df.shape[1]):
            val = df.iloc[row_idx, col_idx]
            if val is None or pd.isna(val):
                continue
            
            val_str = str(val).strip()
            
            # Look for "Guests:" or guest count patterns
            if 'guest' in val_str.lower() and ':' in val_str:
                # Try to extract number after "Guests:"
                match = re.search(r'guests?\s*:\s*(\d+)', val_str, re.IGNORECASE)
                if match:
                    return int(match.group(1))
    
    # Alternative: Calculate from Food sales / Guest Avg
    # This requires finding the Guest Avg column
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
    Check if the file is in POS report format (multiple sheets, one per employee).
    """
    try:
        xlsx = pd.ExcelFile(file_path)
        
        # POS reports typically have many sheets (one per employee)
        if len(xlsx.sheet_names) < 5:
            return False
        
        # Check first sheet for POS report markers
        df = pd.read_excel(file_path, sheet_name=0, header=None)
        
        # Look for common POS report markers
        for row_idx in range(min(10, len(df))):
            for col_idx in range(min(5, df.shape[1])):
                val = df.iloc[row_idx, col_idx]
                if val is not None and not pd.isna(val):
                    val_str = str(val).lower()
                    if 'server sales report' in val_str or 'grs sls' in val_str:
                        return True
        
        return False
    except Exception:
        return False


if __name__ == "__main__":
    # Test the parser
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if is_pos_report_format(file_path):
            print("File is a POS report format")
            employees = parse_pos_report(file_path)
            for emp in employees[:5]:
                print(f"  {emp['name']}: Net Sales=${emp['net_sales']:,.2f}, LBW=${emp['lbw']:,.2f}")
        else:
            print("File is NOT a POS report format")
