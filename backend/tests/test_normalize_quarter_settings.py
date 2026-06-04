"""
Regression test for the canonical quarter-settings normalizer.

Covers:
  1. Dry-run reports diffs without mutating the DB.
  2. apply=true rewrites engine constants to canonical values.
  3. Benchmarks are NOT touched unless normalize_benchmarks=true.
  4. Locked quarters are skipped unless include_locked=true.
  5. lock_after=true sets locked=True on touched quarters.
"""

import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from routes.admin import (  # noqa: E402
    CANONICAL_ENGINE_CONSTANTS,
    CANONICAL_BENCHMARKS,
    normalize_quarter_settings,
)
import routes.admin as admin_module  # noqa: E402


def _make_test_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"test_normalize_{uuid.uuid4().hex[:8]}"
    return client, client[db_name], db_name


def _seed(year, quarter, **overrides):
    doc = {
        "id": str(uuid.uuid4()),
        "year": year,
        "quarter": quarter,
        "weight_ppa": 0.25,
        "weight_lsc": 0.25,
        "weight_lbw": 0.15,
        "weight_glass": 0.10,
        "rt_points_per_mention": 0.5,
        "rt_max_points": 15.0,
        "benchmark_ppa": 55.0,
        "benchmark_lbw": 8.0,
        "benchmark_glass": 1.25,
        "benchmark_lsc": 100.0,
        "bonus_rate": 0.2,
        "bonus_cap": 5.0,
        "locked": False,
    }
    doc.update(overrides)
    return doc


SENTINEL_YEAR = 9099  # outside any real quarter range; used + cleaned up


def _run(coro_factory):
    """Use the real DB, monkey-patch get_db to return a filtered view, run."""
    async def runner():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        # Hard pre-cleanup so test artifacts from a crashed prior run don't pollute.
        await db.quarter_settings.delete_many({"year": SENTINEL_YEAR})
        original_get_db = admin_module.get_db
        admin_module.get_db = lambda: db
        try:
            await coro_factory(db)
        finally:
            admin_module.get_db = original_get_db
            await db.quarter_settings.delete_many({"year": SENTINEL_YEAR})
            client.close()
    asyncio.run(runner())


def test_dry_run_does_not_mutate():
    async def body(db):
        await db.quarter_settings.insert_one(_seed(SENTINEL_YEAR, "Q4"))
        result = await normalize_quarter_settings(apply=False)
        assert result["dry_run"] is True
        # Find OUR sentinel row in the report (others may exist in DB)
        my = [r for r in result["report"] if r["year"] == SENTINEL_YEAR and r["quarter"] == "Q4"]
        assert len(my) == 1 and my[0]["needs_change"] is True
        raw = await db.quarter_settings.find_one({"year": SENTINEL_YEAR, "quarter": "Q4"})
        assert raw["weight_lbw"] == 0.15  # unchanged
    _run(body)


def test_apply_rewrites_engine_constants():
    async def body(db):
        await db.quarter_settings.insert_one(_seed(SENTINEL_YEAR, "Q1"))
        await normalize_quarter_settings(apply=True)
        raw = await db.quarter_settings.find_one({"year": SENTINEL_YEAR, "quarter": "Q1"})
        for key, val in CANONICAL_ENGINE_CONSTANTS.items():
            assert abs(raw[key] - val) < 1e-6, f"{key}: {raw[key]} != {val}"
        # Benchmarks NOT touched
        assert raw["benchmark_glass"] == 1.25
    _run(body)


def test_benchmarks_only_when_flag():
    async def body(db):
        await db.quarter_settings.insert_one(_seed(SENTINEL_YEAR, "Q2"))
        await normalize_quarter_settings(apply=True, normalize_benchmarks=True)
        raw = await db.quarter_settings.find_one({"year": SENTINEL_YEAR, "quarter": "Q2"})
        for key, val in CANONICAL_BENCHMARKS.items():
            assert abs(raw[key] - val) < 1e-6
    _run(body)


def test_locked_quarter_skipped_then_forced():
    async def body(db):
        await db.quarter_settings.insert_one(_seed(SENTINEL_YEAR, "Q4", locked=True))
        r1 = await normalize_quarter_settings(apply=True)
        my1 = [r for r in r1["report"] if r["year"] == SENTINEL_YEAR][0]
        assert my1["applied"] is False
        assert "locked" in (my1["skipped_reason"] or "")
        r2 = await normalize_quarter_settings(apply=True, include_locked=True)
        my2 = [r for r in r2["report"] if r["year"] == SENTINEL_YEAR][0]
        assert my2["applied"] is True
    _run(body)


def test_lock_after_sets_locked_true():
    async def body(db):
        await db.quarter_settings.insert_one(_seed(SENTINEL_YEAR, "Q3"))
        await normalize_quarter_settings(apply=True, lock_after=True)
        raw = await db.quarter_settings.find_one({"year": SENTINEL_YEAR, "quarter": "Q3"})
        assert raw["locked"] is True
        assert "locked_at" in raw
    _run(body)


if __name__ == "__main__":
    test_dry_run_does_not_mutate()
    test_apply_rewrites_engine_constants()
    test_benchmarks_only_when_flag()
    test_locked_quarter_skipped_then_forced()
    test_lock_after_sets_locked_true()
    print("All normalize-quarter-settings tests PASSED")
