# Performance Review Application - PRD

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees that handles:
- Data ingestion (XLSX, scanned PDF, CSV reviews)
- Employee score calculation based on detailed metrics (PPA, LSC, LBW, Glassware, Customer Voice NPS, Public Reviews)
- Generate outputs: downloadable slides for digital signage (Yodeck), leaderboards, reports
- QR code tracking system for Google Reviews

## Core Requirements
1. **Unified Data Flow** - Master employee list updated from multiple sources
2. **Advanced Data Parsing** - Scanned PDF POS reports, CSV review files
3. **QR Code System** - Redirect to Google Reviews with scan tracking
4. **Production Data Management** - Exact PPA/Score calculations
5. **Reporting** - Detailed scoring breakdowns with visual indicators

## Scoring Formula (Q1 2026)
- **Weights:** PPA (25%), LSC (25%), LBW (15%), Glassware (10%), NPS (10%), ReviewTracker (15%)
- **Bonuses:** +0.5 pts per CV promoter, -1 pt per CV detractor
- **Metric bonuses:** Up to 5 pts per metric if >100% of benchmark

## Key Metrics
- **PPA (Per Person Average):** Net Sales / Guest Count (or extracted from "Guest Avg" column)
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

### Scoring Engine
- [x] Complex weighted scoring formula
- [x] Benchmark-based normalization
- [x] Metric bonuses (capped at 5 pts each)
- [x] CV promoter/detractor points
- [x] DAR penalty system

### Data Integrity
- [x] Audit system for score verification
- [x] Data reconciliation tools
- [x] "Fix All" discrepancy resolution
- [x] Official stats sync (CV, RT)

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
- Updated PPA extraction to prioritize "Guest Avg" column from reports
- Modified AI OCR prompt to explicitly extract Guest Average
- Added PPA column support in consolidated XLSX parser
- Verified Chase Winston PPA accuracy: $52.29

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
- None currently

### P1 (High Priority)
- [ ] Momentum Indicators - Add Trend column on Leaderboard
- [ ] Multi-Store Architecture - Support 22 locations with global reporting

### P2 (Medium Priority)
- [ ] Code Refactoring - Break down server.py (12k+ lines)
- [ ] Review Spotlight Feature
- [ ] "Download All Slides" ZIP feature

### P3 (Future)
- [ ] Automated UI scraping for official stats
- [ ] Background task queue (Celery)
- [ ] Historical performance comparison

---

## Technical Architecture

```
/app/
├── backend/
│   ├── server.py           # Main API (12k+ lines - needs modularization)
│   ├── pos_ocr.py          # AI Vision OCR for PDFs
│   ├── pos_report_parser.py # XLSX parsing
│   └── qr_tracking.py      # QR code management
└── frontend/
    └── src/pages/
        ├── DataUploads.js   # Upload handling with polling
        ├── EmployeeList.js  # Employee details
        ├── Leaderboard.js   # Rankings display
        └── ScoringAudit.js  # Data integrity tools
```

## Key Collections (MongoDB)
- `employees_v2` - Main employee data and scores
- `customer_reviews` - ReviewTracker data
- `cv_feedback` - Customer Voice surveys
- `qr_employees` / `qr_scans` - QR tracking

## 3rd Party Integrations
- OpenAI GPT-4o (via Emergent LLM Key) - PDF OCR
