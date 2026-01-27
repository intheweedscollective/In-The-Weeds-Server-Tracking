# Bubba Gump Performance Review System - PRD

## Problem Statement
Build a full-stack application to generate quarterly performance reviews for restaurant employees. The system should:
1. Accept employee performance data via Excel/CSV upload
2. Calculate derived metrics and scores using a deterministic scoring engine
3. Generate AI-powered performance reviews with PDF output
4. Display rankings and analytics dashboards

## Tech Stack
- **Frontend**: React.js, Tailwind CSS, Shadcn/UI
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI Integration**: OpenAI GPT-5.2 via Emergent Integrations

## Core Features

### V2 Scoring Engine (Completed)
A deterministic, in-app scoring engine that replaces Excel-based logic:

#### Data Model
- **Canonical Fields** (from upload): `Employee Name`, `Job Title`, `Guests`, `Net Sales`, `Liquor Sales`, `Beer Sales`, `Wine Sales`, `Glassware Sales`, `LSC Count`, Customer Voice fields
- **Derived Metrics** (app-calculated): PPA, LBW Total, LBW per Guest, Glassware per Guest, Guests per LSC

#### Quarter Settings
- Configurable benchmarks per metric
- Metric weights (must sum to 1.0): PPA(25%), LSC(25%), LBW(20%), Glass(15%), CV(15%)
- Bonus rate and cap settings
- **Server Tier Thresholds**: A-Server min (85.1), B-Server min (70.1) - adjustable
- Lock mechanism after scoring

#### Scoring Logic
1. **Normalized Scores**: `Score = (Metric / Benchmark) × 100`
2. **Bonus Points**: `Bonus = MIN((Score - 100) × Rate, Cap)` for scores > 100
3. **Weighted Total**: `Total = Σ(Score × Weight) + Total Bonus`
4. **Performance Tiers**: Based on percentile rank

### Full Rankings Tab (Completed Jan 26, 2026)
Hierarchy-based rankings with settings-driven server tiering:

#### Hierarchy Order (Fixed)
1. **Trainers** - Job Title contains "Trainer"
2. **Bartenders** - Job Title contains "Bartender" or "Bar"
3. **A-Servers** - Score >= A-Server min threshold (85.1 default)
4. **B-Servers** - Score >= B-Server min AND < A-Server min (70.1 default)
5. **C-Servers** - Score < B-Server min

#### Position Labels
- Trainers: T1, T2, T3...
- Bartenders: Bar1, Bar2, Bar3...
- A-Servers: A1, A2, A3...
- B-Servers: B1, B2, B3...
- C-Servers: C1, C2, C3...

#### Table Columns
Position | Employee Name | Tier | Total Score | Bonus | PPA (earned/possible) | LBW | LSC | Glassware

#### Features
- Filter by Tier (no sorting allowed - rank is final)
- Thresholds displayed from Settings
- Auto-update when Settings change
- **PDF Download** with isolated columns for each point type (Base + Bonus for each metric)

### PDF Download Feature (Completed Jan 26, 2026)
- Download button on Rankings page
- Landscape A4 format
- Columns: Position, Label, Name, Tier, Total Score, Total Bonus, PPA (Base/Bonus), LBW (Base/Bonus), LSC (Base/Bonus), Glass (Base/Bonus), CV Score
- Includes scoring formula legend
- Tier thresholds displayed in header

### Other Features
- Employee list with metrics display
- AI-powered review generation with PDF output
- Analytics dashboard
- Top performers page
- Line graph upload for review PDFs

## API Endpoints

### V2 Endpoints (Primary)
- `POST /api/v2/quarter-settings` - Create quarter settings
- `GET /api/v2/quarter-settings/{year}/{quarter}` - Get settings
- `PUT /api/v2/quarter-settings/{year}/{quarter}` - Update settings (includes tier thresholds)
- `POST /api/v2/quarter-settings/{year}/{quarter}/lock` - Lock settings
- `GET /api/v2/quarter-settings/{year}/{quarter}/benchmark-suggestions` - Get suggestions
- `POST /api/v2/upload/validate` - Validate file before upload
- `POST /api/v2/upload?year=X&quarter=QX` - Upload and score employees
- `GET /api/v2/employees` - Get V2 employees
- `GET /api/v2/rankings/{year}/{quarter}` - Get rankings (by score)
- `GET /api/v2/full-rankings/{year}/{quarter}` - Hierarchy-based rankings
- `GET /api/v2/full-rankings/{year}/{quarter}/pdf` - **NEW** Download rankings as PDF
- `GET /api/v2/top-performers/{year}/{quarter}` - Get top performers
- `GET /api/v2/template` - Download CSV template (includes Job Title)
- `DELETE /api/v2/employees?year=X&quarter=QX` - Clear data (unlocks quarter)

### V1 Endpoints (Legacy)
- `POST /api/upload-excel` - Upload Excel file
- `GET /api/employees` - Get employees
- `POST /api/employees/{id}/generate-review` - Generate review PDF

## Database Collections
- `quarter_settings` - V2 quarter configurations (includes tier thresholds)
- `employees_v2` - V2 scored employee data (includes job_title)
- `employees` - V1 employee data (legacy)
- `reviews` - Generated reviews
- `line_graphs` - Uploaded line graphs

## UI Theme
- **Style**: Bright, fun "Bubba Gump" theme (no dark mode)
- **Colors**: Red primary (#D12E2E), Blue secondary (#005B96), Cream background
- **Font**: Serif headings, clean body text

## File Structure
```
/app/
├── backend/
│   ├── server.py               # FastAPI app, V1 & V2 routes
│   ├── scoring_engine.py       # V2 scoring logic, hierarchy rankings
│   ├── pdf_full_rankings.py    # NEW - Full rankings PDF generator
│   ├── pdf_top_performers.py
│   ├── pdf_analytics.py
│   └── tests/
│       ├── test_v2_scoring_engine.py
│       └── test_full_rankings.py
└── frontend/
    └── src/
        ├── pages/
        │   ├── Dashboard.js
        │   ├── FullRankings.js     # Rankings with PDF download
        │   ├── QuarterSettings.js
        │   ├── EmployeeList.js
        │   ├── ReviewGeneration.js
        │   ├── Analytics.js
        │   └── TopPerformers.js
        └── components/
            └── Navigation.js
```

## Completed (as of Jan 26, 2026)
- ✅ V2 Scoring Engine Backend (scoring_engine.py)
- ✅ V2 API Endpoints (all CRUD operations)
- ✅ Quarter Settings page (/settings)
- ✅ Dashboard V2 integration (upload, validation, display)
- ✅ Comprehensive test suite
- ✅ Download CSV Template feature (includes Job Title)
- ✅ **Phase 5: Q1 2026 Official Scoring Model**
  - Customer Voice (NPS-style): Promoters +1, Passives 0, Detractors -2
  - Review Tracker bonus, DAR penalties
  - New weights: PPA(25%), LSC(25%), LBW(20%), Glass(15%), CV(15%)
- ✅ **Split Alcohol Sales Input** (Liquor + Beer + Wine = LBW Total)
- ✅ **All Pages Updated to V2 API**
- ✅ **Full Rankings Tab**
  - Hierarchy-based sorting: Trainers > Bartenders > A > B > C Servers
  - Settings-driven tier thresholds (A: 85.1, B: 70.1)
  - Position labels (T1, Bar1, A1, B1, C1...)
  - Table with full scoring breakdown
  - Filter by tier (no re-sorting allowed)
  - Settings page tier threshold inputs
- ✅ **Rankings PDF Download**
  - Isolated columns for each point type (Base + Bonus per metric)
  - Landscape A4 format with all 28 employees
  - Scoring formula legend included
- ✅ **PDF Review Generation (V2 Migration)**
  - Reviews page now uses V2 API
  - AI content generation uses V2 metrics
  - PDF includes Q1 2026 scoring breakdown table
- ✅ **Yodeck Slide Generation**
  - 16:9 PNG slides (1920x1080) for digital signage
  - Dark navy professional design, high-contrast, TV-legible
  - Top 10 Performers slide (leaderboard)
  - Tier-specific slides (Trainers, Bartenders, A/B/C-Servers)
  - Paginated for tiers with >10 employees
  - Visual metric indicators (green/yellow/red dots)
  - Download All Slides button
  - Yodeck-ready format (<5MB per slide)
- ✅ **Yodeck Theme Customization (Jan 26, 2026)**
  - Per-quarter theme settings stored in QuarterSettings
  - 4 pre-built themes: Dark Navy, Light Corporate, Bubba Red, Ocean Blue
  - Custom theme with 5 color pickers (Background, Gradient, Text, Accent, Secondary)
  - Theme selection UI on both Settings page and Yodeck page
  - Live preview of theme in Settings page
  - All slides use the selected theme
- ✅ **Special Yodeck Slides (Jan 26, 2026)**
  - "Most Improved" slide - shows top 8 employees with biggest score increase
  - "Promotion Watchlist" slide - B-Servers within 10 points of A-Server threshold
  - "At Risk/Coaching Focus" slide (Manager Only) - C-Servers needing attention
- ✅ **Fixed Slide Download Issue (Jan 26, 2026)**
  - Fixed double `/api/api/` URL issue in download functions
  - Improved download using fetch blob method for reliability
  - Graceful fallback to open in new tab if download fails
- ✅ **Analytics Enhancements (Jan 26, 2026)**
  - Visual range chart on each metric card showing benchmark position
  - Red "Target" benchmark line prominently displayed
  - Blue diamond showing Team Average position relative to benchmark
  - Green/red zone indicators for high/low performance areas
  - Dynamic benchmark values pulled from Quarter Settings
  - "vs Target" percentage showing how team performs against benchmark
  - Metric weights displayed (e.g., PPA 25%, LBW 20%)
  - "Higher/Lower is better" indicator for each metric
- ✅ **Seasonal/Holiday Slide Decorations (Jan 26, 2026)**
  - Added 8 holiday themes: Valentine's Day, St. Patrick's Day, Easter, 4th of July, Halloween, Thanksgiving, Christmas, New Year
  - Auto-detect mode automatically shows decorations based on current date
  - Manual override option on Settings page to force any holiday theme
  - Theme decorations include hearts, shamrocks, eggs, stars, pumpkins, leaves, snowflakes, fireworks
  - Emoji in slide title changes based on selected theme
  - Background colors adapt to holiday (e.g., pink/magenta for Valentine's)
  - Theme and seasonal settings can be updated even when quarter is locked

## Upcoming Tasks (P1)
- None! All major features complete.

## Future/Backlog (P2)
- Download all slides as ZIP archive
- Batch line graph PDF uploads
- Time-series graph auto-generation
- Automated daily/weekly slide pack generation for Yodeck playlists

## Completed Cleanup (Jan 26, 2026)
- ✅ **V1 Legacy Code Removal**
  - Removed V1 PDF endpoints (`/top-performers/pdf`, `/analytics/pdf`)
  - Removed V1 upload endpoint (`/upload-excel`)
  - Removed V1 employee CRUD endpoints
  - Removed V1 models (Employee, EmployeeCreate, Review, etc.)
  - Removed legacy KPI_DEFINITIONS
  - Removed V1 PDF generation functions
  - Deleted `pdf_analytics.py` and `pdf_top_performers.py` files
  - Created V2 PDF endpoints (`/v2/top-performers/{year}/{quarter}/pdf`, `/v2/analytics/{year}/{quarter}/pdf`)
  - Updated frontend to use V2 PDF endpoints
  - Codebase reduced by ~500 lines, now exclusively uses V2 scoring engine
- ✅ **Time-Series Graph Auto-Generation (Jan 26, 2026)**
  - Created `trend_charts.py` module using matplotlib for chart generation
  - Added trend API endpoints:
    - `GET /api/v2/trends/{year}/{quarter}/team` - Team comparison chart (PNG)
    - `GET /api/v2/trends/{year}/{quarter}/team/data` - Team trend data (JSON)
    - `GET /api/v2/trends/{year}/{quarter}/employee/{id}` - Individual employee chart
    - `GET /api/v2/trends/{year}/{quarter}/employee/{id}/data` - Individual trend data
  - Chart types: Comparison bars, Change %, Tier distribution pie charts
  - Metrics compared: PPA, LBW/Guest, Glass/Guest, Guests/LSC, CV Score, Total Score
  - Added "Quarter Trends" tab to Analytics page with:
    - Team Average Comparison chart
    - Tier Distribution comparison (pie charts)
    - Metric change cards with up/down indicators
    - Tier count changes summary
- ✅ **Individual Employee Trend Charts on Reviews Page (Jan 27, 2026)**
  - Added "Trends" toggle button on each employee card in /reviews page
  - Expandable section showing Quarter Comparison Chart (bar chart)
  - Metric Changes panel showing current vs previous quarter values
  - Up/down indicators with percentage change for each metric
  - Color-coded backgrounds (green for improvement, red for decline)
  - Graceful handling when no previous quarter data exists
  - API endpoints used:
    - `GET /api/v2/trends/{year}/{quarter}/employee/{id}?chart_type=comparison` - PNG chart
    - `GET /api/v2/trends/{year}/{quarter}/employee/{id}/data` - JSON trend data
