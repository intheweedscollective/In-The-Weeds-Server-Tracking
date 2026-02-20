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
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        try:
            # Login
            if not await login_to_loyalty_voice(page):
                result["error"] = "Login failed"
                return result
            
            # Navigate to Feedback page
            await page.goto(f"{LV_URL}/Feedback", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Set date filter
            date_filter = page.locator('#date-filter').first
            if await date_filter.is_visible(timeout=5000):
                await date_filter.click()
                await page.wait_for_timeout(1500)
                
                # Use Custom Range for specific quarter
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
            
            # Extract data via JavaScript (ag-grid)
            feedback_data = await page.evaluate("""() => {
                // Try to get all data by scrolling through virtual grid
                const gridBody = document.querySelector('.ag-body-viewport');
                if (gridBody) {
                    // Scroll to load all rows
                    gridBody.scrollTop = 0;
                }
                
                // Collect visible row data
                const rows = [];
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
                        rows.push(rowData);
                    }
                });
                return rows;
            }""")
            
            # Process and structure feedback
            for item in feedback_data:
                rating = parse_rating(item.get("Rating", ""))
                sentiment, points = get_sentiment_and_points(rating)
                
                feedback = {
                    "rating": rating,
                    "rating_str": item.get("Rating", ""),
                    "customer_name": item.get("FkCustomer_FirstName", ""),
                    "date": item.get("DateCreated", ""),
                    "date_of_business": item.get("DateOfBusiness", ""),
                    "shift": item.get("FkTransactionSummary_Shift_Name", ""),
                    "comment": item.get("Body", ""),
                    "store": item.get("FkTransactionSummary_FkLocation_Name", ""),
                    "can_contact": item.get("FkCustomer_CanContact", ""),
                    "sentiment": sentiment,
                    "cv_points": points,
                    "source": "loyalty_voice"
                }
                result["feedback"].append(feedback)
            
            # Try to get more data by scrolling
            if len(result["feedback"]) < 100:
                more_data = await page.evaluate("""async () => {
                    const gridBody = document.querySelector('.ag-body-viewport');
                    const rows = [];
                    
                    if (gridBody) {
                        // Scroll down to load more
                        for (let i = 0; i < 10; i++) {
                            gridBody.scrollTop += 500;
                            await new Promise(r => setTimeout(r, 300));
                        }
                        
                        // Collect all rows again
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
                                rows.push(rowData);
                            }
                        });
                    }
                    return rows;
                }""")
                
                # Add new items not already in list
                existing_dates = {f.get("date") + f.get("customer_name", "") for f in result["feedback"]}
                for item in more_data:
                    key = item.get("DateCreated", "") + item.get("FkCustomer_FirstName", "")
                    if key not in existing_dates:
                        rating = parse_rating(item.get("Rating", ""))
                        sentiment, points = get_sentiment_and_points(rating)
                        
                        feedback = {
                            "rating": rating,
                            "rating_str": item.get("Rating", ""),
                            "customer_name": item.get("FkCustomer_FirstName", ""),
                            "date": item.get("DateCreated", ""),
                            "date_of_business": item.get("DateOfBusiness", ""),
                            "shift": item.get("FkTransactionSummary_Shift_Name", ""),
                            "comment": item.get("Body", ""),
                            "store": item.get("FkTransactionSummary_FkLocation_Name", ""),
                            "can_contact": item.get("FkCustomer_CanContact", ""),
                            "sentiment": sentiment,
                            "cv_points": points,
                            "source": "loyalty_voice"
                        }
                        result["feedback"].append(feedback)
                        existing_dates.add(key)
            
            result["success"] = True
            result["total_count"] = len(result["feedback"])
            print(f"[CV] Scraped {len(result['feedback'])} feedback items")
            
        except Exception as e:
            print(f"[CV] Error: {e}")
            result["error"] = str(e)
        finally:
            await browser.close()
    
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
    
    1. Scrapes feedback from Loyalty Voice
    2. Detects employee mentions (using AI or simple matching)
    3. Stores feedback in cv_feedback collection
    4. Calculates and stores CV points per employee
    """
    import uuid
    
    result = {
        "success": False,
        "new_count": 0,
        "skipped_count": 0,
        "error": None,
        "synced_at": datetime.now(timezone.utc).isoformat()
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
        # Check if already exists
        existing = await db.cv_feedback.find_one({
            "date": item["date"],
            "customer_name": item["customer_name"],
            "quarter": quarter.upper(),
            "year": year
        })
        
        if existing:
            skipped_count += 1
            continue
        
        # Detect employee mentions
        comment = item.get("comment", "")
        detected_employees = detect_employee_in_comment(comment, employee_names)
        
        # Build mentions list
        mentions = []
        for emp in detected_employees:
            emp_name = emp["name"]
            emp_lower = emp_name.lower()
            if emp_lower in employee_lookup:
                emp_data = employee_lookup[emp_lower]
                mentions.append({
                    "employee_id": emp_data["id"],
                    "employee_name": emp_data["name"],
                    "match_type": emp["match_type"],
                    "cv_points": item["cv_points"]
                })
        
        # Store feedback
        feedback_doc = {
            "id": str(uuid.uuid4()),
            "rating": item["rating"],
            "rating_str": item["rating_str"],
            "customer_name": item["customer_name"],
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
