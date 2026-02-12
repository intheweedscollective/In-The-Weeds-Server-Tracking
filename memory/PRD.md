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

## Architecture
```
/app/
├── backend/
│   ├── server.py         # Main API server
│   ├── scoring_engine.py # Scoring calculations
│   ├── snapshot_slides.py # Snapshot slide generator
│   ├── trend_charts.py   # Multi-panel line/bar charts
│   └── yodeck_slides.py  # Yodeck slide generator
└── frontend/
    └── src/
        ├── components/
        │   ├── FinalizeQuarterModal.js # DAR calculator
        │   └── OnboardingGuide.js      # Quick start guide
        └── pages/
            ├── Dashboard.js    # Main dashboard with ROI calc, Training priorities
            ├── FullRankings.js # Rankings + Top 10 sections (merged)
            ├── EmployeeList.js
            ├── ReviewGeneration.js
            ├── Snapshots.js
            ├── Analytics.js
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
- ✅ Multi-panel line charts for employee trends (one per metric)
- ✅ Revenue Impact Calculator (Dashboard)
- ✅ Training Priorities Panel (Dashboard)
- ✅ Onboarding Guide (7-step quick start modal)
- ✅ DAR Calculator (Finalize Quarter with deductions)
- ✅ Peer Comparison Badges (Top 10%, Top 25%, Top 50%)

### Recent Changes (Feb 10, 2026)
- ✅ **Merged Rankings + Top Performers**: Combined into single page at `/rankings`
- ✅ **Removed "Top" Navigation**: Simplified nav bar (8 items instead of 9)
- ✅ **Top 10 by Metric**: Added PPA, LBW/Guest, Glass/Guest, Guests/LSC, CV Score sections
- ✅ **2-Column Grid Layout**: Top 10 metric sections displayed in responsive grid
- ✅ **Deleted TopPerformers.js**: Removed redundant page component
- ✅ **Yodeck Slide Cleanup**: Removed tier-specific slides (A/B/C-Server), only Complete Rankings remains
- ✅ **Format Selection on ALL Slides**: Added 16:9 (Yodeck) and 8.5×11" (Letter) format dropdown on every slide
- ✅ **NEW Top 10 By Metric Slide**: Redesigned to match professional 4-column layout:
  - Dark blue gradient header with Bubba Gump logo
  - "TOP 10 PERFORMERS BY METRIC" title with Quarter/Year
  - 4 metric columns: PPA, Glass/Guest, Guests/LSC, LBW/Guest
  - Dark gray metric headers, light blue column headers
  - Red circular rank badges (#1-#10)
  - Alternating row colors for readability
- ✅ **Letter Format**: 2550x3300 at 300 DPI for high-quality printing

## Backlog

### P0 - Critical
- None

### P1 - High Priority  
- [ ] Redesign "Top 10 Performers" Yodeck slide (based on user's design image)
- [ ] Complete "Concept President" features (Goal Setting, Real-Time Alerts, Incentive Tracking)
- [ ] Multi-Store Architecture (phased approach)

### P2 - Medium Priority
- [ ] Apply consistent aesthetics across all Yodeck slides
- [ ] "Download All Slides" as ZIP feature
- [ ] Production deployment verification

### P3 - Low Priority
- [ ] Automated daily/weekly slide pack generation
- [ ] Batch uploads of line graph PDFs
- [ ] Yodeck Embed Link feature
- [ ] Remove obsolete "CV Weight" backend logic

## Key API Endpoints
- `GET /api/v2/snapshots` - List all snapshots
- `POST /api/v2/snapshots` - Create new snapshot
- `POST /api/v2/snapshots/{id}/upload` - Upload employee data
- `POST /api/v2/snapshots/{id}/recalculate` - Recalculate snapshot scores
- `GET /api/v2/snapshots/{id}/slide` - Generate snapshot PNG slide
- `GET /api/v2/analytics/{year}/{quarter}/pdf` - Generate analytics PDF
- `GET /api/v2/yodeck/{year}/{quarter}/complete-rankings` - Rankings slide
- `GET /api/v2/yodeck/{year}/{quarter}/top-10` - Top 10 slide
- `GET /api/v2/full-rankings/{year}/{quarter}` - Full rankings data
- `GET /api/v2/trends/{year}/{quarter}/employee/{id}` - Employee trend chart
- `GET /api/v2/dars/{year}/{quarter}` - Get DAR entries
- `POST /api/v2/dars/{year}/{quarter}` - Save/finalize DAR entries

## Database Collections
- `employees_v2`: Employee records with scores
- `quarter_settings`: Quarter configuration (includes `is_finalized` flag)
- `snapshots`: Bi-weekly snapshot data
- `dars`: Disciplinary Action Reports

## Notes
- Yodeck API integration not possible on free plan
- Analytics PDF uses Playwright to screenshot frontend charts
- Server tier thresholds are configurable in quarter settings
- "Top Performers" definition: 10% above restaurant average
- DAR deductions: Written Warning = -3 pts, Suspension = -5 pts
