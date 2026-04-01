"""
Snapshot Manager Module
Implements snapshot-first architecture where:
- Snapshots are the parent container for all data
- Uploads are tied to specific snapshots
- Rankings are driven by the latest completed snapshot
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnapshotStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadType(str, Enum):
    POS_REPORT = "pos_report"
    CUSTOMER_VOICE = "customer_voice"
    REVIEW_TRACKER = "review_tracker"


class UploadStatus(str, Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


# Pydantic Models for API
class SnapshotCreate(BaseModel):
    name: str = Field(..., description="Snapshot name (e.g., 'Week 1-2 March 2026')")
    effective_date: str = Field(..., description="Date when this snapshot becomes active (YYYY-MM-DD)")
    period_start: str = Field(..., description="Start of reporting period (YYYY-MM-DD)")
    period_end: str = Field(..., description="End of reporting period (YYYY-MM-DD)")
    quarter: str = Field(default="Q1", description="Quarter (Q1, Q2, Q3, Q4)")
    year: int = Field(default=2026, description="Year")
    notes: Optional[str] = Field(default=None, description="Optional notes")


class SnapshotUpdate(BaseModel):
    name: Optional[str] = None
    effective_date: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    notes: Optional[str] = None


class SnapshotResponse(BaseModel):
    id: str
    name: str
    effective_date: str
    period_start: str
    period_end: str
    quarter: str
    year: int
    status: str
    notes: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    uploads: List[Dict[str, Any]]
    upload_progress: Dict[str, bool]
    employee_count: int
    is_current: bool


def create_snapshot_record(data: SnapshotCreate) -> Dict[str, Any]:
    """Create a new snapshot record with initial state."""
    now = datetime.now(timezone.utc).isoformat()
    snapshot_id = str(uuid.uuid4())
    
    return {
        "id": snapshot_id,
        "name": data.name,
        "effective_date": data.effective_date,
        "period_start": data.period_start,
        "period_end": data.period_end,
        "quarter": data.quarter.upper(),
        "year": data.year,
        "status": SnapshotStatus.DRAFT.value,
        "notes": data.notes,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        # Upload tracking
        "uploads": [],
        "upload_progress": {
            UploadType.POS_REPORT.value: False,
            UploadType.CUSTOMER_VOICE.value: False,
            UploadType.REVIEW_TRACKER.value: False,
        },
        # Results (populated after processing)
        "employees": [],
        "employee_count": 0,
        "benchmarks_used": {},
        "processing_log": [],
        # Metadata
        "is_current": False,
        "version": 1,
    }


def create_upload_record(
    snapshot_id: str,
    upload_type: UploadType,
    filename: str,
    file_size: int,
    parsed_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create an upload record tied to a snapshot."""
    now = datetime.now(timezone.utc).isoformat()
    
    return {
        "id": str(uuid.uuid4()),
        "snapshot_id": snapshot_id,
        "upload_type": upload_type.value,
        "filename": filename,
        "file_size": file_size,
        "uploaded_at": now,
        "status": UploadStatus.UPLOADED.value if parsed_data else UploadStatus.PENDING.value,
        "parsed_data": parsed_data,
        "parsed_at": now if parsed_data else None,
        "record_count": len(parsed_data.get("employees", [])) if parsed_data else 0,
        "error": None,
    }


def calculate_upload_progress(uploads: List[Dict[str, Any]]) -> Dict[str, bool]:
    """Calculate which upload types have been completed."""
    progress = {
        UploadType.POS_REPORT.value: False,
        UploadType.CUSTOMER_VOICE.value: False,
        UploadType.REVIEW_TRACKER.value: False,
    }
    
    for upload in uploads:
        upload_type = upload.get("upload_type")
        status = upload.get("status")
        if upload_type in progress and status in [UploadStatus.PARSED.value, UploadStatus.UPLOADED.value]:
            progress[upload_type] = True
    
    return progress


def can_process_snapshot(snapshot: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Check if a snapshot has all required uploads to be processed.
    Returns (can_process, missing_uploads)
    """
    required_uploads = [UploadType.POS_REPORT.value]
    optional_uploads = [UploadType.CUSTOMER_VOICE.value, UploadType.REVIEW_TRACKER.value]
    
    progress = snapshot.get("upload_progress", {})
    missing = []
    
    for upload_type in required_uploads:
        if not progress.get(upload_type, False):
            missing.append(upload_type)
    
    can_process = len(missing) == 0
    return can_process, missing


def format_snapshot_response(snapshot: Dict[str, Any], is_current: bool = False) -> Dict[str, Any]:
    """Format a snapshot for API response."""
    response = {
        "id": snapshot.get("id"),
        "name": snapshot.get("name"),
        "effective_date": snapshot.get("effective_date"),
        "period_start": snapshot.get("period_start"),
        "period_end": snapshot.get("period_end"),
        "quarter": snapshot.get("quarter"),
        "year": snapshot.get("year"),
        "status": snapshot.get("status"),
        "notes": snapshot.get("notes"),
        "created_at": snapshot.get("created_at"),
        "updated_at": snapshot.get("updated_at"),
        "completed_at": snapshot.get("completed_at"),
        "uploads": snapshot.get("uploads", []),
        "upload_progress": snapshot.get("upload_progress", {}),
        "employee_count": snapshot.get("employee_count", 0),
        "is_current": is_current or snapshot.get("is_current", False),
    }
    
    # Include employees for completed OR in_progress snapshots (sorted by score)
    if snapshot.get("status") in [SnapshotStatus.COMPLETED.value, SnapshotStatus.IN_PROGRESS.value]:
        employees = snapshot.get("employees", [])
        # Sort by total_score or pre_dar_score descending
        sorted_employees = sorted(
            employees,
            key=lambda x: x.get("total_score", x.get("pre_dar_score", 0)) or 0,
            reverse=True
        )
        response["employees"] = sorted_employees
        response["benchmarks"] = snapshot.get("benchmarks_used", {})
    
    return response


# Scoring calculation functions (moved from main logic)
def calculate_employee_scores(
    employee: Dict[str, Any],
    benchmarks: Dict[str, float]
) -> Dict[str, Any]:
    """
    Calculate all scores for an employee based on benchmarks.
    Returns employee dict with calculated scores.
    """
    # Get raw metrics
    ppa = employee.get("ppa", 0) or 0
    lbw_per_guest = employee.get("lbw_per_guest", 0) or 0
    glassware_per_guest = employee.get("glassware_per_guest", 0) or 0
    guests_per_lsc = employee.get("guests_per_lsc", 0) or 0
    
    # Get benchmarks
    benchmark_ppa = benchmarks.get("ppa", 55.0)
    benchmark_lbw = benchmarks.get("lbw", 8.0)
    benchmark_glass = benchmarks.get("glass", 1.25)
    benchmark_lsc = benchmarks.get("lsc", 100.0)
    
    # Calculate normalized scores (percentage of benchmark)
    score_ppa = (ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
    score_lbw = (lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
    score_glass = (glassware_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
    # LSC is inverted - lower guests per LSC is better
    score_lsc = (benchmark_lsc / guests_per_lsc) * 100 if guests_per_lsc > 0 else 0
    
    # Cap scores at 100 for weighted calculation
    capped_ppa = min(score_ppa, 100)
    capped_lbw = min(score_lbw, 100)
    capped_glass = min(score_glass, 100)
    capped_lsc = min(score_lsc, 100)
    
    # Calculate weighted score (75 pts max from POS metrics)
    weighted_score = round(
        capped_ppa * 0.25 +
        capped_lbw * 0.15 +
        capped_glass * 0.10 +
        capped_lsc * 0.25,
        2
    )
    
    # Calculate metric bonuses (for scores > 100)
    def calc_bonus(score: float) -> float:
        if score > 100:
            return min((score - 100) * 0.25, 5.0)
        return 0.0
    
    bonus_ppa = round(calc_bonus(score_ppa), 2)
    bonus_lbw = round(calc_bonus(score_lbw), 2)
    bonus_glass = round(calc_bonus(score_glass), 2)
    bonus_lsc = round(calc_bonus(score_lsc), 2)
    total_metric_bonus = round(bonus_ppa + bonus_lbw + bonus_glass + bonus_lsc, 2)
    
    # Get CV/RT scores (if present)
    cv_score = employee.get("cv_score", 0) or 0
    review_tracker_bonus = employee.get("review_tracker_bonus", 0) or 0
    dar_penalty = employee.get("dar_penalty", 0) or 0
    
    # Calculate total score
    pre_dar_score = round(weighted_score + total_metric_bonus + cv_score + review_tracker_bonus, 2)
    total_score = round(pre_dar_score - dar_penalty, 2)
    
    # Update employee with calculated values
    employee.update({
        "score_ppa": round(score_ppa, 2),
        "score_lbw": round(score_lbw, 2),
        "score_glass": round(score_glass, 2),
        "score_lsc": round(score_lsc, 2),
        "bonus_ppa": bonus_ppa,
        "bonus_lbw": bonus_lbw,
        "bonus_glass": bonus_glass,
        "bonus_lsc": bonus_lsc,
        "total_metric_bonus": total_metric_bonus,
        "weighted_score": weighted_score,
        "pre_dar_score": pre_dar_score,
        "total_score": total_score,
    })
    
    return employee


def assign_performance_tiers(employees: List[Dict[str, Any]], a_min: float = 85, b_min: float = 70) -> List[Dict[str, Any]]:
    """
    Assign performance tiers and ranks to employees.
    
    Tier assignment rules:
    - Bartenders: job_title contains 'bartender' -> tier_label = "Bartender"
    - Trainers: job_title contains 'trainer' -> tier_label = "Trainer"
    - Servers are assigned tiers by SCORE thresholds:
      - >= a_min points: A-Server (default 85+)
      - >= b_min points: B-Server (default 70-84.9)
      - < b_min points: C-Server (default <70)
    """
    # Separate bartenders/trainers from servers
    bartenders = []
    trainers = []
    servers = []
    
    for emp in employees:
        job_title = (emp.get("job_title") or "server").lower()
        score = emp.get("total_score", 0) or emp.get("pre_dar_score", 0) or 0
        
        if "bartender" in job_title or "bar" in job_title:
            emp["tier_label"] = "Bartender"
            bartenders.append(emp)
        elif "trainer" in job_title or "train" in job_title:
            emp["tier_label"] = "Trainer"
            trainers.append(emp)
        else:
            # Assign tier based on score thresholds
            if score >= a_min:
                emp["tier_label"] = "A-Server"
            elif score >= b_min:
                emp["tier_label"] = "B-Server"
            else:
                emp["tier_label"] = "C-Server"
            servers.append(emp)
    
    # Sort each group by total_score descending
    bartenders = sorted(bartenders, key=lambda x: x.get("total_score", 0) or 0, reverse=True)
    trainers = sorted(trainers, key=lambda x: x.get("total_score", 0) or 0, reverse=True)
    servers = sorted(servers, key=lambda x: x.get("total_score", 0) or 0, reverse=True)
    
    # Combine in order: Trainers, Bartenders, A-Servers, B-Servers, C-Servers
    sorted_employees = trainers + bartenders
    
    # Add servers grouped by tier
    a_servers = [e for e in servers if e.get("tier_label") == "A-Server"]
    b_servers = [e for e in servers if e.get("tier_label") == "B-Server"]
    c_servers = [e for e in servers if e.get("tier_label") == "C-Server"]
    
    sorted_employees.extend(a_servers)
    sorted_employees.extend(b_servers)
    sorted_employees.extend(c_servers)
    
    # Assign ranks within each tier
    tier_counts = {}
    for emp in sorted_employees:
        tier = emp.get("tier_label", "Server")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        emp["tier_rank"] = tier_counts[tier]
    
    # Assign overall peer rank
    for i, emp in enumerate(sorted_employees, 1):
        emp["peer_rank"] = i
        emp["peer_rank_display"] = f"{i} of {len(sorted_employees)}"
        
        # Assign performance tier label based on score (for color coding)
        score = emp.get("total_score", 0) or 0
        if score >= 100:
            emp["performance_tier"] = "Top Performer"
        elif score >= 85:
            emp["performance_tier"] = "Above Average"
        elif score >= 70:
            emp["performance_tier"] = "Average"
        elif score >= 60:
            emp["performance_tier"] = "Below Average"
        else:
            emp["performance_tier"] = "Needs Immediate Improvement"
    
    return sorted_employees
