# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees.

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key)

## Current State (2026-04-07)

### Latest Changes
- **Store Performance Index Overhaul (2026-04-07)**:
  - Realigned scoring model based on Bubba Gump Daily Flash Report analysis
  - **NEW WEIGHTS**: Sales (20%), Upsell (20%), Loyalty (25%), Labor (15%), Guest (20%)
  - **NEW: Labor Efficiency category** - tracks Hourly Labor % vs target
  - **Added concept benchmarks** to Quarter Settings:
    - `concept_avg_ppa`: 45.33 (from Flash Report)
    - `concept_lsc_ratio`: 181 (1:181 guests per LSC)
    - `concept_labor_pct`: 17.01%
  - Shows "vs concept" comparisons (e.g., "1.7x better", "+22.9%", "+1.95pp")
  - Awards indicators for Best in Concept achievements
  - Store Health Score increased from 80.9 → 84.2 with new weights

- **Momentum Trend Indicator (2026-04-07)**:
  - Rolling average momentum comparison showing direction and point change (e.g., ↗ +8.3)
  - TrendIndicator component in Dashboard Top 5 Performers section
  - TrendIndicator in Top Performers modal
  - Backend endpoint `/v2/trends/momentum/{year}/{quarter}` provides current score, rolling average, change, direction, percent_change, and snapshots_used
  - Color coding: green for up trend, red for down trend, gray for stable
  - Tooltip with detailed breakdown on hover

- **Help Center & Self-Help Improvements (2026-04-06)**:
  - Completely redesigned Help Center with searchable FAQ (21 questions in 6 categories)
  - New Troubleshooting section with 6 common issues and step-by-step solutions
  - Created reusable HelpTooltip component for contextual help throughout the app
  - Added Quick Actions shortcuts to key pages
  - Fixed outdated scoring formulas (CV = Promoters×0.5 - Detractors×1)
  - Corrected tier thresholds (A-Server ≥85, not 80)
  - Added documentation for new features (Quarterly Summary, Multi-Store, Metric Bonus)

- **Backend Route Modularization (2026-04-06)**:
  - Created admin.py (1,150 lines) and reviews.py (646 lines)
  - server.py reduced from 11,847 to 7,166 lines (40% reduction)

- **Quarterly Summary Report (2026-04-06)**:
  - New print-friendly page at `/quarterly-summary`
  
- **UI Label Updates (2026-04-06)**:
  - "Customer Voice" / "Cust. Voice" replaces "CV Score" / "NPS Score"
  - "Metric Bonus" replaces "POS bonus" / "Metric+"

### Backend Modularization Progress
**server.py: 7,252 → 6,842 lines (410 lines extracted)**

### Route Modules (15 total)
| Module | Lines | Purpose |
|--------|-------|---------|
| `/app/backend/routes/admin.py` | 1,150 | Admin utilities, data sync, fixes |
| `/app/backend/routes/audit.py` | 921 | Scoring audit system |
| `/app/backend/routes/cv.py` | 868 | CV feedback & NPS |
| `/app/backend/routes/yodeck_slides.py` | 859 | Slide generation + Quarterly Summary |
| `/app/backend/routes/pos_upload.py` | 836 | **NEW** POS OCR, PDF parsing |
| `/app/backend/routes/stores.py` | 657 | Multi-store management |
| `/app/backend/routes/trends.py` | 649 | Trend analytics + Momentum |
| `/app/backend/routes/reviews.py` | 646 | Reviews & RT management |
| `/app/backend/routes/upload_jobs.py` | 586 | Background file uploads |
| `/app/backend/routes/employees.py` | 581 | Employee CRUD |
| `/app/backend/routes/finalization.py` | 507 | Quarter finalization |
| `/app/backend/routes/insights.py` | 443 | **NEW** Store health, coaching, reviews |
| `/app/backend/routes/quarter_settings.py` | 302 | Settings management |
| `/app/backend/routes/snapshot_routes.py` | ~500 | Snapshot workflow |
| `/app/backend/server.py` | 6,842 | Main server (core routes) |

### Multi-Store Architecture
- 22 Bubba Gump locations across 5 regions
- Las Vegas store has 27 employees migrated
- Global Overview page at `/global`

### Key Thresholds
- **A-Server**: Score >= 85
- **B-Server**: Score >= 70 and < 85
- **C-Server**: Score < 70
- **Trainer**: Score >= 100 OR designated role

## Prioritized Backlog

### P1 - High Priority
- [x] ~~Production 520 error~~ - DONE (upload_jobs.py)
- [x] ~~Multi-Store Architecture~~ - DONE (stores.py)
- [x] ~~UI Label Updates (Customer Voice, Metric Bonus)~~ - DONE
- [x] ~~Quarterly Summary Report~~ - DONE
- [x] ~~Backend route modularization~~ - DONE (admin.py, reviews.py - 40% reduction)

### P2 - Medium Priority
- [ ] Review Spotlight feature
- [ ] Download All Slides as ZIP

### P3 - Low Priority
- [x] ~~Momentum/Trend indicators~~ - DONE (2026-04-07)
- [ ] Store vs Store comparison
