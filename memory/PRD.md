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

### V2 Scoring Engine (NEW - Completed)
A deterministic, in-app scoring engine that replaces Excel-based logic:

#### Data Model
- **Canonical Fields** (from upload): `Employee Name`, `Guests`, `Net Sales`, `LBW`, `Glassware Sales`, `LSC Count`
- **Derived Metrics** (app-calculated): PPA, LBW per Guest, Glassware per Guest, Guests per LSC

#### Quarter Settings
- Configurable benchmarks per metric
- Metric weights (must sum to 1.0)
- Bonus rate and cap settings
- Lock mechanism after scoring

#### Scoring Logic
1. **Normalized Scores**: `Score = (Metric / Benchmark) × 100`
2. **Bonus Points**: `Bonus = MIN((Score - 100) × Rate, Cap)` for scores > 100
3. **Weighted Total**: `Total = Σ(Score × Weight) + Total Bonus`
4. **Performance Tiers**: Based on percentile rank
   - Top 25%: Top Performer
   - 26-50%: Above Average
   - 51-85%: Below Average
   - 86-100%: Needs Immediate Improvement

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
- `PUT /api/v2/quarter-settings/{year}/{quarter}` - Update settings
- `POST /api/v2/quarter-settings/{year}/{quarter}/lock` - Lock settings
- `GET /api/v2/quarter-settings/{year}/{quarter}/benchmark-suggestions` - Get suggestions from previous quarter
- `POST /api/v2/upload/validate` - Validate file before upload
- `POST /api/v2/upload?year=X&quarter=QX` - Upload and score employees
- `GET /api/v2/employees` - Get V2 employees
- `GET /api/v2/rankings/{year}/{quarter}` - Get rankings
- `GET /api/v2/top-performers/{year}/{quarter}` - Get top performers
- `DELETE /api/v2/employees?year=X&quarter=QX` - Clear data (unlocks quarter)

### V1 Endpoints (Legacy)
- `POST /api/upload-excel` - Upload Excel file
- `GET /api/employees` - Get employees
- `POST /api/employees/{id}/generate-review` - Generate review PDF

## Database Collections
- `quarter_settings` - V2 quarter configurations
- `employees_v2` - V2 scored employee data
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
│   ├── scoring_engine.py   # V2 scoring logic and models
│   └── tests/
│       └── test_v2_scoring_engine.py
└── frontend/
    └── src/
        ├── pages/
        │   ├── Dashboard.js
        │   ├── QuarterSettings.js
        │   ├── EmployeeList.js
        │   ├── ReviewGeneration.js
        │   ├── Analytics.js
        │   └── TopPerformers.js
        └── components/
```

## Completed (as of Jan 26, 2026)
- ✅ V2 Scoring Engine Backend (scoring_engine.py)
- ✅ V2 API Endpoints (all CRUD operations)
- ✅ Quarter Settings page (/settings)
- ✅ Dashboard V2 integration (upload, validation, display)
- ✅ Lint warnings fixed
- ✅ Comprehensive test suite (21 backend tests, all passing)
- ✅ Download CSV Template feature (helps users get correct column format)

## Upcoming Tasks (P1)
1. **Phase 5: Update PDF Review Generation** - Use V2 data model for reviews
2. **Phase 6: Yodeck Slide Generation** - 16:9 leaderboard slides
3. **Update Remaining Pages** - Analytics, Top Performers with V2 data

## Future/Backlog (P2)
- Legacy V1 code cleanup
- Analytics enhancements (benchmark thresholds display)
- Batch line graph PDF uploads
- Time-series graph auto-generation
