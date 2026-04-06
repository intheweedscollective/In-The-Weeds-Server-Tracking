"""
Multi-Store Architecture Routes
Manages multiple restaurant locations with hierarchical data access.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

stores_router = APIRouter(prefix="/v2/stores", tags=["Stores"])

def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# ============================================================================
# MODELS
# ============================================================================

class StoreCreate(BaseModel):
    """Model for creating a new store."""
    name: str = Field(..., description="Store display name", example="Bubba Gump Las Vegas")
    code: str = Field(..., description="Short code for store", example="LV")
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    region: Optional[str] = Field(None, description="Regional grouping", example="West")
    manager_name: Optional[str] = None
    manager_email: Optional[str] = None
    timezone: str = Field("America/Los_Angeles", description="Store timezone")
    is_active: bool = True


class StoreUpdate(BaseModel):
    """Model for updating a store."""
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    region: Optional[str] = None
    manager_name: Optional[str] = None
    manager_email: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None


# ============================================================================
# STORE MANAGEMENT ENDPOINTS
# ============================================================================

@stores_router.get("")
async def list_stores(
    region: Optional[str] = None,
    is_active: bool = True,
    include_stats: bool = False
):
    """
    List all stores with optional filtering.
    
    Args:
        region: Filter by region (e.g., "West", "East")
        is_active: Filter by active status
        include_stats: Include employee counts and average scores
    """
    db = get_db()
    
    # Build query
    query = {}
    if region:
        query["region"] = region
    if is_active is not None:
        query["is_active"] = is_active
    
    stores = await db.stores.find(query, {"_id": 0}).sort("name", 1).to_list(100)
    
    # Add stats if requested
    if include_stats:
        for store in stores:
            store_id = store.get("id")
            
            # Get employee count from latest snapshot
            snapshot = await db.snapshot_workflow.find_one(
                {"store_id": store_id, "is_current": True},
                {"employee_count": 1, "employees": 1}
            )
            
            if snapshot:
                store["employee_count"] = snapshot.get("employee_count", len(snapshot.get("employees", [])))
                employees = snapshot.get("employees", [])
                if employees:
                    scores = [e.get("total_score", 0) for e in employees if e.get("total_score")]
                    store["avg_score"] = round(sum(scores) / len(scores), 1) if scores else 0
                else:
                    store["avg_score"] = 0
            else:
                store["employee_count"] = 0
                store["avg_score"] = 0
    
    # Get distinct regions for filtering
    regions = await db.stores.distinct("region", {"region": {"$ne": None}})
    
    return {
        "stores": stores,
        "total": len(stores),
        "regions": sorted(regions)
    }


@stores_router.get("/regions")
async def list_regions():
    """Get list of all regions with store counts."""
    db = get_db()
    
    pipeline = [
        {"$match": {"is_active": True}},
        {"$group": {
            "_id": "$region",
            "store_count": {"$sum": 1},
            "stores": {"$push": {"id": "$id", "name": "$name", "code": "$code"}}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    results = await db.stores.aggregate(pipeline).to_list(50)
    
    regions = []
    for r in results:
        regions.append({
            "region": r["_id"] or "Unassigned",
            "store_count": r["store_count"],
            "stores": r["stores"]
        })
    
    return {"regions": regions}


@stores_router.get("/{store_id}")
async def get_store(store_id: str):
    """Get a single store by ID."""
    db = get_db()
    
    store = await db.stores.find_one({"id": store_id}, {"_id": 0})
    
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Get latest snapshot info
    snapshot = await db.snapshot_workflow.find_one(
        {"store_id": store_id, "is_current": True},
        {"_id": 0, "id": 1, "name": 1, "quarter": 1, "year": 1, "employee_count": 1, "status": 1}
    )
    
    store["current_snapshot"] = snapshot
    
    return store


@stores_router.post("")
async def create_store(store: StoreCreate):
    """Create a new store."""
    db = get_db()
    
    # Check for duplicate code
    existing = await db.stores.find_one({"code": store.code.upper()})
    if existing:
        raise HTTPException(status_code=400, detail=f"Store with code '{store.code}' already exists")
    
    store_doc = {
        "id": str(uuid.uuid4()),
        "name": store.name,
        "code": store.code.upper(),
        "address": store.address,
        "city": store.city,
        "state": store.state,
        "region": store.region,
        "manager_name": store.manager_name,
        "manager_email": store.manager_email,
        "timezone": store.timezone,
        "is_active": store.is_active,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.stores.insert_one(store_doc)
    
    # Remove _id for response
    store_doc.pop("_id", None)
    
    logger.info(f"Created store: {store.name} ({store.code})")
    
    return {"success": True, "store": store_doc}


@stores_router.put("/{store_id}")
async def update_store(store_id: str, update: StoreUpdate):
    """Update a store."""
    db = get_db()
    
    existing = await db.stores.find_one({"id": store_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Store not found")
    
    update_dict = {k: v for k, v in update.dict().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc)
    
    await db.stores.update_one(
        {"id": store_id},
        {"$set": update_dict}
    )
    
    updated = await db.stores.find_one({"id": store_id}, {"_id": 0})
    
    return {"success": True, "store": updated}


@stores_router.delete("/{store_id}")
async def delete_store(store_id: str, force: bool = False):
    """
    Delete a store.
    
    Args:
        force: If True, delete even if store has data. Otherwise, only deactivate.
    """
    db = get_db()
    
    existing = await db.stores.find_one({"id": store_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Store not found")
    
    # Check for associated data
    snapshot_count = await db.snapshot_workflow.count_documents({"store_id": store_id})
    employee_count = await db.employees_v2.count_documents({"store_id": store_id})
    
    has_data = snapshot_count > 0 or employee_count > 0
    
    if has_data and not force:
        # Just deactivate
        await db.stores.update_one(
            {"id": store_id},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}}
        )
        return {
            "success": True,
            "action": "deactivated",
            "message": f"Store deactivated (has {snapshot_count} snapshots, {employee_count} employees). Use force=true to delete."
        }
    
    if force and has_data:
        # Delete all associated data
        await db.snapshot_workflow.delete_many({"store_id": store_id})
        await db.employees_v2.delete_many({"store_id": store_id})
    
    await db.stores.delete_one({"id": store_id})
    
    return {"success": True, "action": "deleted"}


# ============================================================================
# GLOBAL REPORTING ENDPOINTS
# ============================================================================

@stores_router.get("/reports/overview")
async def get_global_overview(
    quarter: str = "Q1",
    year: int = 2026,
    region: Optional[str] = None
):
    """
    Get global performance overview across all stores.
    
    Returns aggregated metrics for regional/executive dashboards.
    """
    db = get_db()
    
    # Build store filter
    store_query = {"is_active": True}
    if region:
        store_query["region"] = region
    
    stores = await db.stores.find(store_query, {"id": 1, "name": 1, "code": 1, "region": 1}).to_list(100)
    store_ids = [s["id"] for s in stores]
    
    if not store_ids:
        return {
            "quarter": quarter,
            "year": year,
            "region": region,
            "stores": [],
            "summary": {
                "total_stores": 0,
                "total_employees": 0,
                "avg_score": 0,
                "top_performers": 0,
                "needs_coaching": 0
            }
        }
    
    # Get snapshots for all stores
    snapshots = await db.snapshot_workflow.find(
        {
            "store_id": {"$in": store_ids},
            "quarter": quarter.upper(),
            "year": year,
            "is_current": True
        },
        {"_id": 0, "store_id": 1, "employees": 1}
    ).to_list(100)
    
    # Build store performance data
    store_data = []
    all_employees = []
    
    for store in stores:
        store_snapshot = next((s for s in snapshots if s.get("store_id") == store["id"]), None)
        
        if store_snapshot and store_snapshot.get("employees"):
            employees = store_snapshot["employees"]
            scores = [e.get("total_score", 0) for e in employees if e.get("total_score")]
            
            a_servers = len([e for e in employees if e.get("tier_label") in ["A-Server", "Trainer"]])
            c_servers = len([e for e in employees if e.get("tier_label") == "C-Server"])
            
            store_data.append({
                "store_id": store["id"],
                "name": store["name"],
                "code": store["code"],
                "region": store.get("region"),
                "employee_count": len(employees),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "top_score": max(scores) if scores else 0,
                "a_server_count": a_servers,
                "c_server_count": c_servers
            })
            
            all_employees.extend(employees)
        else:
            store_data.append({
                "store_id": store["id"],
                "name": store["name"],
                "code": store["code"],
                "region": store.get("region"),
                "employee_count": 0,
                "avg_score": 0,
                "top_score": 0,
                "a_server_count": 0,
                "c_server_count": 0
            })
    
    # Sort stores by avg_score descending
    store_data.sort(key=lambda x: x["avg_score"], reverse=True)
    
    # Calculate global summary
    all_scores = [e.get("total_score", 0) for e in all_employees if e.get("total_score")]
    
    summary = {
        "total_stores": len(stores),
        "total_employees": len(all_employees),
        "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else 0,
        "top_performers": len([e for e in all_employees if e.get("tier_label") in ["A-Server", "Trainer"]]),
        "needs_coaching": len([e for e in all_employees if e.get("tier_label") == "C-Server"])
    }
    
    return {
        "quarter": quarter,
        "year": year,
        "region": region,
        "stores": store_data,
        "summary": summary
    }


@stores_router.get("/reports/leaderboard")
async def get_global_leaderboard(
    quarter: str = "Q1",
    year: int = 2026,
    region: Optional[str] = None,
    limit: int = 20
):
    """
    Get global employee leaderboard across all stores.
    
    Shows top performers company-wide or by region.
    """
    db = get_db()
    
    # Build store filter
    store_query = {"is_active": True}
    if region:
        store_query["region"] = region
    
    stores = await db.stores.find(store_query, {"id": 1, "name": 1, "code": 1}).to_list(100)
    store_map = {s["id"]: s for s in stores}
    store_ids = list(store_map.keys())
    
    if not store_ids:
        return {"leaderboard": [], "total": 0}
    
    # Get all employees from active snapshots
    snapshots = await db.snapshot_workflow.find(
        {
            "store_id": {"$in": store_ids},
            "quarter": quarter.upper(),
            "year": year,
            "is_current": True
        },
        {"_id": 0, "store_id": 1, "employees": 1}
    ).to_list(100)
    
    # Flatten and enrich employee data
    all_employees = []
    for snapshot in snapshots:
        store_id = snapshot.get("store_id")
        store_info = store_map.get(store_id, {})
        
        for emp in snapshot.get("employees", []):
            all_employees.append({
                "employee_id": emp.get("id"),
                "name": emp.get("name") or emp.get("display_name"),
                "tier_label": emp.get("tier_label"),
                "total_score": emp.get("total_score", 0),
                "store_id": store_id,
                "store_name": store_info.get("name", "Unknown"),
                "store_code": store_info.get("code", "??")
            })
    
    # Sort by score descending
    all_employees.sort(key=lambda x: x["total_score"] or 0, reverse=True)
    
    # Add rank
    for i, emp in enumerate(all_employees[:limit], 1):
        emp["global_rank"] = i
    
    return {
        "quarter": quarter,
        "year": year,
        "region": region,
        "leaderboard": all_employees[:limit],
        "total": len(all_employees)
    }


@stores_router.get("/reports/store-comparison")
async def get_store_comparison(
    quarter: str = "Q1",
    year: int = 2026,
    metric: str = "avg_score"
):
    """
    Compare stores by a specific metric.
    
    Args:
        metric: One of "avg_score", "avg_ppa", "avg_lbw", "employee_count", "a_server_pct"
    """
    db = get_db()
    
    stores = await db.stores.find({"is_active": True}, {"id": 1, "name": 1, "code": 1, "region": 1}).to_list(100)
    store_ids = [s["id"] for s in stores]
    
    snapshots = await db.snapshot_workflow.find(
        {
            "store_id": {"$in": store_ids},
            "quarter": quarter.upper(),
            "year": year,
            "is_current": True
        },
        {"_id": 0, "store_id": 1, "employees": 1}
    ).to_list(100)
    
    snapshot_map = {s["store_id"]: s for s in snapshots}
    
    comparison = []
    for store in stores:
        snapshot = snapshot_map.get(store["id"])
        employees = snapshot.get("employees", []) if snapshot else []
        
        if not employees:
            comparison.append({
                "store_id": store["id"],
                "name": store["name"],
                "code": store["code"],
                "region": store.get("region"),
                "value": 0,
                "metric": metric
            })
            continue
        
        # Calculate metric
        if metric == "avg_score":
            scores = [e.get("total_score", 0) for e in employees if e.get("total_score")]
            value = round(sum(scores) / len(scores), 1) if scores else 0
        elif metric == "avg_ppa":
            ppas = [e.get("ppa", 0) for e in employees if e.get("ppa")]
            value = round(sum(ppas) / len(ppas), 2) if ppas else 0
        elif metric == "avg_lbw":
            lbws = [e.get("lbw_per_guest", 0) for e in employees if e.get("lbw_per_guest")]
            value = round(sum(lbws) / len(lbws), 2) if lbws else 0
        elif metric == "employee_count":
            value = len(employees)
        elif metric == "a_server_pct":
            a_count = len([e for e in employees if e.get("tier_label") in ["A-Server", "Trainer"]])
            value = round((a_count / len(employees)) * 100, 1) if employees else 0
        else:
            value = 0
        
        comparison.append({
            "store_id": store["id"],
            "name": store["name"],
            "code": store["code"],
            "region": store.get("region"),
            "value": value,
            "metric": metric
        })
    
    # Sort by value descending
    comparison.sort(key=lambda x: x["value"], reverse=True)
    
    # Add rank
    for i, item in enumerate(comparison, 1):
        item["rank"] = i
    
    return {
        "quarter": quarter,
        "year": year,
        "metric": metric,
        "comparison": comparison
    }


# ============================================================================
# SEED DATA
# ============================================================================

@stores_router.post("/seed-bubba-gump")
async def seed_bubba_gump_stores():
    """
    Seed database with Bubba Gump restaurant locations.
    For initial setup only.
    """
    db = get_db()
    
    # Check if stores already exist
    existing = await db.stores.count_documents({})
    if existing > 0:
        return {
            "success": False,
            "message": f"Stores already exist ({existing} stores). Clear first to re-seed.",
            "existing_count": existing
        }
    
    # Bubba Gump locations (real locations as of 2024)
    locations = [
        {"name": "Bubba Gump Las Vegas", "code": "LV", "city": "Las Vegas", "state": "NV", "region": "West"},
        {"name": "Bubba Gump Santa Monica", "code": "SM", "city": "Santa Monica", "state": "CA", "region": "West"},
        {"name": "Bubba Gump Long Beach", "code": "LB", "city": "Long Beach", "state": "CA", "region": "West"},
        {"name": "Bubba Gump San Francisco", "code": "SF", "city": "San Francisco", "state": "CA", "region": "West"},
        {"name": "Bubba Gump Monterey", "code": "MT", "city": "Monterey", "state": "CA", "region": "West"},
        {"name": "Bubba Gump San Diego", "code": "SD", "city": "San Diego", "state": "CA", "region": "West"},
        {"name": "Bubba Gump Anaheim", "code": "AN", "city": "Anaheim", "state": "CA", "region": "West"},
        {"name": "Bubba Gump Lahaina Maui", "code": "MU", "city": "Lahaina", "state": "HI", "region": "Hawaii"},
        {"name": "Bubba Gump Oahu", "code": "OA", "city": "Honolulu", "state": "HI", "region": "Hawaii"},
        {"name": "Bubba Gump Kona", "code": "KO", "city": "Kailua-Kona", "state": "HI", "region": "Hawaii"},
        {"name": "Bubba Gump New York Times Square", "code": "NY", "city": "New York", "state": "NY", "region": "East"},
        {"name": "Bubba Gump Chicago", "code": "CH", "city": "Chicago", "state": "IL", "region": "Central"},
        {"name": "Bubba Gump Miami", "code": "MI", "city": "Miami", "state": "FL", "region": "East"},
        {"name": "Bubba Gump Orlando", "code": "OR", "city": "Orlando", "state": "FL", "region": "East"},
        {"name": "Bubba Gump Fort Lauderdale", "code": "FL", "city": "Fort Lauderdale", "state": "FL", "region": "East"},
        {"name": "Bubba Gump Gatlinburg", "code": "GT", "city": "Gatlinburg", "state": "TN", "region": "East"},
        {"name": "Bubba Gump Nashville", "code": "NS", "city": "Nashville", "state": "TN", "region": "Central"},
        {"name": "Bubba Gump New Orleans", "code": "NO", "city": "New Orleans", "state": "LA", "region": "Central"},
        {"name": "Bubba Gump San Antonio", "code": "SA", "city": "San Antonio", "state": "TX", "region": "Central"},
        {"name": "Bubba Gump Galveston", "code": "GA", "city": "Galveston", "state": "TX", "region": "Central"},
        {"name": "Bubba Gump Cancun", "code": "CX", "city": "Cancun", "state": "QR", "region": "International"},
        {"name": "Bubba Gump London", "code": "UK", "city": "London", "state": "UK", "region": "International"},
    ]
    
    stores_to_insert = []
    for loc in locations:
        stores_to_insert.append({
            "id": str(uuid.uuid4()),
            "name": loc["name"],
            "code": loc["code"],
            "city": loc["city"],
            "state": loc["state"],
            "region": loc["region"],
            "address": None,
            "manager_name": None,
            "manager_email": None,
            "timezone": "America/Los_Angeles" if loc["region"] in ["West", "Hawaii"] else "America/New_York",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
    
    await db.stores.insert_many(stores_to_insert)
    
    # Create index
    await db.stores.create_index("id", unique=True)
    await db.stores.create_index("code", unique=True)
    await db.stores.create_index("region")
    
    return {
        "success": True,
        "message": f"Created {len(stores_to_insert)} Bubba Gump stores",
        "stores": [{"code": s["code"], "name": s["name"], "region": s["region"]} for s in stores_to_insert]
    }


@stores_router.post("/migrate-existing-data")
async def migrate_existing_data_to_store(store_code: str = "LV"):
    """
    Migrate existing data (snapshots, employees) to a specific store.
    
    This is a one-time migration for existing single-store data.
    """
    db = get_db()
    
    # Find the store
    store = await db.stores.find_one({"code": store_code.upper()})
    if not store:
        raise HTTPException(status_code=404, detail=f"Store with code '{store_code}' not found")
    
    store_id = store["id"]
    
    # Update snapshots without store_id
    snapshot_result = await db.snapshot_workflow.update_many(
        {"store_id": {"$exists": False}},
        {"$set": {"store_id": store_id}}
    )
    
    # Update employees without store_id
    employee_result = await db.employees_v2.update_many(
        {"store_id": {"$exists": False}},
        {"$set": {"store_id": store_id}}
    )
    
    # Update quarter_settings without store_id
    settings_result = await db.quarter_settings.update_many(
        {"store_id": {"$exists": False}},
        {"$set": {"store_id": store_id}}
    )
    
    return {
        "success": True,
        "store": {"id": store_id, "code": store["code"], "name": store["name"]},
        "migrated": {
            "snapshots": snapshot_result.modified_count,
            "employees": employee_result.modified_count,
            "quarter_settings": settings_result.modified_count
        }
    }
