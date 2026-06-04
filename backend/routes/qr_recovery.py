"""
QR Click Recovery — admin-only file-upload endpoints for re-importing
historical QR scan events that were lost during a destructive wipe.

Context
-------
Before 2026-03-31 the QR tracking pipeline had no immutable audit
trail. A destructive admin action that quarter wiped both `qr_scans`
and `qr_click_log_immutable` (which only existed AFTER the wipe).
Earliest surviving timestamp on preview: `2026-03-31T03:11:41Z`.

Atlas point-in-time backups don't reach that far back on the user's
cluster tier. This recovery tool is the catch-all for any pre-March
data the operator can later source elsewhere — e.g.:
  • POS reports that recorded QR scan timestamps
  • External analytics exports
  • Staff-memory reconstructions written into a CSV/JSON

Design contract — per user's explicit requirements:
  1. Two modes:
       a. `staging`  — write into `qr_scans_pre_march_recovered` only.
                       Nothing touches the live collections. Operator
                       audits the staging collection in Mongo Compass
                       (or via the GET endpoint) before deciding to
                       promote.
       b. `merge`    — write directly into BOTH `qr_scans` AND
                       `qr_click_log_immutable`, skipping any doc whose
                       `id` already exists. Useful when the operator
                       trusts the source.
  2. Dedupe key is the document's `id` field (UUID).
  3. NEVER touches `qr_employees.{yelp,google,tripadvisor}_clicks`
     totals. The operator explicitly asked to rebuild totals only
     after they've reviewed the raw events.
  4. Every action is gated on `require_admin` and audited in
     `qr_recovery_audit` so the operator can prove provenance later.

Endpoints
---------
  POST /api/v2/admin/qr-recovery/import?mode=staging|merge&dry_run=true|false
       multipart upload, expects a JSON file (array of scan-event
       documents) — see SchemaShape below.

  GET  /api/v2/admin/qr-recovery/staging-summary
       Counts rows in staging by (employee_id, platform), date range,
       and number of already-merged ids (would-be skips on promote).

  POST /api/v2/admin/qr-recovery/promote-staging
       Move every staging row into qr_scans + qr_click_log_immutable,
       dedupe on `id`. Idempotent: re-runs do nothing.

  POST /api/v2/admin/qr-recovery/clear-staging
       Delete the staging collection (after a successful promote, or
       when the operator wants to start over with a different source).

  GET  /api/v2/admin/qr-recovery/audit
       The append-only audit log for this module.

Expected JSON document shape
----------------------------
    {
      "id": "<uuid>",                         # REQUIRED. dedupe key.
      "employee_id": "<canonical-uuid>",      # REQUIRED.
      "employee_name": "Robert Mckinnon",     # optional (display)
      "platform": "google",                   # REQUIRED. yelp|google|tripadvisor
      "scanned_at": "2026-02-14T17:42:03Z",  # REQUIRED. ISO 8601.
      "user_agent": "...",                    # optional
      "ip_address": "..."                     # optional
    }

Rows missing any REQUIRED field are returned in `malformed` with the
reason. Rows with a duplicate `id` (on merge) or already in staging
are returned in `skipped_duplicates`.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, UploadFile,
)

from routes.auth import require_admin, AuthUser

logger = logging.getLogger(__name__)

qr_recovery_router = APIRouter(
    prefix="/v2/admin/qr-recovery",
    tags=["QR Recovery"],
)

REQUIRED_FIELDS = ("id", "employee_id", "platform", "scanned_at")
VALID_PLATFORMS = {"yelp", "google", "tripadvisor"}
STAGING_COLLECTION = "qr_scans_pre_march_recovered"
AUDIT_COLLECTION = "qr_recovery_audit"


_db = None  # populated by register_qr_recovery_routes


def _set_db(db):
    global _db
    _db = db


def _validate_row(row: Any) -> Optional[str]:
    """Return None if valid, else a human-readable reason string."""
    if not isinstance(row, dict):
        return f"not an object (got {type(row).__name__})"
    for f in REQUIRED_FIELDS:
        v = row.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            return f"missing required field {f!r}"
    plat = (row.get("platform") or "").strip().lower()
    if plat not in VALID_PLATFORMS:
        return f"invalid platform {row.get('platform')!r} — expected one of {sorted(VALID_PLATFORMS)}"
    # Try to parse scanned_at so we fail loud on malformed timestamps.
    try:
        datetime.fromisoformat(str(row["scanned_at"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return f"scanned_at {row.get('scanned_at')!r} is not a valid ISO-8601 timestamp"
    return None


def _canonicalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a candidate row into the storage schema used by
    qr_scans / qr_click_log_immutable so consumers never see drift."""
    return {
        "id":              str(row["id"]).strip(),
        "employee_id":     str(row["employee_id"]).strip(),
        "resolved_employee_id": row.get("resolved_employee_id") or row.get("employee_id"),
        "employee_name":   (row.get("employee_name") or "").strip() or None,
        "platform":        row["platform"].strip().lower(),
        "scanned_at":      str(row["scanned_at"]).strip(),
        "counter_applied": bool(row.get("counter_applied", False)),
        # Provenance — every recovered row is tagged so we can tell it
        # apart from organic scans in audits later.
        "recovered_via":   row.get("recovered_via") or "qr_recovery_import",
        "recovered_at":    datetime.now(timezone.utc).isoformat(),
        # Pass through optional forensics fields if present.
        "user_agent":      row.get("user_agent"),
        "ip_address":      row.get("ip_address"),
    }


async def _audit(actor: str, action: str, payload: Dict[str, Any]) -> None:
    await _db[AUDIT_COLLECTION].insert_one({
        "id":         str(uuid.uuid4()),
        "actor":      actor,
        "action":     action,
        "logged_at":  datetime.now(timezone.utc).isoformat(),
        **payload,
    })


# ---------------------------------------------------------------------------
# POST /import
# ---------------------------------------------------------------------------

@qr_recovery_router.post("/import")
async def import_pre_march_qr_clicks(
    file: UploadFile = File(...),
    mode: str = Form("staging"),
    dry_run: bool = Form(False),
    user: AuthUser = Depends(require_admin),
) -> Dict[str, Any]:
    """Accept a JSON file (array of scan-event docs), validate each
    row, and either stage them or merge them into the live collections.

    Returns:
        {
          "mode": "staging" | "merge",
          "dry_run": bool,
          "accepted": int,           # rows that would be / were written
          "skipped_duplicates": int, # rows whose id already exists
          "malformed": [             # bad rows (max 50 sampled)
            {"index": 17, "reason": "...", "row": {...}}
          ],
          "total_in_file": int,
        }
    """
    if mode not in ("staging", "merge"):
        raise HTTPException(400, f"mode must be 'staging' or 'merge', got {mode!r}")

    raw = await file.read()
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"invalid JSON: {e.msg} at line {e.lineno} col {e.colno}")
    if not isinstance(rows, list):
        raise HTTPException(400, f"top-level JSON must be an array, got {type(rows).__name__}")

    accepted: List[Dict[str, Any]] = []
    malformed: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        reason = _validate_row(row)
        if reason:
            if len(malformed) < 50:  # cap so the response stays small
                malformed.append({"index": idx, "reason": reason, "row": row})
            continue
        accepted.append(_canonicalize_row(row))

    # Dedupe by id within the file itself (operator may have provided
    # the same row twice — keep first occurrence).
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    intra_file_dupes = 0
    for r in accepted:
        if r["id"] in seen_ids:
            intra_file_dupes += 1
            continue
        seen_ids.add(r["id"])
        deduped.append(r)
    accepted = deduped

    # Detect collection-level duplicates so the operator can see what
    # would be skipped before they pull the trigger.
    if mode == "staging":
        existing_q = _db[STAGING_COLLECTION].find(
            {"id": {"$in": [r["id"] for r in accepted]}},
            {"_id": 0, "id": 1},
        )
    else:
        # In merge mode, a row is a duplicate if it already exists in
        # EITHER qr_scans OR qr_click_log_immutable.
        existing_q = _db.qr_scans.find(
            {"id": {"$in": [r["id"] for r in accepted]}},
            {"_id": 0, "id": 1},
        )
    existing_ids = {d["id"] async for d in existing_q}
    if mode == "merge":
        # Also count the immutable log dupes (typically same set, but
        # guard against drift between the two collections).
        async for d in _db.qr_click_log_immutable.find(
            {"id": {"$in": [r["id"] for r in accepted]}},
            {"_id": 0, "id": 1},
        ):
            existing_ids.add(d["id"])

    to_write = [r for r in accepted if r["id"] not in existing_ids]

    result: Dict[str, Any] = {
        "mode": mode,
        "dry_run": dry_run,
        "total_in_file": len(rows),
        "accepted": len(to_write),
        "skipped_duplicates": len(existing_ids) + intra_file_dupes,
        "skipped_duplicates_in_file": intra_file_dupes,
        "malformed": malformed,
        "malformed_count": sum(
            1 for r in rows if _validate_row(r) is not None
        ),
    }

    if dry_run:
        await _audit(user.email, "import.dry_run", {
            "mode": mode, "filename": file.filename,
            "total_in_file": len(rows),
            "accepted": len(to_write),
            "skipped_duplicates": result["skipped_duplicates"],
            "malformed": result["malformed_count"],
        })
        return result

    if not to_write:
        await _audit(user.email, "import.no_op", {
            "mode": mode, "filename": file.filename,
            "reason": "all rows were duplicates or malformed",
        })
        return result

    if mode == "staging":
        await _db[STAGING_COLLECTION].insert_many(to_write)
        target_label = STAGING_COLLECTION
    else:
        # Merge: write into BOTH qr_scans and qr_click_log_immutable so
        # the existing dashboard / leaderboard queries see the data and
        # the immutable audit trail picks up its lost rows too.
        await _db.qr_scans.insert_many(to_write)
        await _db.qr_click_log_immutable.insert_many(to_write)
        target_label = "qr_scans + qr_click_log_immutable"

    await _audit(user.email, f"import.{mode}", {
        "filename": file.filename,
        "target": target_label,
        "written": len(to_write),
        "skipped_duplicates": result["skipped_duplicates"],
        "malformed": result["malformed_count"],
    })
    result["target"] = target_label
    return result


# ---------------------------------------------------------------------------
# GET /staging-summary
# ---------------------------------------------------------------------------

@qr_recovery_router.get("/staging-summary")
async def staging_summary(
    user: AuthUser = Depends(require_admin),
) -> Dict[str, Any]:
    """Show what's currently parked in the staging collection so the
    operator can audit before promoting. Returns counts by platform,
    earliest/latest timestamps, and how many rows would be skipped on
    promote (already in qr_scans by id)."""
    total = await _db[STAGING_COLLECTION].count_documents({})
    if total == 0:
        return {
            "total": 0,
            "by_platform": {},
            "earliest": None,
            "latest": None,
            "would_skip_on_promote": 0,
        }

    by_platform: Dict[str, int] = {}
    async for d in _db[STAGING_COLLECTION].aggregate([
        {"$group": {"_id": "$platform", "n": {"$sum": 1}}},
    ]):
        by_platform[d.get("_id") or "unknown"] = d.get("n", 0)

    earliest_doc = await _db[STAGING_COLLECTION].find_one(
        {}, {"_id": 0, "scanned_at": 1}, sort=[("scanned_at", 1)],
    )
    latest_doc = await _db[STAGING_COLLECTION].find_one(
        {}, {"_id": 0, "scanned_at": 1}, sort=[("scanned_at", -1)],
    )

    # Would-be skips on promote — count ids that already exist in qr_scans.
    staging_ids = [d["id"] async for d in _db[STAGING_COLLECTION].find(
        {}, {"_id": 0, "id": 1},
    )]
    overlap = await _db.qr_scans.count_documents({"id": {"$in": staging_ids}})

    return {
        "total": total,
        "by_platform": by_platform,
        "earliest": (earliest_doc or {}).get("scanned_at"),
        "latest": (latest_doc or {}).get("scanned_at"),
        "would_skip_on_promote": overlap,
    }


# ---------------------------------------------------------------------------
# POST /promote-staging
# ---------------------------------------------------------------------------

@qr_recovery_router.post("/promote-staging")
async def promote_staging(
    user: AuthUser = Depends(require_admin),
) -> Dict[str, Any]:
    """Move every staging row into qr_scans + qr_click_log_immutable,
    skipping any whose `id` already exists. Staging collection is left
    untouched — call /clear-staging to drop it after a successful
    promote."""
    rows = [d async for d in _db[STAGING_COLLECTION].find({}, {"_id": 0})]
    if not rows:
        return {"written": 0, "skipped": 0, "total": 0,
                "message": "staging is empty — nothing to promote"}

    ids = [r["id"] for r in rows]
    existing_in_scans = {
        d["id"] async for d in _db.qr_scans.find(
            {"id": {"$in": ids}}, {"_id": 0, "id": 1},
        )
    }
    existing_in_immut = {
        d["id"] async for d in _db.qr_click_log_immutable.find(
            {"id": {"$in": ids}}, {"_id": 0, "id": 1},
        )
    }
    to_scans = [r for r in rows if r["id"] not in existing_in_scans]
    to_immut = [r for r in rows if r["id"] not in existing_in_immut]

    if to_scans:
        await _db.qr_scans.insert_many(to_scans)
    if to_immut:
        await _db.qr_click_log_immutable.insert_many(to_immut)

    await _audit(user.email, "promote_staging", {
        "total_in_staging": len(rows),
        "written_to_qr_scans": len(to_scans),
        "written_to_immutable": len(to_immut),
        "skipped_qr_scans": len(rows) - len(to_scans),
        "skipped_immutable": len(rows) - len(to_immut),
    })

    return {
        "total": len(rows),
        "written_to_qr_scans": len(to_scans),
        "written_to_immutable": len(to_immut),
        "skipped_qr_scans": len(rows) - len(to_scans),
        "skipped_immutable": len(rows) - len(to_immut),
    }


# ---------------------------------------------------------------------------
# POST /clear-staging
# ---------------------------------------------------------------------------

@qr_recovery_router.post("/clear-staging")
async def clear_staging(
    user: AuthUser = Depends(require_admin),
) -> Dict[str, Any]:
    """Drop every row from the staging collection. Idempotent."""
    res = await _db[STAGING_COLLECTION].delete_many({})
    await _audit(user.email, "clear_staging", {"deleted": res.deleted_count})
    return {"deleted": res.deleted_count}


# ---------------------------------------------------------------------------
# GET /audit
# ---------------------------------------------------------------------------

@qr_recovery_router.get("/audit")
async def get_audit_log(
    limit: int = 50,
    user: AuthUser = Depends(require_admin),
) -> Dict[str, Any]:
    """Append-only audit log for QR recovery actions. Newest first."""
    limit = max(1, min(limit, 500))
    entries: List[Dict[str, Any]] = []
    async for e in _db[AUDIT_COLLECTION].find(
        {}, {"_id": 0},
    ).sort("logged_at", -1).limit(limit):
        entries.append(e)
    return {"entries": entries, "limit": limit}


def register_qr_recovery_routes(app_router, db) -> None:
    """Wire the recovery router into the main API. Called from server.py."""
    _set_db(db)
    app_router.include_router(qr_recovery_router)
