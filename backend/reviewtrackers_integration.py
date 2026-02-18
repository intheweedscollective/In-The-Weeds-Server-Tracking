"""
ReviewTrackers API Integration - Automatic review sync
"""
import os
import base64
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# ReviewTrackers API endpoints
RT_AUTH_URL = "https://api.reviewtrackers.com/auth"
RT_REVIEWS_URL = "https://api.reviewtrackers.com/reviews"
RT_LOCATIONS_URL = "https://api.reviewtrackers.com/locations"
RT_GROUPS_URL = "https://api.reviewtrackers.com/groups"

# Platform mapping from ReviewTrackers source names to our platform names
SOURCE_TO_PLATFORM = {
    "google": "Google",
    "google_play": "Google",
    "yelp": "Yelp",
    "facebook": "Facebook",
    "tripadvisor": "TripAdvisor",
    "opentable": "OpenTable",
    "foursquare": "Yelp",  # Map to closest
    "yellowpages": "Google",  # Map to closest
    "bbb": "Google",
    "citysearch": "Google",
}


class ReviewTrackersClient:
    """Client for ReviewTrackers API integration."""
    
    def __init__(self):
        self.username = os.environ.get("REVIEWTRACKERS_USERNAME")
        self.password = os.environ.get("REVIEWTRACKERS_PASSWORD")
        self.auth_token = None
        self.account_id = None
        
    async def authenticate(self) -> bool:
        """Authenticate with ReviewTrackers API and get token."""
        if not self.username or not self.password:
            raise ValueError("ReviewTrackers credentials not configured")
        
        # Create Basic Auth header
        credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        
        headers = {
            "accept": "application/vnd.rtx.authorization.v2.hal+json;charset=utf-8",
            "authorization": f"Basic {credentials}",
            "content-type": "application/vnd.rtx.auth.v2.hal+json;charset=utf-8"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(RT_AUTH_URL, headers=headers, timeout=30.0)
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.auth_token = data.get("token")
                self.account_id = data.get("account_id")
                return True
            else:
                print(f"Auth failed: {response.status_code} - {response.text}")
                return False
    
    async def _make_request(self, url: str, params: Dict = None) -> Optional[Dict]:
        """Make authenticated request to ReviewTrackers API."""
        if not self.auth_token:
            await self.authenticate()
        
        headers = {
            "accept": "application/json",
        }
        
        # Use token auth
        auth = (self.username, self.auth_token)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, 
                headers=headers, 
                auth=auth,
                params=params,
                timeout=60.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Request failed: {response.status_code} - {response.text}")
                return None
    
    async def get_locations(self) -> List[Dict]:
        """Get all locations from ReviewTrackers."""
        data = await self._make_request(RT_LOCATIONS_URL)
        if data and "_embedded" in data:
            return data["_embedded"].get("locations", [])
        return []
    
    async def get_reviews(
        self, 
        per_page: int = 100,
        page: int = 1,
        location_id: Optional[int] = None,
        since_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get reviews from ReviewTrackers.
        
        Args:
            per_page: Number of reviews per page (max 500)
            page: Page number
            location_id: Filter by specific location
            since_date: Only get reviews after this date (YYYY-MM-DD)
        """
        params = {
            "account_id": self.account_id,
            "per_page": min(per_page, 500),
            "page": page
        }
        
        if location_id:
            params["location_id"] = location_id
            
        if since_date:
            params["published_at_gte"] = since_date
        
        data = await self._make_request(RT_REVIEWS_URL, params)
        
        if data:
            reviews = data.get("_embedded", {}).get("reviews", [])
            total = data.get("total", len(reviews))
            return {
                "reviews": reviews,
                "total": total,
                "page": page,
                "per_page": per_page
            }
        
        return {"reviews": [], "total": 0, "page": page, "per_page": per_page}
    
    async def get_all_reviews(self, since_date: Optional[str] = None) -> List[Dict]:
        """Get all reviews, handling pagination."""
        all_reviews = []
        page = 1
        per_page = 500
        
        while True:
            result = await self.get_reviews(
                per_page=per_page, 
                page=page,
                since_date=since_date
            )
            
            reviews = result.get("reviews", [])
            all_reviews.extend(reviews)
            
            # Check if we've got all reviews
            if len(reviews) < per_page:
                break
                
            page += 1
            
            # Safety limit
            if page > 100:
                break
        
        return all_reviews


def transform_rt_review(rt_review: Dict) -> Dict[str, Any]:
    """Transform ReviewTrackers review to our format."""
    # Map source to our platform names
    source = rt_review.get("source", "").lower()
    platform = SOURCE_TO_PLATFORM.get(source, "Google")  # Default to Google
    
    # Parse the published date
    published_at = rt_review.get("published_at", "")
    if published_at:
        # Format: "2026-02-15T10:30:00Z" -> "2026-02-15"
        review_date = published_at.split("T")[0] if "T" in published_at else published_at
    else:
        review_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Get rating (ReviewTrackers uses 1-5 scale)
    rating = rt_review.get("rating", 5)
    if rating is None:
        rating = 5
    
    return {
        "rt_id": str(rt_review.get("id", "")),
        "platform": platform,
        "review_date": review_date,
        "rating": int(rating),
        "review_text": rt_review.get("content", "") or "",
        "reviewer_name": rt_review.get("author", ""),
        "source_url": rt_review.get("url", ""),
        "location_id": rt_review.get("location_id"),
        "location_name": rt_review.get("location_name", ""),
        "published_at": published_at,
        "rt_source": source
    }


async def sync_reviews_from_reviewtrackers(
    db,
    quarter: str,
    year: int,
    since_date: Optional[str] = None,
    detect_employees_func = None
) -> Dict[str, Any]:
    """
    Sync reviews from ReviewTrackers to our database.
    
    Returns:
        Dict with sync results (new_count, updated_count, skipped_count, errors)
    """
    from review_tracker import generate_review_hash, POINTS_PER_POSITIVE_MENTION
    import uuid
    
    client = ReviewTrackersClient()
    
    # Authenticate
    auth_success = await client.authenticate()
    if not auth_success:
        return {
            "success": False,
            "error": "Failed to authenticate with ReviewTrackers",
            "new_count": 0,
            "updated_count": 0,
            "skipped_count": 0
        }
    
    # Get reviews
    rt_reviews = await client.get_all_reviews(since_date=since_date)
    
    # Get employee names for detection
    employees = await db.employees_v2.find(
        {"quarter": quarter.upper(), "year": year},
        {"name": 1, "_id": 0}
    ).to_list(500)
    employee_names = [e["name"] for e in employees]
    
    results = {
        "success": True,
        "new_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "total_fetched": len(rt_reviews),
        "errors": []
    }
    
    for rt_review in rt_reviews:
        try:
            # Transform to our format
            review_data = transform_rt_review(rt_review)
            
            # Skip if no review text
            if not review_data["review_text"].strip():
                results["skipped_count"] += 1
                continue
            
            # Generate hash for duplicate detection
            review_hash = generate_review_hash(
                review_data["review_text"],
                review_data["platform"],
                review_data["review_date"]
            )
            
            # Check if already exists
            existing = await db.customer_reviews.find_one({"review_hash": review_hash})
            
            if existing:
                results["skipped_count"] += 1
                continue
            
            # Detect employees
            employee_mentions = []
            if detect_employees_func and employee_names:
                employee_mentions = await detect_employees_func(
                    review_data["review_text"],
                    employee_names
                )
            
            # Calculate total points
            total_points = sum(m.get("points", 0) for m in employee_mentions)
            
            # Create review document
            review_doc = {
                "id": str(uuid.uuid4()),
                "rt_id": review_data["rt_id"],
                "platform": review_data["platform"],
                "review_date": review_data["review_date"],
                "rating": review_data["rating"],
                "review_text": review_data["review_text"],
                "reviewer_name": review_data["reviewer_name"],
                "employee_mentions": employee_mentions,
                "total_points": round(total_points, 2),
                "review_hash": review_hash,
                "quarter": quarter.upper(),
                "year": year,
                "source": "reviewtrackers",
                "rt_source": review_data["rt_source"],
                "location_id": review_data["location_id"],
                "location_name": review_data["location_name"],
                "source_url": review_data["source_url"],
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.customer_reviews.insert_one(review_doc)
            results["new_count"] += 1
            
        except Exception as e:
            results["errors"].append(str(e))
    
    return results
