"""
Restaurant Performance Engine v2.4
Q1 2026 HYBRID Scoring Model - Bubba Gump Shrimp Co.

SCORING MODEL (Hybrid - Spec NPS + Current Promoter Logic):
============================================================

1. WEIGHTED POS METRICS (75 pts max):
   - PPA: 25%
   - LSC: 25%
   - LBW: 15%
   - Glassware: 10%

2. REVIEW TRACKER: +0.5 pts per mention (capped at 15 pts)

3. CUSTOMER VOICE (NPS from Spec + Promoters from Current):
   
   NPS Score (max 10 pts - from Spec):
   - NPS 90-100 = 10 pts
   - NPS 80-89 = 9 pts
   - NPS 70-79 = 8 pts
   - NPS 60-69 = 7 pts
   - NPS 50-59 = 6 pts
   - Below 50 = scaled proportionally
   
   Promoter/Detractor Points (NO CAP - from Current):
   - Promoter (9-10 rating): +1 pt each
   - Detractor (6 or below): -2 pts each
   
   Full CV Formula: (Promoters × 1) + (RT Mentions × 0.5) - (Detractors × 2)

4. METRIC BONUSES (up to 20 pts total):
   - 5 pts max per metric (PPA, LSC, LBW, Glassware)
   - Linear scale from 100%-120% of benchmark

5. DAR: Disciplinary penalties (admin-only, applied at final stage)

TOTAL SCORE = Weighted POS (75 max) + Review Tracker + CV Score + Metric Bonuses (20 max) - DAR
"""

from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
import uuid
import math
import pandas as pd


# ============================================================================
# SCORING CONSTANTS
# ============================================================================

# Customer Voice scoring
CV_PROMOTER_POINTS = 1.0  # +1 per promoter (9-10 rating)
CV_PASSIVE_POINTS = 0     # 0 for passive (7-8)
CV_DETRACTOR_POINTS = -2  # -2 per detractor (6 or below)

# NPS Score: Direct ratio (77% = 7.7 pts, max 10 pts)
NPS_MAX_POINTS = 10

# Review Tracker Bonus — per v3 handout: +0.3 per mention, quarterly cap +20
RT_POINTS_PER_MENTION = 0.3  # Each mention = 0.3 points
RT_MAX_POINTS = 20           # Cap at 20 points (~67 mentions)

# Metric Bonus Settings (User Confirmed)
# 5 pts max per metric, linear scale from 100%-120%
METRIC_BONUS_MAX = 5.0       # Max bonus per metric
METRIC_BONUS_THRESHOLD = 120 # At 120%+, get full 5 pts

# DAR Penalties
DAR_WRITTEN_WARNING = -3
DAR_SUSPENSION = -5

# Legacy constants (kept for backwards compatibility)
NPS_WEIGHT = 0.10
CV_MIN_POINTS = -6
CV_MAX_POINTS = 10


# MAX SCORE BREAKDOWN (User Confirmed Model):
# Weighted POS: 75 pts (PPA 25 + LSC 25 + LBW 15 + Glass 10)
# Metric Bonuses: 20 pts (PPA 5 + LSC 5 + LBW 5 + Glass 5)
# Review Tracker Bonus: Mentions × 0.5 pts (capped at 15 pts)
# Customer Voice: NPS Bonus (0-10 pts) + Survey Points (+1 promoter, -2 detractor, NO CAP)
# CV Formula: (Promoters × 1) + (RT Mentions × 0.5) - (Detractors × 2)
# TOTAL: 95+ pts base possible, plus uncapped CV bonuses


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
    name: str              # Report name (backend-only — used for ingestion/matching)
    display_name: Optional[str] = None  # User-facing. First word rendered everywhere.
    job_title: str = "Server"  # NEW: Job Title for hierarchy-based rankings
    aliases: List[str] = Field(default_factory=list)  # Nicknames for name matching (e.g., ["Trey", "T.Q."])
    guests: int = 0  # Must be > 0
    net_sales: float = 0.0
    
    # === ALCOHOL SALES (individual inputs - convenience fields) ===
    liquor_sales: float = 0.0  # Input only
    beer_sales: float = 0.0    # Input only
    wine_sales: float = 0.0    # Input only
    
    # === CALCULATED LBW (canonical - used for all scoring) ===
    lbw: float = 0.0  # AUTO-CALCULATED: liquor_sales + beer_sales + wine_sales
    
    # === OTHER CORE METRICS ===
    glassware_sales: float = 0.0  # Total glassware dollars
    lsc_count: int = 0  # LSC signups count, >= 0
    
    # === CUSTOMER VOICE FIELDS (from upload) ===
    cv_promoters: int = 0       # Count of 9-10 scores (service-related only)
    cv_passives: int = 0        # Count of 7-8 scores
    cv_detractors: int = 0      # Count of 6 or below scores
    nps_score: Optional[float] = None  # NPS % from Loyalty Voice sync
    cv_source: Optional[str] = None    # "loyalty_voice_sync" or "spreadsheet"
    
    # === REVIEW TRACKER FIELDS (from upload) ===
    review_mentions: int = 0    # Named positive mentions from external platforms
    review_source: Optional[str] = None  # "reviewtrackers_sync" or "spreadsheet"
    
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
    cv_raw_points: Optional[float] = None      # Raw CV calculation (promoter/detractor pts)
    nps_contribution: Optional[float] = None   # NPS% × 10% weight contribution
    cv_score: Optional[float] = None           # CV bonus (promoter/detractor pts only)
    score_cv: Optional[float] = None           # Normalized for weighting (0-100 scale)
    cv_penalty: Optional[float] = None         # Negative CV penalty (applied to final score)
    
    # === REVIEW TRACKER BONUS ===
    review_tracker_bonus: Optional[float] = None
    
    # === COMBINED CV + REVIEW TRACKER (capped at 20 total) ===
    cv_rt_combined: Optional[float] = None     # Combined CV + RT (max 20 per quarter)
    
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
    Q1 2026 User Confirmed Model: PPA(25%), LSC(25%), LBW(15%), Glass(10%)
    CV and Review Tracker are handled as separate bonuses (not weighted)
    """
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    year: int
    quarter: str  # Q1, Q2, Q3, Q4
    
    # === BENCHMARKS (editable before lock) ===
    benchmark_ppa: float = 55.0
    benchmark_lbw: float = 8.0
    benchmark_glass: float = 1.35  # Per handout v3: $1.35 per person
    benchmark_lsc: float = 100.0   # Guests per LSC (lower is better)
    benchmark_cv: float = 5.0     # Expected CV score (baseline for reference)
    
    # === METRIC WEIGHTS (Per-Quarter — historical quarters stay frozen) ===
    # v3 model (Q1 2026 and earlier): 25/25/20/15
    # v3-2 model (Q2 2026+):         27.5/27.5/20/15
    weight_ppa: float = 0.25
    weight_lsc: float = 0.25
    weight_lbw: float = 0.20
    weight_glass: float = 0.15
    weight_cv: float = 0.00       # CV is kept as a bonus (promoter/detractor formula), not weighted
    
    # === BONUS SETTINGS (User Confirmed) ===
    bonus_rate: float = 0.25  # (score - 100) / 20 * 5 = linear to 5 pts at 120%
    bonus_cap: float = 5.0   # Max bonus per metric

    # === REVIEW TRACKER (Per-Quarter — historical quarters stay frozen) ===
    # v2 model (pre-Q2 2026): 0.5 pts/mention, cap 15
    # v3 model (Q2 2026+):    0.3 pts/mention, cap 20
    rt_points_per_mention: float = 0.3
    rt_max_points: float = 20.0
    
    # === SERVER TIER THRESHOLDS (Settings-driven) ===
    a_server_min_score: float = 85.0   # Total Score >= 85 = A-Server
    b_server_min_score: float = 70.0   # Total Score >= 70 AND < 85 = B-Server
    # C-Server: Total Score < 70
    
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
    
    # Customer Voice and Review data now comes from automated sync
    # These columns are NO LONGER NEEDED in the spreadsheet upload
    # CV data synced from Loyalty Voice, Review data synced from ReviewTrackers
    
    # Legacy optional (text fields - deprecated)
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
        "job_title",  # Job Title for hierarchy-based rankings
        # CV and Review data now comes from automated sync - removed from spreadsheet
        # "cv_promoters", "cv_passives", "cv_detractors",  # Customer Voice - AUTO SYNCED
        # "review_mentions",  # Review Tracker - AUTO SYNCED
        "review_tracker", "cv_positive", "cv_negative"   # Legacy text fields (deprecated)
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
    Calculate Customer Voice score (CV).

    Per spec: CV Score = NPS%/10 + (Promoters × +1) + (Detractors × -2)

    - NPS contribution (NPS%/10): up to ~10 pts (e.g. NPS 77 → 7.7 pts)
    - Promoter (9-10 rating): +1 pt each
    - Detractor (≤6): -2 pts each
    - Passive (7-8): 0 pts

    The combined CV Score is added once to the total score (no separate
    nps_contribution add-on; that piece now lives inside cv_score).
    """
    # NPS normalized to 0-100
    nps = employee.nps_score or 0
    nps_normalized = min(max(nps, 0), 100)

    # NPS contribution (kept on the model for transparency / display)
    employee.nps_contribution = round(nps_normalized * 0.10, 2)

    # Combined CV: NPS%/10 + promoter/detractor adjustments (NO CAP)
    promoters = employee.cv_promoters or 0
    detractors = employee.cv_detractors or 0
    cv_bonus = (promoters * CV_PROMOTER_POINTS) + (detractors * CV_DETRACTOR_POINTS)

    employee.cv_score = round(employee.nps_contribution + cv_bonus, 2)
    employee.cv_raw_points = round(cv_bonus, 2)  # Promoter/detractor only, for breakdowns

    return employee


def calculate_review_tracker_bonus(
    employee: EmployeeV2,
    settings: Optional["QuarterSettings"] = None,
) -> EmployeeV2:
    """
    Calculate Review Tracker bonus from external review mentions.

    Per-quarter coefficients (settings.rt_points_per_mention, settings.rt_max_points)
    — historical quarters keep their original rule (e.g. Q1 2026 = 0.5/cap 15,
    Q2 2026+ = 0.3/cap 20 per v3 handout). Falls back to module constants if
    settings is not supplied.
    """
    coef = settings.rt_points_per_mention if settings else RT_POINTS_PER_MENTION
    cap  = settings.rt_max_points         if settings else RT_MAX_POINTS
    review_bonus = (employee.review_mentions or 0) * coef
    review_bonus = min(review_bonus, cap)
    employee.review_tracker_bonus = round(review_bonus, 2)
    return employee


def calculate_combined_cv_rt(employee: EmployeeV2) -> EmployeeV2:
    """
    Store combined CV + Review Tracker for reference.
    
    CV (NPS-based) is part of base score (15% weight).
    Review Tracker is a separate bonus.
    """
    # Store combined score for reference
    employee.cv_rt_combined = round(
        (employee.cv_score or 0) + (employee.review_tracker_bonus or 0), 2
    )
    
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
    For CV/NPS: Already calculated as points in calculate_customer_voice_score
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
    
    # Customer Voice Score - NPS-based (already calculated as points)
    # cv_score contains: NPS% × 0.15 (0-15 points)
    # This is the actual weighted contribution to total score
    employee.score_cv = employee.cv_score or 0
    employee.cv_penalty = 0  # No penalty in new model
    
    return employee


def calculate_bonus_points(employee: EmployeeV2, settings: QuarterSettings) -> EmployeeV2:
    """
    Calculate metric bonus points (User Confirmed Model).
    
    NEW MODEL:
    - 5 pts max for each metric (PPA, LSC, LBW, Glassware)
    - Based on how much they exceed benchmark:
      - 120%+ of benchmark = 5 pts (max)
      - 100%-120% = linear scale (e.g., 110% = 2.5 pts, 105% = 1.25 pts)
      - Below 100% = 0 pts bonus
    
    Formula: bonus = ((score% - 100) / 20) * 5, capped at 5
    """
    def calc_bonus(score: Optional[float]) -> float:
        if score is None or score <= 100:
            return 0
        # Linear scale from 100% to 120%
        # At 100%: 0 pts, at 110%: 2.5 pts, at 120%+: 5 pts
        excess_percent = score - 100  # How much over 100%
        bonus = (excess_percent / 20) * 5  # Scale to 5 pts max at 20% over
        return min(bonus, 5.0)  # Cap at 5 pts
    
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
    Calculate weighted score + total score using CORRECT FORMULA.
    
    SCORING MODEL:
    ==============
    1. WEIGHTED POS METRICS (75% of base):
       - PPA: 25%
       - LSC: 25%  
       - LBW: 15%
       - Glassware: 10%
    
    2. NPS SCORE (10% of base):
       - NPS normalized (0-100) × 10%
       - e.g., NPS 77% = 7.7 pts
    
    3. CV BONUS (NO CAP):
       - +1 pt per promoter (9-10 rating)
       - -2 pts per detractor (6 or below)
    
    4. REVIEW TRACKER BONUS (capped at 15 pts):
       - +0.5 pts per mention
    
    5. METRIC BONUSES (up to 20 pts total, 5 per metric):
       - Linear scale from 100%-120% of benchmark
       - 0.25 pts per 1% above benchmark
    
    TOTAL = Weighted POS (75%) + NPS (10%) + CV Bonus + RT Bonus + Metric Bonuses
    """
    # Cap each metric score at 100 before applying weight
    capped_ppa = min((employee.score_ppa or 0), 100)
    capped_lbw = min((employee.score_lbw or 0), 100)
    capped_glass = min((employee.score_glass or 0), 100)
    capped_lsc = min((employee.score_lsc or 0), 100)
    
    # Calculate weighted POS score using per-quarter weights
    weighted_pos_score = round(
        capped_ppa * settings.weight_ppa +
        capped_lsc * settings.weight_lsc +
        capped_lbw * settings.weight_lbw +
        capped_glass * settings.weight_glass,
        2
    )
    
    # NPS contribution is now bundled into cv_score (see
    # calculate_customer_voice_score). No separate weighted_score add-on.
    employee.weighted_score = round(weighted_pos_score, 2)
    
    # Get CV bonus (now NPS%/10 + promoter/detractor, NO CAP)
    cv_bonus = employee.cv_score or 0
    
    # Get Review Tracker bonus (0.5 pts per mention, capped at 15)
    review_bonus = employee.review_tracker_bonus or 0
    
    # Get metric bonuses (up to 20 pts total)
    metric_bonus = employee.total_metric_bonus or 0
    
    # Pre-DAR score (shown in rankings)
    # = Weighted Score (POS + NPS) + CV Bonus + RT Bonus + Metric Bonuses
    employee.pre_dar_score = round(
        employee.weighted_score + 
        cv_bonus +
        review_bonus +
        metric_bonus,
        2
    )
    
    # Final total score (includes DAR penalties, admin-only)
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
    5. Apply combined CV + RT cap (max 20 points per quarter)
    6. Normalized scores (benchmark-relative)
    7. Metric bonus points (exceeding benchmarks)
    8. DAR penalties (applied last, hidden from rankings)
    9. Total scores
    10. Rankings (based on pre-DAR score)
    11. Performance tiers
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
    
    # Step 4: Calculate Review Tracker bonus (per-quarter coefficients)
    for emp in employees:
        calculate_review_tracker_bonus(emp, settings)
    
    # Step 5: Apply combined CV + RT cap (max 20 per quarter)
    for emp in employees:
        calculate_combined_cv_rt(emp)
    
    # Step 6: Calculate normalized scores (including CV)
    for emp in employees:
        calculate_normalized_scores(emp, settings)
    
    # Step 7: Calculate metric bonus points
    for emp in employees:
        calculate_bonus_points(emp, settings)
    
    # Step 8: Calculate DAR penalties
    for emp in employees:
        calculate_dar_penalty(emp)
    
    # Step 9: Calculate total scores
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


def get_first_name(full_name: str) -> str:
    """DEPRECATED: use get_display_first_name(employee) instead.

    Kept for backwards compatibility with legacy callers that only have a
    bare name string. For any employee-aware rendering path, use
    `get_display_first_name` so Display Name takes precedence over raw
    report_name.
    """
    if not full_name:
        return "Unknown"
    parts = full_name.strip().split()
    if parts:
        return parts[0]
    return full_name


def get_display_first_name(employee) -> str:
    """Return the ONLY string allowed in user-facing outputs.

    Rules (per product directive):
      1. Prefer `display_name`. Return its first word.
      2. If display_name is empty, fallback to first word of `name`
         (report_name is stored there for legacy snapshot rows).
      3. Never return a full name or last name.
      4. Case is preserved; whitespace is trimmed.

    Accepts either an EmployeeV2 pydantic model OR a dict. Safe to call
    on incomplete records — returns "Unknown" if both fields are missing.
    """
    if employee is None:
        return "Unknown"
    if hasattr(employee, "model_dump"):
        display = getattr(employee, "display_name", None)
        report = getattr(employee, "name", None)
    else:
        display = employee.get("display_name")
        report = employee.get("name") or employee.get("report_name")
    for candidate in (display, report):
        if candidate and str(candidate).strip():
            parts = str(candidate).strip().split()
            if parts:
                return parts[0]
    return "Unknown"
    parts = full_name.strip().split()
    if parts:
        return parts[0]
    return full_name


def generate_hierarchy_rankings(employees: List[EmployeeV2], settings: QuarterSettings, first_name_only: bool = True) -> List[Dict[str, Any]]:
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
        
        # Review Bonus — per-quarter coefficients (historical quarters stay frozen).
        review_mentions = emp.review_mentions or 0
        review_bonus = min(
            review_mentions * settings.rt_points_per_mention,
            settings.rt_max_points,
        )
        
        # Metric Bonus: bonuses from exceeding benchmarks in metrics (PPA, LBW, LSC, Glass)
        metric_bonus = emp.total_metric_bonus or 0
        
        # NPS Score: Already weighted (NPS% × 0.15, max 15 pts) - part of base score
        nps_score = emp.nps_score or 0
        nps_points = emp.cv_score or 0  # cv_score now contains NPS points
        
        results.append({
            "position": idx,  # Overall position (1 to N)
            "position_label": position_label,  # Bar1, A1, etc.
            "tier_label": tier,
            "employee_id": emp.id,
            "name": get_display_first_name(emp) if first_name_only else (emp.display_name or emp.name),
            "job_title": emp.job_title or "Server",
            "total_score": round(item["score"], 2),
            "bonus_points": round(metric_bonus + review_bonus, 2),
            "review_bonus": round(review_bonus, 2),
            "metric_bonus": round(metric_bonus, 2),
            "combined_review_bonus": round(review_bonus + nps_points, 2),  # RT + NPS combined
            # Raw metric values
            "ppa": emp.ppa or 0,
            "lbw_per_guest": emp.lbw_per_guest or 0,
            "glassware_per_guest": emp.glassware_per_guest or 0,
            "guests_per_lsc": emp.guests_per_lsc or 0,
            "guest_count": emp.guests or 0,
            "net_sales": emp.net_sales or 0,
            # Percentage scores (0-100)
            "ppa_percentage": emp.score_ppa or 0,
            "lbw_percentage": emp.score_lbw or 0,
            "glassware_percentage": emp.score_glass or 0,
            "lsc_percentage": emp.score_lsc or 0,
            # NPS data
            "nps_score": nps_score,
            "nps_points": round(nps_points, 2),
            # Customer Voice data (for separate CV Score column)
            "cv_promoters": emp.cv_promoters or 0,
            "cv_detractors": emp.cv_detractors or 0,
            "cv_score": emp.cv_score or 0,  # Promoters × 0.5 - Detractors × 1
            # Review data
            "review_mentions": review_mentions,
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
            "performance_tier": emp.performance_tier,
            "peer_rank": emp.peer_rank  # Overall rank by score among ALL peers
        })
    
    return results

