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
- ✅ **Las Vegas Themed Snapshot Backgrounds**: Added 6 background options:
  - Dark Navy (default)
  - Las Vegas Strip (Night)
  - Bellagio Fountains
  - Vegas Skyline
  - Welcome to Vegas Sign
  - Vegas Sunset
- ✅ **Letter Format**: 2550x3300 at 300 DPI for high-quality printing

### Recent Changes (Feb 12, 2026)
- ✅ **Fixed Black Outline Issue on Rankings Slide**: The colored rank labels (T1, T2, A1, A2, B1, C1) and total score now have subtle visible black outlines
  - Font size adjusted to 16px for Rank and Score columns
  - Outline width set to 1px for a clean, professional look
- ✅ **NEW Printable Rankings Slide**: Added stylized word-art rankings slide for printing
  - Dark background with gold confetti, ribbons, and star decorations
  - Word art headers: "RED HATS", "A", "B", "C", "BAR", "UNRANKED"
  - Simple rank/name tables grouped by tier (no metrics)
  - New API endpoint: `GET /api/v2/yodeck/{year}/{quarter}/printable-rankings`
  - New "Printable" button on Rankings page (amber/gold outline with star icon)

### Recent Changes (Feb 16, 2026)
- ✅ **Fixed Rank Badge Sizing on Top 10 Slide (#8)**: Adjusted badge radius to 22px and font to 14px so "#10" fits cleanly
- ✅ **Fixed Promotion Watchlist Slide Error (#9)**: Removed undefined `colors` references causing NameError
- ✅ **Consistent Slide Design (#9)**: All slides now use consistent white background with professional header
- ✅ **Mobile Responsiveness Improvements (#10)**: 
  - Added smaller logo/title on mobile screens
  - Navigation tabs show abbreviated labels on very small screens
  - Hidden decorative splashes on mobile for cleaner layout
  - Smaller KPI values and labels on mobile
- ✅ **All 6 Slide Endpoints Working**: top10, complete-rankings, most-improved, promotion-watchlist, at-risk, printable-rankings

## Backlog

### P0 - Critical
- [ ] **Data Import from POS Reports**: Extract data from scanned/uploaded reports (e.g., Aloha POS) - User's top priority
- [ ] **Multi-Store Architecture**: Support for 22 locations with global reporting

### P1 - High Priority  
- [ ] Complete "Concept President" features (Goal Setting, Real-Time Alerts, Incentive Tracking)

### P2 - Medium Priority
- [ ] "Download All Slides" as ZIP feature
- [ ] Production deployment verification

### P3 - Low Priority
- [ ] Automated daily/weekly slide pack generation
- [ ] Batch uploads of line graph PDFs
- [ ] Yodeck Embed Link feature
- Note: "CV Weight" backend logic is NOT dead code - it's the active 15% weight for Customer Voice metric

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
