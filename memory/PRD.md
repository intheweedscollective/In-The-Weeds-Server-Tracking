# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees that handles:
- Data ingestion (XLSX uploads, scanned PDF POS reports, CSV reviews)
- Employee score calculation based on metrics (PPA, LSC, LBW, Glassware, Customer Voice NPS, Public Reviews)
- Downloadable slides for digital signage (Yodeck)
- Leaderboards and reports

## User Personas
- **Restaurant Manager**: Needs to track employee performance, generate reports, upload data
- **Regional Manager**: Multi-store oversight, global reporting
- **Employees**: View their scores and rankings (via digital signage)

## Core Requirements
1. **Snapshot-First Data Architecture**: Uploads and parsed data tightly coupled to historical "Snapshots"
2. **Advanced Data Parsing**: Handle POS reports (via AI OCR), NPS Toolkit Server Performance Reports, ReviewTracker CSV exports
3. **Accurate Scoring & Finalization**: Weighted scoring logic, DAR deductions, locking finalized quarters
4. **Consistent UI**: All leaderboards, modals, slides pull from active Snapshot as single source of truth
5. **Downloadable Outputs**: Aesthetic PNG/PDF slides matching corporate branding
6. **Multi-Store Support**: 22 locations with global reporting dashboards

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key) for name detection in reviews and POS OCR

## Current State (2026-04-06)

### What's Implemented ✅
- Snapshot workflow system with embedded employees array
- Multiple slide generators (Top 10 By Metric, Complete Rankings, Tier slides, etc.)
- Manual score override endpoint (`/api/v2/snapshot-workflow/snapshots/{id}/manual-score`)
- 9-metric Employee Card with QR scans, RT bonus, Metric bonus
- Data reconciliation tools for Customer Voice and ReviewTracker
- React component refactoring (EmployeeDetailsModal, EmployeeCard, etc.)
- **Background Task Queue** - Persistent job system for large file uploads
- **Multi-Store Architecture** - 22 Bubba Gump locations with global reporting

### New Features (This Session)

#### Background Task Queue (P1 - DONE)
- `/app/backend/routes/upload_jobs.py`
- `POST /api/v2/upload-jobs/direct` - Returns immediately with job_id
- `GET /api/v2/upload-jobs/{job_id}` - Check job status
- Jobs stored in MongoDB (survives restarts)
- Solves 520 timeout on large PDF uploads

#### Multi-Store Architecture (P1 - DONE)
- `/app/backend/routes/stores.py`
- 22 Bubba Gump locations across 5 regions
- Las Vegas store has 27 employees migrated
- Global Overview page at `/global`
- Store performance rankings and company-wide leaderboard

### Working Endpoints
- `GET /api/v2/yodeck/{year}/{quarter}/top10` - Top 10 By Metric slide
- `GET /api/v2/yodeck/{year}/{quarter}/complete-rankings` - Complete Rankings slide
- `POST /api/v2/snapshot-workflow/snapshots/{id}/manual-score` - Manual score override
- `POST /api/v2/upload-jobs/direct` - Background file upload
- `GET /api/v2/upload-jobs/{job_id}` - Check job status
- `GET /api/v2/stores` - List all stores
- `GET /api/v2/stores/reports/overview` - Global performance overview
- `GET /api/v2/stores/reports/leaderboard` - Global employee leaderboard
- `GET /api/v2/stores/reports/store-comparison` - Store metric comparison

### Current Standings (Q1 2026 - 27 employees in Las Vegas)
1. Starwars Mckinnon-Herrera - 112.1 (Trainer)
2. Trey Quick - 108.2 (Trainer)
3. Keisha Martin - 102.5 (Trainer)

### Store Distribution
- **West**: 7 stores (Las Vegas, Santa Monica, Long Beach, San Francisco, Monterey, San Diego, Anaheim)
- **East**: 5 stores (New York, Miami, Orlando, Fort Lauderdale, Gatlinburg)
- **Central**: 5 stores (Chicago, Nashville, New Orleans, San Antonio, Galveston)
- **Hawaii**: 3 stores (Maui, Oahu, Kona)
- **International**: 2 stores (Cancun, London)

## Prioritized Backlog

### P0 - Critical
None currently

### P1 - High Priority
- [x] ~~Production 520 error on large PDF uploads~~ - COMPLETED (upload-jobs system)
- [x] ~~Multi-Store Architecture~~ - COMPLETED (22 locations with global reporting)

### P2 - Medium Priority
- [ ] Backend modularization (server.py is 11.5k lines)
- [ ] Review Spotlight feature
- [ ] Download All Slides as ZIP
- [ ] Scraper complexity refactoring (cv_feedback_scraper.py has >60 cyclomatic complexity)

### P3 - Low Priority
- [ ] Momentum/Trend indicators (compare current vs previous snapshot)
- [ ] Store vs Store comparison feature

## Architecture Notes

### Key Collections
- `snapshot_workflow`: Main collection with embedded `employees[]` array - source of truth
- `employees_v2`: Legacy data collection
- `qr_employees`: Yelp/Google QR click data
- `upload_jobs`: Persistent job queue for background file processing
- `upload_chunks`: Temporary storage for chunked uploads
- `stores`: Store locations and metadata

### Critical Constraints
- **DO NOT** trigger score recalculations on finalized snapshots
- Slide generators read from existing `total_score` without recalculating
- QR data linked by exact string name matching

## Files of Reference
- `/app/backend/routes/upload_jobs.py` - Background upload/job system
- `/app/backend/routes/stores.py` - Multi-store management
- `/app/backend/routes/yodeck_slides.py` - Slide generation endpoints
- `/app/backend/yodeck_slides.py` - Slide image generators
- `/app/backend/server.py` - Main server (11.5k lines - needs modularization)
- `/app/frontend/src/pages/GlobalOverview.jsx` - Global overview page
- `/app/frontend/src/contexts/StoreContext.jsx` - Store context provider
- `/app/frontend/src/components/StoreSelector.jsx` - Store selector dropdown

## Test Reports
- `/app/test_reports/iteration_14.json` - Multi-store architecture tests (26/26 passed)
- `/app/test_reports/iteration_13.json` - React refactoring tests
