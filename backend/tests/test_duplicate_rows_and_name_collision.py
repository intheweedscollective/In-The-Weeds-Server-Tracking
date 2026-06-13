"""
Regression tests for two new reconciliation card types
======================================================

Operator-reported (2026-06-12): Kahi Ramos appeared three times on
the PPA slide but the Reconciliation portal didn't surface ANY card
for her. Root cause: existing card types only handle v2-vs-canonical
gaps. Two new patterns were unguarded:

  1. The active snapshot's `rows[]` array held three entries with
     the same `employee_id` for Kahi — every snapshot-driven report
     rendered the duplicates faithfully.
  2. Two separate active canonicals existed: "Kahi Ramos" and
     "Kahiaulani Ramos". The operator said earlier "Kahi is the
     nickname for Kahiaulani" but no card flagged the situation.

These tests pin both card types:
  * `duplicate_snapshot_rows`
      - Detects when the active snapshot has ≥ 2 rows for the same
        employee_id.
      - `dedupe_snapshot_rows` keeps the first occurrence and removes
        the rest. Guests/sales are NOT summed (avoid inflation).
  * `canonical_name_collision`
      - Detects ≥ 2 active canonicals with the EXACT same name OR
        with a nickname-prefix pair on the same last name.
      - `merge_canonical_into` picks a keeper, marks the others
        merged, folds their aliases + legacy_ids into the keeper.
"""

import asyncio
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BASE  = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

from conftest import ADMIN_TOKEN
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


def _queue():
    r = requests.get(
        f"{BASE}/api/v2/admin/reconciliation/queue",
        headers=ADMIN, timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ===========================================================================
# duplicate_snapshot_rows
# ===========================================================================

@pytest.fixture
def duplicate_rows_snapshot(loop):
    """Make the active snapshot have the same employee_id three times
    in rows[]. Yields (snapshot_id, canonical_id)."""
    db = _db()
    snap_id = f"dup-test-{uuid.uuid4().hex[:8]}"
    canon_id = f"dup-canon-{uuid.uuid4().hex[:6]}"

    async def _seed():
        prior = await db.snapshot_workflow.find_one(
            {"is_current": True}, {"_id": 0, "id": 1},
        )
        if prior:
            await db.snapshot_workflow.update_one(
                {"id": prior["id"]}, {"$set": {"is_current": False}},
            )
        await db.employees.insert_one({
            "id": canon_id, "name": "Dup Test Server",
            "status": "active", "aliases": [], "legacy_ids": [],
        })
        # 5 rows total: 3 for canon_id, 2 unrelated.
        await db.snapshot_workflow.insert_one({
            "id": snap_id, "name": "Dup Test Snap",
            "quarter": "QD", "year": 2999,
            "status": "completed", "is_current": True,
            "rows": [
                {"employee_id": canon_id,
                 "frozen_display_name": "Dup Test Server",
                 "frozen_score": 80, "frozen_metrics": {"ppa": 50}},
                {"employee_id": "other-1",
                 "frozen_display_name": "Other A",
                 "frozen_score": 70, "frozen_metrics": {"ppa": 45}},
                {"employee_id": canon_id,  # ← dup
                 "frozen_display_name": "Dup Test Server",
                 "frozen_score": 80, "frozen_metrics": {"ppa": 50}},
                {"employee_id": "other-2",
                 "frozen_display_name": "Other B",
                 "frozen_score": 60, "frozen_metrics": {"ppa": 40}},
                {"employee_id": canon_id,  # ← dup
                 "frozen_display_name": "Dup Test Server",
                 "frozen_score": 80, "frozen_metrics": {"ppa": 50}},
            ],
            "employees": [], "deleted_names": [],
        })
        return prior

    prior = loop.run_until_complete(_seed())
    yield snap_id, canon_id

    async def _wipe():
        await db.snapshot_workflow.delete_one({"id": snap_id})
        await db.employees.delete_one({"id": canon_id})
        await db.reconciliation_audit.delete_many({"employee_id": canon_id})
        await db.reconciliation_resolved.delete_many({"employee_id": canon_id})
        if prior:
            await db.snapshot_workflow.update_one(
                {"id": prior["id"]}, {"$set": {"is_current": True}},
            )
    loop.run_until_complete(_wipe())


def test_duplicate_rows_surfaces_with_count_and_indices(duplicate_rows_snapshot):
    snap_id, canon_id = duplicate_rows_snapshot
    card = next(
        (c for c in _queue().get("active", [])
         if c["kind"] == "duplicate_snapshot_rows"
            and c["employee_id"] == canon_id),
        None,
    )
    assert card, "duplicate_snapshot_rows card missing"
    assert card["raw_inputs"]["duplicate_count"] == 3
    assert card["raw_inputs"]["duplicate_indices"] == [0, 2, 4]


def test_dedupe_keeps_first_drops_rest(loop, duplicate_rows_snapshot):
    snap_id, canon_id = duplicate_rows_snapshot
    card = next(
        c for c in _queue()["active"]
        if c["kind"] == "duplicate_snapshot_rows"
           and c["employee_id"] == canon_id
    )
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "dedupe_snapshot_rows",
              "reason": "regression test"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["duplicate_copies_removed"] == 2
    assert body["rows_after"] == 3            # 5 - 2 duplicates removed

    async def _check():
        snap = await _db().snapshot_workflow.find_one(
            {"id": snap_id}, {"_id": 0, "rows": 1},
        )
        rows = snap["rows"]
        dup_rows = [r for r in rows if r["employee_id"] == canon_id]
        assert len(dup_rows) == 1, (
            f"expected exactly 1 row for canon, got {len(dup_rows)}"
        )
        # First occurrence kept — its display name is at index 0.
        assert rows[0]["employee_id"] == canon_id
    loop.run_until_complete(_check())


def test_dedupe_card_disappears_after_resolution(duplicate_rows_snapshot):
    _, canon_id = duplicate_rows_snapshot
    card = next(
        c for c in _queue()["active"]
        if c["kind"] == "duplicate_snapshot_rows"
           and c["employee_id"] == canon_id
    )
    requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "dedupe_snapshot_rows"},
        timeout=15,
    ).raise_for_status()
    still_there = next(
        (c for c in _queue().get("active", [])
         if c["kind"] == "duplicate_snapshot_rows"
            and c["employee_id"] == canon_id),
        None,
    )
    assert still_there is None


@pytest.fixture
def post_merge_legacy_id_duplicates(loop):
    """Operator-reported regression (2026-06-12): after a
    merge_canonical_into action, the snapshot still pointed at the
    OLD legacy ids, and the dedupe card missed them because they
    looked like distinct employee_ids. The detection must follow
    legacy_ids[]/merged_into to resolve duplicates by canonical.

    Setup:
      - Keeper canonical 'K' with legacy_ids=[L1] (a merged absorbed id)
      - A merged canonical 'M' that has merged_into=K
      - Snapshot rows[] carries three rows: one with K's id, one with
        L1 (legacy), one with M's id (merged-pre-keeper).
    All three should be flagged as duplicates of K.
    """
    db = _db()
    snap_id = f"post-merge-{uuid.uuid4().hex[:8]}"
    keeper = f"keeper-{uuid.uuid4().hex[:6]}"
    legacy = f"legacy-{uuid.uuid4().hex[:6]}"
    merged = f"merged-{uuid.uuid4().hex[:6]}"

    async def _seed():
        prior = await db.snapshot_workflow.find_one(
            {"is_current": True}, {"_id": 0, "id": 1},
        )
        if prior:
            await db.snapshot_workflow.update_one(
                {"id": prior["id"]}, {"$set": {"is_current": False}},
            )
        await db.employees.insert_many([
            {"id": keeper, "name": "Kahi Keeper",
             "status": "active", "aliases": [], "legacy_ids": [legacy]},
            {"id": merged, "name": "Kahi Old", "status": "merged",
             "merged_into": keeper, "aliases": [], "legacy_ids": []},
        ])
        await db.snapshot_workflow.insert_one({
            "id": snap_id, "name": "Post-merge dup test",
            "quarter": "QM", "year": 2999,
            "status": "completed", "is_current": True,
            "rows": [
                {"employee_id": keeper,
                 "frozen_display_name": "Kahi Keeper",
                 "frozen_score": 80,
                 "frozen_metrics": {"ppa": 50}},
                {"employee_id": legacy,
                 "frozen_display_name": "Kahi Keeper",
                 "frozen_score": 80,
                 "frozen_metrics": {"ppa": 50}},
                {"employee_id": merged,
                 "frozen_display_name": "Kahi Old",
                 "frozen_score": 80,
                 "frozen_metrics": {"ppa": 50}},
                {"employee_id": "unrelated",
                 "frozen_display_name": "Someone Else",
                 "frozen_score": 70, "frozen_metrics": {"ppa": 45}},
            ],
            "employees": [], "deleted_names": [],
        })
        return prior

    prior = loop.run_until_complete(_seed())
    yield snap_id, keeper, legacy, merged

    async def _wipe():
        await db.snapshot_workflow.delete_one({"id": snap_id})
        await db.employees.delete_many(
            {"id": {"$in": [keeper, merged]}}
        )
        await db.reconciliation_audit.delete_many({"employee_id": keeper})
        await db.reconciliation_resolved.delete_many({"employee_id": keeper})
        if prior:
            await db.snapshot_workflow.update_one(
                {"id": prior["id"]}, {"$set": {"is_current": True}},
            )
    loop.run_until_complete(_wipe())


def test_duplicate_detection_follows_legacy_ids_and_merged_into(
    post_merge_legacy_id_duplicates,
):
    """Three rows pointing at three different ids (keeper, its legacy,
    a merged canonical) must all resolve to the same canonical card."""
    snap_id, keeper, legacy, merged = post_merge_legacy_id_duplicates
    card = next(
        (c for c in _queue().get("active", [])
         if c["kind"] == "duplicate_snapshot_rows"
            and c["raw_inputs"]["resolved_canonical_id"] == keeper),
        None,
    )
    assert card, (
        "duplicate_snapshot_rows card missing — detection did not follow "
        "legacy_ids / merged_into to resolve to keeper"
    )
    assert card["raw_inputs"]["duplicate_count"] == 3
    underlying = set(card["raw_inputs"]["underlying_employee_ids"])
    assert underlying == {keeper, legacy, merged}
    assert card["raw_inputs"]["duplicate_indices"] == [0, 1, 2]


def test_dedupe_removes_legacy_id_dupes(loop, post_merge_legacy_id_duplicates):
    """Dedupe must remove the legacy/merged rows and keep only the
    first occurrence (the keeper's row at index 0)."""
    snap_id, keeper, legacy, merged = post_merge_legacy_id_duplicates
    card = next(
        c for c in _queue()["active"]
        if c["kind"] == "duplicate_snapshot_rows"
           and c["raw_inputs"]["resolved_canonical_id"] == keeper
    )
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "dedupe_snapshot_rows",
              "reason": "post-merge regression"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["duplicate_copies_removed"] == 2

    async def _check():
        snap = await _db().snapshot_workflow.find_one(
            {"id": snap_id}, {"_id": 0, "rows": 1},
        )
        rows = snap["rows"]
        # Now should be 2 rows total: keeper + "unrelated".
        assert len(rows) == 2
        # First row stays the keeper.
        assert rows[0]["employee_id"] == keeper
        # No legacy or merged rows remain.
        eids = {r["employee_id"] for r in rows}
        assert legacy not in eids
        assert merged not in eids
    loop.run_until_complete(_check())


# ===========================================================================
# canonical_name_collision
# ===========================================================================

@pytest.fixture
def exact_name_collision(loop):
    """Two active canonicals with the same exact name."""
    db = _db()
    name = f"Sam Test {uuid.uuid4().hex[:4]}"
    a = f"exact-a-{uuid.uuid4().hex[:6]}"
    b = f"exact-b-{uuid.uuid4().hex[:6]}"

    async def _seed():
        await db.employees.insert_many([
            {"id": a, "name": name, "status": "active",
             "aliases": ["Sammie"], "legacy_ids": ["legacy-old-a"]},
            {"id": b, "name": name, "status": "active",
             "aliases": ["Samuel"], "legacy_ids": []},
        ])
    loop.run_until_complete(_seed())
    yield a, b, name

    async def _wipe():
        await db.employees.delete_many({"id": {"$in": [a, b]}})
        await db.reconciliation_audit.delete_many({"employee_id": {"$in": [a, b]}})
    loop.run_until_complete(_wipe())


@pytest.fixture
def nickname_prefix_collision(loop):
    """Kahi-style: same last name, one first name is prefix of the other."""
    db = _db()
    last = f"Ramos-{uuid.uuid4().hex[:4]}"
    short = f"Kahi {last}"
    long_ = f"Kahiaulani {last}"
    short_id = f"short-{uuid.uuid4().hex[:6]}"
    long_id  = f"long-{uuid.uuid4().hex[:6]}"

    async def _seed():
        await db.employees.insert_many([
            {"id": short_id, "name": short, "status": "active",
             "aliases": [], "legacy_ids": []},
            {"id": long_id, "name": long_, "status": "active",
             "aliases": [], "legacy_ids": []},
        ])
    loop.run_until_complete(_seed())
    yield short_id, long_id, short, long_

    async def _wipe():
        await db.employees.delete_many({"id": {"$in": [short_id, long_id]}})
        await db.reconciliation_audit.delete_many(
            {"employee_id": {"$in": [short_id, long_id]}}
        )
    loop.run_until_complete(_wipe())


def test_exact_name_collision_surfaces(exact_name_collision):
    a, b, name = exact_name_collision
    card = next(
        (c for c in _queue().get("active", [])
         if c["kind"] == "canonical_name_collision"
            and (c.get("raw_inputs") or {}).get("match_type") == "exact"
            and c["stored_value"] == name),
        None,
    )
    assert card, "exact-name canonical collision card missing"
    ids = {c["canonical_id"] for c in card["raw_inputs"]["claimants"]}
    assert {a, b}.issubset(ids)


def test_nickname_prefix_collision_surfaces(nickname_prefix_collision):
    short_id, long_id, _short, _long = nickname_prefix_collision
    card = next(
        (c for c in _queue().get("active", [])
         if c["kind"] == "canonical_name_collision"
            and (c.get("raw_inputs") or {}).get("match_type") == "nickname_prefix"
            and short_id in {x["canonical_id"]
                             for x in c["raw_inputs"]["claimants"]}),
        None,
    )
    assert card, "nickname-prefix canonical collision card missing"
    ids = {c["canonical_id"] for c in card["raw_inputs"]["claimants"]}
    assert {short_id, long_id}.issubset(ids)


def test_merge_canonical_folds_aliases_and_legacy_ids(loop, exact_name_collision):
    """Merge B into A. A keeps its name and gains:
       - B's aliases (folded)
       - B's id appended to legacy_ids[] (so v2 rows under B still resolve)
       And B becomes status=merged."""
    a, b, name = exact_name_collision
    card = next(
        c for c in _queue()["active"]
        if c["kind"] == "canonical_name_collision"
           and c["stored_value"] == name
    )
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "merge_canonical_into",
              "target_canonical_id": a,
              "reason": "regression test merge"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["keeper_id"] == a
    assert b in body["merged_canonical_ids"]

    async def _check():
        db = _db()
        keeper = await db.employees.find_one({"id": a}, {"_id": 0})
        loser  = await db.employees.find_one({"id": b}, {"_id": 0})
        # B's alias folded into A.
        assert "Samuel" in (keeper.get("aliases") or [])
        # B's own id and pre-existing legacy_ids stay in keeper's legacy_ids.
        assert b in (keeper.get("legacy_ids") or [])
        # A's pre-existing legacy_id kept.
        assert "legacy-old-a" in (keeper.get("legacy_ids") or [])
        # B is now merged.
        assert loser["status"] == "merged"
        assert loser.get("merged_into") == a
    loop.run_until_complete(_check())


def test_merge_canonical_requires_target(loop, exact_name_collision):
    a, b, name = exact_name_collision
    card = next(
        c for c in _queue()["active"]
        if c["kind"] == "canonical_name_collision"
           and c["stored_value"] == name
    )
    r = requests.post(
        f"{BASE}/api/v2/admin/reconciliation/resolve",
        headers=ADMIN,
        json={"conflict_id": card["conflict_id"],
              "action": "merge_canonical_into"},
        timeout=15,
    )
    assert r.status_code == 400
    assert "target_canonical_id" in r.text.lower()
