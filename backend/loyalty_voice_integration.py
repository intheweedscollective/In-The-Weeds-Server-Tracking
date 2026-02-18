"""
Loyalty Voice Integration - Automated web scraping for Customer Voice data
"""
import os
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

# Loyalty Voice credentials
LV_URL = "https://landrys.loyalty-voice.com"
LV_USERNAME = os.environ.get("LOYALTY_VOICE_USERNAME", "Bglv@ldry.com")
LV_PASSWORD = os.environ.get("LOYALTY_VOICE_PASSWORD", "EZMoney2026")

# Scoring rules
POSITIVE_RATING_MIN = 9  # 9/10 or 10/10 = positive
NEGATIVE_RATING_MAX = 6  # 6/10 or below = negative
POSITIVE_POINTS = 1.0
NEGATIVE_POINTS = -2.0


async def scrape_loyalty_voice_feedback(
    start_date: str = None,
    end_date: str = None
) -> Dict[str, Any]:
    """
    Scrape feedback data from Loyalty Voice.
    
    Returns:
        Dict with feedback items and metadata
    """
    feedback_items = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Navigate to login
            await page.goto(LV_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Login flow - Microsoft SSO
            email_input = page.locator('input[type="email"]')
            if await email_input.is_visible(timeout=5000):
                await email_input.fill(LV_USERNAME)
                await page.locator('input[type="submit"]').click()
                await page.wait_for_timeout(3000)
                
                password_input = page.locator('input[type="password"]')
                if await password_input.is_visible(timeout=5000):
                    await password_input.fill(LV_PASSWORD)
                    await page.locator('input[type="submit"]').click()
                    await page.wait_for_timeout(5000)
                    
                    # Handle "Stay signed in" prompt
                    yes_btn = page.locator('input[value="Yes"]')
                    if await yes_btn.is_visible(timeout=3000):
                        await yes_btn.click()
                        await page.wait_for_timeout(3000)
            
            # Navigate to feedback page
            await page.goto(f"{LV_URL}/feedback", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)
            
            # The page uses role="row" for data rows
            rows = await page.locator('[role="row"]').all()
            
            for row in rows:
                try:
                    # Get the text content of the row
                    row_text = await row.inner_text()
                    
                    # Skip header rows
                    if "Customer Name" in row_text or "Response Date" in row_text:
                        continue
                    
                    # Skip rows without rating
                    if "/ 10" not in row_text:
                        continue
                    
                    # Parse the row text - it follows the pattern:
                    # [icon] Rating \n Customer Name \n Date \n Shift \n Comment \n Store \n Date \n Yes/No
                    lines = [l.strip() for l in row_text.split('\n') if l.strip()]
                    
                    # Find rating line (contains "/ 10")
                    rating_idx = -1
                    for i, line in enumerate(lines):
                        if "/ 10" in line:
                            rating_idx = i
                            break
                    
                    if rating_idx == -1:
                        continue
                    
                    rating_text = lines[rating_idx]
                    rating = parse_rating(rating_text)
                    
                    # Extract other fields relative to rating position
                    item = {
                        "rating": rating,
                        "rating_text": rating_text,
                        "customer_name": lines[rating_idx + 1] if rating_idx + 1 < len(lines) else "",
                        "response_date": lines[rating_idx + 2] if rating_idx + 2 < len(lines) else "",
                        "shift": lines[rating_idx + 3] if rating_idx + 3 < len(lines) else "",
                        "comment": lines[rating_idx + 4] if rating_idx + 4 < len(lines) else "",
                        "store": lines[rating_idx + 5] if rating_idx + 5 < len(lines) else "",
                        "source": "loyalty_voice"
                    }
                    
                    # Validate - must have a customer name and store should reference Bubba Gump
                    if item["customer_name"] and len(item["customer_name"]) > 1:
                        feedback_items.append(item)
                        
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue
            
        except Exception as e:
            print(f"Scraping error: {e}")
            return {"success": False, "error": str(e), "feedback": []}
        finally:
            await browser.close()
    
    return {
        "success": True,
        "feedback": feedback_items,
        "total": len(feedback_items),
        "scraped_at": datetime.now(timezone.utc).isoformat()
    }


def parse_rating(rating_text: str) -> int:
    """Parse rating from text like '10 / 10' or '▲ 10 / 10'."""
    try:
        # Remove icons and extra characters
        clean = rating_text.replace("▲", "").replace("▼", "").strip()
        # Extract first number
        parts = clean.split("/")
        if parts:
            return int(parts[0].strip())
    except:
        pass
    return 0


def calculate_cv_points(rating: int) -> float:
    """Calculate CV points based on rating."""
    if rating >= POSITIVE_RATING_MIN:
        return POSITIVE_POINTS
    elif rating <= NEGATIVE_RATING_MAX:
        return NEGATIVE_POINTS
    else:
        return 0.0  # Neutral (7-8)


async def detect_server_in_comment(
    comment: str,
    employee_names: List[str]
) -> List[Dict[str, Any]]:
    """
    Use AI to detect server names mentioned in feedback comments.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key or not comment.strip():
        return simple_server_match(comment, employee_names)
    
    names_list = ", ".join(employee_names)
    prompt = f"""Analyze this customer feedback comment and identify any employee/server names mentioned.

Employee roster: {names_list}

Feedback comment:
"{comment}"

For each employee mentioned, respond in this exact JSON format (no markdown):
{{"servers": ["Server Name 1", "Server Name 2"]}}

If no employees are mentioned, respond: {{"servers": []}}

Only include names that clearly match someone from the employee roster. Be flexible with partial matches (e.g., "Dan" could match "Daniel")."""

    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"cv-analysis-{datetime.now().timestamp()}",
            system_message="You are a feedback analyzer. Extract server/employee names mentioned. Respond only with valid JSON."
        ).with_model("openai", "gpt-4.1-mini")
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Parse JSON response
        import json
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        data = json.loads(response_text)
        servers = data.get("servers", [])
        
        return [{"name": name, "matched": True} for name in servers]
        
    except Exception as e:
        print(f"AI detection error: {e}")
        return simple_server_match(comment, employee_names)


def simple_server_match(comment: str, employee_names: List[str]) -> List[Dict[str, Any]]:
    """Simple fallback name matching without AI."""
    comment_lower = comment.lower()
    matches = []
    
    for name in employee_names:
        name_parts = name.lower().split()
        first_name = name_parts[0] if name_parts else ""
        
        if name.lower() in comment_lower or (first_name and len(first_name) > 2 and first_name in comment_lower):
            matches.append({"name": name, "matched": True})
    
    return matches


async def sync_loyalty_voice_to_db(
    db,
    quarter: str,
    year: int,
    detect_employees_func=None
) -> Dict[str, Any]:
    """
    Sync Loyalty Voice feedback to database and calculate CV points.
    """
    import uuid
    import hashlib
    
    # Scrape feedback
    scrape_result = await scrape_loyalty_voice_feedback()
    
    if not scrape_result.get("success"):
        return {
            "success": False,
            "error": scrape_result.get("error", "Scraping failed"),
            "new_count": 0
        }
    
    feedback_items = scrape_result.get("feedback", [])
    
    # Get employee names
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"name": 1, "_id": 0}
    ).to_list(500)
    employee_names = [e["name"] for e in employees]
    
    results = {
        "success": True,
        "new_count": 0,
        "skipped_count": 0,
        "total_scraped": len(feedback_items),
        "errors": []
    }
    
    for item in feedback_items:
        try:
            # Generate hash for duplicate detection
            content = f"{item['response_date']}|{item['customer_name']}|{item['rating']}"
            item_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            
            # Check for duplicate
            existing = await db.cv_feedback.find_one({"feedback_hash": item_hash})
            if existing:
                results["skipped_count"] += 1
                continue
            
            # Detect servers mentioned in comment
            servers_mentioned = []
            if detect_employees_func and item.get("comment"):
                servers_mentioned = await detect_employees_func(
                    item["comment"],
                    employee_names
                )
            
            # Calculate points
            rating = item.get("rating", 0)
            points = calculate_cv_points(rating)
            
            # Determine sentiment
            if rating >= POSITIVE_RATING_MIN:
                sentiment = "positive"
            elif rating <= NEGATIVE_RATING_MAX:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            
            # Create feedback document
            feedback_doc = {
                "id": str(uuid.uuid4()),
                "feedback_hash": item_hash,
                "rating": rating,
                "rating_text": item.get("rating_text", ""),
                "customer_name": item.get("customer_name", ""),
                "response_date": item.get("response_date", ""),
                "shift": item.get("shift", ""),
                "comment": item.get("comment", ""),
                "store": item.get("store", ""),
                "servers_mentioned": servers_mentioned,
                "points": points,
                "sentiment": sentiment,
                "quarter": quarter.upper(),
                "year": year,
                "source": "loyalty_voice",
                "synced_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.cv_feedback.insert_one(feedback_doc)
            results["new_count"] += 1
            
        except Exception as e:
            results["errors"].append(str(e))
    
    return results


def get_cv_points_for_employee(cv_feedback: List[Dict], employee_name: str) -> Dict[str, Any]:
    """Calculate total CV points for an employee from feedback."""
    total_points = 0.0
    mentions = []
    
    for feedback in cv_feedback:
        for server in feedback.get("servers_mentioned", []):
            if server.get("name", "").lower() == employee_name.lower():
                points = feedback.get("points", 0)
                total_points += points
                mentions.append({
                    "rating": feedback.get("rating"),
                    "points": points,
                    "sentiment": feedback.get("sentiment"),
                    "date": feedback.get("response_date"),
                    "comment_preview": feedback.get("comment", "")[:50]
                })
    
    return {
        "employee_name": employee_name,
        "total_cv_points": round(total_points, 2),
        "mention_count": len(mentions),
        "positive_count": len([m for m in mentions if m["sentiment"] == "positive"]),
        "negative_count": len([m for m in mentions if m["sentiment"] == "negative"]),
        "mentions": mentions
    }
