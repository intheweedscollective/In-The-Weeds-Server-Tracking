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
    job_title: str = "Server"  # NEW: Job Title for hierarchy-based rankings
    guests: int  # Must be > 0
    net_sales: float
    
    # === ALCOHOL SALES (individual inputs - convenience fields) ===
    liquor_sales: float = 0.0  # Input only
    beer_sales: float = 0.0    # Input only
    wine_sales: float = 0.0    # Input only
    
    # === CALCULATED LBW (canonical - used for all scoring) ===
    lbw: float = 0.0  # AUTO-CALCULATED: liquor_sales + beer_sales + wine_sales
    
    # === OTHER CORE METRICS ===
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
    Q1 2026 Official Model: PPA(25%), LSC(25%), LBW(20%), Glass(15%), CV(15%)
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
    benchmark_cv: float = 5.0     # Expected CV score (baseline for normalization)
    
    # === METRIC WEIGHTS (must sum to 1.0) - Q1 2026 Official ===
    weight_ppa: float = 0.25      # Was 0.30
    weight_lbw: float = 0.20      # Was 0.25
    weight_glass: float = 0.15    # Was 0.20
    weight_lsc: float = 0.25      # Same
    weight_cv: float = 0.15       # NEW - Customer Voice & Review Tracker
    
    # === BONUS SETTINGS ===
    bonus_rate: float = 0.2  # 0.2 per 1% over benchmark
    bonus_cap: float = 5.0   # Max bonus per metric
    
    # === SERVER TIER THRESHOLDS (Settings-driven) ===
    a_server_min_score: float = 85.1   # Total Score >= this = A-Server
    b_server_min_score: float = 70.1   # Total Score >= this AND < A-Server = B-Server
    # C-Server: Total Score < B-Server min
    
    # === PREVIOUS QUARTER AVERAGES (for benchmark suggestions) ===
    prev_avg_ppa: Optional[float] = None
    prev_avg_lbw: Optional[float] = None
    prev_avg_glass: Optional[float] = None
    prev_avg_lsc: Optional[float] = None
    
    # === SLIDE THEME SETTINGS (Per-Quarter Customization) ===
    slide_theme: str = "dark_navy"  # Pre-built themes: dark_navy, light_corporate, bubba_red, ocean_blue, custom
    slide_bg_color: str = "#0A1628"  # Background color (for custom theme)
    slide_bg_gradient: str = "#132238"  # Gradient end color
    slide_text_color: str = "#FFFFFF"  # Primary text color
    slide_accent_color: str = "#D12E2E"  # Accent color (Bubba Gump red)
    slide_secondary_color: str = "#005B96"  # Secondary accent
    slide_custom_bg_image: Optional[str] = None  # Base64 or URL for custom background
    
    # === SEASONAL THEME (Holiday Decorations) ===
    # Options: "auto" (detect by date), "none" (no seasonal), or specific:
    # "valentines", "st_patricks", "easter", "july_4th", "halloween", "thanksgiving", "christmas", "new_year"
    slide_seasonal_theme: str = "auto"  # Default to auto-detect
    
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
    # Core metrics
    "name": ["employee name", "name", "server", "employee", "team member"],
    "job_title": ["job title", "title", "position", "role"],  # NEW: Job Title for hierarchy
    "guests": ["guests", "guest count", "covers", "total guests"],
    "net_sales": ["net sales", "sales", "total sales", "net", "netsales"],
    
    # Alcohol Sales (individual inputs - LBW calculated from these)
    "liquor_sales": ["liquor sales", "liquor", "spirits", "spirits sales"],
    "beer_sales": ["beer sales", "beer"],
    "wine_sales": ["wine sales", "wine"],
    
    # Other core metrics
    "glassware_sales": ["glassware sales", "glassware", "souvenir glass", "glass sales"],
    "lsc_count": ["lsc count", "lsc", "loyalty", "loyalty sign ups", "enrollments", "memberships"],
    
    # Customer Voice (NPS-style)
    "cv_promoters": ["cv promoters", "promoters", "cv 9-10", "nps promoters"],
    "cv_passives": ["cv passives", "passives", "cv 7-8", "nps passives"],
    "cv_detractors": ["cv detractors", "detractors", "cv 0-6", "nps detractors"],
    
    # Review Tracker
    "review_mentions": ["review mentions", "mentions", "positive mentions", "named mentions", "review tracker count"],
    
    # Legacy optional (text fields)
    "review_tracker": ["review tracker text", "reviews text"],
    "cv_positive": ["cv positive", "cv+", "positive feedback"],
    "cv_negative": ["cv negative", "cv-", "negative feedback"],
}

# Columns that should NOT be accepted (they are derived, not raw)
REJECTED_COLUMNS = [
    "ppa", "per person average",
    "pplbw", "lbw per guest", "alcohol per guest",
    "gpg", "glass per guest", "glassware per guest",
    "guests per lsc",
    # LBW total is now REJECTED - must be calculated from Liquor + Beer + Wine
    "lbw", "lbw sales", "lbw total", "total lbw", "alcohol", "alcohol sales", 
    "liquor beer wine", "liquor+beer+wine", "total alcohol",
]


def find_column_match(df_columns: List[str], canonical_field: str) -> Optional[str]:
    """
    Find matching column in dataframe for a canonical field.
    Returns the actual column name from the dataframe, or None if not found.
    """
    candidates = CANONICAL_COLUMN_MAPPING.get(canonical_field, [])
    # Handle None column names safely
    df_columns_lower = {str(col).lower().strip(): col for col in df_columns if col is not None}
    
    for candidate in candidates:
        if candidate in df_columns_lower:
            return df_columns_lower[candidate]
    
    return None


def validate_upload_columns(df_columns: List[str]) -> Dict[str, Any]:
    """
    Validate that required columns exist and return mapping.
    
    Required: name, guests, net_sales, liquor_sales, beer_sales, wine_sales, 
              glassware_sales, lsc_count
    
    REJECTED: Any form of "LBW" total column - must use individual alcohol fields
    
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
    
    # Required fields - note: lbw is now calculated from liquor+beer+wine
    required_fields = [
        "name", "guests", "net_sales", 
        "liquor_sales", "beer_sales", "wine_sales",  # Individual alcohol inputs
        "glassware_sales", "lsc_count"
    ]
    optional_fields = [
        "job_title",  # NEW: Job Title for hierarchy-based rankings
        "cv_promoters", "cv_passives", "cv_detractors",  # Customer Voice
        "review_mentions",  # Review Tracker
        "review_tracker", "cv_positive", "cv_negative"   # Legacy text fields
    ]
    
    # Handle None column names safely
    df_columns_lower = [str(col).lower().strip() for col in df_columns if col is not None]
    
    # Check for rejected (derived) columns - especially LBW totals
    for rejected in REJECTED_COLUMNS:
        if rejected in df_columns_lower:
            result["rejected"].append(rejected)
    
    if result["rejected"]:
        # Check if it's specifically an LBW total column
        lbw_rejected = [r for r in result["rejected"] if 'lbw' in r or 'alcohol' in r]
        if lbw_rejected:
            result["warnings"].append(
                f"Found LBW/alcohol total column(s): {', '.join(lbw_rejected)}. "
                "LBW must be calculated from individual Liquor, Beer, and Wine columns. "
                "Please use columns: 'Liquor Sales', 'Beer Sales', 'Wine Sales' instead."
            )
        else:
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

def calculate_lbw_total(employee: EmployeeV2) -> EmployeeV2:
    """
    Calculate LBW Total from individual Liquor, Beer, and Wine sales.
    This is the ONLY way LBW can be set - no manual override allowed.
    Missing/blank values are treated as zero.
    """
    liquor = employee.liquor_sales or 0.0
    beer = employee.beer_sales or 0.0
    wine = employee.wine_sales or 0.0
    
    employee.lbw = round(liquor + beer + wine, 2)
    return employee


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


def calculate_customer_voice_score(employee: EmployeeV2) -> EmployeeV2:
    """
    Calculate Customer Voice score using NPS-style logic.
    
    - Promoters (9-10): +1 point each
    - Passives (7-8): 0 points
    - Detractors (0-6): -2 points each
    
    Quarterly caps: +10 max, -6 min
    """
    # Calculate raw CV points
    promoter_points = employee.cv_promoters * CV_PROMOTER_POINTS
    passive_points = employee.cv_passives * CV_PASSIVE_POINTS
    detractor_points = employee.cv_detractors * CV_DETRACTOR_POINTS
    
    raw_points = promoter_points + passive_points + detractor_points
    employee.cv_raw_points = round(raw_points, 2)
    
    # Apply quarterly caps
    capped_score = max(CV_MIN_POINTS, min(CV_MAX_POINTS, raw_points))
    employee.cv_score = round(capped_score, 2)
    
    return employee


def calculate_review_tracker_bonus(employee: EmployeeV2) -> EmployeeV2:
    """
    Calculate Review Tracker bonus from external platform mentions.
    
    - Every 5 positive named mentions = +1 bonus point
    - Quarterly cap: +10 bonus points
    - No negative penalties from external platforms
    """
    if employee.review_mentions > 0:
        bonus = employee.review_mentions // RT_MENTIONS_PER_POINT
        employee.review_tracker_bonus = round(min(bonus, RT_MAX_BONUS), 2)
    else:
        employee.review_tracker_bonus = 0
    
    return employee


def calculate_dar_penalty(employee: EmployeeV2) -> EmployeeV2:
    """
    Calculate DAR (Disciplinary Action Report) penalty.
    
    - Written Warning: -3 points
    - Suspension: -5 points
    
    Applied AFTER all other scoring, not visible in rankings.
    """
    warning_penalty = employee.dar_written_warnings * DAR_WRITTEN_WARNING
    suspension_penalty = employee.dar_suspensions * DAR_SUSPENSION
    
    employee.dar_penalty = round(warning_penalty + suspension_penalty, 2)
    
    return employee


def calculate_normalized_scores(employee: EmployeeV2, settings: QuarterSettings) -> EmployeeV2:
    """
    Calculate normalized scores (Q-T logic).
    Score = (Employee Metric / Benchmark) * 100
    
    For LSC (inverse): Score = (Benchmark / Employee Metric) * 100
    For CV: Normalize to 0-100 scale based on benchmark
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
    
    # Customer Voice Score (normalize CV + Review Tracker to 0-100 scale)
    # CV ranges from -6 to +10, Review Tracker from 0 to +10
    # Combined max: 20, min: -6
    # Normalize: ((actual - min) / (max - min)) * 100
    cv_combined = (employee.cv_score or 0) + (employee.review_tracker_bonus or 0)
    cv_min, cv_max = -6, 20
    employee.score_cv = round(((cv_combined - cv_min) / (cv_max - cv_min)) * 100, 2)
    
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
    
    employee.total_metric_bonus = round(
        employee.bonus_ppa + employee.bonus_lbw + 
        employee.bonus_glass + employee.bonus_lsc, 2
    )
    
    return employee


def calculate_total_score(employee: EmployeeV2, settings: QuarterSettings) -> EmployeeV2:
    """
    Calculate weighted score + total score.
    
    Q1 2026 Official Formula:
    Final Score = Weighted(PPA + LSC + LBW + Glass + CV) 
                  + Review Tracker Bonus 
                  + Metric Bonuses
                  - DAR Penalties
    """
    # Calculate weighted score from all 5 metrics
    employee.weighted_score = round(
        (employee.score_ppa or 0) * settings.weight_ppa +
        (employee.score_lbw or 0) * settings.weight_lbw +
        (employee.score_glass or 0) * settings.weight_glass +
        (employee.score_lsc or 0) * settings.weight_lsc +
        (employee.score_cv or 0) * settings.weight_cv,
        2
    )
    
    # Pre-DAR score (shown in rankings)
    employee.pre_dar_score = round(
        employee.weighted_score + 
        (employee.total_metric_bonus or 0) +
        (employee.review_tracker_bonus or 0),
        2
    )
    
    # Final total score (includes DAR, admin-only)
    employee.total_score = round(
        employee.pre_dar_score + (employee.dar_penalty or 0),
        2
    )
    
    return employee


def calculate_rankings(employees: List[EmployeeV2]) -> List[EmployeeV2]:
    """
    Rank employees by pre_dar_score (descending).
    DAR penalties are NOT visible in rankings per spec.
    """
    # Sort by pre_dar_score (before DAR penalties)
    sorted_employees = sorted(
        employees, 
        key=lambda e: e.pre_dar_score or 0, 
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
    Run the complete Q1 2026 scoring pipeline on a list of employees.
    Returns employees with all scores, bonuses, ranks, and tiers calculated.
    
    Pipeline:
    1. Calculate LBW Total from Liquor + Beer + Wine (mandatory first step)
    2. Derived metrics (PPA, LBW/G, Glass/G, G/LSC)
    3. Customer Voice score (NPS-style)
    4. Review Tracker bonus
    5. Normalized scores (benchmark-relative)
    6. Metric bonus points (exceeding benchmarks)
    7. DAR penalties (applied last, hidden from rankings)
    8. Total scores
    9. Rankings (based on pre-DAR score)
    10. Performance tiers
    """
    # Step 1: Calculate LBW Total from individual alcohol sales (MANDATORY)
    for emp in employees:
        calculate_lbw_total(emp)
    
    # Step 2: Calculate derived metrics
    for emp in employees:
        calculate_derived_metrics(emp)
    
    # Step 3: Calculate Customer Voice score
    for emp in employees:
        calculate_customer_voice_score(emp)
    
    # Step 4: Calculate Review Tracker bonus
    for emp in employees:
        calculate_review_tracker_bonus(emp)
    
    # Step 5: Calculate normalized scores (including CV)
    for emp in employees:
        calculate_normalized_scores(emp, settings)
    
    # Step 6: Calculate metric bonus points
    for emp in employees:
        calculate_bonus_points(emp, settings)
    
    # Step 7: Calculate DAR penalties
    for emp in employees:
        calculate_dar_penalty(emp)
    
    # Step 8: Calculate total scores
    for emp in employees:
        calculate_total_score(emp, settings)
    
    # Step 9: Calculate rankings (based on pre_dar_score)
    employees = calculate_rankings(employees)
    
    # Step 10: Assign performance tiers
    employees = calculate_performance_tiers(employees)
    
    # Step 11: Attach quarter/year and settings reference
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
    raw_name = row_data.get("name")
    name = str(raw_name) if raw_name is not None else f"Row {row_number}"
    
    # Check required fields
    if raw_name is None or str(raw_name).strip() == "":
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
        raw_name = row.get("name")
        # Handle both None and pandas NaN
        if raw_name is not None and not (isinstance(raw_name, float) and pd.isna(raw_name)):
            name = str(raw_name).strip().lower()
        else:
            name = ""
        if name and name in names_seen:
            duplicate_names.append(name)
        if name:
            names_seen.add(name)
    
    return {
        "valid": invalid_count == 0 and len(duplicate_names) == 0,
        "total_rows": len(rows),
        "valid_rows": valid_count,
        "invalid_rows": invalid_count,
        "duplicate_names": duplicate_names,
        "validation_results": results
    }


# ============================================================================
# HIERARCHY-BASED RANKINGS (Settings-Driven Server Tiering)
# ============================================================================

def classify_employee_role(employee: EmployeeV2, settings: QuarterSettings) -> Dict[str, Any]:
    """
    Classify employee into hierarchy tier based on job title and score.
    
    FIXED HIERARCHY ORDER (overrides raw score):
    1. Trainer (Job Title contains "Trainer")
    2. Bartender (Job Title contains "Bartender" or "Bar")
    3. A-Server (Score >= A-Server min threshold)
    4. B-Server (Score >= B-Server min AND < A-Server min)
    5. C-Server (Score < B-Server min)
    
    Returns: {
        "hierarchy_rank": 1-5 (1=highest priority),
        "tier_label": "Trainer" | "Bartender" | "A-Server" | "B-Server" | "C-Server",
        "tier_sort_order": int for sorting within hierarchy
    }
    """
    job_title = (employee.job_title or "Server").strip().lower()
    score = employee.pre_dar_score or employee.total_score or 0
    
    # Check for Trainer (highest priority)
    if "trainer" in job_title:
        return {
            "hierarchy_rank": 1,
            "tier_label": "Trainer",
            "tier_sort_order": 1
        }
    
    # Check for Bartender
    if "bartender" in job_title or "bar" in job_title:
        return {
            "hierarchy_rank": 2,
            "tier_label": "Bartender",
            "tier_sort_order": 2
        }
    
    # Server tiers based on score thresholds from settings
    if score >= settings.a_server_min_score:
        return {
            "hierarchy_rank": 3,
            "tier_label": "A-Server",
            "tier_sort_order": 3
        }
    elif score >= settings.b_server_min_score:
        return {
            "hierarchy_rank": 4,
            "tier_label": "B-Server",
            "tier_sort_order": 4
        }
    else:
        return {
            "hierarchy_rank": 5,
            "tier_label": "C-Server",
            "tier_sort_order": 5
        }


def generate_hierarchy_rankings(employees: List[EmployeeV2], settings: QuarterSettings) -> List[Dict[str, Any]]:
    """
    Generate hierarchy-based rankings with position labels (Bar1, A1, B1, etc.)
    
    SORTING RULES:
    1. Sort by hierarchy tier (Trainers first, then Bartenders, then A/B/C Servers)
    2. Within each tier, sort by Total Score descending
    
    Position Labels:
    - Trainers: T1, T2, T3...
    - Bartenders: Bar1, Bar2, Bar3...
    - A-Servers: A1, A2, A3...
    - B-Servers: B1, B2, B3...
    - C-Servers: C1, C2, C3...
    """
    # Classify each employee
    classified = []
    for emp in employees:
        classification = classify_employee_role(emp, settings)
        classified.append({
            "employee": emp,
            "hierarchy_rank": classification["hierarchy_rank"],
            "tier_label": classification["tier_label"],
            "tier_sort_order": classification["tier_sort_order"],
            "score": emp.pre_dar_score or emp.total_score or 0
        })
    
    # Sort: first by hierarchy_rank (ascending), then by score (descending)
    classified.sort(key=lambda x: (x["hierarchy_rank"], -x["score"]))
    
    # Assign position labels within each tier
    tier_counters = {
        "Trainer": 0,
        "Bartender": 0,
        "A-Server": 0,
        "B-Server": 0,
        "C-Server": 0
    }
    
    tier_prefixes = {
        "Trainer": "T",
        "Bartender": "Bar",
        "A-Server": "A",
        "B-Server": "B",
        "C-Server": "C"
    }
    
    results = []
    for idx, item in enumerate(classified, 1):
        tier = item["tier_label"]
        tier_counters[tier] += 1
        position_label = f"{tier_prefixes[tier]}{tier_counters[tier]}"
        
        emp = item["employee"]
        results.append({
            "position": idx,  # Overall position (1 to N)
            "position_label": position_label,  # Bar1, A1, etc.
            "tier_label": tier,
            "employee_id": emp.id,
            "name": emp.name,
            "job_title": emp.job_title or "Server",
            "total_score": round(item["score"], 2),
            "bonus_points": round((emp.total_metric_bonus or 0) + (emp.review_tracker_bonus or 0), 2),
            "ppa_points": {
                "earned": round(min((emp.score_ppa or 0), 100) * 0.25 + (emp.bonus_ppa or 0), 2),
                "possible": 30
            },
            "lbw_points": {
                "earned": round(min((emp.score_lbw or 0), 100) * 0.20 + (emp.bonus_lbw or 0), 2),
                "possible": 25
            },
            "lsc_points": {
                "earned": round(min((emp.score_lsc or 0), 100) * 0.25 + (emp.bonus_lsc or 0), 2),
                "possible": 30
            },
            "glassware_points": {
                "earned": round(min((emp.score_glass or 0), 100) * 0.15 + (emp.bonus_glass or 0), 2),
                "possible": 20
            },
            "performance_tier": emp.performance_tier
        })
    
    return results

