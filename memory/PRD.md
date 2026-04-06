# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees that handles:
- Data ingestion (XLSX uploads, scanned PDF POS reports, CSV reviews)
- Employee score calculation based on metrics (PPA, LSC, LBW, Glassware, Customer Voice NPS, Public Reviews)
- Downloadable slides for digital signage (Yodeck)
- Leaderboards and reports

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key)

## Current State (2026-04-06)

### Recent Changes
- **A-Server threshold** changed from 80 to 85
- **CV Passives tip** corrected (they DO affect NPS)
- **Backend modularization** - Extracted audit routes (1555 lines)

### Route Modules
| Module | Lines | Purpose |
|--------|-------|---------|
| `/app/backend/routes/audit.py` | 917 | Scoring audit system |
| `/app/backend/routes/stores.py` | 657 | Multi-store management |
| `/app/backend/routes/upload_jobs.py` | 586 | Background file uploads |
| `/app/backend/routes/yodeck_slides.py` | 767 | Slide generation |
| `/app/backend/routes/employees.py` | 581 | Employee CRUD |
| `/app/backend/routes/finalization.py` | 507 | Quarter finalization |
| `/app/backend/routes/trends.py` | 512 | Trend analytics |
| `/app/backend/routes/quarter_settings.py` | 279 | Settings management |
| `/app/backend/server.py` | 10,292 | Main server (reduced from 11,847) |

### Multi-Store Architecture
- 22 Bubba Gump locations across 5 regions
- Las Vegas store has 27 employees migrated
- Global Overview page at `/global`

### Working Endpoints
- `GET /api/v2/audit/*` - Scoring audit system (NEW MODULE)
- `GET /api/v2/stores/*` - Multi-store management
- `POST /api/v2/upload-jobs/direct` - Background file upload
- `GET /api/v2/yodeck/{year}/{quarter}/*` - Slide generation

## Prioritized Backlog

### P1 - High Priority
- [x] ~~Production 520 error on large PDF uploads~~ - DONE
- [x] ~~Multi-Store Architecture~~ - DONE
- [ ] Continue backend modularization (CV adjustment ~1500 lines)

### P2 - Medium Priority
- [ ] Review Spotlight feature
- [ ] Download All Slides as ZIP

### P3 - Low Priority
- [ ] Momentum/Trend indicators
- [ ] Store vs Store comparison

## Key Thresholds
- **A-Server**: Score >= 85
- **B-Server**: Score >= 70 and < 85
- **C-Server**: Score < 70
- **Trainer**: Score >= 100 OR designated role

## Files of Reference
- `/app/backend/routes/audit.py` - Extracted audit module
- `/app/backend/routes/stores.py` - Multi-store management
- `/app/backend/routes/upload_jobs.py` - Background uploads
- `/app/backend/server.py` - Main server (10,292 lines)
