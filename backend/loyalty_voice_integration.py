"""
Loyalty Voice Integration - Scrape Server Performance Report for NPS scores

This module navigates to Landry's Loyalty Voice platform and extracts the
Server Performance Report which contains NPS (Net Promoter Score) percentages
for each server, rather than scraping individual feedback items.

Flow:
1. Log into Landry's Loyalty Voice (Microsoft SSO)
2. Navigate to Reports → Server Performance
3. Select date range based on current quarter
4. Scrape NPS % for each server from the report table
5. Store in database and integrate with employee scoring
"""
import os
import asyncio
from datetime import datetime, timezone, date
from typing import Dict, List, Any, Optional, Tuple
from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

load_dotenv()

# Loyalty Voice credentials
LV_URL = "https://landrys.loyalty-voice.com"
LV_USERNAME = os.environ.get("LOYALTY_VOICE_USERNAME", "Bglv@ldry.com")
LV_PASSWORD = os.environ.get("LOYALTY_VOICE_PASSWORD", "EZMoney2026")


def get_quarter_date_range(quarter: str, year: int) -> Tuple[str, str]:
    """
    Get the date range for a given quarter.
    
    Q1: Jan 1 - Mar 31
    Q2: Apr 1 - Jun 30
    Q3: Jul 1 - Sep 30
    Q4: Oct 1 - Dec 31
    
    Returns: (start_date, end_date) in MM/DD/YYYY format
    """
    quarter_ranges = {
        "Q1": ("01/01", "03/31"),
        "Q2": ("04/01", "06/30"),
        "Q3": ("07/01", "09/30"),
        "Q4": ("10/01", "12/31"),
    }
    
    q = quarter.upper()
    if q not in quarter_ranges:
        raise ValueError(f"Invalid quarter: {quarter}. Must be Q1-Q4.")
    
    start_mmdd, end_mmdd = quarter_ranges[q]
    start_date = f"{start_mmdd}/{year}"
    end_date = f"{end_mmdd}/{year}"
    
    return start_date, end_date


def get_current_quarter_dates() -> Tuple[str, str, str, int]:
    """
    Get the current quarter's date range based on today's date.
    
    Returns: (quarter, start_date, end_date, year) where dates are MM/DD/YYYY
    """
    today = date.today()
    year = today.year
    month = today.month
    
    if month <= 3:
        quarter = "Q1"
    elif month <= 6:
        quarter = "Q2"
    elif month <= 9:
        quarter = "Q3"
    else:
        quarter = "Q4"
    
    start_date, end_date = get_quarter_date_range(quarter, year)
    
    return quarter, start_date, end_date, year


async def login_to_loyalty_voice(page: Page) -> bool:
    """
    Handle the login flow for Landry's Loyalty Voice (Microsoft SSO).
    
    Returns True if login successful, False otherwise.
    """
    try:
        # Navigate to main site
        await page.goto(LV_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        # Microsoft SSO - Step 1: Email
        email_input = page.locator('input[type="email"]')
        if await email_input.is_visible(timeout=10000):
            print(f"[LV] Entering email: {LV_USERNAME}")
            await email_input.fill(LV_USERNAME)
            
            # Click Next/Submit
            submit_btn = page.locator('input[type="submit"]')
            await submit_btn.click()
            await page.wait_for_timeout(4000)
        
        # Microsoft SSO - Step 2: Password
        password_input = page.locator('input[type="password"]')
        if await password_input.is_visible(timeout=10000):
            print("[LV] Entering password")
            await password_input.fill(LV_PASSWORD)
            
            # Click Sign in
            submit_btn = page.locator('input[type="submit"]')
            await submit_btn.click()
            await page.wait_for_timeout(5000)
        
        # Microsoft SSO - Step 3: "Stay signed in?" prompt
        yes_btn = page.locator('input[value="Yes"]')
        no_btn = page.locator('input[value="No"]')
        
        if await yes_btn.is_visible(timeout=5000):
            print("[LV] Clicking 'Yes' to stay signed in")
            await yes_btn.click()
            await page.wait_for_timeout(4000)
        elif await no_btn.is_visible(timeout=2000):
            await no_btn.click()
            await page.wait_for_timeout(4000)
        
        # Verify we're logged in by checking the URL or page content
        current_url = page.url
        print(f"[LV] Current URL after login: {current_url}")
        
        # Should be redirected to dashboard or home
        if "loyalty-voice.com" in current_url and "login" not in current_url.lower():
            print("[LV] Login successful!")
            return True
        
        # Check for common dashboard elements
        await page.wait_for_timeout(3000)
        dashboard_check = page.locator('text=Dashboard')
        reports_check = page.locator('text=Reports')
        
        if await dashboard_check.is_visible(timeout=5000) or await reports_check.is_visible(timeout=5000):
            print("[LV] Found dashboard elements - login confirmed")
            return True
        
        print("[LV] Could not confirm login success")
        return False
        
    except Exception as e:
        print(f"[LV] Login error: {e}")
        return False


async def navigate_to_server_performance_report(page: Page) -> bool:
    """
    Navigate from dashboard to Reports → Server Performance.
    
    Returns True if navigation successful.
    """
    try:
        # Step 1: Click on "Reports" in navigation
        print("[LV] Looking for Reports menu...")
        
        # Try various selectors for the Reports menu
        reports_selectors = [
            'a:has-text("Reports")',
            '[href*="/reports"]',
            'nav >> text=Reports',
            'button:has-text("Reports")',
            '.nav-link:has-text("Reports")',
            '[data-menu="reports"]',
        ]
        
        reports_clicked = False
        for selector in reports_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    print(f"[LV] Clicked Reports using selector: {selector}")
                    reports_clicked = True
                    break
            except:
                continue
        
        if not reports_clicked:
            # Try clicking by text content directly
            await page.get_by_text("Reports", exact=True).first.click()
            reports_clicked = True
        
        await page.wait_for_timeout(3000)
        
        # Step 2: Click on "Server Performance" sub-menu
        print("[LV] Looking for Server Performance option...")
        
        server_perf_selectors = [
            'a:has-text("Server Performance")',
            '[href*="server-performance"]',
            '[href*="serverperformance"]',
            'text=Server Performance',
            'li >> text=Server Performance',
            '.dropdown-item:has-text("Server Performance")',
        ]
        
        sp_clicked = False
        for selector in server_perf_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    print(f"[LV] Clicked Server Performance using selector: {selector}")
                    sp_clicked = True
                    break
            except:
                continue
        
        if not sp_clicked:
            await page.get_by_text("Server Performance", exact=False).first.click()
            sp_clicked = True
        
        await page.wait_for_timeout(3000)
        print("[LV] Navigated to Server Performance report page")
        return True
        
    except Exception as e:
        print(f"[LV] Navigation error: {e}")
        return False


async def set_date_range_and_view_report(page: Page, start_date: str, end_date: str) -> bool:
    """
    Set the date range in the report filters and click View Report.
    
    Args:
        start_date: Start date in MM/DD/YYYY format
        end_date: End date in MM/DD/YYYY format
    
    Returns True if report loaded successfully.
    """
    try:
        print(f"[LV] Setting date range: {start_date} to {end_date}")
        
        # Look for date input fields
        # Common patterns: "Start Date", "From", "Begin Date"
        start_selectors = [
            'input[placeholder*="Start"]',
            'input[name*="start"]',
            'input[name*="from"]',
            'input[aria-label*="Start"]',
            'input[aria-label*="From"]',
            '#startDate',
            '#fromDate',
            '.start-date input',
            'label:has-text("Start") + input',
            'label:has-text("From") + input',
        ]
        
        # Try to find and fill start date
        start_filled = False
        for selector in start_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.clear()
                    await el.fill(start_date)
                    print(f"[LV] Filled start date using: {selector}")
                    start_filled = True
                    break
            except:
                continue
        
        # If specific selectors didn't work, try finding by adjacent label
        if not start_filled:
            try:
                # Try clicking on a date picker and typing
                date_inputs = page.locator('input[type="text"]').all()
                inputs = await date_inputs
                for i, inp in enumerate(inputs):
                    placeholder = await inp.get_attribute("placeholder") or ""
                    if "date" in placeholder.lower() or "from" in placeholder.lower() or "start" in placeholder.lower():
                        await inp.clear()
                        await inp.fill(start_date)
                        start_filled = True
                        print(f"[LV] Filled start date in input #{i}")
                        break
            except:
                pass
        
        await page.wait_for_timeout(1000)
        
        # Look for end date input
        end_selectors = [
            'input[placeholder*="End"]',
            'input[name*="end"]',
            'input[name*="to"]',
            'input[aria-label*="End"]',
            'input[aria-label*="To"]',
            '#endDate',
            '#toDate',
            '.end-date input',
            'label:has-text("End") + input',
            'label:has-text("To") + input',
        ]
        
        end_filled = False
        for selector in end_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.clear()
                    await el.fill(end_date)
                    print(f"[LV] Filled end date using: {selector}")
                    end_filled = True
                    break
            except:
                continue
        
        # Fallback for end date
        if not end_filled:
            try:
                date_inputs = page.locator('input[type="text"]').all()
                inputs = await date_inputs
                for i, inp in enumerate(inputs):
                    placeholder = await inp.get_attribute("placeholder") or ""
                    if "end" in placeholder.lower() or "to" in placeholder.lower():
                        await inp.clear()
                        await inp.fill(end_date)
                        end_filled = True
                        print(f"[LV] Filled end date in input #{i}")
                        break
            except:
                pass
        
        await page.wait_for_timeout(1000)
        
        # Click "View Report" or equivalent button
        print("[LV] Looking for View Report button...")
        
        view_selectors = [
            'button:has-text("View Report")',
            'button:has-text("Generate")',
            'button:has-text("Run Report")',
            'button:has-text("Submit")',
            'input[value="View Report"]',
            'a:has-text("View Report")',
            '.btn:has-text("View")',
            '[type="submit"]',
        ]
        
        for selector in view_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    print(f"[LV] Clicked view report using: {selector}")
                    break
            except:
                continue
        
        # Wait for report to load
        await page.wait_for_timeout(5000)
        print("[LV] Report should be loaded now")
        return True
        
    except Exception as e:
        print(f"[LV] Date range/view error: {e}")
        return False


async def scrape_nps_from_report(page: Page) -> List[Dict[str, Any]]:
    """
    Scrape the NPS scores from the Server Performance Report table.
    
    Expected table structure (may vary):
    | Server Name | Responses | NPS | Promoters | Passives | Detractors |
    
    Returns a list of dicts with server name and NPS percentage.
    """
    server_nps_data = []
    
    try:
        print("[LV] Scraping NPS data from report table...")
        
        # Wait for table to be present
        await page.wait_for_selector('table', timeout=10000)
        
        # Try different table selection strategies
        table = page.locator('table').first
        
        # Get all rows
        rows = await table.locator('tbody tr').all()
        
        if not rows:
            # Maybe tbody doesn't exist, try tr directly
            rows = await table.locator('tr').all()
        
        print(f"[LV] Found {len(rows)} rows in table")
        
        for row in rows:
            try:
                cells = await row.locator('td').all()
                
                if not cells or len(cells) < 2:
                    continue
                
                # Extract text from each cell
                cell_texts = []
                for cell in cells:
                    text = await cell.inner_text()
                    cell_texts.append(text.strip())
                
                # Skip header rows
                if any(h in cell_texts[0].lower() for h in ['server', 'employee', 'name', 'total']):
                    if 'nps' in cell_texts[0].lower():
                        continue
                
                # Try to identify which column has the server name and NPS
                # Common layouts:
                # [Server Name, Responses, NPS%, Promoters, Passives, Detractors]
                # or [Server Name, NPS, ...]
                
                server_name = cell_texts[0] if cell_texts else ""
                nps_value = None
                
                # Look for NPS value (should be a percentage, could be negative)
                for i, text in enumerate(cell_texts[1:], 1):
                    # NPS is typically -100 to 100, often shown as percentage
                    clean_text = text.replace('%', '').replace('+', '').strip()
                    try:
                        val = float(clean_text)
                        # NPS should be between -100 and 100
                        if -100 <= val <= 100:
                            # If this looks like an NPS (usually 2nd or 3rd column)
                            if i <= 3 or 'nps' in str(cells[i-1]).lower():
                                nps_value = val
                                break
                    except ValueError:
                        continue
                
                # If we couldn't find NPS by pattern, try the 3rd column (common position)
                if nps_value is None and len(cell_texts) >= 3:
                    try:
                        clean = cell_texts[2].replace('%', '').replace('+', '').strip()
                        nps_value = float(clean)
                    except ValueError:
                        pass
                
                if server_name and nps_value is not None:
                    server_nps_data.append({
                        "server_name": server_name,
                        "nps_score": nps_value,
                        "raw_cells": cell_texts  # For debugging
                    })
                    print(f"[LV] Extracted: {server_name} = {nps_value}% NPS")
                
            except Exception as row_err:
                print(f"[LV] Error parsing row: {row_err}")
                continue
        
        # Alternative: Try to parse using role-based selectors (for ag-grid or similar)
        if not server_nps_data:
            print("[LV] Trying alternative parsing (role-based grid)...")
            
            grid_rows = await page.locator('[role="row"]').all()
            for row in grid_rows:
                try:
                    cells = await row.locator('[role="gridcell"], [role="cell"]').all()
                    if len(cells) >= 2:
                        cell_texts = [await c.inner_text() for c in cells]
                        
                        if cell_texts:
                            server_name = cell_texts[0].strip()
                            # Skip headers
                            if server_name.lower() in ['server', 'name', 'employee']:
                                continue
                            
                            # Find NPS
                            for text in cell_texts[1:]:
                                clean = text.replace('%', '').replace('+', '').strip()
                                try:
                                    nps = float(clean)
                                    if -100 <= nps <= 100:
                                        server_nps_data.append({
                                            "server_name": server_name,
                                            "nps_score": nps,
                                        })
                                        break
                                except:
                                    continue
                except:
                    continue
        
        print(f"[LV] Total servers scraped: {len(server_nps_data)}")
        
    except Exception as e:
        print(f"[LV] Scraping error: {e}")
    
    return server_nps_data


async def scrape_server_performance_report(
    quarter: str = None,
    year: int = None
) -> Dict[str, Any]:
    """
    Main function to scrape the Server Performance Report from Loyalty Voice.
    
    Args:
        quarter: Quarter to scrape (Q1-Q4). If None, uses current quarter.
        year: Year to scrape. If None, uses current year.
    
    Returns:
        Dict with server NPS data and metadata
    """
    # Determine date range
    if quarter is None or year is None:
        current_q, start_date, end_date, current_year = get_current_quarter_dates()
        quarter = quarter or current_q
        year = year or current_year
        start_date, end_date = get_quarter_date_range(quarter, year)
    else:
        start_date, end_date = get_quarter_date_range(quarter, year)
    
    print(f"[LV] Starting Server Performance Report scrape for {quarter} {year}")
    print(f"[LV] Date range: {start_date} to {end_date}")
    
    result = {
        "success": False,
        "quarter": quarter,
        "year": year,
        "date_range": {"start": start_date, "end": end_date},
        "servers": [],
        "error": None,
        "scraped_at": datetime.now(timezone.utc).isoformat()
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        try:
            # Step 1: Login
            print("[LV] Step 1: Logging in...")
            login_success = await login_to_loyalty_voice(page)
            if not login_success:
                result["error"] = "Login failed"
                return result
            
            # Step 2: Navigate to Server Performance Report
            print("[LV] Step 2: Navigating to Server Performance Report...")
            nav_success = await navigate_to_server_performance_report(page)
            if not nav_success:
                result["error"] = "Navigation to report failed"
                return result
            
            # Step 3: Set date range and view report
            print("[LV] Step 3: Setting date range and viewing report...")
            view_success = await set_date_range_and_view_report(page, start_date, end_date)
            if not view_success:
                result["error"] = "Could not set date range or view report"
                return result
            
            # Step 4: Scrape NPS data from the report
            print("[LV] Step 4: Scraping NPS data...")
            server_data = await scrape_nps_from_report(page)
            
            if not server_data:
                # Take a screenshot for debugging
                screenshot_path = f"/tmp/lv_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"[LV] No data found. Screenshot saved to: {screenshot_path}")
                result["error"] = "No server data found in report"
                result["debug_screenshot"] = screenshot_path
                return result
            
            result["success"] = True
            result["servers"] = server_data
            result["server_count"] = len(server_data)
            
            print(f"[LV] Successfully scraped {len(server_data)} servers")
            
        except Exception as e:
            print(f"[LV] Error during scrape: {e}")
            result["error"] = str(e)
            
            # Take error screenshot
            try:
                screenshot_path = f"/tmp/lv_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                result["debug_screenshot"] = screenshot_path
            except:
                pass
        
        finally:
            await browser.close()
    
    return result


async def sync_loyalty_voice_to_db(
    db,
    quarter: str,
    year: int,
    **kwargs  # Accept any extra args for backwards compatibility
) -> Dict[str, Any]:
    """
    Sync Loyalty Voice NPS scores to the database.
    
    This function:
    1. Scrapes the Server Performance Report for NPS scores
    2. Matches server names to employees in the database
    3. Updates the cv_nps collection with the latest scores
    
    Args:
        db: MongoDB database instance
        quarter: Quarter to sync (Q1-Q4)
        year: Year to sync
    
    Returns:
        Dict with sync results
    """
    import uuid
    
    result = {
        "success": False,
        "matched_count": 0,
        "unmatched_servers": [],
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "error": None
    }
    
    # Scrape the report
    scrape_result = await scrape_server_performance_report(quarter, year)
    
    if not scrape_result.get("success"):
        result["error"] = scrape_result.get("error", "Scraping failed")
        result["debug_screenshot"] = scrape_result.get("debug_screenshot")
        return result
    
    server_data = scrape_result.get("servers", [])
    
    if not server_data:
        result["error"] = "No server data returned from scrape"
        return result
    
    # Get all employees for this quarter
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(500)
    
    # Create a name lookup (case-insensitive)
    employee_lookup = {}
    for emp in employees:
        name_lower = emp["name"].lower().strip()
        employee_lookup[name_lower] = emp
        
        # Also add first name only for partial matching
        first_name = name_lower.split()[0] if name_lower else ""
        if first_name and first_name not in employee_lookup:
            employee_lookup[first_name] = emp
    
    # Match and store NPS scores
    matched_servers = []
    unmatched_servers = []
    
    for server in server_data:
        server_name = server.get("server_name", "").strip()
        nps_score = server.get("nps_score")
        
        if not server_name or nps_score is None:
            continue
        
        # Try to match to employee
        server_name_lower = server_name.lower().strip()
        
        matched_employee = None
        
        # Exact match
        if server_name_lower in employee_lookup:
            matched_employee = employee_lookup[server_name_lower]
        else:
            # Try first name match
            first_name = server_name_lower.split()[0] if server_name_lower else ""
            if first_name in employee_lookup:
                matched_employee = employee_lookup[first_name]
            else:
                # Try partial match (contains)
                for emp_name, emp in employee_lookup.items():
                    if server_name_lower in emp_name or emp_name in server_name_lower:
                        matched_employee = emp
                        break
        
        if matched_employee:
            # Store/update NPS score in database
            nps_doc = {
                "id": str(uuid.uuid4()),
                "employee_id": matched_employee["id"],
                "employee_name": matched_employee["name"],
                "scraped_name": server_name,
                "nps_score": nps_score,
                "quarter": quarter.upper(),
                "year": year,
                "source": "loyalty_voice",
                "synced_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert - update if exists for this employee/quarter/year
            await db.cv_nps.update_one(
                {
                    "employee_id": matched_employee["id"],
                    "quarter": quarter.upper(),
                    "year": year
                },
                {"$set": nps_doc},
                upsert=True
            )
            
            matched_servers.append({
                "scraped_name": server_name,
                "matched_name": matched_employee["name"],
                "nps_score": nps_score
            })
        else:
            unmatched_servers.append({
                "scraped_name": server_name,
                "nps_score": nps_score
            })
    
    result["success"] = True
    result["matched_count"] = len(matched_servers)
    result["matched_servers"] = matched_servers
    result["unmatched_servers"] = unmatched_servers
    result["total_scraped"] = len(server_data)
    
    print(f"[LV] Sync complete: {len(matched_servers)} matched, {len(unmatched_servers)} unmatched")
    
    return result


def get_nps_score_for_employee(nps_records: List[Dict], employee_name: str) -> Dict[str, Any]:
    """
    Get the NPS score for a specific employee from synced records.
    
    Args:
        nps_records: List of NPS records from cv_nps collection
        employee_name: Name of the employee to look up
    
    Returns:
        Dict with NPS score and metadata
    """
    employee_name_lower = employee_name.lower().strip()
    
    for record in nps_records:
        record_name = record.get("employee_name", "").lower().strip()
        if record_name == employee_name_lower:
            return {
                "employee_name": employee_name,
                "nps_score": record.get("nps_score", 0),
                "synced_at": record.get("synced_at"),
                "found": True
            }
    
    return {
        "employee_name": employee_name,
        "nps_score": 0,
        "synced_at": None,
        "found": False
    }


# Backwards compatibility - keep old function signature but use new implementation
async def scrape_loyalty_voice_feedback(start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    """
    DEPRECATED: This function is kept for backwards compatibility.
    Use scrape_server_performance_report() instead.
    """
    print("[LV] Warning: scrape_loyalty_voice_feedback is deprecated. Using scrape_server_performance_report.")
    result = await scrape_server_performance_report()
    
    # Convert to old format for compatibility
    return {
        "success": result.get("success", False),
        "feedback": [],  # Old format expected feedback items
        "servers": result.get("servers", []),  # New format: NPS per server
        "total": result.get("server_count", 0),
        "scraped_at": result.get("scraped_at"),
        "error": result.get("error")
    }
