# Bubba Gump Staff Performance Review App

## Original Problem Statement
Build a comprehensive performance review application for restaurant employees.

## Tech Stack
- **Frontend**: React (Vite)
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-4o (via Emergent LLM Key)
- **Auth**: Emergent-managed Google Auth (whitelist via `ALLOWED_ADMIN_EMAILS`)

## Current State (2026-05-14)

### P0: Snapshot PNG Logo Clipping Fix — SHIPPED 2026-05-14

- `png_full_rankings.py::_draw_sidebar` had `logo_y=135` with
  `logo_w_target=320` on a 1:1 logo, putting the logo top edge at
  y=-25 (clipped off the top of the canvas).
- Adjusted to `logo_y=165`, `logo_w_target=260` → logo top at y=35,
  bottom at y=295. "Q2 SERVER" title at center y=335 (top ≈306) has
  clear ~11px gap below the logo, no overlap.
- Verified by generating a test PNG and inspecting pixel rows 0-34
  (zero non-background pixels above the logo) plus AI visual check.


## Current State (2026-05-13)

### P1: Single-Source Scoring Formula — SHIPPED 2026-05-13

The codebase had **4 parallel implementations** of the total-score
formula, each with hardcoded `0.25/0.25/0.15/0.10` weights instead
of the per-quarter `settings.weight_*` columns. Any future admin
weight tweak would have skipped these sites and caused score drift.

**Sites consolidated**:
1. `routes/admin.py:clear_cv_data` — recomputes after CV wipe.
2. `routes/admin.py:clear_rt_data` — recomputes after RT wipe.
3. `routes/snapshots_legacy.py:_sync_snapshot_to_employees_v2`
   (manual snapshot → employee push-back).
4. `routes/snapshots_legacy.py` raw-POS rebuild paths (×2 identical
   blocks at the SSD engine and the v2 SSD engine).

**Delivered**:
- New `scoring_engine.compute_total_score_dict(emp_dict, settings)`
  facade. Reconstructs an `EmployeeV2`, delegates to the canonical
  `calculate_total_score`, returns dict with `weighted_score`,
  `pre_dar_score`, `total_score`. Preserves all other input dict
  keys (id, name, store_id, etc.).
- Each of the 4 inline formulas replaced with one call to the
  facade. Per-quarter weights, RT/CV rules, DAR penalty all flow
  through one place now.
- Regression test `tests/test_scoring_engine_unified.py` with 6
  cases: byte-equality with canonical, weight propagation, 100-cap,
  partial-dict defaults, dict-key preservation, AND a **hard-code
  guard** that fails if the inline formula reappears in `admin.py`
  or `snapshots_legacy.py`.

**Test status**: 6/6 new tests + 22/22 prior architecture regression
tests pass (28 total). 96 pre-existing failures in
`test_v2_scoring_engine.py` / yodeck tests are auth-gated (401
unauthorized) and unrelated to this refactor.

### P0: Ghost QR Card Healing — SHIPPED 2026-05-13

Root-cause for the "QR clicks aren't tracking" symptom. Two physical
laminated cards (Polly, Tarek) were submitted and decoded — both point
at the correct production tracking URL (`/api/qr/go/<uuid>`). The
real problem: the UUIDs baked into the cards no longer exist in
`qr_employees` (a prior wipe + re-seed broke the link). When a scan
hits the backend the redirect to Google still works (so the customer
flow is fine) BUT the per-employee counter increment silently
skips, leaving the immutable log with `employee_name="Unknown"` and
the dashboard showing zero. On prod: immutable log had 60 events in
30 days, dashboard `total_scans` showed 17.

**Delivered (no card reprint required)**:

1. **`qr_employee_id_aliases` collection** — maps printed UUID →
   current `qr_employees.id`. Populated by admin via the heal flow.

2. **`_record_scan()` rewired** — new helper `_resolve_canonical_id()`
   tries direct lookup first, then alias table. Every scan event now
   stores `resolved_employee_id` and `counter_applied` so we can tell
   which events were attributed live vs back-filled.

3. **Admin endpoints (auth-protected)**:
   - `GET  /api/qr/admin/ghost-ids` — lists unresolved UUIDs in the
     immutable log with scan counts, date range, platform breakdown.
   - `GET  /api/qr/admin/suggest-ghost-mappings` — best-effort
     auto-mapping using `qr_daily_snapshots.rows[]` → archived
     scan names → `employees.legacy_ids`.
   - `POST /api/qr/admin/heal-ghost-ids` — writes aliases + replays
     past immutable events into the canonical counter. Idempotent
     (events flagged `counter_applied=true` skipped on re-run).

4. **`/admin/health` extended** — surfaces `ghost_ids.count` and
   `ghost_ids.orphan_scans` so the dashboard badge can prompt
   the admin to heal.

5. **Frontend `QRGhostHeal` page** at `/qr/ghost-heal` —
   shows ghosts, pre-fills suggested mappings with confidence
   ratings, dry-run + heal buttons. Linked to the dashboard
   `QRHealthBadge` (it becomes clickable + amber when ghosts exist).

6. **Regression test** — `tests/test_qr_ghost_heal.py` covers:
   ghost scan logs but skips counter, heal back-fills correctly,
   alias persists, idempotent re-run, live alias-resolved scan
   increments canonical counter. All 4 scenarios passing.

**Production validation steps for the user**:
1. Sign in as admin on prod.
2. Navigate to `/qr/ghost-heal` (or click the amber Ghost ID badge).
3. Review the auto-suggested mappings (Polly = b05709be…, Tarek =
   aee86c9e…, etc.).
4. Click "Heal N Ghost IDs". Dashboard QR Scans count should jump
   from 17 → ~60+ instantly.

### P2: Merge Duplicate Employees — SHIPPED 2026-05-11

User-requested feature from the previous fork. Backed by the canonical
`EmployeeService.merge_employees` we built in Phase 1.

**Delivered**:

1. **Backend** — `routes/employees.py`
   - `GET /api/v2/employees/merge/candidates` — surfaces probable
     duplicate pairs across the canonical active list with four
     heuristics: identical normalized name, substring containment, same
     first-name + last-initial, Levenshtein ≤2 typo distance. Each
     candidate carries `{a, b, reason}`.
   - `POST /api/v2/employees/merge` — body `{survivor_id, duplicate_id}`.
     Survivor inherits the duplicate's aliases, duplicate is flipped to
     `status="merged"` with `merged_into` FK, and the duplicate's
     `employees_v2` mirror row is removed so legacy readers stop
     seeing them. Snapshot embedded `employees[]` is left alone for
     historical accuracy.

2. **Frontend** — `components/NicknameManager.jsx` gets a new
   "Possible Duplicate Employees" indigo panel above the built-in
   defaults. Each pair shows a radio-picker for the survivor + a
   one-click "Merge" button with `window.confirm` safety dialog. The
   panel only renders when the backend surfaces ≥1 candidate.

3. **Regression tests** — `tests/test_employee_merge.py` (2 tests):
   verifies the merge endpoint flips status / aliases / merged_into
   and that `find_by_name_or_alias` resolves the duplicate's old name
   back to the survivor after merge. Heuristic test confirms typos /
   substring pairs are flagged and clearly-distinct names are not.

**Live finding**: Q2 2026 surfaces 2 candidates today —
"Lennie Nguyen ⇄ Glennice Nguyen" (typo distance 2) and
"Julian ⇄ Julian Taveras" (substring). These are the same duplicate
pairs the Phase-1 migration auto-aliased — the heuristic correctly
re-surfaces them so an admin can confirm.



User reported that the "RT Bonus" leaderboard showed lower bonuses for
employees with more mentions (e.g. Jamie 43 mentions → +10.80; Ikey 28
mentions → +9.30). Root cause: `review_tracker_bonus` was stored on
`snapshot.employees[]` at upload time and never recomputed when later
RT uploads bumped `rt_mentions`.

**Delivered**:

1. **One-time recompute** (`scripts/recompute_rt_bonus.py`) — fixed 18
   `employees_v2` rows, 63 snapshot rows, 17 canonical `current_metrics`.

2. **Permanent compute-on-read in `/v2/snapshot-workflow/current-rankings`** —
   every row now has the following three fields refreshed before return,
   using the quarter's coefficients:
     - `review_tracker_bonus` = min(`rt_mentions` × `rt_points_per_mention`,
       `rt_max_points`)
     - `cv_score` = clamp(`nps_score`, 0, 100)/10 + `cv_promoters`
       − 2 × `cv_detractors` *(skipped when `nps_manual_override=true`)*
     - `total_metric_bonus` = sum of `bonus_ppa` + `bonus_lbw`
       + `bonus_glass` + `bonus_lsc`

3. **Frontend compute-on-render** in `FullRankings.js` RT Bonus column
   as a belt-and-suspenders second line of defence.

4. **`/v2/reviews/stats`** also recomputes RT bonus instead of trusting
   the stored field.

5. **Regression test** in `tests/test_current_rankings_recompute.py` —
   seeds a snapshot with deliberately stale RT/CV/MetricBonus values
   and asserts they get refreshed on read; pinned-row override
   behaviour is also locked in.

## Current State (2026-05-13)

### Phase 3 Stage B Complete — Read endpoints switched to FK-join — SHIPPED 2026-05-13

All live read paths now consume the canonical FK-join via
`EmployeeService.get_snapshot_with_join`:
- `/v2/full-rankings/{y}/{q}/snapshot-png` + `/snapshot-pdf`
- All 9 Yodeck slide endpoints (`routes/yodeck_slides.py`)
- `/v2/snapshot-workflow/current-rankings` (live snapshots; finalized
  snapshots still render frozen)

**Fallback ladder** in `get_snapshot_with_join`:
1. `snapshot.rows[]` (preferred, FK-aware)
2. `snapshot.employees[]` (legacy embedded array)
3. `employees_v2` (last-resort, only when no snapshot exists)

Verified live: Diane shows CV +14.0 / Score 100.9 across snapshot PNG,
snapshot PDF, and current-rankings. 13/13 critical endpoints green.
31/31 architecture-tier tests passing.

### Phase 3 Stage C — `employees_v2` archived, ready to drop — SHIPPED 2026-05-13

All 59 `employees_v2` rows archived into `employees_v2_archive` with a
unique `archive_run_id` per run + `archived_at` timestamp. The live
collection is **still present** — Stage C-final (the actual drop)
intentionally requires one production deploy cycle of green before
running `python scripts/archive_employees_v2.py --apply --drop`.

### QR Health Dashboard Badge — SHIPPED 2026-05-13

New `components/QRHealthBadge.jsx` in the dashboard header. Polls
`/api/qr/admin/health` and shows green/amber status + tooltip with
last silent gap. Will surface any future tracking outage within a
page-load instead of weeks later.

## Previous State

### Phase 2B Continued — CV upload identity resolution → canonical service

`routes/cv.py` CV NPS upload (`/v2/cv/upload`) now resolves the server
name through `EmployeeService.find_by_name_or_alias()` first. The
canonical match is then used to locate the `employees_v2` row to
update, which means CV uploads can no longer spawn duplicates because
of a nickname mismatch. Legacy regex-based name match is preserved
as a fallback for rows the canonical collection hasn't seen yet.



**Problem**: Even after Phase 2A wired `/v2/employees` and `current-rankings`
to `EmployeeService`, the downloadable slide endpoints (PNG/PDF snapshot,
all 8 Yodeck slides, Quarterly Summary report) and QR sync still queried
`employees_v2` directly. Terminated/merged employees and stale ghosts
kept leaking onto signage and printables.

**Delivered**:

1. **New `EmployeeService.filter_active_only(rows, snapshot_deleted_names=...)`**
   - Single helper every legacy reader now calls before rendering.
   - Drops `status="terminated"` and `status="merged"` rows.
   - Drops anything in the snapshot's `deleted_names` blocklist.
   - Stamps `canonical_id` on each survivor + overlays canonical display_name.
   - Resolves by id, legacy_id, name, display_name, and every alias.

2. **Wired endpoints (10 total)**:
   - `server.py` → `/v2/full-rankings/{y}/{q}/snapshot-png` + `/snapshot-pdf`
   - `routes/yodeck_slides.py` → top10, complete-rankings, printable-rankings,
     leaderboard-slide, tier/{name}, most-improved, promotion-watchlist,
     at-risk, quarterly-summary (10 of 11 read sites now go through
     the new `_fetch_active_employees(db, year, quarter)` helper)
   - `qr_tracking.py` → sync-with-employees-list, sync-from-employees,
     leaderboard-slide PNG, leaderboard-data JSON (all 4 sites)

3. **Regression tests** — `tests/test_phase2b_slide_filter.py`
   - `test_filter_active_only_drops_terminated_and_overlays_display_name`
   - `test_filter_active_only_keeps_rows_without_canonical_match`
   - All 40 architecture-tier tests still passing.

4. **Live verification** on production data (Q2 2026):
   - `/v2/admin/integrity` → 0/0/0 P0/P1/P2 issues, deploy gate PASS
   - 8 Yodeck slide endpoints + 2 full-rankings endpoints all HTTP 200
   - current-rankings returns 30 employees (canonical-filtered)

**What's NOT done yet (still Phase 2B + Phase 3)**:
- routes/audit.py (~19 direct `employees_v2.find` calls — admin debug
  utilities, lower priority but should still be wired for consistency)
- routes/cv.py (3 sites)
- snapshot_routes.py (~14 sites, several are write paths — distinct from
  read paths, scoped to Phase 3 alongside the snapshot schema migration)
- Phase 3: drop `employees_v2`, migrate `snapshot.employees[]` → thin
  `rows[]` with `employee_id` FKs.



### Phase 1 — Architecture Correction (Employee Data Layer) — SHIPPED 2026-05-10

User flagged that multiple employee truth sources (`employees_v2` +
embedded `snapshot.employees`) were the root cause of months of bugs:
ghost employees on slides, CV/RT showing zeros, manual-add invisibility,
delete-respawn, cross-page mismatches. Requested a permanent
architectural fix, not another patch.

**Delivered (additive only, no existing data modified):**

1. **Canonical `Employee` Pydantic model** — `/app/backend/models/employee.py`
   - Immutable UUID `id` that never changes through renames/merges
   - `status: active | terminated | merged` for soft-delete
   - `aliases[]` and `legacy_ids[]` to absorb historical naming variants
   - `current_metrics` denormalized for fast reads
   - Companion `SnapshotEmployeeRow` for the new thin snapshot schema

2. **Centralized `EmployeeService`** — `/app/backend/services/employee_service.py`
   - The only sanctioned read/write path for employees
   - 11 methods: get_by_id, find_by_name_or_alias, list_active, count_active,
     get_snapshot_rankings (joined), create_employee, rename, terminate,
     reactivate, merge_employees, upsert_current_metrics, write_snapshot_rows

3. **9-check Integrity Suite** — `/app/backend/services/validation_service.py`
   - P0: duplicate_canonical_ids, orphaned_snapshot_refs, employees_missing_id, blocklist_violations
   - P1: duplicate_active_names, inactive_in_current_snap, metric_drift
   - P2: legacy_only_employees, snapshot_only_employees
   - Deploy gate exit-code: 0 on clean, 1 on any P0

4. **Idempotent Migration Script** — `/app/backend/scripts/migrate_employees_to_canonical.py`
   - Backfilled 59 v2 rows + 262 snapshot embedded rows → 37 canonical employees
   - Auto-detected typos / nicknames (`Glennice Nguyen` → alias of `Lennie Nguyen`)
   - Preserved every legacy UUID in `legacy_ids[]` for Phase 3 FK rewires

5. **Production state after migration:**
   - `employees` collection live with 37 active people + 6 unique indexes
   - All P0/P1/P2 validation checks: **0 issues**, deploy gate PASS
   - Legacy paths untouched; nothing has been broken or rewired yet

6. **8 unit tests** in `tests/test_employee_service.py` — all passing
   (idempotent create, immutable id rename, soft-delete + reactivation,
   merge with alias preservation, snapshot rankings join with frozen-name
   precedence, legacy embedded fallback, frozen metric leak prevention).

7. **Architecture doc** at `/app/backend/docs/employee_architecture.md` —
   migration summary, files changed, integrity check results, technical
   debt for Phase 2/3, rollback plan.

**What's NOT done yet (Phase 2 + 3):**
- Phase 2: refactor every route + slide generator + audit + scoring to
  read through `EmployeeService` (no direct collection queries). This
  unblocks "deletes are real" and "slides never show terminated" everywhere.
- Phase 3: migrate every snapshot's `employees[]` → thin `rows[]` with
  `employee_id` FKs. Drop `employees_v2` after final integrity check.

### Earlier Today (2026-05-10) — see CHANGELOG below
- 9+ tactical bug fixes (modal-block, build-blocker, CV-NPS formula,
  sidebar email, unlock benchmarks, snapshot propagation, delete-name
  blocklist, manual-add visibility, slide ghosts, QR drift hardening).

## Current State (2026-05-03)

- **P0: CV / RT showing all zeros on snapshot slides — FIXED 2026-05-10**
  - Root cause: `merge_snapshot_data` writes the canonical CV/RT/NPS data into `snapshot.employees` (embedded array). However, the slide generators (`png_full_rankings.py`, `pdf_full_rankings.py`, `yodeck_slides.py`) and the Employee List page read from the master `employees_v2` collection. The `process_snapshot` and `confirm_pos_review` flows **never propagated CV/RT data back into employees_v2**, so anyone who hadn't manually re-saved each employee was stuck looking at zeros for CV / RT / Metric Bonus on every signage / printable export. Production verified: `snapshot.employees` had cv_score=11.0 / rt_mentions=20 for Keisha; `employees_v2` had cv_score=0 / rt_mentions=0 for the same row.
  - Fix: new `_propagate_snapshot_to_employees_v2` helper in snapshot_routes.py that upserts every CV/RT/NPS/score field from `snapshot.employees` into `employees_v2` (matching by id, falling back to name+quarter+year). Called at the end of both `process_snapshot` and `confirm_pos_review`. `reprocess_snapshot` inherits the fix because it delegates to `process_snapshot`.

- **P0: More delete paths missing the deleted_names blocklist — FIXED 2026-05-10**
  - `DELETE /v2/employees/{id}` (the trash icon on individual employee cards in EmployeeList) and `POST /v2/employees/cleanup/delete` (bulk delete) were both deleting from `employees_v2` and pulling from snapshots without writing to the snapshot's `deleted_names` blocklist. So even with the merge_snapshot_data fix from earlier in the session, the next save re-spawned them. Both endpoints now write to `deleted_names` (with $addToSet) plus auto-recompute the snapshot's employee_count.
  - Also added `POST /snapshots/{id}/mark-deleted` for bulk-blocking employees on snapshots that were created BEFORE the fix shipped.

### Earlier Today (2026-05-10)
- "support@bubbagump.com" → `support@intheweedscollective.com` in HelpCenter.js
- New backend `POST /v2/quarter-settings/{year}/{quarter}/unlock` + Unlock-to-Edit button.
- AuthCallback now refreshes AuthContext so sidebar reflects signed-in admin state immediately.
- Build-blocker fix in GlobalOverview.jsx (hooks-order violation).
- Trailing-slash defensive normalize for `REACT_APP_BACKEND_URL` across api.js + 22 other files.
- OnboardingGuide gated to admins only (was blocking public viewers).
- routes/cv.py: `cv_score` formula now includes NPS%/10 component.
- SidebarLayout shows real email + Admin/Viewer label.
- `merge_snapshot_data` respects `snapshot.deleted_names` so terminated employees don't respawn from POS parsed_data.
- `parse_cv_file` reads true Promoter/Passive/Detractor columns from NPS Toolkit XLSX (with synonyms); estimation only as fallback. Header scan widened to 10 rows; manager filter narrowed so short names like "TK" pass through.

## Current State (2026-05-03)

- **P1: Terminated employees reappear after saving snapshot — FIXED 2026-05-10**
  - Root cause: `merge_snapshot_data` rebuilds the employees dict from the POS upload's `parsed_data` on every save. Deleted employees were being silently re-created because the source upload still contained them, with no record of intent to remove.
  - Fix: snapshots now persist a `deleted_names` blocklist. `merge_snapshot_data` skips matching rows (full-name + first-name match, case-insensitive). Both `/v2/employees/{id}` (employees.py) and `/v2/snapshot-workflow/employees/{id}` (snapshot_routes.py) DELETE endpoints write to the blocklist. New `restore-deleted/{name}` endpoint allows admins to undo if the deletion was a mistake.
  - Regression test: `tests/test_snapshot_deletion_and_cv_parser.py::test_merge_skips_deleted_names`.

- **P1: NPS Toolkit XLSX showing employees with NPS but no promoters/detractors; "TK" missing — FIXED 2026-05-10**
  - Root cause: `parse_cv_file` (snapshot_routes.py) ignored Promoter/Passive/Detractor columns and ALWAYS estimated from NPS — when NPS=0 the estimate produced 0/0/0. Also, the manager-filter `'manager' in str(name).lower()` was too aggressive and the header detection only checked the first 5 rows.
  - Fix: parser now detects `Promoters/Passives/Detractors` columns (with multiple synonyms — "Promoter", "Promoter Count", "# Promoters", etc.) and uses them directly when present; falls back to estimation only when absent. Header scan widened to first 10 rows. Manager filter narrowed to literal "manager" or "X manager" (i.e. just job-title rows), so short names like "TK" pass through.
  - Regression tests: `test_parse_cv_uses_real_promoter_columns_when_present`, `test_parse_cv_falls_back_to_estimation_when_no_pcd_columns`.

- **Clarification — Scoring audit "deducting points":** the `cv_bonus = (Promoters × 1) + (Detractors × −2)` formula is the canonical scoring policy from `scoring_engine.calculate_customer_voice_score`. Audit displays it correctly. Editable in `quarter_settings` if the user wants to change per-detractor weight.

### Earlier Today (2026-05-10) — see CHANGELOG below
- "support@bubbagump.com" → `support@intheweedscollective.com` in HelpCenter.js
- New backend `POST /v2/quarter-settings/{year}/{quarter}/unlock` + Unlock-to-Edit button so admins can edit locked benchmarks.
- AuthCallback now refreshes AuthContext so sidebar reflects signed-in admin state immediately.
- Build-blocker fix in GlobalOverview.jsx (hooks-order violation).
- Trailing-slash defensive normalize for `REACT_APP_BACKEND_URL` across api.js + 22 other files.
- OnboardingGuide gated to admins only (was blocking public viewers).
- routes/cv.py: `cv_score` formula now includes NPS%/10 component.
- SidebarLayout shows real email + Admin/Viewer label.

## Current State (2026-05-03)

- **P0: PRODUCTION BUILD BLOCKED — "compiled with problems" eslint error in `GlobalOverview.jsx` — FIXED 2026-05-10**
  - Root cause: `useMemo` calls (lines 59, 64) ran AFTER an early conditional `return` for the loading state. CRA's `react-scripts build` (CI=true on production) treats `react-hooks/rules-of-hooks` violations as build errors. The deployed `intheweedscollective.com` was running the LAST successfully-compiled bundle from a much earlier commit, so every subsequent code change silently failed to ship.
  - Fix: hoisted both `useMemo` blocks above the `if (loading) return …` so hooks always run in stable order.
  - Also applied to `/app/frontend/src/lib/api.js` and 22 other files: defensive `(REACT_APP_BACKEND_URL || "").replace(/\/+$/, "")` so a trailing slash on the production env var no longer produces `//api/…` URLs that get mis-routed to the SPA index by Cloudflare/ingress (which is exactly what the user was seeing as "blank/zeros" on every screen of production).

- **P0: "Blank QR Dashboard / zeros on Main Dashboard" for unauthenticated viewers — FIXED 2026-05-10**
  - Root cause: backend public GET endpoints were always returning correct data. The pages only *looked* blank because the `OnboardingGuide` modal opened by default for every visitor on first load, covering the entire dashboard with a dark scrim.
  - Fix: `OnboardingGuide.js` now reads `useAuth()` and only renders for whitelisted admins; the floating launcher is hidden for anonymous viewers too.

- **P1: routes/cv.py — `cv_score` missing NPS%/10 component — FIXED 2026-05-10**
  - Root cause: `_recalculate_server_cv_stats` (line 392) and the manual CV upload endpoint (line 607) both wrote `cv_score = (promoters * 1) + (detractors * -2)` directly to `employees_v2`, omitting the `NPS%/10` component the canonical scoring engine adds.
  - Fix: both call sites now compute `cv_score = (clamp(nps,0,100)/10) + (promoters*1) + (detractors*-2)`.
  - Regression tests: `/app/backend/tests/test_cv_score_includes_nps.py` (7 cases, all passing).

- **UX: SidebarLayout shows real email + Admin/Viewer label — 2026-05-10**
  - The sidebar previously displayed only "Viewer · Sign Out", giving the user no visibility into what email Google actually returned. Now shows the email above an "Admin · Sign Out" (green) or "Viewer · Sign Out" (amber) label, plus a tooltip with the full email.

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
