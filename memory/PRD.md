# Performance Review App - PRD

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees (Bubba Gump Shrimp Co.), evolving from Excel to a full-stack web application. The app handles data ingestion from CSV/Excel, calculates employee scores based on configurable metrics, and generates various outputs like PDFs, leaderboards, and slides for digital signage (Yodeck).

## Core Features
1. **Data Ingestion**: CSV/Excel template upload for employee performance data
2. **Quarter Settings**: Admin UI for configuring metric weights, benchmarks, bonus rules, and server tier thresholds
3. **Scoring Engine**: Weighted formula calculation with bonuses/penalties and performance tiers
4. **Rankings Tab**: Employee display sorted by hierarchy (Trainers, Bartenders, A/B/C-Servers)
5. **PDF & Slide Generation**: Individual review PDFs, full rankings PDFs, themed 1920x1080 PNG slides
6. **Time-Series Analytics**: Quarter-over-quarter trend graphs
7. **Bi-Weekly Snapshots**: One-page, color-coded grid of all employees' performance

## Tech Stack
- **Frontend**: React.js, Tailwind CSS, Shadcn/UI
- **Backend**: FastAPI, Python
- **Database**: MongoDB
- **PDF Generation**: ReportLab, Playwright (for screenshot-based charts)
- **Image Generation**: Pillow (PIL)

## Architecture
```
/app/
├── backend/
│   ├── server.py         # Main API server (monolithic, needs refactoring)
│   ├── scoring_engine.py # Scoring calculations
│   ├── snapshot_slides.py # Snapshot slide generator
│   └── yodeck_slides.py  # Yodeck slide generator
└── frontend/
    └── src/
        └── pages/
            ├── Dashboard.js
            ├── Rankings.js
            ├── Employees.js
            ├── Reviews.js
            ├── Snapshots.js
            ├── Analytics.js
            └── Settings.js
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

### Recent Fixes (Jan 31, 2026)
- ✅ **Snapshot LBW Calculation**: Fixed missing `calculate_lbw_total()` call in snapshot upload
- ✅ **Snapshot CV Score**: Added full CV scoring pipeline to snapshot upload
- ✅ **Snapshot Slide Edge-to-Edge**: Rewrote slide generator for full 1920x1080 coverage
- ✅ **CV Column Display**: Changed to use `score_cv` (normalized 0-100) instead of `cv_score`

## Backlog

### P0 - Critical
- [ ] User re-upload data to existing snapshots (required to see fixed calculations)

### P1 - High Priority  
- [ ] Redesign "Top 10 Performers" Yodeck slide (based on user's design image)
- [ ] Individual trend charts in review PDFs

### P2 - Medium Priority
- [ ] Apply consistent aesthetics across all Yodeck slides
- [ ] "Download All Slides" as ZIP feature
- [ ] Code refactoring (split server.py into smaller modules)

### P3 - Low Priority
- [ ] Automated daily/weekly slide pack generation
- [ ] Batch uploads of line graph PDFs
- [ ] Yodeck Embed Link feature

## Key API Endpoints
- `GET /api/v2/snapshots` - List all snapshots
- `POST /api/v2/snapshots` - Create new snapshot
- `POST /api/v2/snapshots/{id}/upload` - Upload employee data
- `GET /api/v2/snapshots/{id}/slide` - Generate snapshot PNG slide
- `GET /api/v2/analytics/{year}/{quarter}/pdf` - Generate analytics PDF
- `GET /api/v2/yodeck/{year}/{quarter}/complete-rankings` - Rankings slide
- `GET /api/v2/yodeck/{year}/{quarter}/top-10` - Top 10 slide

## Database Collections
- `employees_v2`: Employee records with scores
- `quarter_settings`: Quarter configuration
- `snapshots`: Bi-weekly snapshot data

## Notes
- Yodeck API integration not possible on free plan
- Analytics PDF uses Playwright to screenshot frontend charts
- Server tier thresholds are configurable in quarter settings
