"""
Insights Routes - Executive dashboard insights and analytics.

Includes:
- Store Health Score (Store Performance Index)
- Coaching Radar (High-impact coaching opportunities)
- Review Impact Tracker (Revenue influence from reviews)
"""

import logging
from typing import Optional

from fastapi import APIRouter

# Router
insights_router = APIRouter(tags=["Insights"])


def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# ============================================================================
# STORE HEALTH SCORE (STORE PERFORMANCE INDEX)
# ============================================================================

@insights_router.get("/v2/insights/store-health")
async def get_store_health_score(quarter: str = "Q1", year: int = 2026):
    """
    Get Store Health Score - Executive-level view of store performance.

    Aligned to Bubba Gump Daily Flash Report corporate metrics.

    Categories & Weights:
    - Sales Execution (25%): Average PPA scores (per-store benchmark, untouched)
    - Upsell Performance (25%): Bell-curved PPA + LBW + Glassware vs CONCEPT
      averages — equal-thirds. Gives extra credit to the few stores
      at the high end of concept.
    - Loyalty Engagement (20%): Average LSC scores
    - Guest Experience (30%): RT mentions (70%) + CV / NPS (30%)
    """
    employees = await get_db().employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)

    if not employees:
        return {
            "store_health_score": 0,
            "categories": {},
            "message": "No employee data found"
        }

    # Get settings for benchmarks and concept averages
    settings = await get_db().quarter_settings.find_one({"year": year, "quarter": quarter.upper()})
    settings = settings or {}

    # Calculate category scores (normalized to 0-100 scale)
    def avg_score(field, default=0):
        values = [e.get(field, default) or default for e in employees]
        return sum(values) / len(values) if values else 0

    # ------------------------------------------------------------------
    # Bell-curve scoring vs concept low/avg/high.
    # Piecewise-linear (cheap to reason about, no std-dev needed):
    #   x <= low         →   0..60   (steep penalty for the lower tail)
    #   low < x <= avg   →   60..80  (concept-average store lands at 80)
    #   avg < x <= high  →   80..100 (rewards push toward concept best)
    #   x >  high        →   100     (capped — no infinite bonus)
    # This matches operator-stated intent: "give credit to the few
    # teams at the high end" — top quartile gets visibly more than
    # the median.
    # ------------------------------------------------------------------
    def bell(x: Optional[float], low: float, avg: float, high: float) -> float:
        if x is None or x <= 0:
            return 0.0
        if x >= high:
            return 100.0
        if x >= avg:
            span = max(high - avg, 1e-9)
            return 80.0 + (x - avg) / span * 20.0
        if x >= low:
            span = max(avg - low, 1e-9)
            return 60.0 + (x - low) / span * 20.0
        # below the floor — still award something so a near-floor
        # store doesn't crater an otherwise healthy index.
        return max(0.0, (x / max(low, 1e-9)) * 60.0)

    # ========== SALES EXECUTION (25%) ==========
    # Untouched — keeps using the existing per-store PPA score.
    sales_execution = min(avg_score("score_ppa"), 100)

    # Concept-PPA stats for the comparison block (and for Upsell's PPA leg).
    store_avg_ppa = avg_score("ppa")
    concept_avg_ppa  = settings.get("concept_avg_ppa", 45.71)
    concept_low_ppa  = settings.get("concept_low_ppa", 35.40)
    concept_high_ppa = settings.get("concept_high_ppa", 55.72)
    ppa_vs_concept = (
        ((store_avg_ppa - concept_avg_ppa) / concept_avg_ppa * 100)
        if concept_avg_ppa > 0 else 0
    )

    # ========== UPSELL PERFORMANCE (25%) ==========
    # Equal-thirds of bell-curved PPA + LBW/g + Glass/g vs concept.
    # PPA included here too (per operator: high PPA reflects upsell
    # ability even on items we don't track line-by-line like apps
    # and desserts).
    store_avg_lbw_pg   = avg_score("lbw_per_guest")
    store_avg_glass_pg = avg_score("glassware_per_guest")

    # Concept bounds for LBW and Glass: default to per-store benchmark
    # ±20% when the operator hasn't supplied explicit concept stats.
    # They can override these from quarter_settings whenever the Daily
    # Flash gives us new concept-wide numbers.
    bench_lbw   = settings.get("benchmark_lbw",   8.0) or 8.0
    bench_glass = settings.get("benchmark_glass", 1.35) or 1.35
    concept_avg_lbw    = settings.get("concept_avg_lbw",    bench_lbw)
    concept_low_lbw    = settings.get("concept_low_lbw",    bench_lbw * 0.80)
    concept_high_lbw   = settings.get("concept_high_lbw",   bench_lbw * 1.20)
    concept_avg_glass  = settings.get("concept_avg_glass",  bench_glass)
    concept_low_glass  = settings.get("concept_low_glass",  bench_glass * 0.80)
    concept_high_glass = settings.get("concept_high_glass", bench_glass * 1.20)

    ppa_leg   = bell(store_avg_ppa,      concept_low_ppa,   concept_avg_ppa,   concept_high_ppa)
    lbw_leg   = bell(store_avg_lbw_pg,   concept_low_lbw,   concept_avg_lbw,   concept_high_lbw)
    glass_leg = bell(store_avg_glass_pg, concept_low_glass, concept_avg_glass, concept_high_glass)
    upsell_performance = round((ppa_leg + lbw_leg + glass_leg) / 3.0, 2)

    # ========== LOYALTY ENGAGEMENT (20%) ==========
    loyalty_engagement = min(avg_score("score_lsc"), 100)

    total_guests = sum(e.get("guests", 0) or 0 for e in employees)
    total_lsc = sum(e.get("lsc_count", 0) or 0 for e in employees)
    store_lsc_ratio = round(total_guests / total_lsc) if total_lsc > 0 else 0
    concept_lsc_ratio = settings.get("concept_lsc_ratio", 181)
    lsc_vs_concept = round(concept_lsc_ratio / store_lsc_ratio, 1) if store_lsc_ratio > 0 else 0

    # ========== GUEST EXPERIENCE (30%) ==========
    # NEW WEIGHTING (operator request 2026-06-11):
    #   RT mentions ......... 70%
    #   CV / NPS ............ 30%
    # (Was 70% NPS + 30% RT. Flip applies to Store Health Index only
    # — individual scoring engine weights are untouched.)
    nps_avg = avg_score("nps_score")
    nps_normalized = max(0, (nps_avg + 100) / 2)  # -100..100 → 0..100

    rt_mentions_avg = avg_score("rt_mentions")
    rt_normalized = min((rt_mentions_avg / 30) * 100, 100)  # 30 mentions = 100

    guest_experience = (rt_normalized * 0.7) + (nps_normalized * 0.3)

    # ========== OVERALL STORE HEALTH SCORE ==========
    # Weights restored to the 4-category model the explainer shows:
    #   Sales 25% · Upsell 25% · Loyalty 20% · Guest 30%
    store_health = (
        sales_execution     * 0.25 +
        upsell_performance  * 0.25 +
        loyalty_engagement  * 0.20 +
        guest_experience    * 0.30
    )

    # Build benchmarks dict (existing per-store benches + new concept bell-curve config).
    benchmarks = {
        "ppa": settings.get("benchmark_ppa", 55),
        "lbw": bench_lbw,
        "glass": bench_glass,
        "lsc": settings.get("benchmark_lsc", 100),
        "concept": {
            "ppa":   {"low": concept_low_ppa,   "avg": concept_avg_ppa,   "high": concept_high_ppa},
            "lbw":   {"low": concept_low_lbw,   "avg": concept_avg_lbw,   "high": concept_high_lbw},
            "glass": {"low": concept_low_glass, "avg": concept_avg_glass, "high": concept_high_glass},
        },
    }

    # Concept comparison data
    concept_comparison = {
        "ppa": {
            "store": round(store_avg_ppa, 2),
            "concept": concept_avg_ppa,
            "diff_pct": round(ppa_vs_concept, 1),
            "status": "above" if ppa_vs_concept > 0 else "below"
        },
        "lsc_ratio": {
            "store": f"1:{store_lsc_ratio}" if store_lsc_ratio > 0 else "N/A",
            "concept": f"1:{concept_lsc_ratio}",
            "multiplier": f"{lsc_vs_concept}x better" if lsc_vs_concept > 1 else "at concept",
            "status": "above" if lsc_vs_concept > 1 else "at" if lsc_vs_concept == 1 else "below"
        },
    }

    return {
        "store_health_score": round(store_health, 1),
        "categories": {
            "sales_execution": {
                "score": round(sales_execution, 1),
                "weight": 25,
                "label": "Sales Execution",
                "source": "Average PPA scores",
                "trend": "up" if sales_execution >= 80 else "stable" if sales_execution >= 60 else "down",
                "vs_concept": f"+{ppa_vs_concept:.1f}%" if ppa_vs_concept > 0 else f"{ppa_vs_concept:.1f}%"
            },
            "upsell_performance": {
                "score": round(upsell_performance, 1),
                "weight": 25,
                "label": "Upsell Performance",
                "source": "Bell-curve: PPA + LBW + Glassware vs concept (equal thirds)",
                "trend": "up" if upsell_performance >= 80 else "stable" if upsell_performance >= 60 else "down",
                "breakdown": {
                    "ppa":   {"store": round(store_avg_ppa, 2),      "score": round(ppa_leg, 1),
                              "concept": {"low": concept_low_ppa, "avg": concept_avg_ppa, "high": concept_high_ppa}},
                    "lbw":   {"store": round(store_avg_lbw_pg, 2),   "score": round(lbw_leg, 1),
                              "concept": {"low": concept_low_lbw, "avg": concept_avg_lbw, "high": concept_high_lbw}},
                    "glass": {"store": round(store_avg_glass_pg, 2), "score": round(glass_leg, 1),
                              "concept": {"low": concept_low_glass, "avg": concept_avg_glass, "high": concept_high_glass}},
                }
            },
            "loyalty_engagement": {
                "score": round(loyalty_engagement, 1),
                "weight": 20,
                "label": "Loyalty Engagement",
                "source": f"LSC Ratio 1:{store_lsc_ratio}",
                "trend": "up" if loyalty_engagement >= 80 else "stable" if loyalty_engagement >= 60 else "down",
                "vs_concept": f"{lsc_vs_concept}x better" if lsc_vs_concept > 1 else "at concept",
                "best_in_concept": lsc_vs_concept >= 2.0
            },
            "guest_experience": {
                "score": round(guest_experience, 1),
                "weight": 30,
                "label": "Guest Experience",
                "source": "RT mentions (70%) + CV / NPS (30%)",
                "trend": "up" if guest_experience >= 80 else "stable" if guest_experience >= 60 else "down"
            }
        },
        "employee_count": len(employees),
        "quarter": quarter.upper(),
        "year": year,
        "benchmarks": benchmarks,
        "concept_comparison": concept_comparison,
        "awards": {
            "best_in_concept_lsc": lsc_vs_concept >= 2.0,
            "above_concept_ppa": ppa_vs_concept > 10,
        }
    }


# ============================================================================
# COACHING RADAR
# ============================================================================

@insights_router.get("/v2/insights/coaching-radar")
async def get_coaching_radar(quarter: str = "Q1", year: int = 2026):
    """
    Get Coaching Radar - High-impact coaching opportunities.
    
    Identifies employees below benchmark in key areas and estimates
    the potential revenue impact of coaching interventions.
    """
    employees = await get_db().employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not employees:
        return {"coaching_opportunities": [], "message": "No employee data found"}
    
    # Get benchmarks
    settings = await get_db().quarter_settings.find_one({"year": year, "quarter": quarter.upper()})
    benchmarks = {
        "ppa": settings.get("benchmark_ppa", 55) if settings else 55,
        "lbw": settings.get("benchmark_lbw", 8) if settings else 8,
        "glass": settings.get("benchmark_glass", 1.35) if settings else 1.35,
        "lsc": settings.get("benchmark_lsc", 1) if settings else 1
    }
    
    # Revenue impact estimates per metric improvement
    # These are industry-standard estimates for restaurant metrics
    MONTHLY_GUESTS_PER_SERVER = 400  # Estimated monthly guest count per server
    
    coaching_opportunities = []
    
    for emp in employees:
        opportunities = []
        
        # Check Glassware (wine/alcohol upsells)
        glass_per_guest = emp.get("glassware_per_guest", 0) or 0
        if glass_per_guest < benchmarks["glass"]:
            gap = benchmarks["glass"] - glass_per_guest
            # Each $1 increase in glassware per guest = significant revenue
            potential_increase = round(gap * MONTHLY_GUESTS_PER_SERVER * 12, 0)  # Annual
            opportunities.append({
                "category": "Glassware",
                "metric": "glassware_per_guest",
                "current": round(glass_per_guest, 2),
                "benchmark": benchmarks["glass"],
                "gap": round(gap, 2),
                "impact_type": "revenue",
                "potential_monthly": round(potential_increase / 12, 0),
                "description": f"Glassware sales ${glass_per_guest:.2f}/guest vs ${benchmarks['glass']:.2f} benchmark",
                "action": "Focus on wine pairing suggestions and premium drink recommendations"
            })
        
        # Check LBW (bar upsells)
        lbw_per_guest = emp.get("lbw_per_guest", 0) or 0
        if lbw_per_guest < benchmarks["lbw"]:
            gap = benchmarks["lbw"] - lbw_per_guest
            potential_increase = round(gap * MONTHLY_GUESTS_PER_SERVER * 12, 0)
            opportunities.append({
                "category": "LBW",
                "metric": "lbw_per_guest",
                "current": round(lbw_per_guest, 2),
                "benchmark": benchmarks["lbw"],
                "gap": round(gap, 2),
                "impact_type": "revenue",
                "potential_monthly": round(potential_increase / 12, 0),
                "description": f"Bar sales ${lbw_per_guest:.2f}/guest vs ${benchmarks['lbw']:.2f} benchmark",
                "action": "Suggest appetizers, desserts, and premium add-ons"
            })
        
        # Check LSC (loyalty signups)
        lsc_count = emp.get("lsc_count", 0) or 0
        guests = emp.get("guests", 1) or 1
        lsc_rate = lsc_count / guests if guests > 0 else 0
        if lsc_rate < benchmarks["lsc"] / 100:  # Convert to percentage
            gap_pct = (benchmarks["lsc"] / 100) - lsc_rate
            potential_signups = round(gap_pct * MONTHLY_GUESTS_PER_SERVER, 0)
            opportunities.append({
                "category": "Loyalty",
                "metric": "lsc_conversion",
                "current": round(lsc_rate * 100, 1),
                "benchmark": benchmarks["lsc"],
                "gap": round(gap_pct * 100, 1),
                "impact_type": "signups",
                "potential_monthly": potential_signups,
                "description": f"Loyalty conversion {lsc_rate*100:.1f}% vs {benchmarks['lsc']}% benchmark",
                "action": "Mention rewards program benefits during checkout"
            })
        
        # Check PPA (per person average)
        ppa = emp.get("ppa", 0) or 0
        if ppa < benchmarks["ppa"]:
            gap = benchmarks["ppa"] - ppa
            potential_increase = round(gap * MONTHLY_GUESTS_PER_SERVER * 12, 0)
            opportunities.append({
                "category": "PPA",
                "metric": "ppa",
                "current": round(ppa, 2),
                "benchmark": benchmarks["ppa"],
                "gap": round(gap, 2),
                "impact_type": "revenue",
                "potential_monthly": round(potential_increase / 12, 0),
                "description": f"Guest average ${ppa:.2f} vs ${benchmarks['ppa']:.2f} benchmark",
                "action": "Focus on upselling premium items and suggesting add-ons"
            })
        
        if opportunities:
            # Sort by potential impact (highest first)
            opportunities.sort(key=lambda x: x.get("potential_monthly", 0), reverse=True)
            
            coaching_opportunities.append({
                "employee_id": emp.get("id"),
                "employee_name": emp.get("name"),
                "total_score": emp.get("total_score", 0),
                "tier": emp.get("tier_label", ""),
                "opportunities": opportunities[:2],  # Top 2 opportunities per employee
                "total_potential_monthly": sum(o.get("potential_monthly", 0) for o in opportunities)
            })
    
    # Sort by total potential impact and return top opportunities
    coaching_opportunities.sort(key=lambda x: x.get("total_potential_monthly", 0), reverse=True)
    
    return {
        "coaching_opportunities": coaching_opportunities[:10],  # Top 10
        "total_potential_monthly_revenue": sum(c.get("total_potential_monthly", 0) for c in coaching_opportunities[:10]),
        "employees_needing_coaching": len(coaching_opportunities),
        "total_employees": len(employees),
        "benchmarks": benchmarks,
        "quarter": quarter.upper(),
        "year": year
    }


# ============================================================================
# REVIEW IMPACT TRACKER
# ============================================================================

@insights_router.get("/v2/insights/review-impact")
async def get_review_impact(quarter: str = "Q1", year: int = 2026):
    """
    Get Review Impact Tracker - Revenue influence from guest reviews.
    
    Connects review mentions to estimated revenue influence.
    Industry research shows positive reviews drive significant revenue.
    """
    employees = await get_db().employees_v2.find(
        {"quarter": quarter.upper(), "year": year}
    ).to_list(500)
    
    if not employees:
        return {"review_impact": [], "message": "No employee data found"}
    
    # Revenue influence estimates
    # Research shows each positive review can influence $500-1000 in future revenue
    # (through repeat visits, referrals, and new customer acquisition)
    REVENUE_PER_MENTION = 550  # Conservative estimate per review mention
    REVENUE_PER_PROMOTER = 800  # Higher value for promoter (NPS 9-10)
    
    review_impact = []
    
    for emp in employees:
        rt_mentions = emp.get("rt_mentions") or emp.get("review_mentions") or 0
        cv_promoters = emp.get("cv_promoters") or 0
        nps_score = emp.get("nps_score") or 0
        
        # Skip if no guest interaction data
        if rt_mentions == 0 and cv_promoters == 0:
            continue
        
        # Calculate revenue influence
        mention_influence = rt_mentions * REVENUE_PER_MENTION
        promoter_influence = cv_promoters * REVENUE_PER_PROMOTER
        total_influence = mention_influence + promoter_influence
        
        # Guest satisfaction indicator
        if nps_score >= 80:
            satisfaction = "Excellent"
            satisfaction_color = "emerald"
        elif nps_score >= 60:
            satisfaction = "Good"
            satisfaction_color = "blue"
        elif nps_score >= 40:
            satisfaction = "Average"
            satisfaction_color = "amber"
        else:
            satisfaction = "Needs Improvement"
            satisfaction_color = "red"
        
        review_impact.append({
            "employee_id": emp.get("id"),
            "employee_name": emp.get("name"),
            "review_mentions": rt_mentions,
            "cv_promoters": cv_promoters,
            "nps_score": nps_score,
            "satisfaction_level": satisfaction,
            "satisfaction_color": satisfaction_color,
            "mention_revenue_influence": round(mention_influence, 0),
            "promoter_revenue_influence": round(promoter_influence, 0),
            "total_revenue_influence": round(total_influence, 0),
            "tier": emp.get("tier_label", ""),
            "total_score": emp.get("total_score", 0)
        })
    
    # Sort by total revenue influence
    review_impact.sort(key=lambda x: x.get("total_revenue_influence", 0), reverse=True)
    
    # Calculate totals
    total_mentions = sum(e.get("review_mentions", 0) for e in review_impact)
    total_promoters = sum(e.get("cv_promoters", 0) for e in review_impact)
    total_influence = sum(e.get("total_revenue_influence", 0) for e in review_impact)
    
    return {
        "review_impact": review_impact[:15],  # Top 15
        "totals": {
            "total_mentions": total_mentions,
            "total_promoters": total_promoters,
            "total_revenue_influence": round(total_influence, 0),
            "employees_with_impact": len(review_impact)
        },
        "methodology": {
            "revenue_per_mention": REVENUE_PER_MENTION,
            "revenue_per_promoter": REVENUE_PER_PROMOTER,
            "description": "Based on industry research on review-driven revenue (repeat visits, referrals, new customers)"
        },
        "quarter": quarter.upper(),
        "year": year
    }
