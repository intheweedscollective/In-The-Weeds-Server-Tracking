# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees.

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key)

## Current State (2026-04-06)

### Latest Changes
- **Quarterly Summary Report (2026-04-06)**:
  - New print-friendly page at `/quarterly-summary`
  - Shows Executive Overview, Customer Voice Summary, Metric Bonus Summary, and Complete Employee Breakdown
  - Print button for generating physical reports
  - Accessible from Reports & Analytics page
  
- **UI Label Updates (2026-04-06)**:
  - "Customer Voice" / "Cust. Voice" replaces "CV Score" / "NPS Score" everywhere
  - "Metric Bonus" replaces "POS bonus" / "Metric+" everywhere
  - Customer Voice now displays as combined total (Promoters×0.5 - Detractors×1)
  - Updated: EmployeeCard.jsx, EmployeeDetailsModal.jsx, RankingsExpandedRow.jsx, FullRankings.js, ScoringGuide.js, Analytics.js, Dashboard.js, ReviewTracker.js, DataIntegrity.js, ReviewGeneration.js, TopPerformersGrid.jsx, EmployeeEditModal.jsx

### Backend Modularization Progress
**server.py: 11,847 → 8,181 lines (31% reduction)**

### Route Modules
| Module | Lines | Purpose |
|--------|-------|---------|
| `/app/backend/routes/admin.py` | 1,150 | **NEW** Admin utilities, data sync, fixes |
| `/app/backend/routes/audit.py` | 922 | Scoring audit system |
| `/app/backend/routes/cv.py` | 868 | CV feedback & NPS |
| `/app/backend/routes/yodeck_slides.py` | 850+ | Slide generation + Quarterly Summary |
| `/app/backend/routes/stores.py` | 657 | Multi-store management |
| `/app/backend/routes/upload_jobs.py` | 586 | Background file uploads |
| `/app/backend/routes/employees.py` | 581 | Employee CRUD |
| `/app/backend/routes/trends.py` | 512 | Trend analytics |
| `/app/backend/routes/finalization.py` | 507 | Quarter finalization |
| `/app/backend/routes/quarter_settings.py` | 279 | Settings management |
| `/app/backend/server.py` | 8,181 | Main server (remaining) |

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
- [x] ~~Backend route modularization (admin routes)~~ - DONE (admin.py)
- [ ] Continue backend modularization (review routes ~500 lines)

### P2 - Medium Priority
- [ ] Review Spotlight feature
- [ ] Download All Slides as ZIP

### P3 - Low Priority
- [ ] Momentum/Trend indicators
- [ ] Store vs Store comparison
