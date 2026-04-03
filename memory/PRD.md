# Performance Review Application - PRD

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees that handles:
- Data ingestion (XLSX, scanned PDF, CSV reviews)
- Employee score calculation based on detailed metrics (PPA, LSC, LBW, Glassware, Customer Voice NPS, Public Reviews)
- Generate outputs: downloadable slides for digital signage (Yodeck), leaderboards, reports
- QR code tracking system for Google Reviews

## Architecture Change: Snapshot-First Model (Implemented 2026-03-29)

### Previous Flow:
1. Upload data globally
2. Take snapshot
3. Snapshot pulls from latest uploaded data

### New Flow (Implemented):
1. Click "Create New Snapshot"
2. Enter snapshot details (name, date range, quarter)
3. System guides user through required uploads for that snapshot
4. Each uploaded file is permanently tied to that snapshot
5. Process and finalize snapshot
6. Rankings page reflects most recent completed snapshot

### Key Changes:
- Snapshots are now first-class parent records
- Each snapshot contains its own uploaded files, parsed data, and calculated results
- Historical snapshots are frozen and traceable
- No more ambiguity about which data created which snapshot

## Data Model

### `snapshot_workflow` Collection:
```
{
  id: uuid,
  name: "Week 1-2 March 2026",
  effective_date: "2026-03-14",
  period_start: "2026-03-01",
  period_end: "2026-03-14",
  quarter: "Q1",
  year: 2026,
  status: "draft|in_progress|processing|completed|failed",
  notes: string,
  created_at: datetime,
  completed_at: datetime,
  uploads: [
    {
      id: uuid,
      upload_type: "pos_report|customer_voice|review_tracker",
      filename: string,
      status: "uploaded|parsed|failed",
      parsed_data: {...},
      record_count: number
    }
  ],
  upload_progress: {
    pos_report: boolean,
    customer_voice: boolean,
    review_tracker: boolean
  },
  employees: [...], // Calculated results
  employee_count: number,
  benchmarks_used: {...},
  is_current: boolean
}
```

## Scoring Formula (Q1 2026)
- **Weights:** PPA (25%), LSC (25%), LBW (15%), Glassware (10%), NPS (10%), ReviewTracker (15%)
- **CV Scoring:** NPS pts (max 10) + Promoters × 1 - Detractors × 2
- **RT Bonus:** Mentions × 0.5 pts (capped at 15 pts)
- **Metric bonuses:** Up to 5 pts per metric if >100% of benchmark

## Key Metrics
- **PPA (Per Person Average):** Extracted from "Guest Avg" column in Totals row
- **LBW:** (Liquor + Beer + Wine) / Guest Count
- **LSC:** Guest Count / LSC Cards Sold (lower is better)
- **Glassware:** Bar Glassware Sales / Guest Count

---

## What's Been Implemented

### Data Ingestion
- [x] XLSX multi-sheet parsing (one employee per sheet)
- [x] XLSX consolidated format parsing (SSD Engine format)
- [x] PDF parsing via AI Vision OCR (GPT-4o)
- [x] Background task processing with polling for PDFs
- [x] Manual correction UI for OCR results
- [x] ReviewTracker CSV upload
- [x] Customer Voice feedback upload

### Snapshot-First Workflow (NEW)
- [x] Snapshot CRUD (create, read, update, delete)
- [x] Per-snapshot file uploads
- [x] Upload progress tracking (3 steps)
- [x] Snapshot processing & finalization
- [x] Status lifecycle (draft → in_progress → processing → completed)
- [x] Current rankings from latest completed snapshot
- [x] POS Review Modal data persistence fix (2026-03-31) - All 28 employees now correctly display
- [x] Legacy data migration utility
- [x] Top Performers display in snapshot detail
- [x] **Employee metric edit recalculation fix (2026-03-31)** - Editing PPA/metrics now correctly recalculates scores
- [x] **current-rankings now returns active (is_current) snapshot** - Edits visible immediately without reprocessing
- [x] **PDF upload flow fixed (2026-04-01)** - Background job processing with proper endpoint routing

### Scoring Engine
- [x] Complex weighted scoring formula
- [x] Benchmark-based normalization
- [x] Metric bonuses (capped at 5 pts each)
- [x] CV promoter/detractor points
- [x] DAR penalty system

### Reporting
- [x] Leaderboard with rankings
- [x] Employee details modal
- [x] Score breakdown visualization
- [x] PDF slide generation for individual employees

### QR Code System
- [x] QR code generation per employee
- [x] Scan tracking and redirect
- [x] QR management page

---

## Changelog

### 2026-03-29 (Current Session)
- **MAJOR:** Implemented snapshot-first architecture
- Created `snapshot_manager.py` and `snapshot_routes.py`
- Added SnapshotWorkflow and SnapshotDetail pages
- Migrated 28 existing employees to Legacy Migration snapshot
- Added current-rankings API endpoint
- Updated PPA extraction to use "Guest Avg" column from reports

### Previous Sessions
- Fixed PDF parsing (migrated to AI Vision OCR)
- Implemented async background tasks for PDF processing
- Fixed NaN/Infinity JSON serialization errors
- Fixed NPS and Passives calculation
- Added manual correction UI for OCR data
- Fixed ReviewTracker CSV upload endpoint

---

## Roadmap

### P0 (Critical)
- [x] ~~Snapshot processing missing staff data~~ (Fixed 2026-03-30)
- [x] ~~Employee Names UI Fix~~ (Verified 2026-03-31) - 28 employees, no duplicates, display_name/report_name separation working

### P1 (High Priority)
- [x] ~~Update Leaderboard to use snapshot-workflow current-rankings API~~ (Done)
- [x] ~~Momentum Indicators~~ - Implemented Trend column on Leaderboard comparing current vs previous snapshot scores (Done 2026-03-31)
- [ ] Evaluate legacy "Fix All/Remove Excess" ReviewTracker bug (may be obsolete with snapshot architecture)

### P2 (Medium Priority)
- [ ] Multi-Store Architecture - Support 22 locations
- [IN PROGRESS] Code Refactoring - Break down server.py (12k+ lines)
  - [x] Quarter Settings extracted to `/app/backend/routes/quarter_settings.py` (323 lines)
  - [x] Finalization/DAR extracted to `/app/backend/routes/finalization.py` (507 lines)
  - [x] Yodeck Slides extracted to `/app/backend/routes/yodeck_slides.py` (755 lines)
  - [x] Employee CRUD extracted to `/app/backend/routes/employees.py` (563 lines)
  - [x] Trends/Analytics extracted to `/app/backend/routes/trends.py` (512 lines)
  - [ ] Reviews extraction (~600 lines)
  - [ ] POS Upload/OCR extraction (~800 lines)
  - [ ] Remove duplicated code from server.py (final cleanup)
- [ ] Review Spotlight Feature

### P3 (Future)
- [ ] "Download All Slides" ZIP feature
- [ ] Automated UI scraping for official stats
- [ ] Background task queue (Celery)

---

## Technical Architecture

```
/app/
├── backend/
│   ├── server.py              # Main API (~13k lines - refactoring in progress)
│   ├── routes/                # Modular route files (~2,150 lines extracted)
│   │   ├── quarter_settings.py  # Quarter benchmarks, weights, tiers (323 lines)
│   │   ├── finalization.py      # DAR and finalization API (507 lines)
│   │   ├── yodeck_slides.py     # Slide generation endpoints (755 lines)
│   │   └── employees.py         # Employee CRUD, CV stats, DAR (563 lines)
│   ├── snapshot_manager.py    # Snapshot models and scoring functions
│   ├── snapshot_routes.py     # Snapshot workflow API routes
│   ├── pos_ocr.py             # AI Vision OCR for PDFs
│   ├── pos_report_parser.py   # XLSX parsing
│   └── qr_tracking.py         # QR code management
└── frontend/
    └── src/
        ├── components/
        │   └── FinalizeQuarterModal.js  # DAR entry and finalization UI
        └── pages/
            ├── Dashboard.js         # Main dashboard with finalize button
            ├── SnapshotWorkflow.js  # Snapshot list page
            ├── SnapshotDetail.js    # Snapshot detail with uploads
            ├── DataUploads.js       # Legacy upload handling
            ├── EmployeeList.js      # Employee details
            └── LeaderboardRankings.js # Rankings display
```

## Key Collections (MongoDB)
- `snapshot_workflow` - NEW: Snapshot-first data container
- `employees_v2` - Legacy employee data (migrated)
- `customer_reviews` - ReviewTracker data
- `cv_feedback` - Customer Voice surveys
- `qr_employees` / `qr_scans` - QR tracking

## API Endpoints (Snapshot Workflow)
- `POST /api/v2/snapshot-workflow/snapshots` - Create snapshot
- `GET /api/v2/snapshot-workflow/snapshots` - List all
- `GET /api/v2/snapshot-workflow/snapshots/{id}` - Get detail
- `POST /api/v2/snapshot-workflow/snapshots/{id}/upload/{type}` - Upload file
- `POST /api/v2/snapshot-workflow/snapshots/{id}/process` - Finalize
- `POST /api/v2/snapshot-workflow/snapshots/{id}/unlock` - Unlock completed snapshot for editing
- `GET /api/v2/snapshot-workflow/current-rankings` - Active rankings
- `POST /api/v2/snapshot-workflow/migrate-legacy-data` - Migration utility

## Changelog

### 2026-04-03 (Session 7)
- **MAJOR: Frontend Component Refactoring (Code Review Fix)**
  - Refactored `EmployeeList.js` from 1364 lines to 599 lines (56% reduction)
  - Extracted 3 new reusable components:
    - `EmployeeDetailsModal.jsx` (339 lines) - Scoring breakdown, CV breakdown, raw data
    - `EmployeeEditModal.jsx` (340 lines) - Form with LBW auto-calculation, CV stats
    - `EmployeeCard.jsx` (173 lines) - Employee card with metrics grid
  - Created `RankingsExpandedRow.jsx` (389 lines) - Expanded row details for rankings
  - Created `TopPerformersGrid.jsx` (157 lines) - Top performers by metric display
  - All 16 frontend tests passed (100%) - verified via testing_agent_v3_fork
  - Components properly use formatCurrency/formatNumber from utils/formatters.js
  - All data-testid attributes maintained for testing

- **FEATURE: Expanded Employee Card Metrics (9 metrics)**
  - Extended EmployeeCard from 6 to 9 metrics:
    - Row 1: Score, PPA, LBW/G
    - Row 2: Glass/G, G/LSC, CV Score
    - Row 3 (NEW): RT Bonus, Metric Bonus, QR Scans
  - QR scan data fetched from `/api/qr/employees` and merged by employee name
  - Name matching supports full name and first-name fallback for QR data merge

### 2026-04-02 (Session 6)
- **COMPLETED: Cohesive Finalization Workflow**
  - Fixed missing `snapshotId` prop in `Dashboard.js` line 926 - FinalizeQuarterModal now receives snapshot ID correctly
  - Tested complete workflow: Dashboard → Finalize Now → Apply DAR → Finalize Quarter → Verify Lock
  - All 9 backend tests passed (100%): workflow-status, finalize, reopen, quarter-settings, DAR calculations
  - DAR deductions working correctly: Written Warning = -3 pts, Suspension = -5 pts
  
- **MAJOR: Code Refactoring Progress**
  - Created `/app/backend/routes/` directory for modular route files
  - Extracted ~2,660 lines into 5 modular route files:
    - `quarter_settings.py` (323 lines) - Quarter benchmarks, weights, tier thresholds
    - `finalization.py` (507 lines) - DAR entries, quarter finalization, reviews
    - `yodeck_slides.py` (755 lines) - All slide generation endpoints
    - `employees.py` (563 lines) - Employee CRUD, display names, CV stats, DAR
    - `trends.py` (512 lines) - Employee/team trends, bi-weekly charts
  - All routers integrated via `include_router()` and working
  - Slide generation verified working (PNG files generated correctly)
  - Old endpoints in server.py still active for backward compatibility

### 2026-04-01 (Session 5)
- **FIX: Finalize Quarter Modal Contrast & Calculation Issues**
  - Fixed invisible input text in DAR (Written Warnings/Suspensions) fields
  - Added explicit `text-gray-900 bg-white border-gray-300` classes to Input components
  - Verified deduction calculations working: Written Warning (-3 pts) × count + Suspension (-5 pts) × count
  - Final Score updates correctly: Pre-DAR Score - Total Deductions
  - Summary stats (Total Deductions, Employees w/ DAR) update in real-time

### 2026-03-31 (Session 4)
- **CRITICAL FIX: Snapshot-First Display Names & Tier Sorting**
  - Fixed `full-rankings` endpoint in `server.py` to pull from active snapshot instead of legacy `employees_v2`
  - Rankings now properly show `display_name` (first name only) from snapshot data
  - Added `fix-snapshot-names` endpoint to sync display names and re-apply tier assignments
  - All pages (Employees, Rankings, Leaderboard) now show consistent first-name-only display
  - Tier sorting working correctly: Trainers → Bartenders → A-Servers → B-Servers → C-Servers
  - `current-rankings` endpoint now sorts by tier before returning
- **TIER THRESHOLD UPDATE**: Changed server tier thresholds:
  - A-Server: ≥90 (was ≥85)
  - B-Server: 75-89.9 (was 70-84.9)
  - C-Server: <75 (was <70)
- **MOMENTUM INDICATORS IMPLEMENTED**:
  - Added Trend column to Leaderboard showing score changes vs previous snapshot
  - Indicators: 🔥 Hot (+5 or more), ↑ Up (improved), ↓ Down (-2 or more), ⭐ New (no previous data), — Stable
  - Enhanced name matching to handle first-name/full-name discrepancies between snapshots
  - Uses `report_name` and first-name fallback for reliable matching
- **VERIFIED: Employee Names UI Fix**
  - Confirmed 28 employees with no duplicates
  - `display_name` (first name only) shows correctly on Employee cards, Rankings, and Leaderboard
  - `report_name` (full POS name) populates correctly in Edit modal for data matching
  - Employee edits immediately update the active snapshot

### 2026-03-30 (Session 3)
- **CRITICAL FIX: Per-Guest Metrics Calculation**
  - Fixed `merge_snapshot_data` function in `snapshot_routes.py` to properly calculate per-guest metrics from raw POS data
  - Issue: POS OCR produces raw totals (lbw_total, glassware_sales) but merge function expected pre-calculated per-guest values
  - Fix: Added calculations for `lbw_per_guest`, `glassware_per_guest`, `guests_per_lsc` when not pre-populated
  - Result: All 28 employees now have correct scores (69.5-117.2 range) instead of broken values (~53)
- **Code Cleanup:** Removed dead/duplicate code after line 409 in snapshot_routes.py (leftover from botched edit)

### 2026-03-29 (Session 2)
- **CV Scoring Formula Fix:** Updated to (Promoters × 1) + (RT Mentions × 0.5) - (Detractors × 2)
  - Changed CV_PROMOTER_POINTS from 0.5 to 1.0
  - Changed CV_DETRACTOR_POINTS from -1 to -2
  - Updated related hardcoded values in server.py, review_tracker.py, audit_system.py, snapshot_routes.py
- **Unlock Snapshot Feature:** Added ability to edit completed snapshots
  - New endpoint: `POST /api/v2/snapshot-workflow/snapshots/{id}/unlock`
  - Added "Unlock for Editing" button in SnapshotDetail.js
  - Changes status from 'completed' back to 'in_progress'

## 3rd Party Integrations
- OpenAI GPT-4o (via Emergent LLM Key) - PDF OCR
