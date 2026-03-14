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

### Recent Session (March 2026) ✅
- **CV Score Bug Fixed**: Corrected multiple functions that were missing NPS points in cv_score calculation
- **Batch Score Fix**: Fixed 19 employees with incorrect CV scores
- **Data Preservation**: Added logic to preserve existing CV/RT data when raw feedback tables are empty
- **Scoring Formula Alignment**: Unified all scoring functions to use the correct formula
- **Reports Tab Fixed**: Corrected broken download buttons (Top 10 Slide, Rankings PDF, Complete Rankings) - all verified working
- **Detractors Now Manual Only**: Removed automatic detractor calculation from CV uploads. Detractors must be manually entered via DAR or employee edit. Created `/api/v2/admin/clear-all-detractors` endpoint to clear existing detractors.

## Known Issues / Technical Debt

### P0 (Critical)
- None currently

### P1 (High Priority)
- Onboarding modal blocks UI interactions (needs dismiss mechanism)
- Employees not yet associated with stores (Store Leaderboard non-functional)

### P2 (Medium Priority)
- Trend indicators not yet on main dashboard
- server.py is 9k+ lines and needs refactoring into smaller modules

### P3 (Low Priority)
- Background task queue not implemented (long operations could timeout)

## File Structure
```
/app/
├── backend/
│   ├── server.py              # Main API (9k+ lines - needs refactoring)
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
        │   └── ...
        └── components/
```

## Key API Endpoints
- `GET /api/v2/employees` - List employees
- `POST /api/v2/audit/fix-employee/{name}` - Recalculate single employee score
- `POST /api/v2/cv/server-performance/upload` - Upload CV data
- `POST /api/v2/rt/upload` - Upload RT data
- `PUT /api/v2/employees/{id}/cv-stats` - Manual CV stat update

## Credentials
- Loyalty Voice: Bglv@ldry.com / EZMoney2026
- ReviewTrackers: Bglv@ldry.com / EZMoney2026!
