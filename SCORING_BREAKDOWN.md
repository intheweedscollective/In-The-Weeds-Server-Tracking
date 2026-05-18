# Bubba Gump Scoring System - Complete Breakdown

## HIGH-LEVEL OVERVIEW

**Total Score = Base Score + Bonuses + Customer Voice**

| Component | Max Points | Description |
|-----------|------------|-------------|
| Weighted POS Metrics | 85 pts | Core performance metrics |
| Metric Bonuses | 20 pts | Exceeding benchmarks |
| Customer Voice (CV) | Uncapped | NPS + Promoter/Detractor points |
| Review Tracker (RT) | 15 pts | Online review mentions |
| DAR Penalties | Negative | Disciplinary deductions (admin-only) |

**Typical Score Range: 60-120+ points**

---

## DETAILED BREAKDOWN

### 1. WEIGHTED POS METRICS (85 points max)

These are the core operational metrics from POS data. Each metric is scored as:
```
Score = (Employee Value / Benchmark) × 100
```
Then capped at 100 before weighting.

| Metric | Weight | Max Contribution | What It Measures |
|--------|--------|------------------|------------------|
| **PPA** (Per Person Average) | 25% | 25 pts | Average revenue per guest |
| **LSC** (Loyalty Sales) | 25% | 25 pts | Loyalty program enrollments |
| **LBW** (Liquor/Beer/Wine) | 20% | 20 pts | Beverage upsells per guest |
| **Glassware** | 15% | 15 pts | Premium drink sales per guest |

**Example:**
- Employee PPA = $60, Benchmark = $55
- PPA Score = (60/55) × 100 = 109.09%
- Capped Score = 100%
- PPA Contribution = 100 × 0.25 = **25 pts**

**LSC Special Case (Inverse):**
LSC measures "Guests per LSC signup" - lower is better.
```
LSC Score = (Benchmark / Employee Value) × 100
```

---

### 2. METRIC BONUSES (20 points max)

Rewards for exceeding benchmarks. **Each metric can earn up to 5 bonus points.**

| Metric | Max Bonus |
|--------|-----------|
| PPA Bonus | 5 pts |
| LSC Bonus | 5 pts |
| LBW Bonus | 5 pts |
| Glassware Bonus | 5 pts |
| **Total** | **20 pts** |

**Formula:**
```
Bonus = ((Score% - 100) / 20) × 5
```
- At 100% of benchmark = 0 pts
- At 110% of benchmark = 2.5 pts
- At 120%+ of benchmark = 5 pts (max)

**Example:**
- PPA Score = 115%
- PPA Bonus = ((115 - 100) / 20) × 5 = 3.75 pts

---

### 3. CUSTOMER VOICE (CV) - Uncapped

Customer feedback scoring from surveys. **This is uncapped to heavily incentivize great service.**

#### A. NPS Score Component (max 10 pts)
Based on the employee's Net Promoter Score percentage:
```
NPS Points = NPS% / 10
```

| NPS % | Points |
|-------|--------|
| 100% | 10.0 pts |
| 90% | 9.0 pts |
| 80% | 8.0 pts |
| 77% | 7.7 pts |
| 50% | 5.0 pts |
| 0% | 0 pts |

#### B. Survey Points (NO CAP)
Individual survey responses add/subtract points:

| Rating | Category | Points |
|--------|----------|--------|
| 9-10 | Promoter | **+1 pts each** |
| 7-8 | Passive | 0 pts |
| 1-6 | Detractor | **-2 pt each** |

**Example:**
- Employee has NPS of 80%, 15 promoters, 2 detractors
- NPS Points = 80 / 10 = 8.0 pts
- Survey Points = (15 × 1) + (2 × -2) = 15 - 4 = 11 pts
- **Total CV Score = 8.0 + 11 = 19.00 pts**

---

### 4. REVIEW TRACKER (RT) - Max 15 pts

Points for being mentioned in online reviews (Yelp, Google, TripAdvisor, etc.)

**Formula:**
```
RT Bonus = Mentions × 0.33 pts (capped at 20 pts)
```

| Mentions | Points |
|----------|--------|
| 0 | 0 pts |
| 10 | 3 pts |
| 20 | 6 pts |
| 30 | 10 pts (max) |
| 60 | 20 pts (max) |
---

### 5. DAR PENALTIES (Admin-Only)

Disciplinary Action Reports reduce the final score. **Not visible in public rankings.**

| Action | Penalty |
|--------|---------|
| Written Warning | -3 pts each |
| Suspension | -5 pts each |

---

## COMPLETE FORMULA

```
TOTAL SCORE = 
    (PPA_Score × 0.25) +           // Max 25 pts
    (LSC_Score × 0.25) +           // Max 25 pts  
    (LBW_Score × 0.20) +           // Max 20 pts
    (Glass_Score × 0.15) +         // Max 15 pts
    Metric_Bonuses +               // Max 20 pts
    CV_Score +                     // Uncapped
    RT_Bonus -                     // Max 15 pts
    DAR_Penalties                  // Admin only
```

---

## SCORE EXAMPLES

### Example 1: Top Performer (Score: 113.8)
| Component | Value | Points |
|-----------|-------|--------|
| PPA (100% × 0.25) | $62 vs $55 benchmark | 25.0 |
| LSC (100% × 0.25) | 1:1 ratio achieved | 25.0 |
| LBW (95% × 0.15) | $7.60/guest vs $8 | 14.3 |
| Glass (100% × 0.10) | $1.30/guest vs $1.25 | 10.0 |
| **Weighted POS** | | **74.3** |
| PPA Bonus (120%+) | | 5.0 |
| LSC Bonus (115%) | | 3.75 |
| LBW Bonus (95%) | | 0.0 |
| Glass Bonus (104%) | | 1.0 |
| **Metric Bonuses** | | **9.75** |
| CV Score | 80% NPS, 20 promoters | 18.0 |
| RT Bonus | 25 mentions | 12.5 |
| **TOTAL** | | **114.55** |

### Example 2: Average Performer (Score: 78.5)
| Component | Value | Points |
|-----------|-------|--------|
| Weighted POS | At benchmark | 75.0 |
| Metric Bonuses | None | 0.0 |
| CV Score | 60% NPS, 5 promoters | 8.5 |
| RT Bonus | 10 mentions | 5.0 |
| **TOTAL** | | **88.5** |

### Example 3: Needs Improvement (Score: 52.3)
| Component | Value | Points |
|-----------|-------|--------|
| Weighted POS | Below benchmark | 48.0 |
| Metric Bonuses | None | 0.0 |
| CV Score | 40% NPS, 2 detractors | 2.0 |
| RT Bonus | 2 mentions | 1.0 |
| DAR | 1 written warning | -3.0 |
| **TOTAL** | | **48.0** |

---

## TIER ASSIGNMENTS

Based on peer rank percentile:

| Tier | Percentile | Description |
|------|------------|-------------|
| **Top Performer** | Top 25% | Rank 1-7 of 29 |
| **Above Average** | 51-75% | Rank 8-14 of 29 |
| **Below Average** | 26-50% | Rank 15-22 of 29 |
| **Needs Improvement** | Bottom 25% | Rank 23-29 of 29 |

---

## STORE HEALTH INDEX

The Store Performance Index aggregates employee scores into 4 categories:

| Category | Weight | Source |
|----------|--------|--------|
| Sales Execution | 25% | Average PPA scores |
| Upsell Performance | 25% | Average LBW + Glassware |
| Loyalty Engagement | 20% | Average LSC scores |
| Guest Experience | 30% | NPS (70%) + RT mentions (30%) |

**Store Health = Weighted average of all categories (0-100 scale)**

---

## BENCHMARKS (Q1 2026)

| Metric | Benchmark | Description |
|--------|-----------|-------------|
| PPA | $55.00 | Per Person Average |
| LBW | $8.00/guest | Liquor/Beer/Wine per guest |
| Glassware | $1.35/guest | Premium drinks per guest |
| LSC | 1:100 ratio | 1 loyalty signup per 100 guests |

---

## KEY TAKEAWAYS

1. **Base score is 85 points max** from POS metrics
2. **Bonuses can add 20+ points** for exceeding benchmarks
3. **Customer Voice is uncapped** - great service = unlimited upside
4. **RT mentions capped at 15 pts** (30 mentions)
5. **DAR penalties are hidden** from public rankings
6. **Typical top score: 100-120 points**
7. **Average score: 70-85 points**
