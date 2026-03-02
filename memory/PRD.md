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
│   ├── server.py                    # Main API server
│   ├── scoring_engine.py            # Scoring calculations
│   ├── snapshot_slides.py           # Snapshot slide generator
│   ├── trend_charts.py              # Multi-panel line/bar charts
│   ├── yodeck_slides.py             # Yodeck slide generator
│   ├── loyalty_voice_integration.py # Loyalty Voice NPS scraper
│   ├── reviewtrackers_integration.py # ReviewTrackers API client
│   └── review_tracker.py            # Customer review tracking
└── frontend/
    └── src/
        ├── components/
        │   ├── SidebarLayout.jsx     # NEW: Main layout with sidebar nav
        │   ├── FinalizeQuarterModal.js
        │   └── OnboardingGuide.js
        └── pages/
            ├── Dashboard.js          # REDESIGNED: Bento grid layout
            ├── FullRankings.js
            ├── ReviewTracker.js
            ├── YodeckSlides.js
            ├── HelpCenter.js         # NEW: FAQ & documentation
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

### Recent Changes (Mar 2, 2026) - XLSX Upload Support
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

### Changes (Feb 21, 2026) - UI Label & Data Fix
- ✅ Fixed "CV SCORE" label in Rankings page expanded view → Now shows "Review Tracker"
- ✅ Fixed Review Tracker value displaying wrong data (was showing NPS points, now shows mentions × 0.2)
  - Before: Showed `cv_score` (NPS points) = 10 for Diane
  - After: Shows `review_tracker_bonus` = +0.6 (3 mentions × 0.2)
  - Now displays calculation breakdown: "3 mentions × 0.2"

### Changes (Feb 20, 2026) - Scoring Model Overhaul

#### NPS Scoring Simplified
- **NEW Formula**: `NPS% × 0.10` (2.5 pts per 25%, max ±10 pts)
- **Scale**:
  - -100% = -10 pts | -50% = -5 pts | 0% = 0 pts
  - 25% = 2.5 pts | 50% = 5 pts | 75% = 7.5 pts | 100% = 10 pts
- **OLD Formula** (removed): Estimated promoter/detractor counts which were often inaccurate

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

## Notes
- Loyalty Voice scraper uses Playwright to automate login and data extraction
- NPS scores range from -100 to +100
- Employee name matching supports partial/first-name matches
- Date range presets: Quarter-To-Date (current quarter), Custom Range (past quarters)
