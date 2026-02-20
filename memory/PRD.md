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
│   ├── loyalty_voice_integration.py # Loyalty Voice NPS scraper (NEW)
│   ├── reviewtrackers_integration.py # ReviewTrackers API client
│   └── review_tracker.py            # Customer review tracking
└── frontend/
    └── src/
        ├── components/
        │   ├── FinalizeQuarterModal.js
        │   └── OnboardingGuide.js
        └── pages/
            ├── Dashboard.js
            ├── FullRankings.js
            ├── ReviewTracker.js
            ├── YodeckSlides.js
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

### Recent Changes (Feb 20, 2026) - Loyalty Voice NPS Integration
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
- ✅ **NPS Column in Rankings Page**:
  - Added NPS column to rankings table showing each employee's Customer Voice score
  - Color-coded display: Green (≥50% Promoter), Yellow (0-49% Passive), Red (<0 Detractor)
  - "Sync NPS" button to refresh data from Loyalty Voice
  - NPS summary in results header showing total records and average
  - NPS card in expanded employee details with Promoter/Passive/Detractor label

## Backlog

### P0 - Critical
- ✅ **Loyalty Voice NPS Integration (COMPLETED)**
- [ ] **Integrate NPS into Rankings**: Add NPS scores to employee ranking calculation

### P1 - High Priority  
- [ ] **Multi-Store Architecture**: Support for 22 locations with global reporting
- [ ] **Aloha POS Data Import**: Extract data from scanned/uploaded POS reports
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
