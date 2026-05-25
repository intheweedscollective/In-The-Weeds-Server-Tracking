# Bubba Gump Scoring System — Canonical Breakdown

> **Status**: This document mirrors the canonical scoring model locked in
> `scoring_engine.py` (Q2 2026+). It supersedes every earlier version of
> this file. Any drift between the formulas below and `scoring_engine.py`
> is a bug — please file an issue.
> Last rewritten: **2026-05-24** (post Scoring Engine Audit).

---

## High-level overview

**Total Score = Weighted POS + Customer Voice + Metric Bonuses + Review Tracker − DAR**

| Component             | Max Points  | Notes                                                                  |
|-----------------------|-------------|------------------------------------------------------------------------|
| Weighted POS Metrics  | 85 pts      | Core operational performance from POS data                             |
| Metric Bonuses        | 20 pts      | Up to 5 pts/metric for exceeding benchmark                             |
| Customer Voice (CV)   | Uncapped    | NPS%/10 + Promoters − Detractors                                       |
| Review Tracker (RT)   | 20 pts      | 0.33 pts per external mention, capped at 20                            |
| DAR Penalties         | Negative    | Admin-only disciplinary deductions, hidden from public rankings        |

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

LSC measures "guests per loyalty signup" — **lower is better**. The score
flips the ratio:

```
LSC Score = (Benchmark ÷ Employee Value) × 100
```

### Example

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

| Survey rating | Category   | Points         |
|---------------|------------|----------------|
| 9–10          | Promoter   | **+1 pt each** |
| 7–8           | Passive    | 0 pts          |
| 1–6           | Detractor  | **−2 pts each**|

### Example

Employee with NPS 80%, 15 promoters, 2 detractors:

- NPS Points = 80 ÷ 10 = 8.0 pts
- Survey Points = (15 × 1) − (2 × 2) = 15 − 4 = 11 pts
- **CV Score = 8.0 + 11 = 19.0 pts**

> Promoter / Detractor weights are stored per-quarter
> (`cv_promoter_points` / `cv_detractor_points`). Canonical values are
> **+1 / −2**.

---

## 4. Review Tracker (RT) — 20 pts max

Points for being mentioned by name in external reviews
(Yelp / Google / TripAdvisor).

```
RT Bonus = min(Mentions × 0.33, 20)
```

| Mentions | Points    |
|----------|-----------|
| 0        | 0 pts     |
| 10       | 3.3 pts   |
| 30       | 9.9 pts   |
| 60       | 19.8 pts  |
| 61+      | 20 pts (capped) |

> Rate and cap are stored per-quarter (`rt_points_per_mention` /
> `rt_max_points`). Canonical values are **0.33 / 20**.
> CV and RT are **separately tracked** — there is **no combined cap**.

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
    (min(PPA_Score, 100)    × 0.25) +     // 25 pts
    (min(LSC_Score, 100)    × 0.25) +     // 25 pts
    (min(LBW_Score, 100)    × 0.20) +     // 20 pts
    (min(Glass_Score, 100)  × 0.15) +     // 15 pts
    PPA_Bonus + LSC_Bonus + LBW_Bonus + Glass_Bonus +   // up to 20 pts
    CV_Score +                            // uncapped
    min(Mentions × 0.33, 20) −            // up to 20 pts
    DAR_Penalties                         // admin-only deductions
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

Stored per-quarter in `quarter_settings` and editable until the quarter
is **locked**. Locked quarters are immutable history.

---

## Key takeaways

1. **Weighted POS base = 85 pts max** (25/25/20/15).
2. **Metric bonuses add up to 20 pts** (5/metric, linear 100%–120%).
3. **Customer Voice is uncapped** — great service has unlimited upside.
4. **Review Tracker capped at 20 pts** (~61 mentions at 0.33 pts/mention).
5. **CV + RT are separate** — there is no combined cap between them.
6. **DAR penalties are hidden** from public rankings.
7. **Typical scores**: A-Server 85–105, top performers 110–125+.
