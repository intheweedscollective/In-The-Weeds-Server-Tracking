# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees that handles:
- Data ingestion (XLSX uploads, scanned PDF POS reports, CSV reviews)
- Employee score calculation based on metrics (PPA, LSC, LBW, Glassware, Customer Voice NPS, Public Reviews)
- Downloadable slides for digital signage (Yodeck)
- Leaderboards and reports

## User Personas
- **Restaurant Manager**: Needs to track employee performance, generate reports, upload data
- **Regional Manager**: Multi-store oversight (planned)
- **Employees**: View their scores and rankings (via digital signage)

## Core Requirements
1. **Snapshot-First Data Architecture**: Uploads and parsed data tightly coupled to historical "Snapshots"
2. **Advanced Data Parsing**: Handle POS reports (via AI OCR), NPS Toolkit Server Performance Reports, ReviewTracker CSV exports
3. **Accurate Scoring & Finalization**: Weighted scoring logic, DAR deductions, locking finalized quarters
4. **Consistent UI**: All leaderboards, modals, slides pull from active Snapshot as single source of truth
5. **Downloadable Outputs**: Aesthetic PNG/PDF slides matching corporate branding

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key) for name detection in reviews

## Current State (2026-04-06)

### What's Implemented ✅
- Snapshot workflow system with embedded employees array
- Multiple slide generators (Top 10 By Metric, Complete Rankings, Tier slides, etc.)
- Manual score override endpoint (`/api/v2/snapshot-workflow/snapshots/{id}/manual-score`)
- 9-metric Employee Card with QR scans, RT bonus, Metric bonus
- Data reconciliation tools for Customer Voice and ReviewTracker
- React component refactoring (EmployeeDetailsModal, EmployeeCard, etc.)

### Working Endpoints
- `GET /api/v2/yodeck/{year}/{quarter}/top10` - Top 10 By Metric slide (VERIFIED)
- `GET /api/v2/yodeck/{year}/{quarter}/complete-rankings` - Complete Rankings slide (VERIFIED)
- `POST /api/v2/snapshot-workflow/snapshots/{id}/manual-score` - Manual score override

### Current Standings (Q1 2026 - 27 employees)
1. Starwars Mckinnon-Herrera - 112.1 (Trainer)
2. Keisha Martin - 102.5 (Trainer)
3. Diane Peterson - 91.7 (Trainer)

## Prioritized Backlog

### P0 - Critical
None currently

### P1 - High Priority
- [ ] Production 520 error on large PDF uploads (needs background task queue)
- [ ] Multi-Store Architecture (support for 22 locations)

### P2 - Medium Priority
- [ ] Review Spotlight feature
- [ ] Download All Slides as ZIP
- [ ] Backend modularization (server.py is 11.5k lines)
- [ ] Scraper complexity refactoring (cv_feedback_scraper.py has >60 cyclomatic complexity)

### P3 - Low Priority
- [ ] Momentum/Trend indicators (compare current vs previous snapshot)

## Architecture Notes

### Key Collections
- `snapshot_workflow`: Main collection with embedded `employees[]` array - source of truth
- `employees_v2`: Legacy data collection
- `qr_employees`: Yelp/Google QR click data

### Critical Constraints
- **DO NOT** trigger score recalculations on finalized snapshots
- Slide generators read from existing `total_score` without recalculating
- QR data linked by exact string name matching

## Files of Reference
- `/app/backend/routes/yodeck_slides.py` - Slide generation endpoints
- `/app/backend/yodeck_slides.py` - Slide image generators
- `/app/backend/snapshot_slides.py` - Complete rankings slide generator
- `/app/backend/server.py` - Main server (11.5k lines - needs modularization)
- `/app/frontend/src/components/EmployeeCard.jsx` - 9-metric employee card
