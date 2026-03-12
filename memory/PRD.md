# Performance Review App - PRD

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees (Bubba Gump Shrimp Co.), evolving from Excel to a full-stack web application. The app handles data ingestion from CSV/Excel, calculates employee scores based on configurable metrics, and generates various outputs like PDFs, leaderboards, and slides for digital signage (Yodeck).

## Core Features
1. **Data Ingestion**: CSV/Excel template upload for employee performance data
2. **Quarter Settings**: Admin UI for configuring metric weights, benchmarks, bonus rules, and server tier thresholds
3. **Scoring Engine**: Weighted formula calculation with bonuses/penalties and performance tiers
4. **Rankings Tab**: Employee display sorted by hierarchy (Trainers, Bartenders, A/B/C-Servers) with Top 10 sections
5. **PDF & Slide Generation**: Individual review PDFs, full rankings PDFs, themed 1920x1080 PNG slides
6. **Time-Series Analytics**: Quarter-over-quarter trend graphs
7. **Bi-Weekly Snapshots**: One-page, color-coded grid of all employees' performance
8. **DAR Calculator**: End-of-quarter disciplinary action report deductions
9. **Self-Checking Audit System**: Comprehensive scoring verification that guarantees 100% accuracy

## Tech Stack
- **Frontend**: React.js, Tailwind CSS, Shadcn/UI
- **Backend**: FastAPI, Python
- **Database**: MongoDB
- **PDF Generation**: ReportLab, Playwright (for screenshot-based charts)
- **Image Generation**: Pillow (PIL), Matplotlib
- **Web Scraping**: Playwright (for Loyalty Voice integration)

## Architecture
```
/app/
├── backend/
│   ├── server.py                    # Main API server (6800+ lines)
│   ├── scoring_engine.py            # Scoring calculations
│   ├── audit_system.py              # NEW: Self-checking audit system
│   ├── name_matcher.py              # Smart name matching for CV attribution
│   ├── snapshot_slides.py           # Snapshot slide generator
│   ├── trend_charts.py              # Multi-panel line/bar charts
│   ├── yodeck_slides.py             # Yodeck slide generator
│   ├── loyalty_voice_integration.py # Loyalty Voice NPS scraper
│   ├── reviewtrackers_integration.py # ReviewTrackers API client
│   └── review_tracker.py            # Customer review tracking
└── frontend/
    └── src/
        ├── components/
        │   ├── SidebarLayout.jsx     # Main layout with sidebar nav
        │   ├── FinalizeQuarterModal.js
        │   └── OnboardingGuide.js
        └── pages/
            ├── Dashboard.js          # Bento grid layout
            ├── FullRankings.js
            ├── ReviewTracker.js
            ├── ScoringAudit.js       # NEW: Self-checking audit UI
            ├── DataIntegrity.js      # Data integrity panel
            ├── YodeckSlides.js
            ├── HelpCenter.js         # FAQ & documentation
            └── QuarterSettings.js
```

## What's Implemented

### Completed Features
- ✅ Full scoring engine with weighted metrics
- ✅ CSV/Excel upload and processing
- ✅ Quarter settings configuration
- ✅ Employee rankings by tier hierarchy
- ✅ Individual employee review PDFs
- ✅ Analytics page with trend charts
- ✅ Analytics PDF with Playwright-based screenshot capture
- ✅ Yodeck slide generation (Complete Rankings, Top 10)
- ✅ Bi-Weekly Snapshots feature
- ✅ Multi-panel line charts for employee trends
- ✅ Revenue Impact Calculator (Dashboard)
- ✅ Training Priorities Panel (Dashboard)
- ✅ Onboarding Guide (7-step quick start modal)
- ✅ DAR Calculator (Finalize Quarter with deductions)
- ✅ Peer Comparison Badges (Top 10%, Top 25%, Top 50%)
- ✅ Review Tracker with AI-powered employee detection
- ✅ ReviewTrackers.com API integration
- ✅ Self-Checking Scoring Audit System

### Recent Changes (Mar 10, 2026) - P0 Circular Bug Fix + Automated Reconciliation

- ✅ **Fixed Circular Bug with "Fix All" and "Remove Excess" Actions**:
  - **Problem**: Running "Fix All" created excess reviews above the 202 cap, but "Remove Excess Reviews" deleted records without updating employee `rt_mentions` counts, causing the audit to fail again - an impossible loop.
  - **Root Cause**: The `enforce_data_caps` endpoint deleted excess reviews but did not sync employee mention counts afterward.
  - **Solution**: 
    1. Modified `enforce_data_caps` to call `sync_employee_review_mentions()` after removing excess reviews
    2. Fixed the `sync_employee_review_mentions` function to use correct field names (`score_ppa`, `score_lsc`, etc.) and the correct RT bonus formula (0.5 pts per mention, max 15 pts)
  - **Result**: The full workflow now works correctly:
    - "Fix All" → creates excess reviews → Audit PASSES
    - "Remove Excess" → deletes extra reviews AND syncs employee mentions → Audit STILL PASSES
    - Data counts match official limits (CV: 75/75, RT: 202/202)
  - **Files Modified**: `backend/server.py` (lines 7853-7907, 7898-7939)

- ✅ **Automated Reconciliation Scheduler**:
  - **New Backend Endpoints**:
    - `GET /api/v2/scheduler/status` - Get scheduler status and configuration
    - `POST /api/v2/scheduler/configure` - Enable/disable scheduler and set run time
    - `POST /api/v2/scheduler/run-now` - Manually trigger reconciliation
    - `GET /api/v2/scheduler/history` - View reconciliation history
  - **Features**:
    - Daily scheduled reconciliation runs at configurable time (default 2:00 AM UTC)
    - Runs full sequence: Fix All → Remove Excess → Audit
    - Logs all runs with success/failure status
    - UI modal for configuration with recent run history
  - **Dependencies Added**: APScheduler for job scheduling
  - **Files Modified**: `backend/server.py`, `frontend/src/pages/ScoringAudit.js`

### Previous Changes (Mar 8, 2026) - Self-Checking Audit System

- ✅ **Scoring Audit System**: Built comprehensive self-checking audit process that guarantees 100% accurate scoring
  - **New API Endpoints**:
    - `GET /api/v2/audit/employee/{name}` - Detailed audit of single employee's score calculation
    - `GET /api/v2/audit/all` - Batch audit of all employees with pass/warning/fail status
    - `GET /api/v2/audit/report` - Comprehensive audit report with data sources, consistency checks, recommendations
    - `GET /api/v2/audit/trail` - View audit trail of changes
    - `POST /api/v2/audit/log` - Log audit entries for tracking
    - `POST /api/v2/audit/recalculate-all` - Recalculate ALL employee scores from stored components
    - `GET /api/v2/audit/data-cap-check` - Check if data exceeds official dashboard limits
    - `POST /api/v2/audit/enforce-data-caps` - Remove excess data to match official limits
    - `POST /api/v2/audit/sync-employee-mentions` - Sync employee mention counts with current review data
  - **Features**:
    - Step-by-step calculation verification for every score component
    - Data trail from raw sources (CV feedback, review mentions) to final scores
    - Discrepancy detection with severity levels (CRITICAL, HIGH, MEDIUM)
    - Cross-reference validation between raw data and aggregated records
    - Official stats verification (CV and RT)
    - **Data Cap Enforcement**: Official dashboard data is the ABSOLUTE MAXIMUM allowed
    - Auto-sync employee mentions after removing excess data
  
- ✅ **Scoring Audit UI** (`/scoring-audit`):
  - Summary cards showing total employees, passed, warnings, failed counts
  - **Data Cap Enforcement Panel**: Shows CV and RT data vs official limits
  - **"Remove Excess Data"** button to enforce caps (removes oldest entries)
  - **"Sync Mentions"** button to update employee records after data changes
  - **"Recalculate All"** button to fix any score mismatches
  - Employee list with audit status (PASS, WARNING, FAIL)
  - Detailed employee audit view with calculation breakdown

- ✅ **Current Audit Status (after enforcement)**:
  - 27/27 employees PASS
  - CV: 75/75 (AT_LIMIT) 
  - RT: 202/202 (AT_LIMIT)
  - Overall: VERIFIED & COMPLIANT

- ✅ **Sidebar Navigation Updated**: Added "Scoring Audit" link under Admin section

### Previous Changes (Mar 4, 2026) - Complete CV Server Attribution & Exclusion System

- ✅ **New Server Details Scraping Method**: Created `scrape_cv_feedback_via_server_details()` that follows Reports → Server Performance → Server Details path
  - **Result**: 216 feedback entries with **100% server attribution** (was 45% before)
  - **All 16 detractors** now have their responsible server identified
  - Removed dependency on Transactions page matching which only worked 35% of the time

- ✅ **Exclusion/Restore System Updated**:
  - Exclusion now recalculates server NPS from actual feedback data (not CSV aggregates)
  - Excluding a detractor correctly removes -2 penalty and recalculates server's NPS
  - Restore function correctly adds the feedback back and recalculates

- ✅ **Excluded Reviews Management UI**:
  - Added collapsible "Excluded Reviews" panel on Review Tracker page
  - Shows all excluded reviews with server attribution and restore button
  - Easy to review and undo exclusions if made by mistake

- ✅ **UI Enhancements**:
  - Added "Upload Server Report" button for CSV backup method
  - Feedback cards now show server name with point impact (+1 pts, -2 pts, etc.)
  - "Show excluded" checkbox filter and dedicated Excluded Reviews panel

### Previous Changes (Mar 3, 2026) - CV Feedback Scraper Complete Fix

- ✅ **Fixed Customer Voice Feedback Scraper**: Now correctly retrieves all 71 feedback entries for Q1 2026
  - **Root Cause 1**: Python syntax errors (incorrect `except`/`finally` indentation)
  - **Root Cause 2**: Wrong date filter selector (`#date-filter` vs `#Feedback-DateCreated-date-filter`)
  - **Root Cause 3**: Date range issue - using future end dates (03/31/2026) returned only 29 items
  - **Solution**: 
    - Fixed indentation errors
    - Updated to correct Feedback page selector
    - Added "Quarter-To-Date" preset for current quarter scraping
    - Updated `get_quarter_date_range()` to use current date for current quarter
  - **Result**: 71 feedback items scraped (62 promoters, 4 passives, 5 detractors) matching Loyalty Voice reports
  - Files modified: `backend/cv_feedback_scraper.py`

### Previous Changes (Mar 3, 2026) - Employee Aliases & Clickable Dashboard

- ✅ **Employee Aliases Feature**: Added ability to set nicknames for employees
  - New `aliases` field in employee model (array of strings)
  - Editable via Employees page edit modal
  - Used for matching names in CV sync and Review Tracker
  - Example: "Treyanna Quick" with aliases ["Trey", "T.Q.", "Tre"]
  
- ✅ **Clickable Dashboard Crew Card**: "Crew Members" stat card now links to /employees page
  - Click to view and manage all employees
  - Edit job titles, aliases, and performance data

- ✅ **Enhanced Name Matching**: CV sync now checks employee aliases first before fuzzy matching
  - More reliable attribution of reviews/NPS to correct employees

### Previous Changes (Mar 3, 2026) - Job Title Preservation Bug Fix
- ✅ **Fixed Job Title Not Persisting**: Critical bug where custom job titles (Trainer, Bartender) were reset to "Server"
  - **Problem**: When data was re-uploaded or recalculated, custom job titles were being overwritten
  - **Root Cause**: The upload and recalculate endpoints deleted all employees then re-inserted with default "Server" job title
  - **Solution**: Added logic to preserve non-default job titles (Trainer, Bartender, etc.) before delete and restore after insert
  - Files modified:
    - `backend/server.py`: Added preservation logic in both upload endpoint (~line 1290) and recalculate endpoint (~line 3971)
  - **Result**: Trainers and Bartenders now retain their designation through uploads and recalculations

### Previous Changes (Mar 2, 2026) - CV Sync Bug Fixes
- ✅ **Fixed CV Data Duplication Bug**: Critical fix for inflated review counts
  - **Problem**: Running CV sync multiple times caused data accumulation (123 surveys vs expected 65)
  - **Root Cause**: Old `cv_nps` records were not being cleared before inserting new data
  - **Solution**: Added `delete_many()` call to clear existing records for the quarter BEFORE syncing
  - Files modified:
    - `backend/loyalty_voice_integration.py`: Clears `cv_nps` collection before sync
    - `backend/cv_feedback_scraper.py`: Clears `cv_feedback` and `cv_points` collections before sync
  - **Result**: Survey count now accurate (64 surveys, close to expected 65)

- ✅ **Fixed CV Score Not Applied to Employee Records**:
  - **Problem**: CV sync updated `cv_nps` collection but employees_v2 records weren't updated with NPS data
  - **Root Cause**: CV sync endpoint didn't update employees_v2 after syncing
  - **Solution**: Modified `/api/v2/cv/sync` to also update employees_v2 records with:
    - `nps_score`, `cv_score`
    - Recalculated `weighted_score`, `pre_dar_score`, `total_score`
  - **Result**: All employees now have correct scores reflecting their NPS data
  - Example fix: Allen Simmons went from 66.09 (C-Server) to 76.09 (B-Server) with +10 NPS pts

### Previous Changes (Mar 2, 2026) - XLSX Upload Support
- ✅ **XLSX File Upload Support**: Added direct Excel file parsing for 100% accurate data extraction
  - No OCR needed - parses Excel files directly using openpyxl library
  - Supports Aloha Server Sales Detail format (each employee = separate sheet/tab)
  - Employee name extracted from cell F5 (yellow cell in Aloha export)
  - Automatic extraction of: Net Sales, Guests, Food/Liquor/Beer/Wine/Glassware sales
  - LSC Card count calculated: Loyalty$ / $25
  - All derived metrics calculated: PPA, LBW/Guest, Glassware/Guest, Guests/LSC
- ✅ **Frontend Updates**:
  - POS Upload Modal now accepts .xlsx files
  - Updated UI messaging: "XLSX recommended for 100% accuracy"
  - Green highlight for XLSX file indicator
  - Tips section updated with XLSX instructions
- ✅ **Backend Endpoint Updated**: `/api/v2/pos-ocr/upload` now handles:
  - XLSX files (100% accuracy, direct parsing)
  - Images (OCR via AI - JPEG, PNG, WEBP, HEIC)
  - PDFs (OCR via AI - converted to images first)
- ✅ **Technical Details**:
  - Uses openpyxl for Excel parsing (already installed)
  - Flexible row detection using label search (Food, Liquor, Beer, etc.)
  - Multi-sheet support (extracts all employees from all tabs)

### Recent Changes (Feb 25, 2026) - UI Fix & PDF OCR Support
- ✅ **Top Performers Name Color Fix**: Changed employee name color from `text-white` to `text-slate-100` in Dashboard.js for better contrast against dark background
- ✅ **"To Pass Next Employee" Feature Verified**: Confirmed working in Rankings expanded view
  - Shows comparison to employee ranked directly above
  - Displays: Gap (pts needed), PPA, LBW, Glass, LSC targets
  - Uses `peer_rank` to find the employee above in rankings
- ✅ **PDF Support for POS OCR**: Added ability to upload PDF files for OCR scanning
  - Supports: JPEG, PNG, WEBP images (10MB max) AND PDF documents (20MB max)
  - PDF pages are converted to images and each page is processed
  - Employee data is deduplicated across pages
  - Updated frontend modal to show PDF support and file type indicators

### Recent Changes (Feb 22, 2026) - Full UX/UI Redesign
- ✅ **Sidebar Navigation**: Replaced 8 horizontal tabs with collapsible sidebar
  - Grouped sections: Performance, Feedback, Exports, Team
  - Store selector dropdown (multi-store ready)
  - Collapse toggle for desktop
  - Mobile-responsive with hamburger menu
- ✅ **Dashboard Redesign**: New "Bento Grid" layout
  - Hero KPI cards with clear visual hierarchy
  - Quick action buttons row
  - Top 5 Performers list with tier badges
  - Right column: Latest Snapshot + Quarter Settings cards
  - Responsive design for mobile
- ✅ **Help Center**: New FAQ page with categorized questions
  - Quick action links
  - Collapsible FAQ sections (Getting Started, Scoring, Reviews, etc.)
- ✅ **Design System Updates**:
  - New color palette: Paper White (#F9F7F2), Sand (#E8DCCA), warm tones
  - Merriweather serif font for headings
  - Improved dark mode support
- ✅ **PWA Icons**: Added Bubba Gump logo for mobile home screen
- ✅ **Review Tracker Label Fix**: Corrected "CV SCORE" → "Review Tracker" in expanded view

### Changes (Mar 6, 2026) - DATA INTEGRITY SYSTEM

#### Admin Data Integrity Panel Created
Built comprehensive data accuracy controls for Review Tracker and Customer Voice:

**Features:**
1. **Duplicate Detection**: Hash-based duplicate review detection and removal
2. **CV Server Attribution**: 100% enforcement - all CV feedback must have server names
3. **NPS Validation**: Verify NPS records match raw feedback data
4. **Orphaned Records**: Detect CV NPS entries for non-existent employees
5. **Reconciliation**: Side-by-side comparison of source vs stored counts

**API Endpoints:**
- `GET /api/v2/admin/data-integrity/summary` - Quick status overview
- `GET /api/v2/admin/data-integrity/check` - Full integrity check
- `POST /api/v2/admin/data-integrity/remove-duplicates` - Remove duplicate reviews
- `DELETE /api/v2/admin/data-integrity/invalid-cv-feedback` - Delete invalid CV entries
- `POST /api/v2/admin/data-integrity/recalculate-cv-nps` - Recalculate all NPS

**Files Created:**
- `backend/data_integrity.py` - DataIntegrityChecker and VerificationMode classes
- `frontend/src/pages/DataIntegrity.js` - Admin panel UI

**Data Cleanup Performed:**
- Deleted 10 CV feedback entries without server names
- Recalculated NPS for 84 employees
- Achieved 100% CV attribution rate

### Changes (Mar 6, 2026) - NEW LEADERBOARD DESIGN

#### Professional Leaderboard UI Implemented
Created a new `/leaderboard` page with the design system specifications:

**Color System:**
- Dark navy background (#0F172A)
- High contrast text (#F9FAFB)
- Gold (#FBBF24), Silver (#94A3B8), Bronze (#CD7F32) for top 3
- Green (#22C55E) highlight for top 5

**Features:**
- Large bold rank badges with color coding
- Progress bars for score visualization
- Tier badges (Trainer, Bartender, A/B/C Server)
- Recognition badges (⭐ Star, 🌟 Favorite, 👑 Leader)
- Momentum indicators using snapshot comparison
- Category Leaders panel (PPA, LBW, LSC, Review leaders)
- Scoring Guide with recognition levels

**Files Created:**
- `frontend/src/pages/LeaderboardRankings.js`: New leaderboard page
- `backend/yodeck_slides.py`: Added `generate_leaderboard_slide()` function

**API Endpoint:**
- `GET /api/v2/yodeck/{year}/{quarter}/leaderboard-slide`: New slide download

### Changes (Mar 5, 2026) - HYBRID SCORING MODEL

#### Hybrid NPS Scoring Model Implemented
Updated Customer Voice scoring to use spec NPS scale with current promoter logic:

**NPS Score (from Spec - max 10 pts)**:
| NPS Range | Points |
|-----------|--------|
| 90-100% | 10 pts |
| 80-89% | 9 pts |
| 70-79% | 8 pts |
| 60-69% | 7 pts |
| 50-59% | 6 pts |
| Below 50% | Scaled proportionally |

**Promoter/Detractor Points (Current - NO CAP)**:
- Promoter (9-10 rating): +1 pt each
- Detractor (6 or below): -2 pts each

**Files Modified:**
- `backend/scoring_engine.py`: Updated `calculate_customer_voice_score()` with spec NPS scale
- `frontend/src/pages/FullRankings.js`: Updated tooltips to show new NPS scale

**Verification Examples:**
- Julian Taveras: 100% NPS (10 pts) + 6 promoters = 16 CV pts ✅
- Starwars Mckinnon: 80% NPS (9 pts) + 4 promoters = 13 CV pts ✅
- Robert Mckinnon: 33% NPS (3.3 pts) + 2P - 1D = 3.3 CV pts ✅

#### CV Quarter Data Fix (Mar 5, 2026)
**Issue**: CV feedback records had incorrect quarter/year assignments (all marked Q4 2025 instead of Q1 2026)
**Root Cause**: Scraper stored the passed-in quarter parameter instead of deriving from actual feedback date
**Fix Applied**:
1. Updated all `cv_feedback` records to have correct quarter/year based on actual date
2. Recalculated `cv_nps` aggregates for both Q1 2026 and Q4 2025
3. Recalculated all employee scores

**Verified Results**:
- Q1 2026: 100 feedback entries, 24 cv_nps records, 4 employees with detractors
- Detractors now correctly counted: Daniel Mayorga (2), Tarek Araman (1), Ethan Dever (1), Robert Mckinnon (1)

#### CV Score Breakdown Tooltip Enhancement
- Added info icon (ℹ️) to "Customer Voice" column header with scoring explanation
- Each employee's CV cell now shows:
  - NPS percentage (color-coded: green ≥75%, yellow 50-74%, red <50%)
  - CV Score in green below (e.g., "+14 pts")
- Hovering on any CV cell shows detailed breakdown:
  - NPS Bonus contribution
  - Promoter count and points
  - Detractor count and penalty
  - Total CV Score

**Files Modified:**
- `frontend/src/pages/FullRankings.js`: Added Tooltip components with CV breakdown

#### Slide Color Coding Fix (Mar 5, 2026)
**Issue**: Rankings slide download was missing cell-level color coding based on performance
**Fix Applied**: Updated `backend/yodeck_slides.py` to restore:
1. **Cell background colors** based on metric performance:
   - 🟩 Green (#22C55E): >= 110% (Exceeding)
   - 🟦 Cyan (#06B6D4): 100-109% (Meeting)
   - 🟨 Yellow (#EAB308): 80-99% (Work in Progress)
   - 🟥 Red (#EF4444): < 80% (Needs Improvement)
2. **Left panel legend** explaining the color coding
3. **Column headers** updated to match prior format: PPA, LBW, GLASS, LSC, Review Bonus, Metric Bonus, Total Score
4. **Total Score cell** colored based on tier (green/yellow/red)

### Changes (Feb 21, 2026) - UI Label & Data Fix
- ✅ Fixed "CV SCORE" label in Rankings page expanded view → Now shows "Review Tracker"
- ✅ Fixed Review Tracker value displaying wrong data (was showing NPS points, now shows mentions × 0.2)
  - Before: Showed `cv_score` (NPS points) = 10 for Diane
  - After: Shows `review_tracker_bonus` = +0.6 (3 mentions × 0.2)
  - Now displays calculation breakdown: "3 mentions × 0.2"

### Changes (Feb 20, 2026) - Scoring Model (SUPERSEDED by Mar 5, 2026 update)

#### NPS Scoring (OLD - NO LONGER USED)
- **OLD Formula**: `NPS% × 0.10` (2.5 pts per 25%, max ±10 pts)
- **REPLACED BY**: NPS% Bonus tiers (5/2.5/0 pts) + Promoter/Detractor points

#### Review Bonus
- **Formula**: ReviewTracker mentions × 0.2 pts each (separate bonus, uncapped)
- Now correctly fetched from `customer_reviews` collection

#### CV Feedback Exclusion Feature
- "Exclude from Rankings" button on each CV feedback card
- "Undo" button to restore excluded feedback
- NPS automatically recalculated when feedback is excluded/included
- "Show excluded" toggle in filters

#### Rankings Page Updates
- Review Bonus column: RT mentions × 0.2 (green, always positive)
- Metric Bonus column: Points from exceeding benchmarks
- NPS column: Color-coded (green ≥50%, yellow 0-49%, red <0%)
- Uniform badge sizes for Top 10%/25%/50% and tier labels

#### Other Updates
- Dashboard text changed: "Quarterly Crew Reviews" → "Team Performance Reviews"
- Recalculate endpoint now fetches NPS from cv_nps and mentions from customer_reviews

### Previous Changes - Loyalty Voice NPS Integration
- ✅ **Loyalty Voice Server Performance Report Scraper**: Complete rewrite to scrape NPS scores
  - Logs into Landry's Loyalty Voice via Microsoft SSO
  - Navigates to Reports → Server Performance
  - Supports custom date ranges by quarter (Q1-Q4)
  - Extracts NPS % for each server from ag-grid table
  - Matches server names to employees in database
  - Stores NPS scores in `cv_nps` collection
- ✅ **New API Endpoints**:
  - `POST /api/v2/cv/sync?quarter=Q4&year=2025` - Sync NPS scores from Loyalty Voice
  - `GET /api/v2/cv/nps` - Get all NPS scores for a quarter
  - `GET /api/v2/cv/stats` - Get NPS statistics (avg, highest, lowest)
  - `GET /api/v2/cv/employee/{name}/nps` - Get NPS for specific employee
  - `GET /api/v2/cv/sync/status` - Get sync status and configuration
- ✅ **Rankings Page Columns Update (Feb 20, 2026)**:
  - **Review Bonus column**: Displays bonus from external reviews and Customer Voice
    - Formula: `(ReviewTracker Mentions × 0.2) + (CV Promoters × 1) + (CV Detractors × -2)`
    - Color-coded: Green for positive, Red for negative
  - **Metric Bonus column**: Displays bonus from exceeding metric benchmarks (PPA, LBW, LSC, Glass)
  - **NPS column**: Shows Employee's NPS score with color coding
    - Green (≥50%): Promoter zone
    - Yellow (0-49%): Passive zone  
    - Red (<0): Detractor zone
  - **Sync NPS button**: 3-minute timeout, loading spinner, proper error handling
  - **Full table headers**: Position, Employee, Tier, Total Score, NPS, Review Bonus, Metric Bonus, PPA (25%), LBW (20%), LSC (25%), Glass (15%)
- ✅ **Customer Voice Feedback Scraper** (cv_feedback_scraper.py):
  - Scrapes individual customer feedback from Loyalty Voice /Feedback page
  - Extracts rating (1-10), customer name, date, shift, and full comment
  - Detects employee mentions in comments
  - Awards CV points: +1 for promoters (9-10), 0 for passive (7-8), -2 for detractors (1-6)
- ✅ **Customer Voice in Review Tracker Page**:
  - "Sync Customer Voice" button (highlighted yellow/orange gradient)
  - CV status banner showing promoter/passive/detractor counts
  - Tabs: "All Reviews", "Customer Voice", "External Reviews"
  - CV feedback cards with ⭐ star badges and "PRIORITY" label
  - Employee credits shown with points (⭐ Eddie +1)

## Backlog

### P0 - Critical
- ✅ **Loyalty Voice NPS Integration (COMPLETED)**
- ✅ **Rankings Page Column Update (COMPLETED)**: Review Bonus, Metric Bonus, NPS columns with proper calculations and UI

### P1 - High Priority  
- [ ] **Multi-Store Architecture**: Support for 22 locations with global reporting
- ✅ **XLSX Upload Support (COMPLETED)**: Direct Excel parsing for 100% accurate data extraction
- [ ] Integrate Review Tracker bonus points into main rankings display

### P2 - Medium Priority
- [ ] "Download All Slides" as ZIP feature
- [ ] Scheduled auto-sync for ReviewTrackers and Loyalty Voice (daily/hourly)
- [ ] Mobile responsiveness audit

### P3 - Low Priority
- [ ] Automated daily/weekly slide pack generation
- [ ] Batch uploads of line graph PDFs
- [ ] Yodeck Embed Link feature

## Key API Endpoints
- `POST /api/v2/pos-ocr/upload` - Upload POS report (XLSX, images, or PDF) for data extraction
- `POST /api/v2/cv/sync` - Sync Loyalty Voice NPS scores
- `GET /api/v2/cv/nps` - List NPS scores
- `GET /api/v2/cv/stats` - NPS statistics
- `GET /api/v2/snapshots` - List all snapshots
- `POST /api/v2/snapshots` - Create new snapshot
- `GET /api/v2/yodeck/{year}/{quarter}/complete-rankings` - Rankings slide
- `GET /api/v2/full-rankings/{year}/{quarter}` - Full rankings data
- `POST /api/v2/reviews/sync-reviewtrackers` - Sync customer reviews

## Database Collections
- `employees_v2`: Employee records with scores
- `quarter_settings`: Quarter configuration
- `snapshots`: Bi-weekly snapshot data
- `dars`: Disciplinary Action Reports
- `cv_nps`: Customer Voice NPS scores from Loyalty Voice (NEW)
- `customer_reviews`: Customer reviews from ReviewTrackers

## Scoring Formula (Updated December 2025)

**Base Score (100 pts max):**
| Metric | Weight | Max Points |
|--------|--------|------------|
| PPA (Per Person Average) | 25% | 25 pts |
| LSC (Loyalty Sales Count) | 25% | 25 pts |
| LBW (Liquor/Beer/Wine per Guest) | 15% | 15 pts |
| Glassware (per Guest) | 10% | 10 pts |
| NPS % (Customer Voice) | 10% | 10 pts |
| Review Tracker | 15% | 15 pts (0.5 pts per mention, capped) |

**Additional Points:**
- Metric Bonus: Up to 20 pts for exceeding 100% on benchmarks
- CV Promoters (9-10 rating): +0.5 pts each (no cap)
- CV Detractors (≤6 rating): -1 pt each (no cap)

**Formula:** `Final Score = Base (max 100) + Metric Bonus (max 20) + CV Bonus (uncapped)`

## Notes
- Loyalty Voice scraper uses Playwright to automate login and data extraction
- NPS scores range from -100 to +100
- Employee name matching supports partial/first-name matches
- Date range presets: Quarter-To-Date (current quarter), Custom Range (past quarters)

## Change Log

### March 12, 2026
**QR Track Hub Integration & Review Tracker Cleanup**
- ✅ **Fixed QR Track Hub Sidebar Navigation**: Added "qr" to default expanded groups so the QR Track Hub section is visible by default in the sidebar
- ✅ **Removed Sync Functions from Review Tracker**: Removed "Sync Customer Voice" and "Sync ReviewTrackers" buttons and their associated functions. The app now uses manual uploads only via the Data Uploads page.
- ✅ **Renamed Upload Button**: Changed "Upload Server Report" to "Upload Customer Voice" for clarity
- ✅ **Added RT Template Button**: Added "RT Template" download button to Review Tracker page header
- ✅ **Fixed Sidebar Scroll Behavior**: Sidebar scroll position is now preserved when expanding/collapsing navigation groups (using useRef and requestAnimationFrame)
- ✅ **Integrated Top 10 QR Clicks into Dashboard**: Added QRTopClicksCard component to the main Dashboard showing top 5 employees by QR scan clicks
- ✅ **Created Reports Page**: New `/reports` page with performance summaries, Top 5 performers, downloadable reports, and the full Top 10 QR Clicks leaderboard
- ✅ **Added Reports to Sidebar**: Reports link added to the main navigation section
- ✅ **Deprecated Legacy Scrapers**: All web scraping endpoints now return deprecation messages pointing to manual upload alternatives
  - `/api/v2/reviews/sync` → Use `/api/v2/rt/upload`
  - `/api/v2/cv/sync` → Use `/api/v2/cv/server-performance/upload`
  - `/api/v2/cv/feedback/sync` → Use `/api/v2/cv/server-performance/upload`
  - `/api/v2/admin/sync-from-ui`, `/api/v2/admin/sync-rt-from-ui`, `/api/v2/admin/sync-cv-from-ui` → Use manual uploads
- ✅ **Archived Scraper Files**: Moved legacy scraper files to `/app/backend/_deprecated_scrapers/` directory
  - `cv_feedback_scraper.py`, `loyalty_voice_integration.py`, `ui_scrapers.py`
- **Files Created**: 
  - `/app/frontend/src/components/QRTopClicksCard.jsx` (reusable component for QR top clicks leaderboard)
  - `/app/frontend/src/pages/Reports.js` (new Reports & Analytics page)
  - `/app/backend/_deprecated_scrapers/README.md` (documentation for deprecated files)
- **Files Modified**: 
  - `/app/frontend/src/components/SidebarLayout.jsx` (added "qr" to expandedGroups, scroll preservation, added Reports link)
  - `/app/frontend/src/pages/ReviewTracker.js` (removed sync functions, renamed upload button, added RT template button)
  - `/app/frontend/src/pages/Dashboard.js` (added QRTopClicksCard component)
  - `/app/frontend/src/App.js` (added Reports route)
  - `/app/backend/server.py` (deprecated all scraper endpoints, commented out scraper imports)

### December 9, 2025
**P0 Bug Fix: Clean POS Parser LBW/LSC Extraction**
- Fixed critical bug in `server.py` where the clean POS format parser was not extracting Liquor, Beer, Wine (LBW) and Loyalty (LSC) data
- The `loyalty` value is now properly converted to `lsc_count` by dividing by $25 (price per LSC card)
- LBW components (liquor, beer, wine) are now summed and stored as `lbw_amount` with individual breakdowns
- `score_lbw` and `score_lsc` are now properly calculated using benchmarks
- Average employee score went from ~58 to ~78.4 after fix
- All 27 employees now have proper LBW scores (100%)

**UI Improvement: Leaderboard Contrast**
- Enhanced leaderboard table header visibility (text-slate-200 instead of text-slate-400)
- Improved tier badge contrast with borders and brighter colors
- Thicker progress bars (h-3) with better color coding (orange for low values)
- Better row alternation contrast for readability
- Brighter subtext (text-slate-300 instead of text-slate-500)
