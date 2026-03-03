"""
Loyalty Voice Feedback Scraper - Customer Voice Comments

This module scrapes individual customer feedback/comments from the Loyalty Voice
Feedback page, detects employee mentions, and calculates CV points.

Point System:
- Rating 9-10: +1 point (Promoter)
- Rating 7-8: 0 points (Passive)
- Rating 1-6: -2 points (Detractor)
"""
import os
import re
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

# Point values for CV feedback
CV_PROMOTER_POINTS = 1      # Rating 9-10
CV_PASSIVE_POINTS = 0       # Rating 7-8
CV_DETRACTOR_POINTS = -2    # Rating 1-6


def get_quarter_date_range(quarter: str, year: int) -> Tuple[str, str]:
    """Get date range for a quarter in MM/DD/YYYY format."""
    quarter_ranges = {
        "Q1": ("01/01", "03/31"),
        "Q2": ("04/01", "06/30"),
        "Q3": ("07/01", "09/30"),
        "Q4": ("10/01", "12/31"),
    }
    q = quarter.upper()
    if q not in quarter_ranges:
        raise ValueError(f"Invalid quarter: {quarter}")
    start_mmdd, end_mmdd = quarter_ranges[q]
    return f"{start_mmdd}/{year}", f"{end_mmdd}/{year}"


def parse_rating(rating_str: str) -> int:
    """Parse rating from string like '10 / 10' or '8'."""
    if not rating_str:
        return 0
    match = re.search(r'(\d+)', rating_str)
    return int(match.group(1)) if match else 0


def get_sentiment_and_points(rating: int) -> Tuple[str, int]:
    """Get sentiment category and points based on rating."""
    if rating >= 9:
        return "promoter", CV_PROMOTER_POINTS
    elif rating >= 7:
        return "passive", CV_PASSIVE_POINTS
    else:
        return "detractor", CV_DETRACTOR_POINTS


async def login_to_loyalty_voice(page: Page) -> bool:
    """Login to Loyalty Voice via Microsoft SSO."""
    try:
        await page.goto(LV_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        email_input = page.locator('input[type="email"]')
        if await email_input.is_visible(timeout=10000):
            await email_input.fill(LV_USERNAME)
            await page.locator('input[type="submit"]').click()
            await page.wait_for_timeout(4000)
        
        password_input = page.locator('input[type="password"]')
        if await password_input.is_visible(timeout=10000):
            await password_input.fill(LV_PASSWORD)
            await page.locator('input[type="submit"]').click()
            await page.wait_for_timeout(5000)
        
        yes_btn = page.locator('input[value="Yes"]')
        if await yes_btn.is_visible(timeout=5000):
            await yes_btn.click()
            await page.wait_for_timeout(4000)
        
        return "loyalty-voice.com" in page.url and "login" not in page.url.lower()
    except Exception as e:
        print(f"[CV] Login error: {e}")
        return False


async def scrape_transactions_for_servers(
    page: Page,
    start_date: str,
    end_date: str
) -> Dict[str, str]:
    """
    Scrape the Transactions page to build a mapping of customer name -> server name.
    This allows us to credit the correct server for each CV review.
    
    Args:
        page: Playwright page (already logged in)
        start_date: Start date in MM/DD/YYYY format
        end_date: End date in MM/DD/YYYY format
    
    Returns:
        Dict mapping customer first name (lowercase) to server name
    """
    customer_to_server = {}
    
    try:
        # Navigate to Transactions page
        await page.goto(f"{LV_URL}/Transactions", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Try to set page size to maximum (100 or All)
        try:
            page_size_selector = page.locator('.ag-paging-page-size select, select.ag-paging-page-size, .ag-page-size select')
            if await page_size_selector.count() > 0:
                await page_size_selector.first.select_option("100")
                await page.wait_for_timeout(2000)
                print("[CV] Set page size to 100")
        except Exception as e:
            print(f"[CV] Could not set page size: {e}")
        
        # Set date filter
        date_filter = page.locator('#date-filter').first
        if await date_filter.is_visible(timeout=5000):
            await date_filter.click()
            await page.wait_for_timeout(1500)
            
            # Use Custom Range
            custom = page.locator('li:has-text("Custom Range")').first
            if await custom.is_visible(timeout=2000):
                await custom.click()
                await page.wait_for_timeout(1000)
                
                # Fill dates
                start_input = page.locator('input[name="daterangepicker_start"]').first
                end_input = page.locator('input[name="daterangepicker_end"]').first
                
                if await start_input.is_visible(timeout=2000):
                    await start_input.clear()
                    await start_input.fill(start_date)
                if await end_input.is_visible(timeout=2000):
                    await end_input.clear()
                    await end_input.fill(end_date)
                
                await page.wait_for_timeout(1000)
            
            # Apply
            apply = page.locator('.applyBtn').first
            if await apply.is_visible(timeout=2000):
                await apply.click(force=True)
                await page.wait_for_timeout(5000)
        
        # Extract transaction data from the grid - handle both pagination and scroll
        transactions = await page.evaluate("""async () => {
            const gridBody = document.querySelector('.ag-body-viewport');
            const allRows = new Map();
            
            if (!gridBody) return [];
            
            // Helper to collect visible rows
            function collectRows() {
                const agRows = document.querySelectorAll('.ag-row');
                agRows.forEach(row => {
                    const cells = row.querySelectorAll('.ag-cell');
                    const rowData = {};
                    cells.forEach(cell => {
                        const colId = cell.getAttribute('col-id');
                        if (colId) {
                            rowData[colId] = cell.innerText?.trim() || '';
                        }
                    });
                    if (Object.keys(rowData).length > 0) {
                        const key = JSON.stringify(rowData);
                        if (!allRows.has(key)) {
                            allRows.set(key, rowData);
                        }
                    }
                });
            }
            
            // Check for pagination
            const paginationPanel = document.querySelector('.ag-paging-panel');
            const nextBtn = document.querySelector('[ref="btNext"], .ag-paging-button[ref="btNext"], button.ag-paging-button:has([ref="btNext"])');
            const lastBtn = document.querySelector('[ref="btLast"], .ag-paging-button[ref="btLast"]');
            
            if (paginationPanel && nextBtn) {
                // Pagination mode - click through all pages
                let prevCount = 0;
                let sameCountLoops = 0;
                const maxPages = 50;
                
                for (let page = 0; page < maxPages; page++) {
                    collectRows();
                    
                    // Check if we've collected all rows
                    if (allRows.size === prevCount) {
                        sameCountLoops++;
                        if (sameCountLoops >= 3) break;
                    } else {
                        sameCountLoops = 0;
                        prevCount = allRows.size;
                    }
                    
                    // Try to go to next page
                    const next = document.querySelector('[ref="btNext"]:not([disabled]), .ag-paging-button[ref="btNext"]:not([disabled])');
                    if (next && !next.disabled && next.getAttribute('aria-disabled') !== 'true') {
                        next.click();
                        await new Promise(r => setTimeout(r, 1000));
                    } else {
                        break;
                    }
                }
            } else {
                // Virtual scroll mode - scroll through all data
                gridBody.scrollTop = 0;
                await new Promise(r => setTimeout(r, 1000));
                
                const viewportHeight = gridBody.clientHeight;
                const totalHeight = gridBody.scrollHeight;
                const scrollIterations = Math.ceil(totalHeight / (viewportHeight * 0.25)) + 30;
                
                collectRows();
                
                for (let i = 0; i < scrollIterations; i++) {
                    gridBody.scrollTop += viewportHeight * 0.25;
                    await new Promise(r => setTimeout(r, 300));
                    collectRows();
                }
                
                gridBody.scrollTop = gridBody.scrollHeight;
                await new Promise(r => setTimeout(r, 1000));
                collectRows();
            }
            
            return Array.from(allRows.values());
        }""")
        
        print(f"[CV] Scraped {len(transactions)} transactions")
        
        # Log column names from first transaction for debugging
        if transactions and len(transactions) > 0:
            print(f"[CV] Transaction columns available: {list(transactions[0].keys())}")
        
        # Build customer -> server mapping
        # Try different possible column names for customer and server
        customer_cols = ['Customer_Name', 'FkCustomer_FirstName', 'CustomerFirstName', 'Customer', 'FirstName', 'GuestName', 'Guest']
        server_cols = ['ServerName', 'Server', 'Employee', 'FkEmployee_Name', 'EmployeeName', 'Staff', 'Waiter']
        
        for txn in transactions:
            customer_name = None
            server_name = None
            
            # Find customer name
            for col in customer_cols:
                if col in txn and txn[col]:
                    customer_name = txn[col].strip().lower()
                    break
            
            # Find server name
            for col in server_cols:
                if col in txn and txn[col]:
                    server_name = txn[col].strip()
                    break
            
            if customer_name and server_name:
                customer_to_server[customer_name] = server_name
        
        print(f"[CV] Built customer->server mapping with {len(customer_to_server)} entries")
        
    except Exception as e:
        print(f"[CV] Error scraping transactions: {e}")
    
    return customer_to_server


async def scrape_cv_feedback(
    quarter: str = None,
    year: int = None
) -> Dict[str, Any]:
    """
    Scrape customer voice feedback from Loyalty Voice Feedback page.
    
    Returns dict with feedback items including rating, comment, date, etc.
    """
    # Default to current quarter
    if quarter is None:
        today = date.today()
        month = today.month
        year = year or today.year
        quarter = "Q1" if month <= 3 else "Q2" if month <= 6 else "Q3" if month <= 9 else "Q4"
    
    quarter = quarter.upper()
    year = year or date.today().year
    start_date, end_date = get_quarter_date_range(quarter, year)
    
    print(f"[CV] Scraping feedback for {quarter} {year} ({start_date} - {end_date})")
    
    result = {
        "success": False,
        "quarter": quarter,
        "year": year,
        "feedback": [],
        "error": None,
        "scraped_at": datetime.now(timezone.utc).isoformat()
    }
    
    customer_to_server = {}
    feedback_items = []
    
    # SESSION 1: Scrape Transactions page for customer -> server mapping
    print("[CV] Session 1: Scraping Transactions page for server assignments...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await context.new_page()
            
            try:
                # Login
                if not await login_to_loyalty_voice(page):
                    result["error"] = "Login failed (session 1)"
                    return result
                
                customer_to_server = await scrape_transactions_for_servers(page, start_date, end_date)
                print(f"[CV] Session 1 complete: {len(customer_to_server)} customer->server mappings")
                
            except Exception as e:
                print(f"[CV] Session 1 error: {e}")
                # Continue anyway - we can still scrape feedback without mappings
            finally:
                await browser.close()
    except Exception as e:
        print(f"[CV] Session 1 browser error: {e}")
    
    # SESSION 2: Scrape Feedback page for CV reviews (separate browser)
    print("[CV] Session 2: Scraping Feedback page for CV reviews...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await context.new_page()
            
            # Capture API responses for grid data
            api_data = []
            async def handle_response(response):
                try:
                    if "/api/" in response.url and response.status == 200:
                        content_type = response.headers.get("content-type", "")
                        if "json" in content_type:
                            data = await response.json()
                            if isinstance(data, list) and len(data) > 0:
                                if any(isinstance(item, dict) and ('Rating' in item or 'Body' in item) for item in data[:5] if isinstance(item, dict)):
                                    api_data.extend(data)
                                    print(f"[CV] Captured {len(data)} items from API: {response.url}")
                except:
                    pass
            
            page.on("response", handle_response)
            
            try:
                # Login again for session 2
                if not await login_to_loyalty_voice(page):
                    result["error"] = "Login failed (session 2)"
                    await browser.close()
                    return result
                
                # Navigate to Feedback page
                await page.goto(f"{LV_URL}/Feedback", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)  # Wait longer for full page load
                
                # Set date filter - the Feedback page uses specific input IDs
                print(f"[CV] Setting date filter to {start_date} - {end_date}")
                
                # The Feedback page has date filter inputs with specific IDs
                date_filter_selectors = [
                    '#Feedback-DateCreated-date-filter',  # Main date filter on Feedback page
                    '#Feedback-DateOfBusiness-date-filter',
                    '#date-filter', 
                    '.date-filter', 
                    '[data-filter="date"]'
                ]
                date_filter_found = False
                
                for selector in date_filter_selectors:
                    date_filter = page.locator(selector).first
                    try:
                        if await date_filter.is_visible(timeout=3000):
                            await date_filter.click()
                            await page.wait_for_timeout(1500)
                            date_filter_found = True
                            print(f"[CV] Found date filter with selector: {selector}")
                            break
                    except:
                        continue
                
                if date_filter_found:
                    # Use Custom Range for specific quarter
                    custom = page.locator('li:has-text("Custom Range")').first
                    if await custom.is_visible(timeout=3000):
                        await custom.click()
                        await page.wait_for_timeout(1000)
                        
                        # Fill dates
                        start_input = page.locator('input[name="daterangepicker_start"]').first
                        end_input = page.locator('input[name="daterangepicker_end"]').first
                        
                        if await start_input.is_visible(timeout=2000):
                            await start_input.clear()
                            await start_input.fill(start_date)
                            print(f"[CV] Filled start date: {start_date}")
                        if await end_input.is_visible(timeout=2000):
                            await end_input.clear()
                            await end_input.fill(end_date)
                            print(f"[CV] Filled end date: {end_date}")
                        
                        await page.wait_for_timeout(1000)
                        
                        # Apply the date filter
                        apply = page.locator('.applyBtn').first
                        if await apply.is_visible(timeout=2000):
                            await apply.click(force=True)
                            print("[CV] Applied date filter")
                            await page.wait_for_timeout(6000)  # Wait longer for data to load
                else:
                    print("[CV] Date filter not found with any selector")
                
                # Try to set page size to 100 (after date filter is applied)
                try:
                    page_size_selectors = [
                        '.ag-paging-page-size select',
                        'select.ag-paging-page-size', 
                        '.ag-page-size select',
                        '.ag-paging-page-size-wrapper select'
                    ]
                    for selector in page_size_selectors:
                        page_size_el = page.locator(selector).first
                        if await page_size_el.count() > 0:
                            await page_size_el.select_option("100")
                            print(f"[CV] Set page size to 100 using selector: {selector}")
                            await page.wait_for_timeout(3000)
                            break
                except Exception as e:
                    print(f"[CV] Could not set page size: {e}")
                
                # Check how many total records we should expect
                try:
                    page_summary = await page.locator('.ag-paging-row-summary-panel').inner_text()
                    print(f"[CV] Pagination summary: {page_summary}")
                except:
                    pass
                
                # Wait for API data to be captured
                await page.wait_for_timeout(3000)
                
                # If we captured API data, use that (more reliable)
                if api_data:
                    print(f"[CV] Using API-captured data: {len(api_data)} items")
                    feedback_data = api_data
                else:
                    # Fallback to scraping the grid
                    print("[CV] No API data captured, falling back to grid scraping")
                    # Try to find and click "Export" or "Show All" if available
                    try:
                        # Check for page size selector
                        page_size = page.locator('select.ag-paging-page-size, .ag-page-size select')
                        if await page_size.count() > 0:
                            await page_size.first.select_option("100")
                            await page.wait_for_timeout(2000)
                    except:
                        pass
                    
                    # Scrape feedback with pagination support (same approach as Transactions)
                    feedback_data = await page.evaluate("""async () => {
                        const gridBody = document.querySelector('.ag-body-viewport');
                        const allRows = new Map();
                        
                        if (!gridBody) return [];
                        
                        // Helper to collect visible rows
                        function collectRows() {
                            const agRows = document.querySelectorAll('.ag-row');
                            agRows.forEach(row => {
                                const cells = row.querySelectorAll('.ag-cell');
                                const rowData = {};
                                cells.forEach(cell => {
                                    const colId = cell.getAttribute('col-id');
                                    if (colId) {
                                        rowData[colId] = cell.innerText?.trim() || '';
                                    }
                                });
                                if (Object.keys(rowData).length > 0 && rowData.Rating) {
                                    // Use composite key for deduplication
                                    const key = (rowData.DateCreated || '') + '|' + (rowData.FkCustomer_FirstName || '') + '|' + (rowData.Body || '').substring(0, 50);
                                    if (!allRows.has(key)) {
                                        allRows.set(key, rowData);
                                    }
                                }
                            });
                        }
                        
                        // Check for pagination controls
                        const paginationPanel = document.querySelector('.ag-paging-panel');
                        
                        if (paginationPanel) {
                            // PAGINATION MODE - click through all pages
                            console.log('[CV Feedback] Using pagination mode');
                            let prevCount = 0;
                            let sameCountLoops = 0;
                            const maxPages = 100;  // Support up to 100 pages
                            
                            for (let pageNum = 0; pageNum < maxPages; pageNum++) {
                                // Collect rows on current page
                                collectRows();
                                console.log('[CV Feedback] Page ' + (pageNum + 1) + ': collected ' + allRows.size + ' total rows');
                                
                                // Check if we've stopped finding new rows
                                if (allRows.size === prevCount) {
                                    sameCountLoops++;
                                    if (sameCountLoops >= 2) {
                                        console.log('[CV Feedback] No new rows found, stopping pagination');
                                        break;
                                    }
                                } else {
                                    sameCountLoops = 0;
                                    prevCount = allRows.size;
                                }
                                
                                // Try to click next button
                                const nextBtn = document.querySelector('[ref="btNext"]:not([disabled]), .ag-paging-button[ref="btNext"]:not([disabled])');
                                if (nextBtn && !nextBtn.disabled && nextBtn.getAttribute('aria-disabled') !== 'true') {
                                    nextBtn.click();
                                    await new Promise(r => setTimeout(r, 1500));  // Wait for page to load
                                } else {
                                    console.log('[CV Feedback] No more pages (next button disabled)');
                                    break;
                                }
                            }
                        } else {
                            // SCROLL MODE - for virtual scrolling grids
                            console.log('[CV Feedback] Using scroll mode');
                            gridBody.scrollTop = 0;
                            await new Promise(r => setTimeout(r, 1000));
                            
                            const viewportHeight = gridBody.clientHeight;
                            const totalHeight = gridBody.scrollHeight;
                            const scrollIterations = Math.ceil(totalHeight / (viewportHeight * 0.2)) + 50;
                            
                            collectRows();
                            
                            for (let i = 0; i < scrollIterations; i++) {
                                gridBody.scrollTop += viewportHeight * 0.2;
                                await new Promise(r => setTimeout(r, 400));
                                collectRows();
                            }
                            
                            // Final passes
                            gridBody.scrollTop = gridBody.scrollHeight;
                            await new Promise(r => setTimeout(r, 1000));
                            collectRows();
                            
                            gridBody.scrollTop = 0;
                            await new Promise(r => setTimeout(r, 500));
                            collectRows();
                        }
                        
                        console.log('[CV Feedback] Total rows collected: ' + allRows.size);
                        return Array.from(allRows.values());
                    }""")
                
                # Process and structure feedback
                for item in feedback_data:
                    rating = parse_rating(item.get("Rating", ""))
                    sentiment, points = get_sentiment_and_points(rating)
                    
                    # Get customer name and look up their server
                    customer_name = item.get("FkCustomer_FirstName", "")
                    customer_key = customer_name.strip().lower() if customer_name else ""
                    
                    # Look up the server who served this customer
                    server_name = customer_to_server.get(customer_key, "")
                    
                    feedback = {
                        "rating": rating,
                        "rating_str": item.get("Rating", ""),
                        "customer_name": customer_name,
                        "date": item.get("DateCreated", ""),
                        "date_of_business": item.get("DateOfBusiness", ""),
                        "shift": item.get("FkTransactionSummary_Shift_Name", ""),
                        "comment": item.get("Body", ""),
                        "store": item.get("FkTransactionSummary_FkLocation_Name", ""),
                        "can_contact": item.get("FkCustomer_CanContact", ""),
                        "sentiment": sentiment,
                        "cv_points": points,
                        "source": "loyalty_voice",
                        "server_name": server_name  # Server who served this customer
                    }
                    result["feedback"].append(feedback)
                
                # Log stats
                with_server = sum(1 for f in result["feedback"] if f.get("server_name"))
                print(f"[CV] Scraped {len(result['feedback'])} feedback items, {with_server} with server assignments")
                result["success"] = True
                
            except Exception as e:
                print(f"[CV] Session 2 error: {e}")
                result["error"] = str(e)
            finally:
                await browser.close()
                
    except Exception as e:
        print(f"[CV] Session 2 browser error: {e}")
        result["error"] = str(e)
    
    return result


def detect_employee_in_comment(comment: str, employee_names: List[str]) -> List[Dict]:
    """
    Detect employee mentions in a comment.
    Returns list of detected employees.
    """
    if not comment:
        return []
    
    comment_lower = comment.lower()
    detected = []
    
    for name in employee_names:
        name_lower = name.lower()
        # Check for full name
        if name_lower in comment_lower:
            detected.append({"name": name, "match_type": "full"})
        else:
            # Check for first name
            first_name = name_lower.split()[0] if name_lower else ""
            if first_name and len(first_name) > 2 and first_name in comment_lower:
                # Verify it's a word boundary match
                pattern = r'\b' + re.escape(first_name) + r'\b'
                if re.search(pattern, comment_lower):
                    detected.append({"name": name, "match_type": "first_name"})
    
    return detected


async def sync_cv_feedback_to_db(
    db,
    quarter: str,
    year: int,
    use_ai_detection: bool = True
) -> Dict[str, Any]:
    """
    Sync CV feedback from Loyalty Voice to the database.
    
    1. CLEARS existing cv_feedback and cv_points data for this quarter
    2. Scrapes feedback from Loyalty Voice (Transactions page for server mapping, Feedback page for reviews)
    3. Stores feedback in cv_feedback collection
    4. Calculates and stores CV points per employee
    """
    import uuid
    
    result = {
        "success": False,
        "new_count": 0,
        "skipped_count": 0,
        "error": None,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "cleared_feedback_count": 0,
        "cleared_points_count": 0
    }
    
    # Scrape feedback
    scrape_result = await scrape_cv_feedback(quarter, year)
    
    if not scrape_result.get("success"):
        result["error"] = scrape_result.get("error", "Scraping failed")
        return result
    
    feedback_items = scrape_result.get("feedback", [])
    
    if not feedback_items:
        result["error"] = "No feedback found for this period"
        return result
    
    # CRITICAL: Clear ALL existing cv_feedback and cv_points records for this quarter
    # This prevents data duplication and ensures counts are accurate
    feedback_delete = await db.cv_feedback.delete_many({
        "quarter": quarter.upper(),
        "year": year
    })
    result["cleared_feedback_count"] = feedback_delete.deleted_count
    
    points_delete = await db.cv_points.delete_many({
        "quarter": quarter.upper(),
        "year": year
    })
    result["cleared_points_count"] = points_delete.deleted_count
    
    print(f"[CV] Cleared {feedback_delete.deleted_count} feedback + {points_delete.deleted_count} points records for {quarter} {year}")
    
    # Get employee names for matching
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(500)
    
    employee_names = [e["name"] for e in employees]
    employee_lookup = {e["name"].lower(): e for e in employees}
    
    # Process each feedback item
    new_count = 0
    skipped_count = 0
    
    for item in feedback_items:
        # Since we cleared all existing data, no need to check for duplicates
        
        # CV Credit: Server who served the table gets the points (no comment mention bonus)
        comment = item.get("comment", "")
        server_name = item.get("server_name", "")
        
        # Build mentions list - ONLY from server assignment for CV
        mentions = []
        
        # Server who served the table (from Transactions page)
        if server_name:
            server_lower = server_name.lower()
            matched = False
            
            # Try exact match first
            if server_lower in employee_lookup:
                emp_data = employee_lookup[server_lower]
                mentions.append({
                    "employee_id": emp_data["id"],
                    "employee_name": emp_data["name"],
                    "match_type": "server_assignment",
                    "cv_points": item["cv_points"]
                })
                matched = True
            
            # Try partial match (first name or last name)
            if not matched:
                for emp_name_lower, emp_data in employee_lookup.items():
                    emp_parts = emp_name_lower.split()
                    server_parts = server_lower.split()
                    # Match if first names match or last names match
                    if (emp_parts and server_parts and 
                        (emp_parts[0] == server_parts[0] or 
                         (len(emp_parts) > 1 and len(server_parts) > 1 and emp_parts[-1] == server_parts[-1]))):
                        mentions.append({
                            "employee_id": emp_data["id"],
                            "employee_name": emp_data["name"],
                            "match_type": "server_assignment_partial",
                            "cv_points": item["cv_points"]
                        })
                        break
        
        # NOTE: For CV, we do NOT check comment mentions - only server assignment matters
        # Comment mentions are for External Reviews (Google, Yelp, etc.) only
        
        # Store feedback
        feedback_doc = {
            "id": str(uuid.uuid4()),
            "rating": item["rating"],
            "rating_str": item["rating_str"],
            "customer_name": item["customer_name"],
            "server_name": server_name,  # Server who served this table
            "date": item["date"],
            "date_of_business": item["date_of_business"],
            "shift": item["shift"],
            "comment": comment,
            "store": item["store"],
            "sentiment": item["sentiment"],
            "cv_points": item["cv_points"],
            "mentions": mentions,
            "quarter": quarter.upper(),
            "year": year,
            "source": "loyalty_voice",
            "synced_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.cv_feedback.insert_one(feedback_doc)
        new_count += 1
    
    # Calculate total CV points per employee
    pipeline = [
        {"$match": {"quarter": quarter.upper(), "year": year}},
        {"$unwind": "$mentions"},
        {"$group": {
            "_id": "$mentions.employee_id",
            "employee_name": {"$first": "$mentions.employee_name"},
            "total_cv_points": {"$sum": "$mentions.cv_points"},
            "mention_count": {"$sum": 1},
            "promoter_count": {"$sum": {"$cond": [{"$eq": ["$sentiment", "promoter"]}, 1, 0]}},
            "passive_count": {"$sum": {"$cond": [{"$eq": ["$sentiment", "passive"]}, 1, 0]}},
            "detractor_count": {"$sum": {"$cond": [{"$eq": ["$sentiment", "detractor"]}, 1, 0]}}
        }}
    ]
    
    cv_stats = await db.cv_feedback.aggregate(pipeline).to_list(500)
    
    # Store CV points summary per employee
    for stat in cv_stats:
        await db.cv_points.update_one(
            {
                "employee_id": stat["_id"],
                "quarter": quarter.upper(),
                "year": year
            },
            {"$set": {
                "employee_id": stat["_id"],
                "employee_name": stat["employee_name"],
                "total_cv_points": stat["total_cv_points"],
                "mention_count": stat["mention_count"],
                "promoter_count": stat["promoter_count"],
                "passive_count": stat["passive_count"],
                "detractor_count": stat["detractor_count"],
                "quarter": quarter.upper(),
                "year": year,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
    
    result["success"] = True
    result["new_count"] = new_count
    result["skipped_count"] = skipped_count
    result["total_scraped"] = len(feedback_items)
    result["employees_with_mentions"] = len(cv_stats)
    
    print(f"[CV] Sync complete: {new_count} new, {skipped_count} skipped")
    
    return result
