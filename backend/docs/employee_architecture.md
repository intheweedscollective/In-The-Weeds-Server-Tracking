# Employee Data Layer — Architecture Correction (Phase 1)

**Status:** Phase 1 of 3 — foundation deployed, read paths still legacy.
**Owner:** In the Weeds Collective platform.
**Date:** 2026-05-10.

## 1. Architecture Summary

### Before (the problem)

```
                       ┌─────────────────┐
   POS / CV / RT  ───► │  employees_v2   │ ◄── EmployeeList page, Slides, Audit
   uploads             │  (long-lived)   │
                       └─────────────────┘
                              ▲    ▲
                              │    │  (drift)
                              │    │
                       ┌─────────────────┐
   Snapshot save  ───► │ snapshot.       │ ◄── Snapshot UI, Rankings
   merge_snapshot_data │   employees[]   │      Yodeck slides
                       │ (embedded copy) │
                       └─────────────────┘
```

Two sources of truth. Different routes read from different ones. Drift
between them caused: ghost employees on slides, CV/RT showing zeros on
some employees but not others, deleted-employee respawn, manual-add
invisibility, score mismatches across screens.

### After (Phase 1 + future)

```
   POS / CV / RT  ──┐                ┌────────────────────────────┐
   uploads          │                │      employees             │
                    └──►  EmployeeService ◄─── (canonical)        │
                          • get_by_id                              │
   All UI screens ──────► • find_by_name_or_alias                  │
   Slide generators       • list_active                            │
   Audit / scoring        • create / rename / terminate / merge    │
   QR sync                • upsert_current_metrics                 │
                          • get_snapshot_rankings (joined view)    │
                          • write_snapshot_rows                    │
                                                                  ▼
                                                       ┌─────────────────┐
                                                       │ snapshot_workflow│
                                                       │   .rows[]        │
                                                       │ ({employee_id +  │
                                                       │  frozen_metrics})│
                                                       └─────────────────┘
```

- Single canonical collection `employees`.
- One service module `services/employee_service.py` is the ONLY way to
  read/write employees. New employee touches anywhere else are a code
  review red flag.
- Snapshots store thin `rows[]` with `employee_id` foreign keys + frozen
  display name + frozen metrics. The full canonical record is joined at
  read time (`get_snapshot_rankings`).
- Soft-delete: `status: "active" | "terminated" | "merged"`. Terminated
  employees disappear from active rankings but remain renderable in
  historical snapshots.
- Identity is immutable: `id` (UUID4) NEVER changes. Renames, merges,
  and re-hires all preserve the id and append the old name to
  `aliases[]` so future uploads find the same person.

## 2. Migration Summary (Phase 1 — additive only)

| Metric                                  | Count |
|-----------------------------------------|-------|
| Rows scanned in `employees_v2`          | 59    |
| Rows scanned in snapshot.employees[]    | 262   |
| Distinct people resolved                | 37    |
| Duplicate id collisions auto-merged     | ~6    |
| Canonical rows written to `employees`   | 37    |

**Examples of resolutions captured:**
- `Thaddeus Hashey` → alias of `Tad Hashey` (same person)
- `Jose Planoarte Villa` → alias of `Jose Plancarte Villa` (typo)
- 3 legacy UUIDs per person tracked in `legacy_ids[]` for Phase 3 FK rewires.

**Migration script:** `scripts/migrate_employees_to_canonical.py`
- Default: dry-run (no writes)
- `--apply`: writes to MongoDB
- Idempotent (safe to re-run; upserts by id then by name)

## 3. Collections Changed

| Collection                  | Phase 1 change |
|-----------------------------|----------------|
| `employees` (NEW)           | Created. 37 canonical rows. 4 unique indexes (`id`, `name`, `status`, `aliases`, `legacy_ids`). |
| `employees_v2`              | **Untouched.** Still active source for legacy read paths. Will be deprecated in Phase 2 and dropped in Phase 3. |
| `snapshot_workflow`         | **Untouched.** Still uses embedded `employees[]`. Phase 3 will migrate each doc to thin `rows[]`. |
| `snapshot_workflow.rows[]`  | New optional schema, currently empty on every doc. Service supports both shapes transparently. |

## 4. Files Added / Refactored

### New files
- `backend/models/employee.py` — Pydantic `Employee`, `SnapshotEmployeeRow`, `EmployeeCurrentMetrics`
- `backend/services/employee_service.py` — Centralized data-access layer
- `backend/services/validation_service.py` — 9 integrity checks
- `backend/scripts/migrate_employees_to_canonical.py` — Backfill script (idempotent)
- `backend/scripts/run_validation_suite.py` — Validation runner + deploy gate
- `backend/tests/test_employee_service.py` — 8 unit tests (all passing)
- `backend/docs/employee_architecture.md` — This document

### Existing files in Phase 1
**No existing files modified.** The legacy read paths still point at
`employees_v2` and `snapshot.employees[]`. Phase 2 will rewire them
through `EmployeeService` one router at a time.

## 5. Integrity Checks Performed

`EmployeeValidator` enforces:

| # | Check                          | Severity | Result after migration |
|---|--------------------------------|----------|------------------------|
| 1 | duplicate_canonical_ids        | P0       | 0 issues |
| 2 | orphaned_snapshot_refs         | P0       | 0 issues |
| 3 | employees_missing_id           | P0       | 0 issues |
| 4 | blocklist_violations           | P0       | 0 issues |
| 5 | duplicate_active_names         | P1       | 0 issues |
| 6 | inactive_in_current_snap       | P1       | 0 issues |
| 7 | metric_drift                   | P1       | 0 issues |
| 8 | legacy_only_employees          | P2       | 0 issues |
| 9 | snapshot_only_employees        | P2       | 0 issues |

**Deploy gate: PASS** (zero P0 issues).

Run anytime:
```bash
python scripts/run_validation_suite.py          # report
python scripts/run_validation_suite.py --json   # raw JSON
python scripts/run_validation_suite.py --gate   # exit code 1 if any P0
```

## 6. Remaining Technical Debt (Phase 2 / 3)

### Phase 2 — Route refactor (no DB schema changes)
1. `snapshot_routes.merge_snapshot_data` should resolve every parsed
   employee through `EmployeeService.find_by_name_or_alias` and use the
   canonical id; new employees should call `EmployeeService.create_employee`.
2. `routes/employees.py` POST/PUT/DELETE/list — all → service.
3. `routes/cv.py`, `qr_tracking.py`, `audit_routes.py`, `scoring_engine.py`
   — all employee reads must go through service.
4. Slide generators (`png_full_rankings.py`, `pdf_full_rankings.py`,
   `yodeck_slides.py`) read via `EmployeeService.get_snapshot_rankings`.
5. Frontend `current-rankings` endpoint switches to the joined service view.
6. Re-run validation as a pre-deploy gate in CI.

### Phase 3 — Snapshot schema migration
1. For each existing snapshot, transform `employees[]` → `rows[]`:
   - lookup each embedded row's canonical id via name match;
   - freeze the display name + metrics into a `SnapshotEmployeeRow`;
   - persist `rows[]`, then remove `employees[]`.
2. Drop `employees_v2` (keep a one-time DB backup first).
3. Re-run full validation including `orphaned_snapshot_refs`.

### Out-of-scope today (worth tracking)
- Multi-store: `store_id` field is present but unused. Phase 2 will gate
  reads on it for the upcoming 22-location rollout.
- Audit log per employee mutation (create/rename/merge events). Currently
  not captured beyond `updated_at`.

## 7. Rollback Plan

Phase 1 is **purely additive** — no existing data was modified. Rolling
back is trivial:

```bash
# Wipe the canonical collection
mongo "$MONGO_URL" --eval 'db.getSiblingDB("staff_score_db").employees.drop()'
```

All legacy read paths continue to work because nothing was rewired in
Phase 1. No application restart needed.

Phase 2 and Phase 3 rollback plans will be documented when those phases
ship — each will include a feature flag so the read path can flip back
to legacy with no DB change.

## 8. Production Deployment Notes

1. The new `employees` collection now exists in production
   (`bubba-gump.qzyk7kp.mongodb.net/staff_score_db`). It is **dormant**
   — no application code reads from it yet, so it cannot affect anything.
2. Re-running `python scripts/migrate_employees_to_canonical.py --apply`
   is safe — it's idempotent. Useful after a future upload introduces
   a brand new employee, to keep the canonical view up to date until
   Phase 2 ships.
3. Validation script can be wired into a deploy hook to fail any future
   deploy that would introduce P0 data corruption.
4. **No frontend changes** were made or required in Phase 1.

## 9. Why This Won't Drift Again

Once Phase 2 lands, every employee read **must** go through
`EmployeeService`. The service:
- always uses the immutable canonical id when persisting snapshot rows,
- freezes display values at snapshot time so renames don't rewrite
  history,
- excludes `terminated` / `merged` employees from current views by
  default — they can only appear in a historical snapshot deliberately,
- exposes one merge path; nickname clashes resolve to one row, not two.

The validation suite catches violations before deploy. Adding new
employee-touching code that bypasses the service will produce a P0
issue on the next validation run — the gate fails the deploy.
