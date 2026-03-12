"""
Multi-Store Management Module
Supports 22 Landry's restaurant locations with global reporting.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid

store_router = APIRouter(prefix="/stores", tags=["stores"])

# Store database reference (set during registration)
db = None

def set_db(database):
    global db
    db = database


class Store(BaseModel):
    """Restaurant store/location model."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # e.g., "Bubba Gump Galveston"
    code: str  # Short code e.g., "BGGAL"
    brand: str = "Bubba Gump"  # Brand name
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    region: Optional[str] = None  # e.g., "Gulf Coast", "West Coast"
    timezone: str = "America/Chicago"
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Store-specific settings
    settings: Dict[str, Any] = Field(default_factory=dict)
    
    # Review platform links
    yelp_url: Optional[str] = None
    google_place_id: Optional[str] = None
    tripadvisor_url: Optional[str] = None


class StoreCreate(BaseModel):
    """Model for creating a new store."""
    name: str
    code: str
    brand: str = "Bubba Gump"
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    region: Optional[str] = None
    timezone: str = "America/Chicago"
    yelp_url: Optional[str] = None
    google_place_id: Optional[str] = None
    tripadvisor_url: Optional[str] = None


class StoreUpdate(BaseModel):
    """Model for updating a store."""
    name: Optional[str] = None
    code: Optional[str] = None
    brand: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    region: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None
    settings: Optional[Dict[str, Any]] = None
    yelp_url: Optional[str] = None
    google_place_id: Optional[str] = None
    tripadvisor_url: Optional[str] = None


# Default Landry's stores
DEFAULT_STORES = [
    {"name": "Bubba Gump San Francisco", "code": "BGSF", "city": "San Francisco", "state": "CA", "region": "West Coast"},
    {"name": "Bubba Gump Santa Monica", "code": "BGSM", "city": "Santa Monica", "state": "CA", "region": "West Coast"},
    {"name": "Bubba Gump Long Beach", "code": "BGLB", "city": "Long Beach", "state": "CA", "region": "West Coast"},
    {"name": "Bubba Gump Monterey", "code": "BGMON", "city": "Monterey", "state": "CA", "region": "West Coast"},
    {"name": "Bubba Gump Lahaina", "code": "BGLAH", "city": "Lahaina", "state": "HI", "region": "Hawaii"},
    {"name": "Bubba Gump Kona", "code": "BGKON", "city": "Kona", "state": "HI", "region": "Hawaii"},
    {"name": "Bubba Gump Oahu", "code": "BGOAH", "city": "Honolulu", "state": "HI", "region": "Hawaii"},
    {"name": "Bubba Gump Chicago", "code": "BGCHI", "city": "Chicago", "state": "IL", "region": "Midwest"},
    {"name": "Bubba Gump New York Times Square", "code": "BGNYTS", "city": "New York", "state": "NY", "region": "Northeast"},
    {"name": "Bubba Gump Miami", "code": "BGMIA", "city": "Miami", "state": "FL", "region": "Southeast"},
    {"name": "Bubba Gump Orlando", "code": "BGORL", "city": "Orlando", "state": "FL", "region": "Southeast"},
    {"name": "Bubba Gump Gatlinburg", "code": "BGGAT", "city": "Gatlinburg", "state": "TN", "region": "Southeast"},
    {"name": "Bubba Gump Myrtle Beach", "code": "BGMYR", "city": "Myrtle Beach", "state": "SC", "region": "Southeast"},
    {"name": "Bubba Gump Galveston", "code": "BGGAL", "city": "Galveston", "state": "TX", "region": "Gulf Coast"},
    {"name": "Bubba Gump San Antonio", "code": "BGSA", "city": "San Antonio", "state": "TX", "region": "Gulf Coast"},
    {"name": "Bubba Gump Kemah", "code": "BGKEM", "city": "Kemah", "state": "TX", "region": "Gulf Coast"},
    {"name": "Bubba Gump New Orleans", "code": "BGNO", "city": "New Orleans", "state": "LA", "region": "Gulf Coast"},
    {"name": "Bubba Gump Cancun", "code": "BGCAN", "city": "Cancun", "state": "QR", "region": "International"},
    {"name": "Bubba Gump London", "code": "BGLON", "city": "London", "state": "UK", "region": "International"},
    {"name": "Bubba Gump Tokyo", "code": "BGTOK", "city": "Tokyo", "state": "JP", "region": "International"},
    {"name": "Bubba Gump Hong Kong", "code": "BGHK", "city": "Hong Kong", "state": "HK", "region": "International"},
    {"name": "Bubba Gump Manila", "code": "BGMAN", "city": "Manila", "state": "PH", "region": "International"},
]


# ============================================================================
# STORE CRUD ENDPOINTS
# ============================================================================

@store_router.get("")
async def get_all_stores(
    region: Optional[str] = None,
    is_active: Optional[bool] = None
):
    """Get all stores with optional filtering."""
    query = {}
    if region:
        query["region"] = region
    if is_active is not None:
        query["is_active"] = is_active
    
    stores = await db.stores.find(query, {"_id": 0}).sort("name", 1).to_list(100)
    
    # Get regions for filtering
    regions = await db.stores.distinct("region")
    
    return {
        "stores": stores,
        "total": len(stores),
        "regions": sorted([r for r in regions if r])
    }


@store_router.get("/{store_id}")
async def get_store(store_id: str):
    """Get a specific store by ID or code."""
    store = await db.stores.find_one(
        {"$or": [{"id": store_id}, {"code": store_id.upper()}]},
        {"_id": 0}
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@store_router.post("")
async def create_store(store: StoreCreate):
    """Create a new store."""
    # Check for duplicate code
    existing = await db.stores.find_one({"code": store.code.upper()})
    if existing:
        raise HTTPException(status_code=400, detail=f"Store with code {store.code} already exists")
    
    store_doc = {
        "id": str(uuid.uuid4()),
        "name": store.name,
        "code": store.code.upper(),
        "brand": store.brand,
        "address": store.address,
        "city": store.city,
        "state": store.state,
        "zip_code": store.zip_code,
        "region": store.region,
        "timezone": store.timezone,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings": {},
        "yelp_url": store.yelp_url,
        "google_place_id": store.google_place_id,
        "tripadvisor_url": store.tripadvisor_url
    }
    
    await db.stores.insert_one(store_doc)
    del store_doc["_id"]
    return store_doc


@store_router.put("/{store_id}")
async def update_store(store_id: str, store: StoreUpdate):
    """Update a store."""
    existing = await db.stores.find_one(
        {"$or": [{"id": store_id}, {"code": store_id.upper()}]}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Store not found")
    
    update_data = {k: v for k, v in store.model_dump().items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.stores.update_one({"id": existing["id"]}, {"$set": update_data})
    
    updated = await db.stores.find_one({"id": existing["id"]}, {"_id": 0})
    return updated


@store_router.delete("/{store_id}")
async def delete_store(store_id: str):
    """Soft delete a store (set is_active to False)."""
    result = await db.stores.update_one(
        {"$or": [{"id": store_id}, {"code": store_id.upper()}]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Store not found")
    return {"success": True, "message": "Store deactivated"}


@store_router.post("/initialize")
async def initialize_default_stores():
    """Initialize the database with default Landry's stores."""
    existing_count = await db.stores.count_documents({})
    if existing_count > 0:
        return {
            "success": False,
            "message": f"Stores already exist ({existing_count}). Use force=true to reset.",
            "existing_count": existing_count
        }
    
    created = 0
    for store_data in DEFAULT_STORES:
        store_doc = {
            "id": str(uuid.uuid4()),
            "name": store_data["name"],
            "code": store_data["code"],
            "brand": "Bubba Gump",
            "city": store_data["city"],
            "state": store_data["state"],
            "region": store_data["region"],
            "timezone": "America/Chicago",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "settings": {}
        }
        await db.stores.insert_one(store_doc)
        created += 1
    
    return {
        "success": True,
        "message": f"Created {created} default stores",
        "stores_created": created
    }


# ============================================================================
# STORE STATISTICS & REPORTING
# ============================================================================

@store_router.get("/{store_id}/stats")
async def get_store_stats(store_id: str, quarter: str = "Q1", year: int = 2026):
    """Get performance statistics for a specific store."""
    store = await db.stores.find_one(
        {"$or": [{"id": store_id}, {"code": store_id.upper()}]},
        {"_id": 0}
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Get employees for this store
    employees = await db.employees_v2.find(
        {"store_id": store["id"], "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    ).to_list(500)
    
    if not employees:
        # Fallback: if no store_id assigned, get all employees (for backward compatibility)
        employees = await db.employees_v2.find(
            {"quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(500)
    
    # Calculate stats
    total_employees = len(employees)
    avg_score = sum(e.get("total_score", 0) for e in employees) / total_employees if total_employees > 0 else 0
    
    # Get top performers
    sorted_employees = sorted(employees, key=lambda x: x.get("total_score", 0), reverse=True)
    top_performers = sorted_employees[:5]
    
    # Get metric averages
    metric_avgs = {
        "ppa": sum(e.get("ppa", 0) for e in employees) / total_employees if total_employees > 0 else 0,
        "lbw_per_guest": sum(e.get("lbw_per_guest", 0) for e in employees) / total_employees if total_employees > 0 else 0,
        "glassware_per_guest": sum(e.get("glassware_per_guest", 0) for e in employees) / total_employees if total_employees > 0 else 0,
        "guests_per_lsc": sum(e.get("guests_per_lsc", 0) for e in employees) / total_employees if total_employees > 0 else 0,
    }
    
    return {
        "store": store,
        "quarter": quarter.upper(),
        "year": year,
        "total_employees": total_employees,
        "average_score": round(avg_score, 2),
        "top_performers": [{"name": e["name"], "score": e.get("total_score", 0)} for e in top_performers],
        "metric_averages": {k: round(v, 2) for k, v in metric_avgs.items()}
    }


@store_router.get("/reports/global")
async def get_global_report(quarter: str = "Q1", year: int = 2026):
    """Get global performance report across all stores."""
    stores = await db.stores.find({"is_active": True}, {"_id": 0}).to_list(100)
    
    store_stats = []
    for store in stores:
        # Get employees for this store
        employees = await db.employees_v2.find(
            {"store_id": store["id"], "quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(500)
        
        if employees:
            avg_score = sum(e.get("total_score", 0) for e in employees) / len(employees)
            top_score = max(e.get("total_score", 0) for e in employees)
            store_stats.append({
                "store_id": store["id"],
                "store_name": store["name"],
                "code": store["code"],
                "region": store.get("region"),
                "employee_count": len(employees),
                "average_score": round(avg_score, 2),
                "top_score": round(top_score, 2)
            })
    
    # Sort by average score
    store_stats.sort(key=lambda x: x["average_score"], reverse=True)
    
    # Calculate global averages
    all_scores = [s["average_score"] for s in store_stats if s["average_score"] > 0]
    global_avg = sum(all_scores) / len(all_scores) if all_scores else 0
    
    # Group by region
    by_region = {}
    for stat in store_stats:
        region = stat.get("region", "Unknown")
        if region not in by_region:
            by_region[region] = []
        by_region[region].append(stat)
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "total_stores": len(store_stats),
        "global_average_score": round(global_avg, 2),
        "store_rankings": store_stats,
        "by_region": by_region
    }


@store_router.get("/reports/leaderboard")
async def get_store_leaderboard(quarter: str = "Q1", year: int = 2026):
    """Get store leaderboard comparing all locations."""
    stores = await db.stores.find({"is_active": True}, {"_id": 0}).to_list(100)
    
    leaderboard = []
    for store in stores:
        employees = await db.employees_v2.find(
            {"store_id": store["id"], "quarter": quarter.upper(), "year": year},
            {"_id": 0}
        ).to_list(500)
        
        if employees:
            scores = [e.get("total_score", 0) for e in employees]
            leaderboard.append({
                "rank": 0,  # Will be set after sorting
                "store_id": store["id"],
                "store_name": store["name"],
                "code": store["code"],
                "region": store.get("region"),
                "city": store.get("city"),
                "state": store.get("state"),
                "employee_count": len(employees),
                "average_score": round(sum(scores) / len(scores), 2),
                "top_score": round(max(scores), 2),
                "lowest_score": round(min(scores), 2),
                "score_spread": round(max(scores) - min(scores), 2)
            })
    
    # Sort and assign ranks
    leaderboard.sort(key=lambda x: x["average_score"], reverse=True)
    for i, store in enumerate(leaderboard, 1):
        store["rank"] = i
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "leaderboard": leaderboard,
        "total_stores": len(leaderboard)
    }


# ============================================================================
# REGISTRATION
# ============================================================================

def register_store_routes(app_router, database):
    """Register store routes with the main application."""
    set_db(database)
    app_router.include_router(store_router)
