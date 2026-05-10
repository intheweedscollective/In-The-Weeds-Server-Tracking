# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees.

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key)
- **Auth**: Emergent-managed Google Auth (whitelist via `ALLOWED_ADMIN_EMAILS`)

## Current State (2026-05-10)

### Latest Changes (2026-05-10 Session) — Public-View Onboarding Block

- **P0: "Blank QR Dashboard / zeros on Main Dashboard" for unauthenticated viewers — FIXED 2026-05-10**
  - Root cause: backend public GET endpoints (`/api/qr/stats`, `/api/qr/employees`, `/api/v2/snapshot-workflow/current-rankings`) were always returning correct data. The pages only *looked* blank because the `OnboardingGuide` modal opened by default for every visitor on first load (no localStorage flag yet), covering the entire dashboard with a dark scrim. Public viewers don't know to click X.
  - Fix in `/app/frontend/src/components/OnboardingGuide.js`:
    1. Imported `useAuth` and gated the modal on `user.is_admin`.
    2. `useEffect` now waits for `authLoading` to finish, then short-circuits for non-admins (modal stays closed, hasSeenOnboarding stays false so it can still surface if they later sign in).
    3. The floating launcher button (rocket FAB at bottom-left) is also hidden for non-admins — there's nothing for them to onboard into.
  - Verified: anonymous visit to `/` and `/qr` now shows the full dashboards with no modal blocking; admin sign-in still gets the tour the first time.

## Current State (2026-05-03)

### Latest Changes (2026-05-03 Session) — POS Parser Hardening

- **P0: POS "SSS Q2P5W1.pdf" upload produced broken LBW/glassware values — FIXED 2026-05-03**
  - Symptom 1: Review-modal GLASSWARE column showed `$0` for every employee even though the DB had correct values.
  - Root cause 1: `SnapshotDetail.js` Review modal read `emp.glassware_sales || emp._raw?.bar_glassware_sales` but the parsed POS payload puts the field directly as `emp.bar_glassware_sales` (no `_raw` nesting, no `glassware_sales` alias).
  - Fix: added `emp.bar_glassware_sales` to the OR chain in all 4 spots in `SnapshotDetail.js`.

  - Symptom 2: 15 of 30 employees had wildly corrupt liquor/beer/wine values (e.g. Thomas Kozan `liquor=$17,319,941,816`, Abigail `liquor=$2.86`, Starwars `beer=$170,725`, Jamie Rousseau `food=$4,513,710`). One phantom employee named `"av"` (glyph artifact, real name was Caitlin Carden).
  - Root cause 2: PyMuPDF emitted word-tuples for two physically-separate rows (Food@y=171 and Liquor@y=180) with Y-coordinates that zigzag-interleaved (skewed text rendering). The sequential Y-clustering in `_cluster_rows` lumped them into one 14-token row, and `_parse_metric_row` stuffed two columns' worth of digits into each band. `_join_column_tokens` then concatenated fragments like `["1","707","25"]` into `"170725"` instead of `1707.25`. Single-token values like `"4.10300"` (=$4,103.00) also mis-parsed to `4.103`. Letter-for-digit glyph misreads ("so" for "50", "L,quor" for "Liquor") compounded the issue.
  - Fixes in `native_pos_parser.py`:
    1. Merged-row guard: if a row contains 2+ category labels (Food/Liquor/Beer/Wine/Bar Glassware/Loyalty/Totals) it's treated as skewed/corrupt and skipped so the regex fallback fills it.
    2. Plausibility bound: any category Net Sls > $100k on a per-server page is nulled so regex fallback recomputes it.
    3. `_join_column_tokens` rewritten to detect a trailing 2-digit cents token across N input tokens, or a trailing `.XX` decimal token.
    4. Single-token `X.YYYYY` pattern (period = thousands sep + baked-in cents) now reconstructs as `X,YYY.ZZ`.
    5. `_grab_label_value` extended to capture up to 3 numeric tokens and accept the `"so"` glyph as cents.
    6. Page-level label normalization (`L,quor` → `Liquor`) applied before regex.
    7. Implausibly-tiny rule: if the column-band path produced `>0 but <$10` for food/liquor/beer/glassware, override with the regex fallback (wine exempted since it legitimately can be tiny).
    8. `_extract_name` now skips <4-char no-space alphabetic rows (prevents stray "av" glyph from being picked as a server name).
  - Regression tests: `/app/backend/tests/test_native_pos_parser.py` (12 cases, all passing) covering every pattern observed in SSS Q2P5W1.
  - Verified end-to-end: re-parsed stored PDF, overwrote `snapshot_workflow.uploads.parsed_data`, called `confirm-pos-review`, force-recalculated `lbw`/`lbw_per_guest` (the endpoint was preferring the stale cached `lbw` field), renamed "av" → "Caitlin Carden". All 30 employees now have plausible values: LBW/guest median=6.75 (range 5.00–12.31), Thomas Kozan liquor=$1,816 (was $17.3B), Starwars liquor=$1,982.50 (was $0), Caitlin Carden exists with correct POS data.

## Current State (2026-04-27)

### Latest Changes (2026-04-27 Session)

- **P0: Snapshot Report — Pixel-accurate clone of reference (FIXED 2026-04-27 v3)**
  - User feedback: revert diamond bg, sidebar text was illegible, grid numbers must be BLACK (not white), RT column was empty, "Bonus" column should read "Metric Bonus".
  - Implementation:
    * Reverted to SOLID dark navy bg matching reference exactly.
    * Sidebar fonts upsized for legibility on dark navy: Q SERVER 46pt, PERFORMANCE 58pt, SNAPSHOT 46pt, date 24pt, legend 20pt, footer 20pt.
    * All numbers inside colored grid tiles render in BLACK text (no more white-on-color contrast issues).
    * **RT column** now populated via `RT = min(mentions × 0.5, 15)` — 0.5 pts per ReviewTracker name mention, capped at 15.
    * **"Bonus" column header** renamed to **"Metric Bonus"** and reads from `metric_bonus` field only (POS-metric benchmark exceedance points only — excludes review_bonus).
    * Trend ▲ / — preserved.
  - Files: `/app/backend/png_full_rankings.py`, `/app/backend/pdf_full_rankings.py`.
  - Verified via `/api/v2/full-rankings/2026/Q1/snapshot-png` (HTTP 200, 207 KB) + `analyze_file_tool` 6/6 visual checks pass.

- **CV Score formula confirmation pending from user** — currently `CV = (NPS%/10) + (Promoters × 1) − (Detractors × 2)` per `scoring_engine.py`. User flagged it may be incorrect; awaiting their confirmation before adjusting.

- **P0: Snapshot Report (PNG/PDF) Visual Layout Mirror — FIXED 2026-04-27 (initial pass)**
  - Iter 2 feedback from user: column spacing should match reference, cells need white grid dividers + thin black border for definition, Name column must NOT be black/navy, and the diamond-pattern image must be the slide-wide background.
  - Implementation:
    * Diamond bg image (`/app/backend/assets/snapshot_bg.jpg`) loaded as the full 1920×1080 canvas.
    * `Rank / Name / Trend` cells switched from dark-navy to WHITE fill with dark text (matching reference).
    * Every cell now drawn as a rounded-rect tile (4px radius) with a 1px black outline + a white gutter behind the cell — together they produce the white-grid + black-border effect in the reference.
    * Zero values render as plain `0.0` (no `+0.0`).
    * Title/date proportions tightened so "PERFORMANCE" no longer overshadows the rest of the sidebar.
  - Files: `/app/backend/png_full_rankings.py`, `/app/backend/pdf_full_rankings.py`.
  - Verified via `/api/v2/full-rankings/2026/Q1/snapshot-png` (HTTP 200, 601 KB) + `analyze_file_tool` 5/5 visual checks pass.

- **P0: Snapshot Report (PNG/PDF) Visual Layout Mirror — FIXED 2026-04-27 (initial pass)**
  - User-reference template required: dark-navy body rows (matching header), each metric cell as a colored "tile" with thin navy gutters acting as borders, first three columns (Rank/Name/Trend) on dark-navy without color fill.
  - Fixed sign artefact "+-44.3" by switching to Python `{:+.1f}` formatting (now renders true negatives correctly).
  - Trend column now renders ▲ (green) for improving / — (gray) for flat / ▼ (red) for declining instead of literal "=".
  - Date format moved from `%Y-%m-%d` → `%B %d, %Y` (e.g. "April 27, 2026").
  - Score column now uses absolute thresholds (≥100 blue, 80–100 green, 70–80 yellow, <70 red) matching reference instead of A/B tier logic.
  - Files: `/app/backend/png_full_rankings.py` (full rewrite), `/app/backend/pdf_full_rankings.py` (full rewrite, now 16:9 canvas).
  - Verified via live endpoint `GET /api/v2/full-rankings/2026/Q1/snapshot-png` + `analyze_file_tool` (8/8 layout checks pass).

- **P2: Yodeck slide column labels updated — FIXED 2026-04-27**
  - `/app/backend/yodeck_slides.py` line 1244: "PPA / LBW / LSC / GLASS" → "PPA % / LBW % / LSC % / GLASS %" so viewers don't confuse percentages with absolute scores.

### Latest Changes (2026-02 Session - Continued)

- **P0: Save Snapshot Reverts Edits + Resurrects Duplicates (FIXED 2026-04-25)**:
  - **Bug**: Clicking "Save Snapshot" on the Quick-Edit page reverted manual NPS/LBW edits to raw POS values AND resurrected previously-deleted duplicate employees.
  - **Root cause 1 (ghost resurrection)**: `sync_pos_from_employees_v2` merged employees_v2 INTO existing `pos_upload.parsed_data.employees`, so deleted rows lingered in the POS list and got re-merged into `snapshot.employees` on the next `/process` call.
  - **Root cause 2 (NPS revert)**: Reprocess ran store-level CV redistribution against ALL rows including ones the user had just hand-edited; user's NPS value got overwritten by `(promoters - detractors) / total * 100` from the distributed store-level upload.
  - **Fix 1**: `sync_pos_from_employees_v2` now REBUILDS `pos_upload.parsed_data.employees` ENTIRELY from `employees_v2` (plus salvages legacy fields like `food_sales` from the old POS rows). Also prunes orphan rows from `snapshot.employees` whose ids no longer exist in employees_v2.
  - **Fix 2**: `update_employee` (server.py) writes `nps_manual_override=true` on both `employees_v2` and `snapshot.employees` whenever PUT body contains any of {nps_score, cv_promoters, cv_passives, cv_detractors}. `merge_snapshot_data` (snapshot_routes.py) now skips CV redistribution for flagged rows.
  - **Fix 3 (bonus)**: Mirror `guests` <-> `guest_count` in the PUT payload so one-field edits keep both in sync.
  - **Files**: `/app/backend/snapshot_routes.py` (`sync_pos_from_employees_v2`, `merge_snapshot_data`), `/app/backend/server.py` (`update_employee`).
  - **Test coverage**: `/app/backend/tests/test_save_snapshot_bug.py` (smoke) + iteration 23 (16/16 backend tests pass via testing agent).

### Latest Changes (2026-02 Session)

- **TripAdvisor added to QR Tracker (FIXED 2026-02)**:
  - Full parity with Yelp & Google across the QR Track Hub.
  - Backend (`/app/backend/qr_tracking.py`):
    - New `tripadvisor_clicks` field on QR employees (initialized on create/bulk/sync-from-employees).
    - New `tripadvisor_url` field in QR Settings (with old-doc backfill in GET).
    - New `TRIPADVISOR_REVIEW_URL` env fallback (defaults to tripadvisor.com/UserReview).
    - New `/api/qr/ta/{id}` simplified redirect endpoint (mirrors `/api/qr/go/{id}`).
    - `/api/qr/scan/{id}/tripadvisor` accepts the third platform.
    - `/api/qr/stats` now returns `tripadvisor_scans` + every top_10 row has `tripadvisor_clicks`.
    - Bulk ZIP download emits three PNGs per employee: `Name_google_qr.png`, `Name_yelp_qr.png`, `Name_tripadvisor_qr.png`.
    - Reset endpoints (per-employee and global) also zero `tripadvisor_clicks`.
  - Frontend:
    - `QRSettings.jsx`: TripAdvisor Review URL input field with external-link preview.
    - `QRLeaderboard.jsx`: TripAdvisor column + included in total.
    - `QRDashboard.jsx`: 5-column stats grid with TripAdvisor StatCard, per-emp row TripAdvisor count.
    - `QREmployees.jsx`: TripAdvisor download button per employee, included in ZIP, included in totals.
    - `QRTopClicksCard.jsx`: TripAdvisor quick-stat tile + per-row count.
    - `EmployeeCard.jsx` + `EmployeeList.js`: TripAdvisor clicks aggregated into QR Scans total.
  - Verified via curl: tracking, stats, settings persistence, and per-platform redirect all work.



- **Snapshot Workflow Edits Not Persisting (FIXED 2026-02)**:
  - Root cause 1: Master `PUT /v2/employees/{id}` only synced `name/title/tier/total_score`
    back to `snapshot_workflow.employees` - metric edits (guests, liquor_sales, etc.) were
    written to `employees_v2` but never to the snapshot. Since `EmployeeList` re-fetches
    from `/v2/snapshot-workflow/current-rankings` (reads the snapshot), users saw stale
    values and concluded "changes didn't save".
  - Root cause 2: The snapshot-UUID fallback in the master PUT searched `employees_v2` by
    name without filtering by the snapshot's quarter/year, matching a same-named
    employee in a different quarter and syncing to the wrong snapshot.
  - Fix: Sync ALL editable metric fields (ppa, lbw, liquor/beer/wine, glassware, guests,
    scores, tiers, CV/RT fields) to the snapshot employee element, and filter the
    name-fallback lookup by the originating snapshot's quarter/year.
  - File: `/app/backend/server.py` `update_employee` (~lines 2346-2575).

- **LBW Not Summing All Three Items on Data Upload (FIXED 2026-02)**:
  - Root cause: `process_pdf_job` and `process_xlsx_job` in `/app/backend/routes/upload_jobs.py`
    (used by `/api/v2/upload-jobs/direct`, the endpoint DataUploads.js hits for PDF/XLSX
    parse+preview) did NOT include `lbw_total` in the response. The preview table
    (`emp.lbw_total`) showed blank/undefined.
  - Fix: Compute `lbw_total = liquor + beer + wine` and flatten `_raw` fields up to
    top level in the job result. XLSX now also adds `safe_float` helper.


### Latest Changes
- **Complete Rankings Slide Fix (2026-04-14)**:
  - Changed Complete Rankings to read from employees_v2 (dashboard) instead of snapshot_workflow
  - Slide now calculates tiers from scores (A>=85, B>=70, C<70) rather than using stored tier_label
  - Eliminates all name mismatch and duplicate issues between snapshot and dashboard
  - Added one-shot correction endpoint: GET /api/v2/audit/apply-corrections/2026/Q1
    - Restores Lennie Nguyen with correct scores (90.2, A-Server)
    - Fixes Keisha Martin display_name and score (114.0)
    - Corrects all tier labels based on score thresholds
  - Smart delete: handles duplicate employees by removing lowest-scoring entry only

- **Bug Fix: Blank Page on POS Upload (2026-04-14)**:
  - Fixed React crash (ReferenceError) on `/uploads` page when PDF preview table tried to render
  - Root cause: Missing `idx` parameter in `.map()` callback in `DataUploads.js` line 748
  - Also fixed `editingEmployee` comparison to use index instead of `emp.name`

- **Data Cross-Reference Audit Tools (2026-04-14)**:
  - `GET /api/v2/audit/cross-reference/{year}/{quarter}` — compares snapshot_workflow vs employees_v2 field-by-field
  - `POST /api/v2/audit/sync-from-snapshot/{year}/{quarter}?employee_name=X` — syncs snapshot data → dashboard
  - `POST /api/v2/audit/sync-to-snapshot/{year}/{quarter}?employee_name=X` — syncs dashboard data → snapshot
  - Production finding: Lennie had ALL ZEROS in snapshot but correct data in dashboard; loyalty_sales was 0 in snapshot for all 27 employees; several tier mismatches

- **Complete Rankings Slide Redesign (2026-04-11)**:
  - Simplified slide to show ONLY: Tier header sections + First Name + Rank
  - Added colorful rainbow bubbles background (`/app/backend/assets/backgrounds/rainbow_bubbles.jpg`)
  - Tiers displayed as columns: TRAINERS, BARTENDERS, A-SERVERS, B-SERVERS, C-SERVERS
  - Each employee shown with rank number and first name only
  - Updated default background from "dark" to "rainbow_bubbles" across all pages
  - 16:9 format for Yodeck display

- **Backend Modularization - Phase 2 (2026-04-10)**:
  - Extracted legacy snapshot routes from `server.py` to `routes/snapshots_legacy.py`
  - **server.py reduced: 4,411 → 3,347 lines (~1,064 lines removed)**
  - Routes extracted: `/v2/snapshots`, `/v2/snapshots/backgrounds`, `/v2/snapshots/{id}`, `/v2/snapshots/{id}/upload`, `/v2/snapshots/{id}/recalculate`, `/v2/snapshots/{id}/sync-from-employees`, `/v2/parse-clean-pos`
  - **IMPORTANT**: Two separate snapshot systems exist:
    - `routes/snapshots_legacy.py` → uses `db.snapshots` collection (for `/snapshots` page)
    - `snapshot_routes.py` → uses `db.snapshot_workflow` collection (main workflow)
  - All 11 backend tests passed (100% success rate)

- **Store Performance Index Overhaul (2026-04-07)**:
  - Realigned scoring model based on Bubba Gump Daily Flash Report analysis
  - **NEW WEIGHTS**: Sales (20%), Upsell (20%), Loyalty (25%), Labor (15%), Guest (20%)
  - **NEW: Labor Efficiency category** - tracks Hourly Labor % vs target
  - **Added concept benchmarks** to Quarter Settings:
    - `concept_avg_ppa`: 45.33 (from Flash Report)
    - `concept_lsc_ratio`: 181 (1:181 guests per LSC)
    - `concept_labor_pct`: 17.01%
  - Shows "vs concept" comparisons (e.g., "1.7x better", "+22.9%", "+1.95pp")
  - Awards indicators for Best in Concept achievements
  - Store Health Score increased from 80.9 → 84.2 with new weights

- **Momentum Trend Indicator (2026-04-07)**:
  - Rolling average momentum comparison showing direction and point change (e.g., ↗ +8.3)
  - TrendIndicator component in Dashboard Top 5 Performers section
  - TrendIndicator in Top Performers modal
  - Backend endpoint `/v2/trends/momentum/{year}/{quarter}` provides current score, rolling average, change, direction, percent_change, and snapshots_used
  - Color coding: green for up trend, red for down trend, gray for stable
  - Tooltip with detailed breakdown on hover

- **Help Center & Self-Help Improvements (2026-04-06)**:
  - Completely redesigned Help Center with searchable FAQ (21 questions in 6 categories)
  - New Troubleshooting section with 6 common issues and step-by-step solutions
  - Created reusable HelpTooltip component for contextual help throughout the app
  - Added Quick Actions shortcuts to key pages
  - Fixed outdated scoring formulas (CV = Promoters×0.5 - Detractors×1)
  - Corrected tier thresholds (A-Server ≥85, not 80)
  - Added documentation for new features (Quarterly Summary, Multi-Store, Metric Bonus)

- **Backend Route Modularization (2026-04-06)**:
  - Created admin.py (1,150 lines) and reviews.py (646 lines)
  - server.py reduced from 11,847 to 7,166 lines (40% reduction)

- **Quarterly Summary Report (2026-04-06)**:
  - New print-friendly page at `/quarterly-summary`
  
- **UI Label Updates (2026-04-06)**:
  - "Customer Voice" / "Cust. Voice" replaces "CV Score" / "NPS Score"
  - "Metric Bonus" replaces "POS bonus" / "Metric+"

### Backend Modularization Progress
**server.py: 4,411 → 3,347 lines (24% reduction in this session)**
**Total reduction: 11,847 → 3,347 lines (72% reduction overall)**

### Route Modules (16 total)
| Module | Lines | Purpose |
|--------|-------|---------|
| `/app/backend/routes/admin.py` | 1,150 | Admin utilities, data sync, fixes |
| `/app/backend/routes/audit.py` | 921 | Scoring audit system |
| `/app/backend/routes/cv.py` | 868 | CV feedback & NPS |
| `/app/backend/routes/yodeck_slides.py` | 859 | Slide generation + Quarterly Summary |
| `/app/backend/routes/pos_upload.py` | 836 | POS OCR, PDF parsing |
| `/app/backend/routes/snapshots_legacy.py` | ~1,000 | **NEW** Legacy snapshot routes (db.snapshots) |
| `/app/backend/routes/stores.py` | 657 | Multi-store management |
| `/app/backend/routes/trends.py` | 649 | Trend analytics + Momentum |
| `/app/backend/routes/reviews.py` | 646 | Reviews & RT management |
| `/app/backend/routes/upload_jobs.py` | 586 | Background file uploads |
| `/app/backend/routes/employees.py` | 581 | Employee CRUD |
| `/app/backend/routes/finalization.py` | 507 | Quarter finalization |
| `/app/backend/routes/insights.py` | 443 | Store health, coaching, reviews |
| `/app/backend/routes/quarter_settings.py` | 302 | Settings management |
| `/app/backend/routes/scheduler.py` | ~200 | Automated reconciliation scheduler |
| `/app/backend/snapshot_routes.py` | ~3,100 | Main snapshot workflow (db.snapshot_workflow) |
| `/app/backend/server.py` | 3,347 | Main server (core routes) |

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
- [x] ~~Backend route modularization~~ - DONE (72% reduction - 11,847 → 3,347 lines)

### P2 - Medium Priority
- [ ] Review Spotlight feature (Deferred by user)
- [ ] Download All Slides as ZIP (Deferred by user)

### P3 - Low Priority
- [x] ~~Momentum/Trend indicators~~ - DONE (2026-04-07)
- [ ] Store vs Store comparison
- [ ] Auto-import Daily Flash XLSX for concept benchmarks

## Architecture Notes
### Dual Snapshot Systems
The app uses TWO separate snapshot implementations:
1. **Legacy Snapshots** (`routes/snapshots_legacy.py`):
   - Uses `db.snapshots` collection
   - Serves `/snapshots` page
   - Simpler workflow
2. **Snapshot Workflow** (`snapshot_routes.py`):
   - Uses `db.snapshot_workflow` collection
   - Serves `/snapshot-workflow` and `/snapshot-workflow/:id` pages
   - Full finalization, POS import, and scoring pipeline
