"""
Yodeck Slide Generation Routes
Generates PNG slides for digital signage (Yodeck) in 16:9 and letter formats.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Router will be included in main server.py
yodeck_router = APIRouter(prefix="/v2/yodeck", tags=["Yodeck Slides"])

def get_db():
    """Get database instance from shared module to avoid circular imports"""
    from database import get_database
    return get_database()


async def _fetch_active_employees(
    db,
    year: int,
    quarter: str,
    *,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    """
    Phase 3 Stage B helper: Read employees for the quarter through the
    canonical FK-join. Prefers `snapshot_workflow.rows[]` (thin FK array
    populated by `materialize_rows_from_employees`), falls back to the
    snapshot's legacy `employees[]`, and finally to `employees_v2`
    when no snapshot exists. Terminated / merged / blocklisted
    employees are filtered automatically.

    Every slide generator route MUST go through this helper instead of
    querying `employees_v2` directly.
    """
    from services.employee_service import EmployeeService
    svc = EmployeeService(db)

    # 1) Prefer the active snapshot for this quarter via FK-join.
    snap = await db.snapshot_workflow.find_one(
        {"is_current": True, "year": year, "quarter": quarter.upper()},
        {"_id": 0, "id": 1},
    )
    if not snap:
        snap = await db.snapshot_workflow.find_one(
            {"status": "completed", "year": year, "quarter": quarter.upper()},
            {"_id": 0, "id": 1},
            sort=[("effective_date", -1), ("completed_at", -1)],
        )
    if snap:
        joined = await svc.get_snapshot_with_join(snapshot_id=snap["id"])
        rows = (joined or {}).get("employees") or []
        if rows:
            return rows[:limit]

    # 2) No snapshot — last-resort fallback to legacy mirror.
    docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0},
    ).to_list(limit)
    if not docs:
        return []
    return await svc.filter_active_only(docs)


def get_first_name(full_name: str) -> str:
    """Extract first name only from full name for privacy on public displays."""
    if not full_name:
        return "Unknown"
    # Handle hyphenated names like "Starwars Mckinnon-Herrera"
    parts = full_name.strip().split()
    if parts:
        return parts[0]
    return full_name

# ============================================================================
# YODECK SLIDE ENDPOINTS
# ============================================================================

@yodeck_router.get("/{year}/{quarter}/top10")
async def get_yodeck_top10_slide(year: int, quarter: str, format: str = "16:9", background: str = "dark"):
    """
    Generate Top 10 Performers By Metric slide.
    Shows 4 metric columns: PPA, Glass/Guest, Guests/LSC, LBW/Guest
    
    USES SNAPSHOT-FIRST ARCHITECTURE - reads from active snapshot for data consistency.
    
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
        background: Background key from available backgrounds
    """
    from yodeck_slides import generate_top_10_by_metric_slide
    
    db = get_db()
    
    # SNAPSHOT-FIRST: Get employees from the active snapshot
    snapshot = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter.upper(), "year": year},
        {"_id": 0}
    )
    
    if not snapshot:
        snapshot = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter.upper(), "year": year},
            {"_id": 0},
            sort=[("effective_date", -1), ("completed_at", -1)]
        )
    
    if not snapshot or not snapshot.get("employees"):
        # Fallback to canonical-filtered employees_v2 if no snapshot
        employees_docs = await _fetch_active_employees(db, year, quarter)
    else:
        # Filter snapshot embedded employees through canonical service too.
        from services.employee_service import EmployeeService
        employees_docs = await EmployeeService(db).filter_active_only(
            snapshot.get("employees", []),
            snapshot_deleted_names=snapshot.get("deleted_names") or [],
        )
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    # Get the most recent snapshot date for this quarter
    data_date = snapshot.get("effective_date") if snapshot else None
    if not data_date:
        most_recent_snapshot = await db.snapshots.find_one(
            {"year": year, "quarter": quarter.upper()},
            {"snapshot_date": 1},
            sort=[("snapshot_date", -1)]
        )
        if most_recent_snapshot and most_recent_snapshot.get("snapshot_date"):
            data_date = most_recent_snapshot["snapshot_date"]
    
    # Generate slide with the new design
    slide_bytes = generate_top_10_by_metric_slide(
        employees=employees_docs,
        quarter=quarter.upper(),
        year=year,
        output_format=format,
        background=background,
        data_date=data_date
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"top10_by_metric_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@yodeck_router.get("/{year}/{quarter}/complete-rankings")
async def get_yodeck_complete_rankings_slide(year: int, quarter: str, format: str = "16:9", background: str = "dark"):
    """
    Generate a complete rankings slide showing ALL employees top to bottom on one slide.
    
    READS FROM employees_v2 (dashboard) as the authoritative data source.
    Auto-applies data corrections before generating.
    """
    from snapshot_slides import generate_snapshot_slide
    from routes.audit import apply_data_corrections
    
    db = get_db()
    
    # Auto-apply corrections before generating slide
    try:
        await apply_data_corrections(year, quarter)
    except Exception as e:
        logger.warning(f"Auto-corrections failed (non-blocking): {e}")
    
    # Phase 2B: route through canonical EmployeeService so terminated /
    # merged employees never appear on the complete-rankings slide.
    employees = await _fetch_active_employees(db, year, quarter, limit=200)
    
    if not employees:
        raise HTTPException(status_code=404, detail=f"No employee data found for {quarter} {year}")
    
    # Get settings for tier thresholds
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ) or {}
    
    a_min = settings.get("a_server_min_score", 85)
    b_min = settings.get("b_server_min_score", 70)
    
    # Transform employees for the slide generator
    slide_employees = []
    for emp in employees:
        # Use display_name (preferred name) if set, otherwise fall back to name
        display = emp.get("display_name") or emp.get("name") or "Unknown"
        score = emp.get("pre_dar_score", 0) or emp.get("total_score", 0) or 0
        
        # Calculate tier from score, but preserve Trainer/Bartender roles
        stored_tier = (emp.get("tier_label") or emp.get("performance_tier") or "").strip()
        job_title = (emp.get("job_title") or "").lower().strip()
        
        if stored_tier in ("Trainer",) or "trainer" in job_title or "red hat" in job_title:
            tier = "Trainer"
        elif stored_tier in ("Bartender",) or "bartender" in job_title or "bar" in job_title:
            tier = "Bartender"
        elif score >= a_min:
            tier = "A-Server"
        elif score >= b_min:
            tier = "B-Server"
        else:
            tier = "C-Server"
        
        slide_emp = {
            "id": emp.get("id"),
            "name": get_first_name(display),
            "tier_label": tier,
            "total_score": score,
            "score_ppa": emp.get("score_ppa", 0) or 0,
            "score_lbw": emp.get("score_lbw", 0) or 0,
            "score_glass": emp.get("score_glass", 0) or 0,
            "score_lsc": emp.get("score_lsc", 0) or 0,
            "cv_score": emp.get("cv_score", 0) or 0,
            "rt_mentions": emp.get("rt_mentions", 0) or emp.get("review_mentions", 0) or 0,
            "rt_bonus": emp.get("review_tracker_bonus", 0) or min((emp.get("rt_mentions", 0) or 0) * 0.3, 20),
            "total_metric_bonus": emp.get("total_metric_bonus", 0) or 0,
        }
        slide_employees.append(slide_emp)
    
    # Generate the snapshot slide
    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    png_bytes = generate_snapshot_slide(
        employees=slide_employees,
        benchmarks={},
        snapshot_date=snapshot_date,
        background=background,
        quarter=quarter.upper(),
        a_min=a_min,
        b_min=b_min
    )
    
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=rankings_{quarter}_{year}.png"}
    )


@yodeck_router.get("/{year}/{quarter}/printable-rankings")
async def get_yodeck_printable_rankings_slide(year: int, quarter: str, format: str = "16:9"):
    """
    Generate a stylized printable rankings slide with word art headers.
    Groups employees by tier (Red Hats, A, B, C, Bar, Unranked) - NO metrics, just rank and name.
    
    format: "16:9" for screens (1920x1080) or "letter" for printing (2550x3300)
    """
    from yodeck_slides import generate_printable_rankings_slide
    
    db = get_db()
    
    # Get all employees for the quarter (filtered through canonical service).
    employees = await _fetch_active_employees(db, year, quarter, limit=1000)
    
    if not employees:
        raise HTTPException(status_code=404, detail=f"No employees found for {quarter} {year}")
    
    # Sort by tier and score
    tier_order = {"Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4}
    employees.sort(key=lambda x: (
        tier_order.get(x.get("tier_label", "C-Server"), 5),
        -(x.get("total_score", 0) or 0)
    ))
    
    # Clean employee data - use first name only for privacy
    clean_employees = []
    for emp in employees:
        full_name = emp.get("name", "Unknown")
        clean_employees.append({
            "name": get_first_name(full_name),
            "tier_label": emp.get("tier_label", ""),
            "total_score": emp.get("total_score", 0)
        })
    
    slide_bytes = generate_printable_rankings_slide(
        rankings=clean_employees,
        quarter=quarter,
        year=year,
        output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"printable_rankings_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@yodeck_router.get("/{year}/{quarter}/leaderboard-slide")
async def get_leaderboard_slide(year: int, quarter: str, format: str = "16:9"):
    """
    Generate a professional leaderboard slide with the new design system.
    
    Features:
    - Dark navy background with high contrast
    - Gold/Silver/Bronze for top 3
    - Green highlight for top 5
    - Momentum indicators (using snapshot comparison)
    - Recognition badges (5/10/20 mentions)
    - Category leaders panel
    """
    from yodeck_slides import generate_leaderboard_slide as gen_leaderboard
    
    db = get_db()
    
    # Get all employees for the quarter (filtered through canonical service)
    employees = await _fetch_active_employees(db, year, quarter)
    
    if not employees:
        raise HTTPException(status_code=404, detail=f"No data for {quarter} {year}")
    
    # Get settings for tier thresholds
    settings = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ) or {}
    
    a_server_min = settings.get("a_server_min_score", 85.0)
    b_server_min = settings.get("b_server_min_score", 70.0)
    
    # Build rankings with tier labels
    def get_sort_key(e):
        job = str(e.get("job_title", "server")).lower()
        if job == "trainer":
            return (0, -float(e.get("total_score", 0) or 0))
        elif job == "bartender":
            return (1, -float(e.get("total_score", 0) or 0))
        else:
            return (2, -float(e.get("total_score", 0) or 0))
    
    sorted_employees = sorted(employees, key=get_sort_key)
    
    rankings = []
    position = 1
    for emp in sorted_employees:
        job = str(emp.get("job_title", "server")).lower()
        total = emp.get("total_score", 0) or 0
        
        if job == "trainer":
            tier_label = "Trainer"
        elif job == "bartender":
            tier_label = "Bartender"
        else:
            if total >= a_server_min:
                tier_label = "A-Server"
            elif total >= b_server_min:
                tier_label = "B-Server"
            else:
                tier_label = "C-Server"
        
        rankings.append({
            "employee_id": emp.get("id"),
            "name": get_first_name(emp.get("name", "Unknown")),
            "position": position,
            "score": total,
            "job_title": emp.get("job_title", "Server"),
            "tier_label": tier_label
        })
        position += 1
    
    # Get previous scores from second-latest snapshot for momentum
    snapshots = await db.snapshots.find(
        {"year": year, "quarter": quarter.upper()}
    ).sort("snapshot_date", -1).to_list(2)
    
    previous_scores = {}
    if len(snapshots) > 1:
        prev_snapshot = snapshots[1]
        for emp in (prev_snapshot.get("employees_data") or []):
            previous_scores[emp.get("id")] = emp.get("total_score", 0) or emp.get("pre_dar_score", 0) or 0
    
    # Generate slide
    slide_bytes = gen_leaderboard(
        rankings=rankings,
        employees=employees,
        quarter=quarter.upper(),
        year=year,
        previous_scores=previous_scores
    )
    
    filename = f"leaderboard_{quarter}_{year}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@yodeck_router.get("/{year}/{quarter}/tier/{tier_name}")
async def get_yodeck_tier_slide(year: int, quarter: str, tier_name: str, page: int = 1):
    """
    Generate tier-specific slide (1920x1080 PNG).
    Uses per-quarter theme settings.
    
    tier_name: "trainers", "bartenders", "a-servers", "b-servers", "c-servers"
    page: Page number for tiers with >10 employees (default: 1)
    """
    from yodeck_slides import generate_tier_slide
    from scoring_engine import EmployeeV2, QuarterSettings, generate_hierarchy_rankings
    
    db = get_db()
    
    # Map URL tier name to internal tier label
    tier_map = {
        "trainers": "Trainer",
        "bartenders": "Bartender",
        "a-servers": "A-Server",
        "b-servers": "B-Server",
        "c-servers": "C-Server",
    }
    
    tier_label = tier_map.get(tier_name.lower())
    if not tier_label:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier_name}. Use: trainers, bartenders, a-servers, b-servers, c-servers")
    
    # Get settings and rankings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await _fetch_active_employees(db, year, quarter)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = []
    for doc in employees_docs:
        try:
            employees.append(EmployeeV2(**doc))
        except Exception:
            continue
    rankings = generate_hierarchy_rankings(employees, settings)
    
    # Filter by tier
    tier_employees = [r for r in rankings if r.get("tier_label") == tier_label]
    
    if not tier_employees:
        raise HTTPException(status_code=404, detail=f"No employees in {tier_label} tier")
    
    # Paginate (10 per slide)
    max_per_page = 10
    total_pages = (len(tier_employees) + max_per_page - 1) // max_per_page
    
    if page < 1 or page > total_pages:
        raise HTTPException(status_code=400, detail=f"Invalid page. Valid range: 1-{total_pages}")
    
    start_idx = (page - 1) * max_per_page
    end_idx = start_idx + max_per_page
    page_employees = tier_employees[start_idx:end_idx]
    
    # Get theme settings
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    # Generate slide with theme
    slide_bytes = generate_tier_slide(
        tier_label,
        page_employees,
        quarter.upper(),
        year,
        page=page,
        total_pages=total_pages,
        theme=theme,
        custom_colors=custom_colors,
        custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme
    )
    
    filename = f"yodeck_{tier_name}_{quarter}_{year}_p{page}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@yodeck_router.get("/{year}/{quarter}/all")
async def get_all_yodeck_slides(year: int, quarter: str):
    """
    Get metadata about all available Yodeck slides for a quarter.
    Returns download URLs for each slide.
    """
    from yodeck_slides import THEMES
    from scoring_engine import EmployeeV2, QuarterSettings, generate_hierarchy_rankings
    
    db = get_db()
    
    # Get settings and rankings
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await _fetch_active_employees(db, year, quarter)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = []
    for doc in employees_docs:
        try:
            employees.append(EmployeeV2(**doc))
        except Exception:
            continue
    rankings = generate_hierarchy_rankings(employees, settings)
    
    # Count employees per tier
    tier_counts = {"Trainer": 0, "Bartender": 0, "A-Server": 0, "B-Server": 0, "C-Server": 0}
    for r in rankings:
        tier = r.get("tier_label", "A-Server")
        if tier in tier_counts:
            tier_counts[tier] += 1
    
    # Build slide manifest - all slides support both formats
    format_options = ["16:9", "letter"]
    slides = []
    
    # Top 10 By Metric (new design)
    slides.append({
        "id": "top10",
        "name": "Top 10 Performers By Metric",
        "description": "PPA, Glass/Guest, LSC, LBW leaders",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/top10",
        "pages": 1,
        "category": "primary",
        "formats": format_options
    })
    
    # Complete Rankings (all employees on one slide)
    slides.append({
        "id": "complete-rankings",
        "name": "Complete Rankings",
        "description": "All team members top to bottom",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/complete-rankings",
        "employee_count": len(rankings),
        "pages": 1,
        "category": "primary",
        "formats": format_options
    })
    
    # Special slides
    slides.append({
        "id": "most-improved",
        "name": "Most Improved",
        "endpoint": f"/api/v2/yodeck/{year}/{quarter}/most-improved",
        "pages": 1,
        "category": "special",
        "formats": format_options
    })
    
    # Promotion watchlist (B-Servers close to A)
    b_servers_close = len([r for r in rankings if r.get("tier_label") == "B-Server" and (settings.a_server_min_score - r.get("total_score", 0)) <= 10])
    if b_servers_close > 0:
        slides.append({
            "id": "promotion-watchlist",
            "name": "Promotion Watchlist",
            "endpoint": f"/api/v2/yodeck/{year}/{quarter}/promotion-watchlist",
            "employee_count": b_servers_close,
            "pages": 1,
            "category": "special",
            "formats": format_options
        })
    
    # At Risk (C-Servers) - manager only
    if tier_counts["C-Server"] > 0:
        slides.append({
            "id": "at-risk",
            "name": "Coaching Focus (Manager Only)",
            "endpoint": f"/api/v2/yodeck/{year}/{quarter}/at-risk",
            "employee_count": tier_counts["C-Server"],
            "pages": 1,
            "category": "manager",
            "formats": format_options
        })
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "total_employees": len(employees),
        "tier_counts": tier_counts,
        "theme": settings.slide_theme or "dark_navy",
        "available_themes": list(THEMES.keys()),
        "slides": slides
    }


@yodeck_router.get("/{year}/{quarter}/most-improved")
async def get_yodeck_most_improved_slide(year: int, quarter: str, format: str = "16:9"):
    """Generate Most Improved slide - employees with biggest score increase.
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    from yodeck_slides import generate_most_improved_slide
    from scoring_engine import EmployeeV2, QuarterSettings, generate_hierarchy_rankings
    
    db = get_db()
    
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    # Get current quarter rankings (filtered through canonical service)
    employees_docs = await _fetch_active_employees(db, year, quarter)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = []
    for doc in employees_docs:
        try:
            employees.append(EmployeeV2(**doc))
        except Exception:
            continue
    current_rankings = generate_hierarchy_rankings(employees, settings)
    
    # Try to get previous quarter rankings
    prev_quarter_map = {"Q1": "Q4", "Q2": "Q1", "Q3": "Q2", "Q4": "Q3"}
    prev_quarter = prev_quarter_map.get(quarter.upper(), "Q4")
    prev_year = year - 1 if quarter.upper() == "Q1" else year
    
    prev_employees_docs = await _fetch_active_employees(db, prev_year, prev_quarter)
    
    prev_rankings = []
    if prev_employees_docs:
        prev_settings_doc = await db.quarter_settings.find_one(
            {"year": prev_year, "quarter": prev_quarter},
            {"_id": 0}
        )
        if prev_settings_doc:
            prev_settings = QuarterSettings(**prev_settings_doc)
            prev_employees = []
            for doc in prev_employees_docs:
                try:
                    prev_employees.append(EmployeeV2(**doc))
                except Exception:
                    continue
            prev_rankings = generate_hierarchy_rankings(prev_employees, prev_settings)
    
    # Get theme settings
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    slide_bytes = generate_most_improved_slide(
        current_rankings, prev_rankings, quarter.upper(), year,
        theme=theme, custom_colors=custom_colors, custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme, output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"most_improved_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@yodeck_router.get("/{year}/{quarter}/promotion-watchlist")
async def get_yodeck_promotion_watchlist_slide(year: int, quarter: str, format: str = "16:9"):
    """Generate Promotion Watchlist slide - B-Servers close to A-Server threshold.
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    from yodeck_slides import generate_promotion_watchlist_slide
    from scoring_engine import EmployeeV2, QuarterSettings, generate_hierarchy_rankings
    
    db = get_db()
    
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await _fetch_active_employees(db, year, quarter)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = []
    for doc in employees_docs:
        try:
            employees.append(EmployeeV2(**doc))
        except Exception:
            continue
    rankings = generate_hierarchy_rankings(employees, settings)
    
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    slide_bytes = generate_promotion_watchlist_slide(
        rankings, settings.a_server_min_score, quarter.upper(), year,
        theme=theme, custom_colors=custom_colors, custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme, output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"promotion_watchlist_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@yodeck_router.get("/{year}/{quarter}/at-risk")
async def get_yodeck_at_risk_slide(year: int, quarter: str, format: str = "16:9"):
    """Generate At Risk / Coaching Focus slide - C-Servers needing attention. Manager only.
    Args:
        format: "16:9" for Yodeck (1920x1080) or "letter" for 8.5x11" print (2550x3300)
    """
    from yodeck_slides import generate_at_risk_slide
    from scoring_engine import EmployeeV2, QuarterSettings, generate_hierarchy_rankings
    
    db = get_db()
    
    settings_doc = await db.quarter_settings.find_one(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    )
    if not settings_doc:
        raise HTTPException(status_code=404, detail=f"Settings not found for {quarter} {year}")
    
    settings = QuarterSettings(**settings_doc)
    
    employees_docs = await _fetch_active_employees(db, year, quarter)
    
    if not employees_docs:
        raise HTTPException(status_code=404, detail=f"No employee data for {quarter} {year}")
    
    employees = []
    for doc in employees_docs:
        try:
            employees.append(EmployeeV2(**doc))
        except Exception:
            continue
    rankings = generate_hierarchy_rankings(employees, settings)
    
    theme = settings.slide_theme or "dark_navy"
    custom_colors = None
    if theme == "custom":
        custom_colors = {
            "background": settings.slide_bg_color,
            "background_gradient": settings.slide_bg_gradient,
            "primary": settings.slide_accent_color,
            "secondary": settings.slide_secondary_color,
            "text_white": settings.slide_text_color,
        }
    
    # Get seasonal theme setting
    seasonal_theme = getattr(settings, 'slide_seasonal_theme', 'auto')
    
    slide_bytes = generate_at_risk_slide(
        rankings, settings.b_server_min_score, quarter.upper(), year,
        theme=theme, custom_colors=custom_colors, custom_bg_image=settings.slide_custom_bg_image,
        seasonal_theme=seasonal_theme, output_format=format
    )
    
    format_suffix = "letter" if format == "letter" else "16x9"
    filename = f"coaching_focus_{quarter}_{year}_{format_suffix}.png"
    return Response(
        content=slide_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@yodeck_router.get("/themes")
async def get_available_themes():
    """Get list of available slide themes, including seasonal options."""
    from yodeck_slides import THEMES, SEASONAL_THEMES, get_current_seasonal_theme
    
    current_seasonal = get_current_seasonal_theme()
    
    return {
        "themes": list(THEMES.keys()),
        "default": "dark_navy",
        "seasonal_themes": {
            key: {"name": val["name"], "emoji": val["emoji"]} 
            for key, val in SEASONAL_THEMES.items()
        },
        "seasonal_options": ["auto", "none"] + list(SEASONAL_THEMES.keys()),
        "current_auto_seasonal": current_seasonal,
        "current_seasonal_name": SEASONAL_THEMES[current_seasonal]["name"] if current_seasonal else None
    }



# ============================================================================
# QUARTERLY SUMMARY REPORT ENDPOINT
# ============================================================================

@yodeck_router.get("/reports/{year}/{quarter}/quarterly-summary")
async def get_quarterly_summary_report(year: int, quarter: str):
    """
    Generate a PDF quarterly summary report with Customer Voice and Metric Bonus data.
    This endpoint returns JSON data that the frontend can use to generate a print-ready view.
    """
    db = get_db()
    
    # Get all employees for the quarter (filtered through canonical service)
    employees = await _fetch_active_employees(db, year, quarter)
    
    if not employees:
        raise HTTPException(status_code=404, detail=f"No employees found for {quarter} {year}")
    
    # Sort by total score
    employees.sort(key=lambda x: -(x.get("total_score", 0) or 0))
    
    # Calculate summary statistics
    total_employees = len(employees)
    total_cv_score = sum(e.get("cv_score", 0) or 0 for e in employees)
    total_promoters = sum(e.get("cv_promoters", 0) or 0 for e in employees)
    total_detractors = sum(e.get("cv_detractors", 0) or 0 for e in employees)
    total_passives = sum(e.get("cv_passives", 0) or 0 for e in employees)
    total_metric_bonus = sum(e.get("total_metric_bonus", 0) or 0 for e in employees)
    total_rt_bonus = sum(e.get("review_tracker_bonus", 0) or 0 for e in employees)
    
    avg_score = sum(e.get("total_score", 0) or 0 for e in employees) / total_employees if total_employees > 0 else 0
    avg_cv_score = total_cv_score / total_employees if total_employees > 0 else 0
    avg_metric_bonus = total_metric_bonus / total_employees if total_employees > 0 else 0
    
    # Top performers by CV
    top_cv = sorted(employees, key=lambda x: -(x.get("cv_score", 0) or 0))[:5]
    top_cv_data = [{
        "name": e.get("name", "Unknown"),
        "cv_score": e.get("cv_score", 0) or 0,
        "cv_promoters": e.get("cv_promoters", 0) or 0,
        "cv_detractors": e.get("cv_detractors", 0) or 0
    } for e in top_cv]
    
    # Top performers by Metric Bonus
    top_metric = sorted(employees, key=lambda x: -(x.get("total_metric_bonus", 0) or 0))[:5]
    top_metric_data = [{
        "name": e.get("name", "Unknown"),
        "total_metric_bonus": e.get("total_metric_bonus", 0) or 0,
        "ppa": e.get("ppa", 0) or 0,
        "guests_per_lsc": e.get("guests_per_lsc", 0) or 0,
        "lbw_per_guest": e.get("lbw_per_guest", 0) or 0,
        "glassware_per_guest": e.get("glassware_per_guest", 0) or 0
    } for e in top_metric]
    
    # Full employee list for the table
    employee_list = [{
        "name": e.get("name", "Unknown"),
        "job_title": e.get("job_title", "Server"),
        "total_score": e.get("total_score", 0) or 0,
        "cv_score": e.get("cv_score", 0) or 0,
        "cv_promoters": e.get("cv_promoters", 0) or 0,
        "cv_detractors": e.get("cv_detractors", 0) or 0,
        "total_metric_bonus": e.get("total_metric_bonus", 0) or 0,
        "review_tracker_bonus": e.get("review_tracker_bonus", 0) or 0
    } for e in employees]
    
    return {
        "quarter": quarter.upper(),
        "year": year,
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_employees": total_employees,
            "avg_score": round(avg_score, 2),
            "total_cv_score": round(total_cv_score, 1),
            "avg_cv_score": round(avg_cv_score, 2),
            "total_promoters": total_promoters,
            "total_detractors": total_detractors,
            "total_passives": total_passives,
            "total_metric_bonus": round(total_metric_bonus, 1),
            "avg_metric_bonus": round(avg_metric_bonus, 2),
            "total_rt_bonus": round(total_rt_bonus, 1)
        },
        "top_customer_voice": top_cv_data,
        "top_metric_bonus": top_metric_data,
        "employees": employee_list
    }
