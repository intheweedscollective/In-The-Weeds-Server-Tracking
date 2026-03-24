# Staff Score Engine - Performance Review Application

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees that handles:
- Data ingestion (XLSX upload)
- Employee score calculation based on configurable metrics
- Generate outputs: leaderboards, downloadable slides for digital signage (Yodeck), reports

## Core Scoring Formula (User Confirmed)
```
Total Score = Base POS Score + CV Score + RT Bonus + Metric Bonus

Base POS Score (75 pts max):
- PPA: 25%
- LSC: 25%
- LBW: 15%
- Glassware: 10%

CV Score (Customer Voice):
- NPS Points: NPS% / 10 (max 10 pts)
- Promoter Bonus: +0.5 per promoter (9-10 rating)
- Detractor Penalty: -1 per detractor (≤6 rating)
- Formula: cv_score = nps_pts + (promoters × 0.5) - (detractors × 1)

RT Bonus (Review Tracker):
- 0.5 pts per mention
- Capped at 15 pts

Metric Bonus (up to 20 pts):
- 5 pts max per metric at 120%+ of benchmark
- Linear scale from 100%-120%
```

## DATA ARCHITECTURE (SIMPLIFIED - March 16, 2026)

### Single Source of Truth
All data uploads now go directly to `employees_v2` collection. This is the MASTER data.

**Data Flow:**
1. **Upload** → `/api/v2/data/upload-pos` → `employees_v2` (master)
2. **Sync** → Auto-syncs to latest snapshot
3. **Dashboard** → Reads from `employees_v2`

**Upload Endpoints (All update `employees_v2` + sync to snapshots):**
- `POST /api/v2/data/upload-pos` - Unified POS upload (NEW)
- `POST /api/v2/cv/server-performance/upload` - Customer Voice data
- `POST /api/v2/rt/upload` - Review Tracker data

### Previous Architecture (DEPRECATED)
Previously, data could be uploaded to snapshots separately, causing sync issues between Dashboard and Snapshots. This has been fixed.

## Tech Stack
- Frontend: React with Shadcn/UI components
- Backend: FastAPI (Python)
- Database: MongoDB
- Integrations: OpenAI GPT-4o (via Emergent LLM Key)

## What's Been Implemented

### Core Features ✅
- Employee data upload via XLSX
- Complete scoring engine with all metrics
- Leaderboard with hierarchy-based rankings (Trainer > Bartender > A/B/C Server)
- Snapshot system for historical data
- QR code generation for employees
- AI-powered performance review generation

### March 16, 2026 Session ✅
- **UNIFIED DATA UPLOAD**: Created new `/api/v2/data/upload-pos` endpoint that saves directly to `employees_v2` and auto-syncs to snapshots
- **Dashboard/Snapshot Sync**: All three upload endpoints (POS, CV, RT) now automatically sync `employees_v2` to the latest snapshot
- **"Single Source of Truth" UI**: Updated Data Uploads page to clearly show that all uploads update Dashboard and Snapshots automatically
- **Simplified Data Flow**: Removed confusion about where to upload data - now there's ONE place for each data type

### Earlier Session (March 2026) ✅
- **CV Score Bug Fixed**: Corrected multiple functions that were missing NPS points in cv_score calculation
- **Batch Score Fix**: Fixed 19 employees with incorrect CV scores
- **Data Preservation**: Added logic to preserve existing CV/RT data when raw feedback tables are empty
- **Scoring Formula Alignment**: Unified all scoring functions to use the correct formula
- **Reports Tab Fixed**: Corrected broken download buttons (Top 10 Slide, Rankings PDF, Complete Rankings)
- **Detractors Now Manual Only**: Removed automatic detractor calculation from CV uploads
- **Audit Formula Fixed**: All 27 employees now pass audit
- **Executive Insights Dashboard**: Added Store Performance Index, Coaching Radar, Guest Impact Tracker panels

## Known Issues / Technical Debt

### P0 (Critical)
- None currently

### P1 (High Priority)
- Employees not yet associated with stores (Store Leaderboard non-functional)
- Trend indicators not yet on main dashboard

### P2 (Medium Priority)
- Onboarding modal can be dismissed but reappears on fresh browser sessions
- server.py is 11k+ lines and needs refactoring into smaller modules

### P3 (Low Priority)
- Background task queue not implemented (long operations could timeout)

### December 2026 Session ✅
- **Employee Cleanup Tool Enhanced**: Expanded invalid pattern detection to catch more test/invalid entries like "Server Sales", "Total", "Demo User", "Test Employee", and many more patterns
- **Multi-Select Delete Feature**: Added bulk selection and delete functionality to Employees page:
  - "Select Multiple" button toggles select mode
  - Checkboxes on all employee cards when in select mode
  - "Select All" / "Deselect All" buttons
  - "Delete Selected" with confirmation dialog
  - Bulk delete via `/api/v2/employees/cleanup/delete` endpoint
- **Fixed "Not Assessed" on Analytics Page**: Performance tiers were missing from database. Fixed by:
  1. Running a one-time migration script to populate existing employee tiers
  2. Added fallback tier calculation in `get_employees_v2` API so tiers are computed on-the-fly if missing
- **Testing**: All features verified with 100% pass rate (backend: 11/11 tests, frontend: all multi-select features working)

### December 2026 Session (Continued) ✅
- **Scoring Guide Page Added**: Created comprehensive `/scoring-guide` page with collapsible sections explaining:
  - Score Formula overview (POS Metrics + Bonuses + CV Score + RT Bonus)
  - Weighted POS Metrics breakdown (PPA 25%, LSC 25%, LBW 15%, Glassware 10%)
  - Metric Bonuses (up to 20 pts)
  - Customer Voice scoring (NPS + Promoter/Detractor points - UNCAPPED)
  - Review Tracker bonus (0.5 pts per mention, max 15)
  - DAR Penalties (admin-only)
  - Store Health Index
  - Performance Tiers
- **Navigation Updated**: Added "Scoring Guide" link to sidebar (under EXPORTS section)
- **Data Integrity Verified**: All 29 employees now pass scoring audit (VERIFIED status)
- **Circular Bug Status**: The `enforce_data_caps` endpoint already includes logic to sync `rt_mentions` after removing excess reviews via `sync_employee_review_mentions()` function

## File Structure
```
/app/
├── backend/
│   ├── server.py              # Main API (12k+ lines - needs refactoring)
│   ├── scoring_engine.py      # Scoring constants and models
│   ├── snapshot_slides.py     # Slide generation
│   └── pos_report_parser.py   # POS data parsing
└── frontend/
    └── src/
        ├── pages/
        │   ├── EmployeeList.js
        │   ├── FullRankings.js
        │   ├── Leaderboard.js
        │   ├── DataUploads.js
        │   ├── ReviewTracker.js
        │   ├── ScoringGuide.js    # NEW: Detailed scoring explanation page
        │   └── ...
        └── components/
            ├── SidebarLayout.jsx  # Navigation with Scoring Guide link
            └── ...
```

## Key API Endpoints
- `GET /api/v2/employees` - List employees
- `POST /api/v2/audit/fix-employee/{name}` - Recalculate single employee score
- `POST /api/v2/cv/server-performance/upload` - Upload CV data
- `POST /api/v2/rt/upload` - Upload RT data
- `PUT /api/v2/employees/{id}/cv-stats` - Manual CV stat update
- `GET /api/v2/employees/cleanup/analyze` - Analyze employees for test/invalid data
- `POST /api/v2/employees/cleanup/delete` - Bulk delete employees by ID

## Credentials
- Loyalty Voice: Bglv@ldry.com / EZMoney2026
- ReviewTrackers: Bglv@ldry.com / EZMoney2026!
