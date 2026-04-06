# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees.

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key)

## Current State (2026-04-06)

### Backend Modularization Progress
**server.py: 11,847 → 8,607 lines (27% reduction)**

### Route Modules
| Module | Lines | Purpose |
|--------|-------|---------|
| `/app/backend/routes/audit.py` | 917 | Scoring audit system |
| `/app/backend/routes/cv.py` | 868 | CV feedback & NPS |
| `/app/backend/routes/yodeck_slides.py` | 767 | Slide generation |
| `/app/backend/routes/stores.py` | 657 | Multi-store management |
| `/app/backend/routes/upload_jobs.py` | 586 | Background file uploads |
| `/app/backend/routes/employees.py` | 581 | Employee CRUD |
| `/app/backend/routes/trends.py` | 512 | Trend analytics |
| `/app/backend/routes/finalization.py` | 507 | Quarter finalization |
| `/app/backend/routes/quarter_settings.py` | 279 | Settings management |
| `/app/backend/server.py` | 8,607 | Main server (remaining) |

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
- [ ] Continue backend modularization (admin routes ~1500 lines)

### P2 - Medium Priority
- [ ] Review Spotlight feature
- [ ] Download All Slides as ZIP

### P3 - Low Priority
- [ ] Momentum/Trend indicators
- [ ] Store vs Store comparison
