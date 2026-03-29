"""
Review Tracker Module - AI-powered review aggregation and employee attribution
"""
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()

# Platforms supported
PLATFORMS = ["Google", "Yelp", "Facebook", "TripAdvisor", "OpenTable"]

# Points configuration
POINTS_PER_POSITIVE_MENTION = 0.5


def generate_review_hash(review_text: str, platform: str, date: str) -> str:
    """Generate a hash for duplicate detection based on review content."""
    content = f"{platform}|{date}|{review_text.strip().lower()}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


async def detect_employees_in_review(
    review_text: str,
    employee_names: List[str]
) -> List[Dict[str, Any]]:
    """
    Use AI to detect employee mentions in review text and determine sentiment.
    Returns list of {name, sentiment, points}
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        # Fallback to simple name matching if no API key
        return simple_name_match(review_text, employee_names)
    
    # Build the prompt
    names_list = ", ".join(employee_names)
    prompt = f"""Analyze this customer review and identify any employee names mentioned.

Employee roster: {names_list}

Review text:
"{review_text}"

For each employee mentioned, determine if the mention is POSITIVE, NEGATIVE, or NEUTRAL based on context.

Respond in this exact JSON format (no markdown, just raw JSON):
{{"mentions": [{{"name": "Employee Name", "sentiment": "positive"}}, ...]}}

If no employees are mentioned, respond: {{"mentions": []}}

Only include names that clearly match someone from the employee roster. Be flexible with nicknames or partial matches (e.g., "Terry" could match "Terrance")."""

    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"review-analysis-{datetime.now().timestamp()}",
            system_message="You are a review analyzer. Extract employee mentions and sentiment. Respond only with valid JSON."
        ).with_model("openai", "gpt-4.1-mini")
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Parse the JSON response
        import json
        # Clean up response if it has markdown code blocks
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        data = json.loads(response_text)
        mentions = data.get("mentions", [])
        
        # Add points based on sentiment
        result = []
        for mention in mentions:
            name = mention.get("name", "")
            sentiment = mention.get("sentiment", "neutral").lower()
            # Only positive mentions get points
            points = POINTS_PER_POSITIVE_MENTION if sentiment == "positive" else 0.0
            result.append({
                "name": name,
                "sentiment": sentiment,
                "points": points
            })
        
        return result
        
    except Exception as e:
        print(f"AI detection error: {e}")
        # Fallback to simple matching
        return simple_name_match(review_text, employee_names)


def simple_name_match(review_text: str, employee_names: List[str]) -> List[Dict[str, Any]]:
    """Simple fallback name matching without AI."""
    review_lower = review_text.lower()
    mentions = []
    
    for name in employee_names:
        # Check for full name or first name
        name_parts = name.lower().split()
        first_name = name_parts[0] if name_parts else ""
        
        if name.lower() in review_lower or (first_name and len(first_name) > 2 and first_name in review_lower):
            # Default to positive sentiment for simple matching
            mentions.append({
                "name": name,
                "sentiment": "positive",
                "points": POINTS_PER_POSITIVE_MENTION
            })
    
    return mentions


def calculate_review_points_for_employee(reviews: List[Dict], employee_name: str) -> float:
    """Calculate total review points for a specific employee."""
    total_points = 0.0
    
    for review in reviews:
        for mention in review.get("employee_mentions", []):
            if mention.get("name", "").lower() == employee_name.lower():
                total_points += mention.get("points", 0.0)
    
    return round(total_points, 2)


def get_review_stats(reviews: List[Dict], employee_names: List[str]) -> Dict[str, Any]:
    """Get aggregated review statistics."""
    stats = {
        "total_reviews": len(reviews),
        "by_platform": {},
        "by_employee": {},
        "recent_reviews": []
    }
    
    # Initialize platform counts
    for platform in PLATFORMS:
        stats["by_platform"][platform] = 0
    
    # Initialize employee stats
    for name in employee_names:
        stats["by_employee"][name] = {
            "mentions": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "points": 0.0
        }
    
    # Build a mapping of partial names to full names for matching
    name_mapping = {}
    for full_name in employee_names:
        # Map full name
        name_mapping[full_name.lower()] = full_name
        # Map first name
        parts = full_name.split()
        if parts:
            name_mapping[parts[0].lower()] = full_name
            # Also map common nicknames/short forms
            first_name = parts[0].lower()
            # Handle nicknames like "Trey" for "Treyanna", "TK" for "Thomas Kozan"
            if len(first_name) > 4:
                name_mapping[first_name[:4]] = full_name  # First 4 chars
                name_mapping[first_name[:3]] = full_name  # First 3 chars
    
    # Process reviews
    for review in reviews:
        platform = review.get("platform", "")
        if platform in stats["by_platform"]:
            stats["by_platform"][platform] += 1
        
        for mention in review.get("employee_mentions", []):
            emp_name = mention.get("name", "")
            sentiment = mention.get("sentiment", "neutral")
            points = mention.get("points", 0.0)
            
            # Try to match the mentioned name to a full employee name
            matched_name = None
            emp_lower = emp_name.lower()
            
            # Direct match
            if emp_lower in name_mapping:
                matched_name = name_mapping[emp_lower]
            else:
                # Try partial matching - check if mentioned name is start of any employee's first name
                for full_name in employee_names:
                    first_name = full_name.split()[0].lower() if full_name.split() else ""
                    if first_name.startswith(emp_lower) or emp_lower.startswith(first_name[:3]):
                        matched_name = full_name
                        break
            
            if matched_name and matched_name in stats["by_employee"]:
                stats["by_employee"][matched_name]["mentions"] += 1
                stats["by_employee"][matched_name][sentiment] += 1
                stats["by_employee"][matched_name]["points"] += points
    
    # Round points
    for name in stats["by_employee"]:
        stats["by_employee"][name]["points"] = round(stats["by_employee"][name]["points"], 2)
    
    # Get 5 most recent reviews
    sorted_reviews = sorted(reviews, key=lambda x: x.get("review_date", ""), reverse=True)
    stats["recent_reviews"] = sorted_reviews[:5]
    
    return stats
