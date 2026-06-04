"""
Single source of truth for writes into `employees_v2`.

Every place in the codebase that used to call
`db.employees_v2.insert_one(doc)` now calls
`upsert_employee_v2(db, doc)` instead.

Why
---
`employees_v2` rows are uniquely identified by the tuple
`(name_normalized, quarter, year)` where
`name_normalized = name.strip().upper()`. The compound unique index
created in `server.py` startup enforces this at the storage layer.

A naive `insert_one` would either succeed (creating a duplicate row
under a slightly different spelling, which is what kept feeding the
Data Reconciliation "legacy_duplicate" queue) or, post-index, raise
`DuplicateKeyError` and crash the upload. The upsert pattern below:

* Computes `name_normalized` from the doc's `name`.
* Uses `$setOnInsert` for fields that must NOT clobber an existing
  row (`id`, `created_at`, `name_normalized`).
* Uses `$set` for everything else (the new POS / snapshot values
  flow into the existing row's metrics).
* Returns the stable `id` of the resulting row so callers can
  continue using the existing-row id when an upsert resolved to an
  existing key.

Callers that don't provide name/quarter/year fall back to a plain
insert so the helper is fully backwards-compatible.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


def normalize_name(name: Optional[str]) -> str:
    """The exact transform used by the unique index. Keep this and
    the create_index call in server.startup_event in lock-step."""
    return (name or "").strip().upper()


async def upsert_employee_v2(
    db: AsyncIOMotorDatabase, doc: Dict[str, Any]
) -> str:
    """Idempotent write into employees_v2 keyed by
    (name_normalized, quarter, year). Returns the stable id of the
    resulting document (existing one on update, newly minted on insert)."""
    raw_name = doc.get("name")
    name_norm = normalize_name(raw_name)
    quarter = doc.get("quarter")
    year = doc.get("year")
    now = datetime.now(timezone.utc).isoformat()

    # Fall-back insert path: caller didn't populate name/quarter/year,
    # so we can't dedupe. Tag the doc with name_normalized for the
    # future and use a regular insert.
    if not name_norm or not quarter or not year:
        if "id" not in doc:
            doc["id"] = str(uuid.uuid4())
        doc.setdefault("created_at", now)
        doc["updated_at"] = now
        doc["name_normalized"] = name_norm
        await db.employees_v2.insert_one(doc)
        return doc["id"]

    candidate_id = doc.get("id") or str(uuid.uuid4())
    # $setOnInsert: identity fields that must never overwrite an existing row.
    set_on_insert = {
        "id": candidate_id,
        "name_normalized": name_norm,
        "created_at": doc.get("created_at") or now,
        # Lock the filter keys on insert too — Mongo applies $setOnInsert
        # only when actually upserting a brand new doc.
        "quarter": quarter,
        "year": year,
    }
    # $set: everything else, including metrics from the new POS feed.
    set_fields = {
        k: v for k, v in doc.items()
        if k not in ("_id", "id", "created_at", "name_normalized",
                     "quarter", "year")
    }
    set_fields["updated_at"] = now

    res = await db.employees_v2.update_one(
        {"name_normalized": name_norm, "quarter": quarter, "year": year},
        {"$setOnInsert": set_on_insert, "$set": set_fields},
        upsert=True,
    )

    if res.upserted_id is not None:
        return candidate_id

    existing = await db.employees_v2.find_one(
        {"name_normalized": name_norm, "quarter": quarter, "year": year},
        {"_id": 0, "id": 1},
    )
    return (existing or {}).get("id") or candidate_id


async def upsert_employees_v2_bulk(
    db: AsyncIOMotorDatabase, docs: list
) -> list:
    """Convenience wrapper over `upsert_employee_v2` for the snapshot
    finalization paths that used to call `insert_many`. Returns the
    list of resulting ids in input order."""
    ids = []
    for d in docs:
        ids.append(await upsert_employee_v2(db, d))
    return ids
