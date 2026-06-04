"""
Regression test for the (name_normalized, quarter, year) uniqueness
contract on `employees_v2`.

Background
----------
Until 2026-06-03 every POS upload / admin import / snapshot finalization
called `db.employees_v2.insert_one(doc)` directly. Two consecutive
imports of the same employee under slightly different spellings (case,
trailing whitespace, etc.) produced two rows, and those duplicates
poured into the Data Reconciliation `legacy_duplicate` queue forever.

Fix:
  1. Compound unique index on (name_normalized, quarter, year) created
     on FastAPI startup in `server.py`.
  2. Every insert site now goes through
     `services.employee_v2_writer.upsert_employee_v2`, which routes the
     write through an `update_one(..., upsert=True)` keyed on
     (name_normalized, quarter, year).

This test exercises both layers:
  • The helper upserts a fresh row, then upserts a second time under a
    different-casing/leading-whitespace name and asserts:
      - only ONE row exists in the bucket,
      - the row's `id` is stable across the two writes,
      - non-zero metrics from the second write flow into the row.
  • A raw `insert_one` of a duplicate row blows up with
    `DuplicateKeyError`, proving the index actually enforces the
    constraint (catches accidental future regressions where someone
    bypasses the helper).
"""

import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

load_dotenv("/app/backend/.env")

# Import the helper under test.
import sys
sys.path.insert(0, "/app/backend")
from services.employee_v2_writer import upsert_employee_v2, normalize_name


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


@pytest.fixture
def fixture_name():
    """Distinctive name guaranteed not to collide with prod data."""
    return f"ZzzIndexFixture_{uuid.uuid4().hex[:8]}"


def test_unique_index_is_present(loop):
    """Backend startup must have created the index. Tested via the
    list_indexes() API rather than introspecting server logs."""
    async def _check():
        idxs = await _db().employees_v2.index_information()
        # Find an index whose key set matches our compound spec.
        match = [
            name for name, info in idxs.items()
            if [t[0] for t in info["key"]] ==
               ["name_normalized", "quarter", "year"]
        ]
        assert match, (
            f"compound (name_normalized, quarter, year) index missing — "
            f"existing indexes: {list(idxs.keys())}"
        )
        # Must be unique.
        for name in match:
            assert idxs[name].get("unique") is True, (
                f"index {name} exists but is not unique: {idxs[name]}"
            )
    loop.run_until_complete(_check())


def test_upsert_helper_collapses_case_variants(loop, fixture_name):
    """Two writes under different-cased / whitespace-padded names
    must converge to a single row with a stable id."""
    db = _db()
    q, y = "Q2", 9099  # poison-pill year so we never collide with prod
    spelling_a = fixture_name
    spelling_b = f"  {fixture_name.upper()}  "  # different case + whitespace

    async def _go():
        try:
            # First write — should INSERT.
            id_a = await upsert_employee_v2(db, {
                "name": spelling_a,
                "quarter": q,
                "year": y,
                "total_score": 50.0,
                "guest_count": 100,
            })
            # Second write under the same normalized name — must
            # update the same row, not create a second one.
            id_b = await upsert_employee_v2(db, {
                "name": spelling_b,
                "quarter": q,
                "year": y,
                "total_score": 80.0,   # newer score wins via $set
                "rt_mentions": 7,      # new metric flows in
            })
            assert id_a == id_b, (
                f"upsert should return the same id; got {id_a!r} vs {id_b!r}"
            )
            cnt = await db.employees_v2.count_documents({
                "name_normalized": normalize_name(spelling_a),
                "quarter": q, "year": y,
            })
            assert cnt == 1, (
                f"two case-variant writes produced {cnt} rows — index/upsert broken"
            )
            row = await db.employees_v2.find_one(
                {"id": id_a}, {"_id": 0},
            )
            assert row["total_score"] == 80.0, (
                f"second write must overwrite total_score via $set; got {row}"
            )
            assert row["rt_mentions"] == 7, (
                f"second write must add new fields via $set; got {row}"
            )
            # name_normalized must be the strip().upper() of the latest name.
            assert row["name_normalized"] == normalize_name(spelling_a)
        finally:
            await db.employees_v2.delete_many({
                "name_normalized": normalize_name(spelling_a),
                "quarter": q, "year": y,
            })
    loop.run_until_complete(_go())


def test_raw_insert_one_of_duplicate_raises_DuplicateKeyError(loop, fixture_name):
    """If anyone bypasses the helper and calls insert_one directly with
    a (name_normalized, quarter, year) tuple that already exists, the
    unique index must reject the write. This is the safety net that
    catches future regressions."""
    db = _db()
    q, y = "Q2", 9099
    nn = normalize_name(fixture_name)

    async def _go():
        try:
            await upsert_employee_v2(db, {
                "name": fixture_name,
                "quarter": q, "year": y,
            })
            # Now try to sneak in a second row by bypassing the helper.
            with pytest.raises(DuplicateKeyError):
                await db.employees_v2.insert_one({
                    "id": str(uuid.uuid4()),
                    "name": fixture_name + " (dup)",
                    "name_normalized": nn,
                    "quarter": q,
                    "year": y,
                })
        finally:
            await db.employees_v2.delete_many({
                "name_normalized": nn, "quarter": q, "year": y,
            })
    loop.run_until_complete(_go())


def test_legacy_duplicate_queue_does_not_resurface_after_upsert_cleanup(loop):
    """End-to-end: after the dedupe + index migration ran, the Data
    Reconciliation queue must report 0 active legacy_duplicate cards
    for any name that exists exactly once per (quarter, year) tuple."""
    import requests
    BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"

    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # We don't assert active=0 (real legacy-typo profiles might still
    # exist for the operator to triage), but no card should now appear
    # twice for the same (name, quarter, year) tuple.
    seen = set()
    for c in d.get("active", []):
        if c.get("kind") != "legacy_duplicate":
            continue
        key = (
            (c.get("employee_name") or "").strip().upper(),
            c.get("raw_inputs", {}).get("quarter"),
            c.get("raw_inputs", {}).get("year"),
        )
        assert key not in seen, (
            f"duplicate legacy card for {key} — dedupe migration missed something"
        )
        seen.add(key)
