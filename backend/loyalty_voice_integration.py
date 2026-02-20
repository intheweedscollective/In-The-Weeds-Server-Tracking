"""
Loyalty Voice Integration - Scrape Server Performance Report for CV scores

This module navigates to Landry's Loyalty Voice platform and extracts the
Server Performance Report which contains NPS (Net Promoter Score) percentages
for each server.

CV Scoring Logic:
- Each survey response where the server received a 9-10 rating = +1 point (Promoter)
- Each survey response where the server received a 1-6 rating = -2 points (Detractor)
- Passive (7-8 rating) = 0 points

We extract: Received (# responses), Avg Rating, NPS% to calculate promoter/detractor counts.
"""
import os
import asyncio
import re
from datetime import datetime, timezone, date
from typing import Dict, List, Any, Optional, Tuple
from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

load_dotenv()

# Loyalty Voice credentials
LV_URL = "https://landrys.loyalty-voice.com"
LV_USERNAME = os.environ.get("LOYALTY_VOICE_USERNAME", "Bglv@ldry.com")
LV_PASSWORD = os.environ.get("LOYALTY_VOICE_PASSWORD", "EZMoney2026")

# CV Point values
CV_PROMOTER_POINTS = 1   # Rating 9-10
CV_DETRACTOR_POINTS = -2  # Rating 1-6


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


def get_current_quarter() -> Tuple[str, int]:
    """
    Get the current quarter based on today's date.
    Returns: (quarter, year)
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
    
    return quarter, year


async def login_to_loyalty_voice(page: Page) -> bool:
    """
    Handle the login flow for Landry's Loyalty Voice (Microsoft SSO).
    Returns True if login successful.
    """
    try:
        print("[LV] Navigating to login page...")
        await page.goto(LV_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        # Microsoft SSO - Step 1: Email
        email_input = page.locator('input[type="email"]')
        if await email_input.is_visible(timeout=10000):
            print(f"[LV] Entering email: {LV_USERNAME}")
            await email_input.fill(LV_USERNAME)
            await page.locator('input[type="submit"]').click()
            await page.wait_for_timeout(4000)
        
        # Microsoft SSO - Step 2: Password
        password_input = page.locator('input[type="password"]')
        if await password_input.is_visible(timeout=10000):
            print("[LV] Entering password")
            await password_input.fill(LV_PASSWORD)
            await page.locator('input[type="submit"]').click()
            await page.wait_for_timeout(5000)
        
        # Microsoft SSO - Step 3: "Stay signed in?" prompt
        yes_btn = page.locator('input[value="Yes"]')
        if await yes_btn.is_visible(timeout=5000):
            print("[LV] Clicking 'Yes' to stay signed in")
            await yes_btn.click()
            await page.wait_for_timeout(4000)
        
        current_url = page.url
        print(f"[LV] Current URL after login: {current_url}")
        
        if "loyalty-voice.com" in current_url and "login" not in current_url.lower():
            print("[LV] Login successful!")
            return True
        
        return False
        
    except Exception as e:
        print(f"[LV] Login error: {e}")
        return False


async def navigate_and_set_date_range(page: Page, quarter: str, year: int) -> bool:
    """
    Navigate to Server Performance Report and set the date range.
    Returns True if successful.
    """
    try:
        # Navigate directly to Server Performance report
        print(f"[LV] Navigating to Server Performance Report...")
        await page.goto(f"{LV_URL}/Report/ServerPerformance", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click on date filter to open the date picker
        print("[LV] Opening date picker...")
        await page.locator('#date-filter').click()
        await page.wait_for_timeout(1500)
        
        # Determine which preset to use based on quarter
        current_q, current_year = get_current_quarter()
        
        if quarter == current_q and year == current_year:
            # Use Quarter-To-Date for current quarter
            print("[LV] Using 'Quarter-To-Date' preset...")
            preset = page.locator('li:has-text("Quarter-To-Date")').first
            await preset.click()
            await page.wait_for_timeout(1500)
        else:
            # Use Custom Range for other quarters
            print(f"[LV] Using 'Custom Range' for {quarter} {year}...")
            custom_range = page.locator('li:has-text("Custom Range")').first
            await custom_range.click()
            await page.wait_for_timeout(1500)
            
            # Set start and end dates
            start_date, end_date = get_quarter_date_range(quarter, year)
            
            start_input = page.locator('.daterangepicker input[name="daterangepicker_start"]').first
            end_input = page.locator('.daterangepicker input[name="daterangepicker_end"]').first
            
            if await start_input.is_visible(timeout=3000):
                await start_input.clear()
                await start_input.fill(start_date)
                print(f"[LV] Set start date: {start_date}")
            
            if await end_input.is_visible(timeout=3000):
                await end_input.clear()
                await end_input.fill(end_date)
                print(f"[LV] Set end date: {end_date}")
            
            await page.wait_for_timeout(1000)
        
        # Click Apply button with force=True to handle potential overlays
        print("[LV] Clicking Apply...")
        apply_btn = page.locator('.applyBtn').first
        if await apply_btn.is_visible(timeout=3000):
            await apply_btn.click(force=True)
            await page.wait_for_timeout(5000)
            print("[LV] Date range applied!")
        
        return True
        
    except Exception as e:
        print(f"[LV] Navigation/date error: {e}")
        return False


async def scrape_nps_from_aggrid(page: Page) -> List[Dict[str, Any]]:
    """
    Scrape data from the ag-grid table on the Server Performance Report.
    
    Expected columns: Name, Location, Sent, Received, Response Rate, Avg. Rating, NPS
    
    Returns list of dicts with server_name, received count, avg_rating, nps_score,
    and calculated CV points (promoters * 1 + detractors * -2).
    """
    server_data = []
    
    try:
        # Wait for ag-grid to be present
        print("[LV] Waiting for data grid to load...")
        await page.wait_for_selector('.ag-row', timeout=15000, state='attached')
        await page.wait_for_timeout(3000)
        
        # Try to set page size to maximum (100)
        try:
            page_size_select = page.locator('select').first
            if await page_size_select.count() > 0:
                await page_size_select.select_option('100')
                await page.wait_for_timeout(3000)
                print("[LV] Set page size to 100")
        except:
            pass
        
        # Get all rows
        rows = await page.locator('.ag-row').all()
        print(f"[LV] Found {len(rows)} rows in grid")
        
        for row in rows:
            try:
                cells = await row.locator('.ag-cell').all()
                if len(cells) < 7:
                    continue
                
                cell_values = []
                for cell in cells:
                    text = await cell.inner_text()
                    cell_values.append(text.strip())
                
                # Column mapping:
                # 0: Name, 1: Location, 2: Sent, 3: Received, 4: Response Rate, 5: Avg. Rating, 6: NPS
                server_name = cell_values[0] if len(cell_values) > 0 else ""
                location = cell_values[1] if len(cell_values) > 1 else ""
                received_str = cell_values[3] if len(cell_values) > 3 else "0"
                avg_rating_str = cell_values[5] if len(cell_values) > 5 else "0"
                nps_str = cell_values[6] if len(cell_values) > 6 else "0%"
                
                # Skip empty rows, header rows, or store-only rows
                if not server_name or server_name.startswith('Bubba') or len(server_name) < 3:
                    continue
                if any(header in server_name.lower() for header in ['name', 'server', 'total']):
                    continue
                
                # Parse values
                try:
                    received = int(received_str) if received_str else 0
                except ValueError:
                    received = 0
                
                try:
                    avg_rating = float(avg_rating_str) if avg_rating_str else 0
                except ValueError:
                    avg_rating = 0
                
                nps_match = re.match(r'(-?\d+(?:\.\d+)?)', nps_str.replace('%', ''))
                nps_score = float(nps_match.group(1)) if nps_match else 0
                
                # Calculate promoters and detractors from NPS and response count
                # NPS = (% Promoters) - (% Detractors)
                # If NPS=100, all are promoters. If NPS=0, could be all passive or equal promoters/detractors.
                # We can estimate based on avg rating:
                # - If avg >= 9 and NPS > 0, likely all promoters
                # - If avg >= 7 and NPS == 0, likely all passive
                # - If avg < 7, has detractors
                
                if received == 0:
                    promoters = 0
                    detractors = 0
                    passives = 0
                elif nps_score == 100:
                    # All responses were 9-10 (promoters)
                    promoters = received
                    detractors = 0
                    passives = 0
                elif nps_score == 0:
                    if avg_rating >= 7:
                        # All responses were 7-8 (passive)
                        promoters = 0
                        detractors = 0
                        passives = received
                    else:
                        # Mixed or detractors - estimate based on avg rating
                        detractors = received
                        promoters = 0
                        passives = 0
                elif nps_score > 0:
                    # More promoters than detractors
                    # NPS = P - D, where P + D + Passive = received
                    # If NPS = 50% with 2 responses: could be 1 promoter, 0 detractor, 1 passive
                    promoter_pct = (nps_score + 100) / 200  # Rough estimate
                    promoters = max(1, round(received * promoter_pct))
                    detractors = 0
                    passives = received - promoters
                else:
                    # More detractors than promoters (negative NPS)
                    detractor_pct = (-nps_score) / 100
                    detractors = max(1, round(received * detractor_pct))
                    promoters = 0
                    passives = received - detractors
                
                # Calculate CV points
                cv_points = (promoters * CV_PROMOTER_POINTS) + (detractors * CV_DETRACTOR_POINTS)
                
                server_data.append({
                    "server_name": server_name,
                    "location": location,
                    "received": received,
                    "avg_rating": avg_rating,
                    "nps_score": nps_score,
                    "promoters": promoters,
                    "passives": passives,
                    "detractors": detractors,
                    "cv_points": cv_points,
                    "raw_data": cell_values
                })
                
            except Exception as row_err:
                continue
        
        print(f"[LV] Successfully scraped {len(server_data)} servers")
        
    except Exception as e:
        print(f"[LV] Scraping error: {e}")
    
    return server_data


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
    # Determine quarter/year
    if quarter is None or year is None:
        current_q, current_year = get_current_quarter()
        quarter = quarter or current_q
        year = year or current_year
    
    quarter = quarter.upper()
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
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        try:
            # Step 1: Login
            print("[LV] Step 1: Logging in...")
            login_success = await login_to_loyalty_voice(page)
            if not login_success:
                result["error"] = "Login failed"
                return result
            
            # Step 2: Navigate and set date range
            print("[LV] Step 2: Setting date range...")
            nav_success = await navigate_and_set_date_range(page, quarter, year)
            if not nav_success:
                result["error"] = "Navigation/date range setup failed"
                return result
            
            # Step 3: Scrape NPS data
            print("[LV] Step 3: Scraping NPS data...")
            server_data = await scrape_nps_from_aggrid(page)
            
            if not server_data:
                screenshot_path = f"/tmp/lv_no_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"[LV] No data found. Screenshot: {screenshot_path}")
                result["error"] = "No server data found in report"
                result["debug_screenshot"] = screenshot_path
                return result
            
            result["success"] = True
            result["servers"] = server_data
            result["server_count"] = len(server_data)
            
            print(f"[LV] Successfully scraped {len(server_data)} servers")
            
        except Exception as e:
            print(f"[LV] Error: {e}")
            result["error"] = str(e)
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
    **kwargs
) -> Dict[str, Any]:
    """
    Sync Loyalty Voice NPS scores to the database.
    
    This function:
    1. Scrapes the Server Performance Report for NPS scores
    2. Matches server names to employees in the database
    3. Updates the cv_nps collection with the latest scores
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
    
    # Create name lookup (case-insensitive, with variations)
    employee_lookup = {}
    for emp in employees:
        name_lower = emp["name"].lower().strip()
        employee_lookup[name_lower] = emp
        
        # Also add first name only
        first_name = name_lower.split()[0] if name_lower else ""
        if first_name and len(first_name) > 2:
            if first_name not in employee_lookup:
                employee_lookup[first_name] = emp
    
    # Match and store NPS scores
    matched_servers = []
    unmatched_servers = []
    
    for server in server_data:
        server_name = server.get("server_name", "").strip()
        nps_score = server.get("nps_score", 0)
        
        if not server_name:
            continue
        
        server_name_lower = server_name.lower().strip()
        matched_employee = None
        
        # Try exact match
        if server_name_lower in employee_lookup:
            matched_employee = employee_lookup[server_name_lower]
        else:
            # Try first name match
            first_name = server_name_lower.split()[0]
            if first_name in employee_lookup:
                matched_employee = employee_lookup[first_name]
            else:
                # Try partial/fuzzy match
                for emp_name, emp in employee_lookup.items():
                    if server_name_lower in emp_name or emp_name in server_name_lower:
                        matched_employee = emp
                        break
        
        if matched_employee:
            nps_doc = {
                "id": str(uuid.uuid4()),
                "employee_id": matched_employee["id"],
                "employee_name": matched_employee["name"],
                "scraped_name": server_name,
                "received": server.get("received", 0),
                "nps_score": nps_score,
                "avg_rating": server.get("avg_rating", 0),
                "promoters": server.get("promoters", 0),
                "passives": server.get("passives", 0),
                "detractors": server.get("detractors", 0),
                "cv_points": server.get("cv_points", 0),
                "quarter": quarter.upper(),
                "year": year,
                "source": "loyalty_voice",
                "synced_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert
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
                "nps_score": nps_score,
                "cv_points": server.get("cv_points", 0),
                "promoters": server.get("promoters", 0),
                "detractors": server.get("detractors", 0)
            })
        else:
            unmatched_servers.append({
                "scraped_name": server_name,
                "nps_score": nps_score,
                "cv_points": server.get("cv_points", 0)
            })
    
    result["success"] = True
    result["matched_count"] = len(matched_servers)
    result["matched_servers"] = matched_servers
    result["unmatched_servers"] = unmatched_servers
    result["total_scraped"] = len(server_data)
    
    print(f"[LV] Sync complete: {len(matched_servers)} matched, {len(unmatched_servers)} unmatched")
    
    return result


def get_nps_score_for_employee(nps_records: List[Dict], employee_name: str) -> Dict[str, Any]:
    """Get NPS score for a specific employee."""
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
