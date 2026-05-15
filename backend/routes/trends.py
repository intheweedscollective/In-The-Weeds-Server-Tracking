"""
Trends & Analytics Routes
Handles employee and team trend analysis, charts, and bi-weekly comparisons.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from typing import Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Router will be included in main server.py
trends_router = APIRouter(prefix="/v2/trends", tags=["Trends & Analytics"])

def get_db():
    """Get database instance from shared module to avoid circular imports"""
    from database import get_database
    return get_database()

def get_previous_quarter(quarter: str, year: int):
    """Get previous quarter and year"""
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    idx = quarters.index(quarter.upper())
    if idx == 0:
        return "Q4", year - 1
    return quarters[idx - 1], year


# ============================================================================
# EMPLOYEE TREND ENDPOINTS
# ============================================================================

@trends_router.get("/{year}/{quarter}/employee/{employee_id}")
async def get_employee_trend_chart(year: int, quarter: str, employee_id: str, chart_type: str = "comparison"):
    """
    Generate trend chart for an individual employee.
    
    chart_type: "comparison" (line chart with employee, benchmark, restaurant avg) or "change" (% change chart)
    """
    from trend_charts import generate_employee_change_chart, generate_employee_comparison_chart
    
    db = get_db()
    
    # Get current quarter data
    current_doc = await db.employees_v2.find_one(
        {"year": year, "quarter": quarter.upper(), "id": employee_id},
        {"_id": 0}
    )
    if not current_doc:
        raise HTTPException(status_code=404, detail="Employee not found for current quarter")
    
    # Get previous quarter data
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_doc = await db.employees_v2.find_one(
        {"year": prev_year, "quarter": prev_quarter, "name": current_doc.get("name")},
        {"_id": 0}
    )
    
    # Generate chart
    if chart_type == "change":
        chart_bytes = generate_employee_change_chart(
            current_doc.get("name", "Employee"),
            current_doc, previous_doc,
            quarter.upper(), year
        )
    else:
        # Get benchmarks from quarter settings
        settings = await db.quarter_settings.find_one(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        )
        benchmarks = {
            'ppa': settings.get('benchmark_ppa', 55.0) if settings else 55.0,
            'lbw_per_guest': settings.get('benchmark_lbw', 8.0) if settings else 8.0,
            'glassware_per_guest': settings.get('benchmark_glass', 1.0) if settings else 1.0,
            'guests_per_lsc': settings.get('benchmark_lsc', 100.0) if settings else 100.0,
            'cv_score': settings.get('benchmark_cv', 5.0) if settings else 5.0,
            'pre_dar_score': settings.get('a_server_min_score', 85.0) if settings else 85.0
        }
        
        # Get snapshot history for this employee in this quarter
        employee_name = current_doc.get("name")
        snapshots = await db.snapshots.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0, "snapshot_date": 1, "employees": 1}
        ).sort("snapshot_date", 1).to_list(100)
        
        snapshot_history = []
        restaurant_avg_history = []
        metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
        
        for snap in snapshots:
            snap_date = snap.get("snapshot_date", "")
            employees_in_snap = snap.get("employees", [])
            
            # Find this employee in the snapshot
            emp_data = next((e for e in employees_in_snap if e.get("name") == employee_name), None)
            if emp_data:
                emp_snapshot = {"date": snap_date}
                for metric in metrics:
                    emp_snapshot[metric] = emp_data.get(metric, 0) or 0
                snapshot_history.append(emp_snapshot)
            
            # Calculate restaurant averages for each metric in this snapshot
            rest_avg_entry = {"date": snap_date}
            for metric in metrics:
                values = [e.get(metric, 0) or 0 for e in employees_in_snap if e.get(metric) is not None]
                rest_avg_entry[metric] = sum(values) / len(values) if values else 0
            restaurant_avg_history.append(rest_avg_entry)
        
        # Always add current employee data as "Current" data point
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_emp_snapshot = {"date": current_date}
        for metric in metrics:
            current_emp_snapshot[metric] = current_doc.get(metric, 0) or 0
        
        # Add current data if it's different from the last snapshot or if no snapshots
        if not snapshot_history or snapshot_history[-1].get('date') != current_date:
            snapshot_history.append(current_emp_snapshot)
            
            # Also add current restaurant average
            all_current_employees = await db.employees_v2.find(
                {"year": year, "quarter": quarter.upper()},
                {"_id": 0}
            ).to_list(1000)
            
            current_rest_avg = {"date": current_date}
            for metric in metrics:
                values = [e.get(metric, 0) for e in all_current_employees if e.get(metric) is not None]
                current_rest_avg[metric] = sum(values) / len(values) if values else 0
            restaurant_avg_history.append(current_rest_avg)
        
        # Calculate current restaurant average (for fallback)
        all_employees = await db.employees_v2.find(
            {"year": year, "quarter": quarter.upper()},
            {"_id": 0}
        ).to_list(1000)
        
        restaurant_averages = {}
        for metric in metrics:
            values = [e.get(metric, 0) for e in all_employees if e.get(metric) is not None]
            restaurant_averages[metric] = sum(values) / len(values) if values else 0
        
        chart_bytes = generate_employee_comparison_chart(
            current_doc.get("name", "Employee"),
            current_doc, previous_doc,
            quarter.upper(), year,
            benchmarks=benchmarks,
            restaurant_averages=restaurant_averages,
            snapshot_history=snapshot_history,
            restaurant_avg_history=restaurant_avg_history
        )
    
    return Response(
        content=chart_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=trend_{employee_id}_{quarter}_{year}.png"}
    )


@trends_router.get("/{year}/{quarter}/employee/{employee_id}/data")
async def get_employee_trend_data(year: int, quarter: str, employee_id: str):
    """
    Get raw trend data for an employee (current vs previous quarter).
    Returns JSON for frontend chart rendering.
    """
    db = get_db()
    
    # Get current quarter data
    current_doc = await db.employees_v2.find_one(
        {"year": year, "quarter": quarter.upper(), "id": employee_id},
        {"_id": 0}
    )
    if not current_doc:
        raise HTTPException(status_code=404, detail="Employee not found for current quarter")
    
    # Get previous quarter data
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_doc = await db.employees_v2.find_one(
        {"year": prev_year, "quarter": prev_quarter, "name": current_doc.get("name")},
        {"_id": 0}
    )
    
    metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
    
    current_values = {}
    previous_values = {}
    changes = {}
    
    for metric in metrics:
        curr_val = current_doc.get(metric, 0) or 0
        prev_val = previous_doc.get(metric, 0) if previous_doc else 0
        
        current_values[metric] = curr_val
        previous_values[metric] = prev_val
        
        if prev_val and prev_val != 0:
            pct_change = ((curr_val - prev_val) / abs(prev_val)) * 100
        else:
            pct_change = 0 if curr_val == 0 else 100
        
        changes[metric] = round(pct_change, 1)
    
    return {
        "employee_name": current_doc.get("name"),
        "employee_id": employee_id,
        "current_quarter": quarter.upper(),
        "current_year": year,
        "previous_quarter": prev_quarter,
        "previous_year": prev_year,
        "has_previous_data": previous_doc is not None,
        "current": current_values,
        "previous": previous_values,
        "changes": changes
    }


# ============================================================================
# TEAM TREND ENDPOINTS
# ============================================================================

@trends_router.get("/{year}/{quarter}/team")
async def get_team_trend_chart(year: int, quarter: str, chart_type: str = "comparison"):
    """
    Generate team-wide trend chart comparing current vs previous quarter.
    
    chart_type: "comparison" (bar chart) or "distribution" (tier pie charts)
    """
    from trend_charts import generate_team_comparison_chart, generate_tier_distribution_chart
    
    db = get_db()
    
    # Get current quarter employees
    current_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not current_docs:
        raise HTTPException(status_code=404, detail="No employees found for current quarter")
    
    # Get previous quarter employees
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_docs = await db.employees_v2.find(
        {"year": prev_year, "quarter": prev_quarter},
        {"_id": 0}
    ).to_list(5000)
    
    # Generate chart
    if chart_type == "distribution":
        chart_bytes = generate_tier_distribution_chart(
            current_docs, previous_docs,
            quarter.upper(), year
        )
    else:
        chart_bytes = generate_team_comparison_chart(
            current_docs, previous_docs,
            quarter.upper(), year
        )
    
    return Response(
        content=chart_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=team_trend_{quarter}_{year}.png"}
    )


@trends_router.get("/{year}/{quarter}/team/data")
async def get_team_trend_data(year: int, quarter: str):
    """
    Get raw team trend data (current vs previous quarter averages).
    Returns JSON for frontend chart rendering.
    """
    db = get_db()
    
    # Get current quarter employees
    current_docs = await db.employees_v2.find(
        {"year": year, "quarter": quarter.upper()},
        {"_id": 0}
    ).to_list(5000)
    
    if not current_docs:
        raise HTTPException(status_code=404, detail="No employees found for current quarter")
    
    # Get previous quarter employees
    prev_quarter, prev_year = get_previous_quarter(quarter, year)
    previous_docs = await db.employees_v2.find(
        {"year": prev_year, "quarter": prev_quarter},
        {"_id": 0}
    ).to_list(5000)
    
    metrics = ['ppa', 'lbw_per_guest', 'glassware_per_guest', 'guests_per_lsc', 'cv_score', 'pre_dar_score']
    
    def calc_avg(employees, metric):
        values = [e.get(metric, 0) for e in employees if e.get(metric) is not None]
        return round(sum(values) / len(values), 2) if values else 0
    
    def count_tiers(employees):
        tiers = {'Trainer': 0, 'Bartender': 0, 'A-Server': 0, 'B-Server': 0, 'C-Server': 0}
        for emp in employees:
            tier = emp.get('tier_label', 'C-Server')
            if tier in tiers:
                tiers[tier] += 1
        return tiers
    
    current_avgs = {m: calc_avg(current_docs, m) for m in metrics}
    previous_avgs = {m: calc_avg(previous_docs, m) for m in metrics} if previous_docs else {m: 0 for m in metrics}
    
    changes = {}
    for m in metrics:
        curr = current_avgs[m]
        prev = previous_avgs[m]
        if prev and prev != 0:
            changes[m] = round(((curr - prev) / abs(prev)) * 100, 1)
        else:
            changes[m] = 0
    
    return {
        "current_quarter": quarter.upper(),
        "current_year": year,
        "previous_quarter": prev_quarter,
        "previous_year": prev_year,
        "has_previous_data": len(previous_docs) > 0,
        "current_count": len(current_docs),
        "previous_count": len(previous_docs),
        "current_averages": current_avgs,
        "previous_averages": previous_avgs,
        "changes": changes,
        "current_tier_distribution": count_tiers(current_docs),
        "previous_tier_distribution": count_tiers(previous_docs) if previous_docs else {}
    }


# ============================================================================
# BI-WEEKLY TREND ENDPOINTS
# ============================================================================

@trends_router.get("/biweekly/{employee_name}")
async def get_biweekly_trend_chart(
    employee_name: str,
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    time_range: str = "quarter"  # "quarter", "year", or "all"
):
    """
    Generate a bi-weekly trend line chart for an employee showing their Total Score
    vs Restaurant Average over time, using data from bi-weekly snapshots.
    
    Args:
        employee_name: Name of the employee
        year: Year to filter (defaults to current year)
        quarter: Quarter to filter (e.g., "Q1") - only used if time_range is "quarter"
        time_range: "quarter" (default), "year", or "all"
    
    Returns PNG image of the line chart.
    """
    from trend_charts import generate_biweekly_trend_chart
    from datetime import datetime as dt
    
    db = get_db()
    
    # Default to current year/quarter if not specified
    if not year:
        year = dt.now().year
    if not quarter:
        month = dt.now().month
        quarter = f"Q{(month - 1) // 3 + 1}"
    
    # Build query based on time_range
    query = {}
    if time_range == "quarter":
        query["year"] = year
        query["quarter"] = quarter.upper()
    elif time_range == "year":
        query["year"] = year
    # "all" has no filter
    
    # Fetch snapshots
    snapshots = await db.snapshots.find(query, {"_id": 0}).sort("snapshot_date", 1).to_list(100)
    
    if not snapshots:
        raise HTTPException(status_code=404, detail="No snapshots found for the specified period")
    
    # Extract employee scores and restaurant averages
    employee_scores = []
    restaurant_averages = []
    
    for snapshot in snapshots:
        snapshot_date = snapshot.get("snapshot_date")
        employees = snapshot.get("employees", [])
        
        if not employees:
            continue
        
        # Find the employee in this snapshot (case-insensitive match)
        emp_data = None
        for emp in employees:
            if emp.get("name", "").lower() == employee_name.lower():
                emp_data = emp
                break
        
        # Calculate restaurant average for this snapshot
        all_scores = [e.get("total_score", 0) or 0 for e in employees if e.get("total_score") is not None]
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        restaurant_averages.append({
            "date": snapshot_date,
            "avg_score": round(avg_score, 2)
        })
        
        if emp_data:
            employee_scores.append({
                "date": snapshot_date,
                "total_score": emp_data.get("total_score", 0) or 0
            })
    
    if not employee_scores:
        raise HTTPException(
            status_code=404, 
            detail=f"Employee '{employee_name}' not found in any snapshots for the specified period"
        )
    
    # Generate the chart
    chart_bytes = generate_biweekly_trend_chart(
        employee_name=employee_name,
        employee_scores=employee_scores,
        restaurant_averages=restaurant_averages,
        quarter=quarter.upper() if quarter else None,
        year=year,
        time_range=time_range
    )
    
    return Response(
        content=chart_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={employee_name}_trend.png"}
    )


@trends_router.get("/biweekly/{employee_name}/data")
async def get_biweekly_trend_data(
    employee_name: str,
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    time_range: str = "quarter"
):
    """
    Get raw bi-weekly trend data for an employee (JSON format).
    Useful for custom visualizations or debugging.
    """
    from datetime import datetime as dt
    
    db = get_db()
    
    if not year:
        year = dt.now().year
    if not quarter:
        month = dt.now().month
        quarter = f"Q{(month - 1) // 3 + 1}"
    
    query = {}
    if time_range == "quarter":
        query["year"] = year
        query["quarter"] = quarter.upper()
    elif time_range == "year":
        query["year"] = year
    
    snapshots = await db.snapshots.find(query, {"_id": 0}).sort("snapshot_date", 1).to_list(100)
    
    employee_scores = []
    restaurant_averages = []
    
    for snapshot in snapshots:
        snapshot_date = snapshot.get("snapshot_date")
        employees = snapshot.get("employees", [])
        
        if not employees:
            continue
        
        emp_data = None
        for emp in employees:
            if emp.get("name", "").lower() == employee_name.lower():
                emp_data = emp
                break
        
        all_scores = [e.get("total_score", 0) or 0 for e in employees if e.get("total_score") is not None]
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        restaurant_averages.append({
            "date": snapshot_date,
            "avg_score": round(avg_score, 2)
        })
        
        if emp_data:
            employee_scores.append({
                "date": snapshot_date,
                "total_score": emp_data.get("total_score", 0) or 0,
                "name": emp_data.get("name")
            })
    
    return {
        "employee_name": employee_name,
        "time_range": time_range,
        "year": year,
        "quarter": quarter.upper() if quarter else None,
        "snapshot_count": len(snapshots),
        "employee_data_points": len(employee_scores),
        "employee_scores": employee_scores,
        "restaurant_averages": restaurant_averages
    }



# ============================================================================
# MOMENTUM / TREND INDICATORS (Rolling Average Comparison)
# ============================================================================

@trends_router.get("/momentum/{year}/{quarter}")
async def get_all_employee_momentum(year: int, quarter: str, lookback_snapshots: int = 1):
    """
    Calculate momentum/trend for ALL employees in a quarter.
    Compares each employee's current snapshot score against the score from
    the immediately preceding snapshot (lookback_snapshots=1, default).
    Pass `lookback_snapshots=N` to compare against a rolling N-snapshot avg.
    
    Returns:
        Dictionary mapping employee_id to trend data:
        {
            "employee_id": {
                "current_score": 85.5,
                "rolling_avg": 82.3,
                "change": 3.2,
                "direction": "up",  // "up", "down", "stable"
                "percent_change": 3.89,
                "snapshots_used": 3
            }
        }
    """
    db = get_db()
    quarter = quarter.upper()
    
    # Get all snapshots for this quarter, ordered by date
    snapshots = await db.snapshot_workflow.find(
        {"year": year, "quarter": quarter, "status": {"$in": ["completed", "in_progress"]}},
        {"_id": 0, "employees": 1, "effective_date": 1, "name": 1, "created_at": 1}
    ).sort("effective_date", -1).to_list(20)
    
    if not snapshots:
        # Fall back to employees_v2 if no snapshots
        employees = await db.employees_v2.find(
            {"year": year, "quarter": quarter},
            {"_id": 0, "id": 1, "name": 1, "total_score": 1}
        ).to_list(500)
        
        # No historical data, return neutral trends
        return {
            emp.get("id") or emp.get("name"): {
                "current_score": emp.get("total_score", 0) or 0,
                "rolling_avg": emp.get("total_score", 0) or 0,
                "change": 0,
                "direction": "stable",
                "percent_change": 0,
                "snapshots_used": 0,
                "employee_name": emp.get("name")
            }
            for emp in employees
        }
    
    # Build employee score history from snapshots
    # Most recent snapshot is the "current" score.
    # Key by NAME (not id) because each snapshot has its own employee
    # records with fresh UUIDs — the same person has different `id`s in
    # different snapshots, so id-keyed grouping makes everyone look like
    # a 1-snapshot newcomer with a "stable" trend.
    employee_history = {}  # {employee_name: {"name": ..., "scores": [...]}}

    def _hist_key(emp: dict) -> str:
        # Use the canonical `name` field (which has been alias-normalised by
        # the snapshot pipeline — e.g. "Matthew Spath" report_name → "Matt
        # Spath" name). report_name often varies between weekly POS reports
        # so it's NOT reliable for cross-snapshot grouping.
        return (emp.get("name") or emp.get("report_name") or "").strip().lower()

    for snapshot in reversed(snapshots):  # Oldest first
        for emp in snapshot.get("employees", []):
            key = _hist_key(emp)
            if not key:
                continue
            if key not in employee_history:
                employee_history[key] = {
                    "name": emp.get("name"),
                    "scores": []
                }
            employee_history[key]["scores"].append(emp.get("total_score", 0) or 0)
    
    # Calculate momentum for each employee
    momentum_data = {}

    def _emit(key: str, payload: dict):
        # Emit under multiple keys so frontends keyed by id/name/lower-name
        # all hit. Frontend tries `momentumData[employee.employee_id] ||
        # momentumData[employee.name]`.
        if key:
            momentum_data[key] = payload
        nm = payload.get("employee_name")
        if nm:
            momentum_data[nm] = payload          # exact-case display name
            momentum_data[nm.lower()] = payload  # lowercase fallback

    for emp_id, data in employee_history.items():
        scores = data["scores"]
        name = data["name"]
        
        if len(scores) == 0:
            continue
        
        current_score = scores[-1]  # Most recent
        
        if len(scores) == 1:
            # Only one data point, no trend
            _emit(emp_id, {
                "current_score": round(current_score, 2),
                "rolling_avg": round(current_score, 2),
                "change": 0,
                "direction": "stable",
                "percent_change": 0,
                "snapshots_used": 1,
                "employee_name": name
            })
        else:
            # Calculate rolling average of previous scores (excluding current)
            previous_scores = scores[:-1][-lookback_snapshots:]  # Last N scores before current
            rolling_avg = sum(previous_scores) / len(previous_scores) if previous_scores else current_score
            
            change = current_score - rolling_avg
            percent_change = (change / rolling_avg * 100) if rolling_avg != 0 else 0
            
            # Determine direction with threshold (0.5 pts = stable)
            if change > 0.5:
                direction = "up"
            elif change < -0.5:
                direction = "down"
            else:
                direction = "stable"
            
            _emit(emp_id, {
                "current_score": round(current_score, 2),
                "rolling_avg": round(rolling_avg, 2),
                "change": round(change, 2),
                "direction": direction,
                "percent_change": round(percent_change, 1),
                "snapshots_used": len(previous_scores),
                "employee_name": name,
                "previous_score": round(scores[-2], 2),
            })
    
    return momentum_data


@trends_router.get("/momentum/{year}/{quarter}/{employee_id}")
async def get_employee_momentum(year: int, quarter: str, employee_id: str, lookback_snapshots: int = 4):
    """
    Get momentum/trend data for a single employee.
    """
    all_momentum = await get_all_employee_momentum(year, quarter, lookback_snapshots)
    
    if employee_id not in all_momentum:
        # Try to find by name
        for emp_id, data in all_momentum.items():
            if data.get("employee_name", "").lower() == employee_id.lower():
                return data
        raise HTTPException(status_code=404, detail="Employee not found")
    
    return all_momentum[employee_id]
