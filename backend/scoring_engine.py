"""
Restaurant Performance Engine v2.1
Q1 2026 Official Scoring Model - Bubba Gump Shrimp Co.

Scoring Logic:
- PPA (25%), LSC (25%), LBW (20%), Glassware (15%), Customer Voice (15%)
- Customer Voice: NPS-style internal feedback scoring
- Review Tracker: External platform bonus points
- DAR: Disciplinary penalties (admin-only, applied at final stage)
"""

from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
import uuid
import math


# ============================================================================
# CUSTOMER VOICE & REVIEW TRACKER CONSTANTS
# ============================================================================

# Customer Voice NPS-style scoring
CV_PROMOTER_POINTS = 1      # Score 9-10
CV_PASSIVE_POINTS = 0       # Score 7-8
CV_DETRACTOR_POINTS = -2    # Score 6 or below
CV_MAX_POINTS = 10          # Quarterly cap for positive
CV_MIN_POINTS = -6          # Quarterly floor for negative

# Review Tracker
RT_MENTIONS_PER_POINT = 5   # Every 5 positive mentions = +1 point
RT_MAX_BONUS = 10           # Quarterly cap

# DAR Penalties
DAR_WRITTEN_WARNING = -3
DAR_SUSPENSION = -5


# ============================================================================
# DATA MODELS
# ============================================================================

class EmployeeV2(BaseModel):
    """
    Employee model with Q1 2026 official scoring fields.
    Raw data from upload + derived metrics + scores + Customer Voice + DAR
    """
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # === CANONICAL FIELDS (from upload) ===
    name: str
    guests: int  # Must be > 0
    net_sales: float
    lbw: float  # Total LBW dollars
    glassware_sales: float  # Total glassware dollars
    lsc_count: int  # LSC signups count, >= 0
    
    # === CUSTOMER VOICE FIELDS (from upload) ===
    cv_promoters: int = 0       # Count of 9-10 scores (service-related only)
    cv_passives: int = 0        # Count of 7-8 scores
    cv_detractors: int = 0      # Count of 6 or below scores
    
    # === REVIEW TRACKER FIELDS (from upload) ===
    review_mentions: int = 0    # Named positive mentions from external platforms
    
    # === DAR FIELDS (admin-only, not in upload) ===
    dar_written_warnings: int = 0
    dar_suspensions: int = 0
    
    # === LEGACY OPTIONAL FIELDS ===
    review_tracker: Optional[str] = None
    cv_positive: Optional[str] = None
    cv_negative: Optional[str] = None
    
    # === DERIVED METRICS (app-calculated) ===
    ppa: Optional[float] = None  # Net Sales / Guests
    lbw_per_guest: Optional[float] = None  # LBW / Guests
    glassware_per_guest: Optional[float] = None  # Glassware Sales / Guests
    guests_per_lsc: Optional[float] = None  # Guests / LSC Count (null if LSC=0)
    
    # === NORMALIZED SCORES (benchmark-relative) ===
    score_ppa: Optional[float] = None  # (PPA / Benchmark) * 100
    score_lbw: Optional[float] = None  # (LBW/Guest / Benchmark) * 100
    score_glass: Optional[float] = None  # (Glass/Guest / Benchmark) * 100
    score_lsc: Optional[float] = None  # (Benchmark / Guests per LSC) * 100 (inverse)
    
    # === CUSTOMER VOICE SCORE ===
    cv_raw_points: Optional[float] = None      # Raw CV calculation before cap
    cv_score: Optional[float] = None           # Capped CV score (-6 to +10)
    score_cv: Optional[float] = None           # Normalized for weighting (0-100 scale)
    
    # === REVIEW TRACKER BONUS ===
    review_tracker_bonus: Optional[float] = None  # Capped at 10
    
    # === BONUS POINTS (for exceeding benchmarks) ===
    bonus_ppa: Optional[float] = None
    bonus_lbw: Optional[float] = None
    bonus_glass: Optional[float] = None
    bonus_lsc: Optional[float] = None
    total_metric_bonus: Optional[float] = None
    
    # === DAR PENALTY (applied at final stage, not visible in rankings) ===
    dar_penalty: Optional[float] = None  # Hidden from rankings display
    
    # === FINAL SCORE & RANKING ===
    weighted_score: Optional[float] = None      # Before bonuses and penalties
    pre_dar_score: Optional[float] = None       # Score shown in rankings (before DAR)
    total_score: Optional[float] = None         # Final score (includes DAR, admin-only)
    peer_rank: Optional[int] = None             # 1-based rank (based on pre_dar_score)
    peer_rank_display: Optional[str] = None     # "X of N"
    performance_tier: Optional[str] = None      # Top Performer, etc.
    
    # === METADATA ===
    quarter: Optional[str] = None  # Q1, Q2, Q3, Q4
    year: Optional[int] = None
    quarter_settings_id: Optional[str] = None  # Links to locked settings
    additional_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuarterSettings(BaseModel):
    """
    Quarter-specific settings including benchmarks.
    Once scores are generated, settings become locked.
    """
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    year: int
    quarter: str  # Q1, Q2, Q3, Q4
    
    # === BENCHMARKS (editable before lock) ===
    benchmark_ppa: float = 55.0
    benchmark_lbw: float = 8.0
    benchmark_glass: float = 1.0
    benchmark_lsc: float = 100.0  # Guests per LSC (lower is better)
    
    # === METRIC WEIGHTS (must sum to 1.0) ===
    weight_ppa: float = 0.30
    weight_lbw: float = 0.25
    weight_glass: float = 0.20
    weight_lsc: float = 0.25
    
    # === BONUS SETTINGS ===
    bonus_rate: float = 0.2  # 0.2 per 1% over benchmark
    bonus_cap: float = 5.0  # Max bonus per metric
    
    # === PREVIOUS QUARTER AVERAGES (for benchmark suggestions) ===
    prev_avg_ppa: Optional[float] = None
    prev_avg_lbw: Optional[float] = None
    prev_avg_glass: Optional[float] = None
    prev_avg_lsc: Optional[float] = None
    
    # === LOCK STATUS ===
    is_locked: bool = False
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = None
    
    # === METADATA ===
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# COLUMN MAPPING CONFIGURATION
# ============================================================================

CANONICAL_COLUMN_MAPPING = {
    "name": ["employee name", "name", "server", "employee", "team member"],
    "guests": ["guests", "guest count", "covers", "total guests"],
    "net_sales": ["net sales", "sales", "total sales", "net", "netsales"],
    "lbw": ["lbw", "lbw sales", "alcohol", "alcohol sales", "liquor beer wine", "liquor+beer+wine"],
    "glassware_sales": ["glassware sales", "glassware", "souvenir glass", "glass sales"],
    "lsc_count": ["lsc count", "lsc", "loyalty", "loyalty sign ups", "enrollments", "memberships"],
    # Optional
    "review_tracker": ["review tracker", "reviews"],
    "cv_positive": ["cv positive", "cv+", "positive"],
    "cv_negative": ["cv negative", "cv-", "negative"],
}

# Columns that should NOT be accepted (they are derived, not raw)
REJECTED_COLUMNS = [
    "ppa", "per person average",
    "pplbw", "lbw per guest", "alcohol per guest",
    "gpg", "glass per guest", "glassware per guest",
    "guests per lsc",
]


def find_column_match(df_columns: List[str], canonical_field: str) -> Optional[str]:
    """
    Find matching column in dataframe for a canonical field.
    Returns the actual column name from the dataframe, or None if not found.
    """
    candidates = CANONICAL_COLUMN_MAPPING.get(canonical_field, [])
    df_columns_lower = {col.lower().strip(): col for col in df_columns}
    
    for candidate in candidates:
        if candidate in df_columns_lower:
            return df_columns_lower[candidate]
    
    return None


def validate_upload_columns(df_columns: List[str]) -> Dict[str, Any]:
    """
    Validate that required columns exist and return mapping.
    Returns: {
        "valid": bool,
        "mapping": {canonical_field: actual_column},
        "missing": [list of missing required fields],
        "rejected": [list of rejected derived columns found],
        "warnings": [list of warnings]
    }
    """
    result = {
        "valid": True,
        "mapping": {},
        "missing": [],
        "rejected": [],
        "warnings": []
    }
    
    required_fields = ["name", "guests", "net_sales", "lbw", "glassware_sales", "lsc_count"]
    optional_fields = ["review_tracker", "cv_positive", "cv_negative"]
    
    df_columns_lower = [col.lower().strip() for col in df_columns]
    
    # Check for rejected (derived) columns
    for rejected in REJECTED_COLUMNS:
        if rejected in df_columns_lower:
            result["rejected"].append(rejected)
    
    if result["rejected"]:
        result["warnings"].append(
            f"Found derived metric columns that should not be uploaded: {', '.join(result['rejected'])}. "
            "These will be calculated by the app from raw data."
        )
    
    # Find mappings for required fields
    for field in required_fields:
        match = find_column_match(df_columns, field)
        if match:
            result["mapping"][field] = match
        else:
            result["missing"].append(field)
    
    # Find mappings for optional fields
    for field in optional_fields:
        match = find_column_match(df_columns, field)
        if match:
            result["mapping"][field] = match
    
    if result["missing"]:
        result["valid"] = False
    
    return result


# ============================================================================
# SCORING ENGINE
# ============================================================================

def calculate_derived_metrics(employee: EmployeeV2) -> EmployeeV2:
    """
    Calculate derived metrics from raw data.
    PPA, LBW/Guest, Glassware/Guest, Guests/LSC
    """
    if employee.guests > 0:
        employee.ppa = round(employee.net_sales / employee.guests, 2)
        employee.lbw_per_guest = round(employee.lbw / employee.guests, 2)
        employee.glassware_per_guest = round(employee.glassware_sales / employee.guests, 2)
        
        if employee.lsc_count > 0:
            employee.guests_per_lsc = round(employee.guests / employee.lsc_count, 2)
        else:
            employee.guests_per_lsc = None
    
    return employee


def calculate_normalized_scores(employee: EmployeeV2, settings: QuarterSettings) -> EmployeeV2:
    """
    Calculate normalized scores (Q-T logic).
    Score = (Employee Metric / Benchmark) * 100
    
    For LSC (inverse): Score = (Benchmark / Employee Metric) * 100
    """
    # PPA Score
    if employee.ppa and settings.benchmark_ppa > 0:
        employee.score_ppa = round((employee.ppa / settings.benchmark_ppa) * 100, 2)
    else:
        employee.score_ppa = 0
    
    # LBW Score
    if employee.lbw_per_guest and settings.benchmark_lbw > 0:
        employee.score_lbw = round((employee.lbw_per_guest / settings.benchmark_lbw) * 100, 2)
    else:
        employee.score_lbw = 0
    
    # Glassware Score
    if employee.glassware_per_guest and settings.benchmark_glass > 0:
        employee.score_glass = round((employee.glassware_per_guest / settings.benchmark_glass) * 100, 2)
    else:
        employee.score_glass = 0
    
    # LSC Score (INVERSE - lower guests per LSC is better)
    if employee.guests_per_lsc and employee.guests_per_lsc > 0:
        employee.score_lsc = round((settings.benchmark_lsc / employee.guests_per_lsc) * 100, 2)
    else:
        employee.score_lsc = 0
    
    return employee


def calculate_bonus_points(employee: EmployeeV2, settings: QuarterSettings) -> EmployeeV2:
    """
    Calculate bonus points (Y-AB logic).
    If Score > 100: Bonus = MIN((Score - 100) * rate, cap)
    Else: Bonus = 0
    """
    def calc_bonus(score: Optional[float]) -> float:
        if score is None or score <= 100:
            return 0
        return min((score - 100) * settings.bonus_rate, settings.bonus_cap)
    
    employee.bonus_ppa = round(calc_bonus(employee.score_ppa), 2)
    employee.bonus_lbw = round(calc_bonus(employee.score_lbw), 2)
    employee.bonus_glass = round(calc_bonus(employee.score_glass), 2)
    employee.bonus_lsc = round(calc_bonus(employee.score_lsc), 2)
    
    employee.total_bonus = round(
        employee.bonus_ppa + employee.bonus_lbw + 
        employee.bonus_glass + employee.bonus_lsc, 2
    )
    
    return employee


def calculate_total_score(employee: EmployeeV2, settings: QuarterSettings) -> EmployeeV2:
    """
    Calculate weighted score + total score.
    """
    employee.weighted_score = round(
        (employee.score_ppa or 0) * settings.weight_ppa +
        (employee.score_lbw or 0) * settings.weight_lbw +
        (employee.score_glass or 0) * settings.weight_glass +
        (employee.score_lsc or 0) * settings.weight_lsc,
        2
    )
    
    employee.total_score = round(
        employee.weighted_score + (employee.total_bonus or 0),
        2
    )
    
    return employee


def calculate_rankings(employees: List[EmployeeV2]) -> List[EmployeeV2]:
    """
    Rank employees by total score (descending).
    Assign peer_rank and peer_rank_display.
    """
    # Sort by total_score descending
    sorted_employees = sorted(
        employees, 
        key=lambda e: e.total_score or 0, 
        reverse=True
    )
    
    total_count = len(sorted_employees)
    
    for idx, emp in enumerate(sorted_employees, 1):
        emp.peer_rank = idx
        emp.peer_rank_display = f"{idx} of {total_count}"
    
    return sorted_employees


def calculate_performance_tiers(employees: List[EmployeeV2]) -> List[EmployeeV2]:
    """
    Assign performance tiers based on percentile.
    - Top 25%: Top Performer
    - 51-75%: Above Average
    - 26-50%: Below Average  
    - Bottom 15%: Needs Immediate Improvement
    - 16-25%: Below Average (catch-all)
    """
    if not employees:
        return employees
    
    total = len(employees)
    
    for emp in employees:
        if emp.peer_rank is None:
            emp.performance_tier = "Not Ranked"
            continue
        
        # Calculate percentile (1 = top, 100 = bottom)
        percentile = (emp.peer_rank / total) * 100
        
        if percentile <= 25:
            emp.performance_tier = "Top Performer"
        elif percentile <= 50:
            emp.performance_tier = "Above Average"
        elif percentile <= 85:
            emp.performance_tier = "Below Average"
        else:
            emp.performance_tier = "Needs Immediate Improvement"
    
    return employees


def run_full_scoring(employees: List[EmployeeV2], settings: QuarterSettings) -> List[EmployeeV2]:
    """
    Run the complete scoring pipeline on a list of employees.
    Returns employees with all scores, bonuses, ranks, and tiers calculated.
    """
    # Step 1: Calculate derived metrics
    for emp in employees:
        calculate_derived_metrics(emp)
    
    # Step 2: Calculate normalized scores
    for emp in employees:
        calculate_normalized_scores(emp, settings)
    
    # Step 3: Calculate bonus points
    for emp in employees:
        calculate_bonus_points(emp, settings)
    
    # Step 4: Calculate total scores
    for emp in employees:
        calculate_total_score(emp, settings)
    
    # Step 5: Calculate rankings
    employees = calculate_rankings(employees)
    
    # Step 6: Assign performance tiers
    employees = calculate_performance_tiers(employees)
    
    # Step 7: Attach quarter/year and settings reference
    for emp in employees:
        emp.quarter = settings.quarter
        emp.year = settings.year
        emp.quarter_settings_id = settings.id
    
    return employees


# ============================================================================
# BENCHMARK SUGGESTION ENGINE
# ============================================================================

def suggest_benchmarks_from_previous(prev_avg: float, metric_type: str = "higher_better") -> Dict[str, float]:
    """
    Calculate benchmark suggestions based on previous quarter average.
    
    For higher-is-better metrics (PPA, LBW, Glassware):
        Low = Avg × 1.05
        High = Avg × 1.20
        Default = Avg × 1.15
    
    For inverse metrics (LSC):
        Low = Avg ÷ 1.20
        High = Avg ÷ 1.05
        Default = Avg ÷ 1.15
    """
    if metric_type == "higher_better":
        return {
            "low": round(prev_avg * 1.05, 2),
            "high": round(prev_avg * 1.20, 2),
            "default": round(prev_avg * 1.15, 2)
        }
    else:  # inverse (lower is better)
        return {
            "low": round(prev_avg / 1.20, 2),
            "high": round(prev_avg / 1.05, 2),
            "default": round(prev_avg / 1.15, 2)
        }


def calculate_previous_quarter_averages(employees: List[EmployeeV2]) -> Dict[str, float]:
    """
    Calculate averages from a list of employees (typically previous quarter).
    Returns averages for each metric.
    """
    if not employees:
        return {}
    
    valid_ppa = [e.ppa for e in employees if e.ppa is not None]
    valid_lbw = [e.lbw_per_guest for e in employees if e.lbw_per_guest is not None]
    valid_glass = [e.glassware_per_guest for e in employees if e.glassware_per_guest is not None]
    valid_lsc = [e.guests_per_lsc for e in employees if e.guests_per_lsc is not None]
    
    return {
        "avg_ppa": round(sum(valid_ppa) / len(valid_ppa), 2) if valid_ppa else None,
        "avg_lbw": round(sum(valid_lbw) / len(valid_lbw), 2) if valid_lbw else None,
        "avg_glass": round(sum(valid_glass) / len(valid_glass), 2) if valid_glass else None,
        "avg_lsc": round(sum(valid_lsc) / len(valid_lsc), 2) if valid_lsc else None,
    }


# ============================================================================
# VALIDATION
# ============================================================================

class ValidationResult(BaseModel):
    """Result of validating an employee row"""
    valid: bool
    employee_name: str
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


def validate_employee_row(row_data: Dict[str, Any], row_number: int) -> ValidationResult:
    """
    Validate a single employee row from upload.
    """
    errors = []
    warnings = []
    name = str(row_data.get("name", f"Row {row_number}"))
    
    # Check required fields
    if not row_data.get("name") or str(row_data.get("name")).strip() == "":
        errors.append("Employee Name is required")
    
    # Guests must be > 0
    guests = row_data.get("guests")
    if guests is None:
        errors.append("Guests is required")
    elif not isinstance(guests, (int, float)) or guests <= 0:
        errors.append(f"Guests must be > 0 (got: {guests})")
    
    # Net Sales >= 0
    net_sales = row_data.get("net_sales")
    if net_sales is None:
        errors.append("Net Sales is required")
    elif not isinstance(net_sales, (int, float)) or net_sales < 0:
        errors.append(f"Net Sales must be >= 0 (got: {net_sales})")
    
    # LBW >= 0
    lbw = row_data.get("lbw")
    if lbw is None:
        errors.append("LBW is required")
    elif not isinstance(lbw, (int, float)) or lbw < 0:
        errors.append(f"LBW must be >= 0 (got: {lbw})")
    
    # Glassware Sales >= 0
    glassware = row_data.get("glassware_sales")
    if glassware is None:
        errors.append("Glassware Sales is required")
    elif not isinstance(glassware, (int, float)) or glassware < 0:
        errors.append(f"Glassware Sales must be >= 0 (got: {glassware})")
    
    # LSC Count >= 0 (0 is allowed)
    lsc = row_data.get("lsc_count")
    if lsc is None:
        errors.append("LSC Count is required")
    elif not isinstance(lsc, (int, float)) or lsc < 0:
        errors.append(f"LSC Count must be >= 0 (got: {lsc})")
    
    return ValidationResult(
        valid=len(errors) == 0,
        employee_name=name,
        errors=errors,
        warnings=warnings
    )


def validate_upload_data(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate all rows in an upload.
    Returns summary of validation results.
    """
    results = []
    valid_count = 0
    invalid_count = 0
    names_seen = set()
    duplicate_names = []
    
    for idx, row in enumerate(rows, 1):
        result = validate_employee_row(row, idx)
        results.append(result)
        
        if result.valid:
            valid_count += 1
        else:
            invalid_count += 1
        
        # Check for duplicate names
        name = row.get("name", "").strip().lower()
        if name in names_seen:
            duplicate_names.append(name)
        names_seen.add(name)
    
    return {
        "valid": invalid_count == 0 and len(duplicate_names) == 0,
        "total_rows": len(rows),
        "valid_rows": valid_count,
        "invalid_rows": invalid_count,
        "duplicate_names": duplicate_names,
        "validation_results": results
    }
