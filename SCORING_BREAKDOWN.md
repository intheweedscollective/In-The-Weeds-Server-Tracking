# Bubba Gump Scoring System — Canonical Breakdown

> **Status**: This document mirrors the canonical scoring model locked in
> `scoring_engine.py` (Q2 2026+). It supersedes every earlier version of
> this file. Any drift between the formulas below and `scoring_engine.py`
> is a bug — please file an issue.
> Last rewritten: **2026-05-24** (post Scoring Engine Audit).

---

## High-level overview

**Total Score = Weighted POS + Customer Voice + Metric Bonuses + Review Tracker − DAR**

| Component | Max Points | Description |
|-----------|------------|-------------|
| Weighted POS Metrics | 85 pts | Core performance metrics |
| Metric Bonuses | 20 pts | Exceeding benchmarks |
| Customer Voice (CV) | Uncapped | NPS + Promoter/Detractor points |
| Review Tracker (RT) | 20 pts | Online review mentions |
| DAR Penalties | Negative | Disciplinary deductions (admin-only) |

**Typical Score Range**: 60–125+ points.

---

## 1. Weighted POS Metrics (85 pts max)

Each metric is scored as `(employee_value ÷ benchmark) × 100`, **capped at 100**
before applying its weight. Weights are stored per-quarter in
`quarter_settings`; the canonical values are:

| Metric                       | Weight | Max Contribution |
|------------------------------|--------|------------------|
| **PPA** (Per Person Average) | 25%    | 25 pts           |
| **LSC** (Guests per signup)  | 25%    | 25 pts           |
| **LBW** (Liquor/Beer/Wine)   | 20%    | 20 pts           |
| **Glassware**                | 15%    | 15 pts           |
| **TOTAL**                    | 85%    | **85 pts**       |

### LSC special case (inverse)

### 1. WEIGHTED POS METRICS (85 points max)

```
LSC Score = (Benchmark ÷ Employee Value) × 100
```

| Metric | Weight | Max Contribution | What It Measures |
|--------|--------|------------------|------------------|
| **PPA** (Per Person Average) | 25% | 25 pts | Average revenue per guest |
| **LSC** (Loyalty Sales) | 25% | 25 pts | Loyalty program enrollments |
| **LBW** (Liquor/Beer/Wine) | 20% | 20 pts | Beverage upsells per guest |
| **Glassware** | 15% | 15 pts | Souvenier Glassware sales per guest |

- Employee PPA = $60, Benchmark = $55
- Raw Score = (60 ÷ 55) × 100 = 109.09%
- Capped Score = 100%
- PPA Contribution = 100 × 0.25 = **25 pts**

---

## 2. Metric Bonuses (20 pts max)

Each metric earns up to **5 bonus points** for performance above benchmark.

| Metric           | Max Bonus |
|------------------|-----------|
| PPA Bonus        | 5 pts     |
| LSC Bonus        | 5 pts     |
| LBW Bonus        | 5 pts     |
| Glassware Bonus  | 5 pts     |
| **Total**        | **20 pts**|

**Formula**:

```
Bonus = ((Score% − 100) ÷ 20) × 5
```

| Score % of benchmark | Bonus |
|----------------------|-------|
| ≤ 100%               | 0 pts |
| 110%                 | 2.5 pts |
| 120%+                | 5 pts (capped) |

### Example

- PPA Score = 115%
- PPA Bonus = ((115 − 100) ÷ 20) × 5 = **3.75 pts**

---

## 3. Customer Voice (CV) — Uncapped

Customer feedback. **Intentionally uncapped** to incentivize great service.

```
CV Score = (NPS% ÷ 10) + (Promoters × 1) − (Detractors × 2)
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

## 4. Review Tracker (RT) — 20 pts max

Points for being mentioned by name in external reviews
(Yelp / Google / TripAdvisor).

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

---

## 5. DAR Penalties (Admin-only, hidden from public rankings)

| Action          | Penalty       |
|-----------------|---------------|
| Written Warning | −3 pts each   |
| Suspension      | −5 pts each   |

---

## Complete formula

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

## Worked example — Top Performer

| Component               | Raw value                | Points  |
|-------------------------|--------------------------|---------|
| PPA (115% capped at 100)| $63 / $55                | 25.00   |
| LSC (110% capped at 100)| 91 guests/signup vs 100  | 25.00   |
| LBW (95%)               | $7.60/guest vs $8.00     | 19.00   |
| Glass (104%)            | $1.40/guest vs $1.35     | 15.00   |
| **Weighted POS**        |                          | **84.00** |
| PPA Bonus (115%)        |                          | 3.75    |
| LSC Bonus (110%)        |                          | 2.50    |
| LBW Bonus (95%)         |                          | 0.00    |
| Glass Bonus (104%)      |                          | 1.00    |
| **Metric Bonuses**      |                          | **7.25**  |
| CV (80% NPS, 20 promoters, 2 detractors) | 8 + 20 − 4    | 24.00   |
| RT (25 mentions)        | 25 × 0.33                | 8.25    |
| **TOTAL**               |                          | **123.50** |

---

## Server class (job-title × score)

Assigned by `scoring_engine.calculate_server_tier`:

| Class       | Rule                                                   |
|-------------|--------------------------------------------------------|
| Trainer     | Job title contains "trainer" (or score ≥ 100)          |
| Bartender   | Job title contains "bartender"                         |
| A-Server    | Score ≥ 85                                             |
| B-Server    | 70 ≤ Score < 85                                        |
| C-Server    | Score < 70                                             |

## Ranking tier (peer-percentile, for snapshot tier widgets)

Assigned by `scoring_engine.calculate_performance_tiers`:

| Tier                          | Percentile          |
|-------------------------------|---------------------|
| Top Performer                 | Top 25%             |
| Above Average                 | 25% – 50%           |
| Below Average                 | 50% – 85%           |
| Needs Immediate Improvement   | Bottom 15%          |

> **Server class** ≠ **Ranking tier**. Server class is an absolute label
> based on score thresholds and job title. Ranking tier is a relative
> peer-percentile band recalculated every snapshot.

---

## Benchmarks (canonical defaults)

| Metric    | Benchmark      | Notes                                    |
|-----------|----------------|------------------------------------------|
| PPA       | $55.00         | Per Person Average                       |
| LBW       | $8.00 / guest  | Liquor / Beer / Wine per guest           |
| Glassware | $1.35 / guest  | Premium drinks per guest                 |
| LSC       | 100 guests     | 1 loyalty signup per 100 guests (inverse)|

| Metric | Benchmark | Description |
|--------|-----------|-------------|
| PPA | $55.00 | Per Person Average |
| LBW | $8.00/guest | Liquor/Beer/Wine per guest |
| Glassware | $1.35/guest | Premium drinks per guest |
| LSC | 1:100 ratio | 1 loyalty signup per 100 guests |

---

## Key takeaways

1. **Base score is 85 points max** from POS metrics
2. **Bonuses can add 20+ points** for exceeding benchmarks
3. **Customer Voice is uncapped** - great service = unlimited upside
4. **RT mentions capped at 20 pts** (30 mentions)
5. **DAR penalties are hidden** from public rankings
6. **Typical top score: 100-120 points**
7. **Average score: 70-85 points**
