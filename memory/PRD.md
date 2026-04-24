# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees.

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key)

## Current State (2026-04-14)

### Latest Changes (2026-02 Session)

- **Snapshot Workflow Edits Not Persisting (FIXED 2026-02)**:
  - Root cause 1: Master `PUT /v2/employees/{id}` only synced `name/title/tier/total_score`
    back to `snapshot_workflow.employees` - metric edits (guests, liquor_sales, etc.) were
    written to `employees_v2` but never to the snapshot. Since `EmployeeList` re-fetches
    from `/v2/snapshot-workflow/current-rankings` (reads the snapshot), users saw stale
    values and concluded "changes didn't save".
  - Root cause 2: The snapshot-UUID fallback in the master PUT searched `employees_v2` by
    name without filtering by the snapshot's quarter/year, matching a same-named
    employee in a different quarter and syncing to the wrong snapshot.
  - Fix: Sync ALL editable metric fields (ppa, lbw, liquor/beer/wine, glassware, guests,
    scores, tiers, CV/RT fields) to the snapshot employee element, and filter the
    name-fallback lookup by the originating snapshot's quarter/year.
  - File: `/app/backend/server.py` `update_employee` (~lines 2346-2575).

- **LBW Not Summing All Three Items on Data Upload (FIXED 2026-02)**:
  - Root cause: `process_pdf_job` and `process_xlsx_job` in `/app/backend/routes/upload_jobs.py`
    (used by `/api/v2/upload-jobs/direct`, the endpoint DataUploads.js hits for PDF/XLSX
    parse+preview) did NOT include `lbw_total` in the response. The preview table
    (`emp.lbw_total`) showed blank/undefined.
  - Fix: Compute `lbw_total = liquor + beer + wine` and flatten `_raw` fields up to
    top level in the job result. XLSX now also adds `safe_float` helper.


### Latest Changes
- **Complete Rankings Slide Fix (2026-04-14)**:
  - Changed Complete Rankings to read from employees_v2 (dashboard) instead of snapshot_workflow
  - Slide now calculates tiers from scores (A>=85, B>=70, C<70) rather than using stored tier_label
  - Eliminates all name mismatch and duplicate issues between snapshot and dashboard
  - Added one-shot correction endpoint: GET /api/v2/audit/apply-corrections/2026/Q1
    - Restores Lennie Nguyen with correct scores (90.2, A-Server)
    - Fixes Keisha Martin display_name and score (114.0)
    - Corrects all tier labels based on score thresholds
  - Smart delete: handles duplicate employees by removing lowest-scoring entry only

- **Bug Fix: Blank Page on POS Upload (2026-04-14)**:
  - Fixed React crash (ReferenceError) on `/uploads` page when PDF preview table tried to render
  - Root cause: Missing `idx` parameter in `.map()` callback in `DataUploads.js` line 748
  - Also fixed `editingEmployee` comparison to use index instead of `emp.name`

- **Data Cross-Reference Audit Tools (2026-04-14)**:
  - `GET /api/v2/audit/cross-reference/{year}/{quarter}` — compares snapshot_workflow vs employees_v2 field-by-field
  - `POST /api/v2/audit/sync-from-snapshot/{year}/{quarter}?employee_name=X` — syncs snapshot data → dashboard
  - `POST /api/v2/audit/sync-to-snapshot/{year}/{quarter}?employee_name=X` — syncs dashboard data → snapshot
  - Production finding: Lennie had ALL ZEROS in snapshot but correct data in dashboard; loyalty_sales was 0 in snapshot for all 27 employees; several tier mismatches

- **Complete Rankings Slide Redesign (2026-04-11)**:
  - Simplified slide to show ONLY: Tier header sections + First Name + Rank
  - Added colorful rainbow bubbles background (`/app/backend/assets/backgrounds/rainbow_bubbles.jpg`)
  - Tiers displayed as columns: TRAINERS, BARTENDERS, A-SERVERS, B-SERVERS, C-SERVERS
  - Each employee shown with rank number and first name only
  - Updated default background from "dark" to "rainbow_bubbles" across all pages
  - 16:9 format for Yodeck display

- **Backend Modularization - Phase 2 (2026-04-10)**:
  - Extracted legacy snapshot routes from `server.py` to `routes/snapshots_legacy.py`
  - **server.py reduced: 4,411 → 3,347 lines (~1,064 lines removed)**
  - Routes extracted: `/v2/snapshots`, `/v2/snapshots/backgrounds`, `/v2/snapshots/{id}`, `/v2/snapshots/{id}/upload`, `/v2/snapshots/{id}/recalculate`, `/v2/snapshots/{id}/sync-from-employees`, `/v2/parse-clean-pos`
  - **IMPORTANT**: Two separate snapshot systems exist:
    - `routes/snapshots_legacy.py` → uses `db.snapshots` collection (for `/snapshots` page)
    - `snapshot_routes.py` → uses `db.snapshot_workflow` collection (main workflow)
  - All 11 backend tests passed (100% success rate)

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
**server.py: 4,411 → 3,347 lines (24% reduction in this session)**
**Total reduction: 11,847 → 3,347 lines (72% reduction overall)**

### Route Modules (16 total)
| Module | Lines | Purpose |
|--------|-------|---------|
| `/app/backend/routes/admin.py` | 1,150 | Admin utilities, data sync, fixes |
| `/app/backend/routes/audit.py` | 921 | Scoring audit system |
| `/app/backend/routes/cv.py` | 868 | CV feedback & NPS |
| `/app/backend/routes/yodeck_slides.py` | 859 | Slide generation + Quarterly Summary |
| `/app/backend/routes/pos_upload.py` | 836 | POS OCR, PDF parsing |
| `/app/backend/routes/snapshots_legacy.py` | ~1,000 | **NEW** Legacy snapshot routes (db.snapshots) |
| `/app/backend/routes/stores.py` | 657 | Multi-store management |
| `/app/backend/routes/trends.py` | 649 | Trend analytics + Momentum |
| `/app/backend/routes/reviews.py` | 646 | Reviews & RT management |
| `/app/backend/routes/upload_jobs.py` | 586 | Background file uploads |
| `/app/backend/routes/employees.py` | 581 | Employee CRUD |
| `/app/backend/routes/finalization.py` | 507 | Quarter finalization |
| `/app/backend/routes/insights.py` | 443 | Store health, coaching, reviews |
| `/app/backend/routes/quarter_settings.py` | 302 | Settings management |
| `/app/backend/routes/scheduler.py` | ~200 | Automated reconciliation scheduler |
| `/app/backend/snapshot_routes.py` | ~3,100 | Main snapshot workflow (db.snapshot_workflow) |
| `/app/backend/server.py` | 3,347 | Main server (core routes) |

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
- [x] ~~Backend route modularization~~ - DONE (72% reduction - 11,847 → 3,347 lines)

### P2 - Medium Priority
- [ ] Review Spotlight feature (Deferred by user)
- [ ] Download All Slides as ZIP (Deferred by user)

### P3 - Low Priority
- [x] ~~Momentum/Trend indicators~~ - DONE (2026-04-07)
- [ ] Store vs Store comparison
- [ ] Auto-import Daily Flash XLSX for concept benchmarks

## Architecture Notes
### Dual Snapshot Systems
The app uses TWO separate snapshot implementations:
1. **Legacy Snapshots** (`routes/snapshots_legacy.py`):
   - Uses `db.snapshots` collection
   - Serves `/snapshots` page
   - Simpler workflow
2. **Snapshot Workflow** (`snapshot_routes.py`):
   - Uses `db.snapshot_workflow` collection
   - Serves `/snapshot-workflow` and `/snapshot-workflow/:id` pages
   - Full finalization, POS import, and scoring pipeline
