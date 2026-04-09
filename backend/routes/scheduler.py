"""
Scheduler Routes - Automated reconciliation scheduler.

Includes:
- Scheduler status
- Scheduler configuration
- Manual run trigger
- Reconciliation history
"""

from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter
from pydantic import BaseModel

# Router
scheduler_router = APIRouter(tags=["Scheduler"])


def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


def get_scheduler():
    """Get APScheduler instance from server module"""
    from server import scheduler
    return scheduler


# ============================================================================
# MODELS
# ============================================================================

class SchedulerConfig(BaseModel):
    """Configuration for automated reconciliation scheduler."""
    enabled: bool = False
    schedule_hour: int = 2  # Default: 2 AM
    schedule_minute: int = 0
    quarter: str = "Q1"
    year: int = 2026


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def run_automated_reconciliation(quarter: str = "Q1", year: int = 2026):
    """
    Run the full reconciliation sequence:
    1. Fix All Discrepancies (sync reviews and recalculate scores)
    2. Enforce Data Caps (remove excess reviews)
    3. Run Audit (verify all employees pass)
    
    NOTE: This function requires refactoring to work with the modularized routes.
    The audit functions were moved to routes/audit.py as route handlers.
    """
    db = get_db()
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "automated_reconciliation",
        "quarter": quarter.upper(),
        "year": year,
        "steps": [],
        "success": False,
        "error": "Automated reconciliation requires manual execution via the Scoring Audit page."
    }
    
    # Store the log entry
    await db.reconciliation_history.insert_one(log_entry)
    
    return log_entry


# ============================================================================
# ROUTES
# ============================================================================

@scheduler_router.get("/v2/scheduler/status")
async def get_scheduler_status():
    """Get the current status of the automated reconciliation scheduler."""
    db = get_db()
    scheduler = get_scheduler()
    
    config = await db.scheduler_config.find_one({"_id": "reconciliation"}, {"_id": 0})
    
    jobs = scheduler.get_jobs()
    reconciliation_job = next((j for j in jobs if j.id == "reconciliation_job"), None)
    
    return {
        "scheduler_running": scheduler.running,
        "config": config or {"enabled": False, "schedule_hour": 2, "schedule_minute": 0, "quarter": "Q1", "year": 2026},
        "next_run": reconciliation_job.next_run_time.isoformat() if reconciliation_job and reconciliation_job.next_run_time else None,
        "job_active": reconciliation_job is not None
    }


@scheduler_router.post("/v2/scheduler/configure")
async def configure_scheduler(config: SchedulerConfig):
    """Configure and enable/disable the automated reconciliation scheduler."""
    db = get_db()
    scheduler = get_scheduler()
    
    # Save config to database
    await db.scheduler_config.update_one(
        {"_id": "reconciliation"},
        {"$set": {
            "enabled": config.enabled,
            "schedule_hour": config.schedule_hour,
            "schedule_minute": config.schedule_minute,
            "quarter": config.quarter,
            "year": config.year,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    # Remove existing job if any
    try:
        scheduler.remove_job("reconciliation_job")
    except Exception:
        pass  # Job doesn't exist, which is fine
    
    if config.enabled:
        # Add new scheduled job
        scheduler.add_job(
            run_automated_reconciliation,
            CronTrigger(hour=config.schedule_hour, minute=config.schedule_minute),
            id="reconciliation_job",
            kwargs={"quarter": config.quarter, "year": config.year},
            replace_existing=True
        )
        next_run = scheduler.get_job("reconciliation_job").next_run_time
        return {
            "success": True,
            "message": f"Scheduler enabled. Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')}",
            "next_run": next_run.isoformat()
        }
    else:
        return {
            "success": True,
            "message": "Scheduler disabled"
        }


@scheduler_router.post("/v2/scheduler/run-now")
async def run_reconciliation_now(quarter: str = "Q1", year: int = 2026):
    """Manually trigger the full reconciliation sequence immediately."""
    result = await run_automated_reconciliation(quarter, year)
    return result


@scheduler_router.get("/v2/scheduler/history")
async def get_reconciliation_history(limit: int = 10):
    """Get the history of automated reconciliation runs."""
    db = get_db()
    history = await db.reconciliation_log.find(
        {},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {"history": history}
