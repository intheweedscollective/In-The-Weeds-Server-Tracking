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

### Full Rankings Tab (NEW - Completed Jan 26, 2026)
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
- `GET /api/v2/full-rankings/{year}/{quarter}` - **NEW** Hierarchy-based rankings
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
│   ├── server.py           # FastAPI app, V1 & V2 routes
│   ├── scoring_engine.py   # V2 scoring logic, hierarchy rankings
│   └── tests/
│       ├── test_v2_scoring_engine.py
│       └── test_full_rankings.py
└── frontend/
    └── src/
        ├── pages/
        │   ├── Dashboard.js
        │   ├── FullRankings.js    # NEW
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
- ✅ **Full Rankings Tab (NEW)**
  - Hierarchy-based sorting: Trainers > Bartenders > A > B > C Servers
  - Settings-driven tier thresholds (A: 85.1, B: 70.1)
  - Position labels (T1, Bar1, A1, B1, C1...)
  - Table with full scoring breakdown
  - Filter by tier (no re-sorting allowed)
  - Settings page tier threshold inputs

## Upcoming Tasks (P1)
1. **PDF Review Generation Migration** - Use V2 data model for reviews
2. **Yodeck Slide Generation** - 16:9 leaderboard slides

## Future/Backlog (P2)
- Legacy V1 code cleanup
- Analytics enhancements (benchmark thresholds display)
- Batch line graph PDF uploads
- Time-series graph auto-generation
- Rankings Tab PDF export
