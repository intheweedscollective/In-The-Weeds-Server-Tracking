"""
Regression tests for the 3 admin endpoints that used to carry stale
inline CV math:

  • POST /v2/admin/clear-all-detractors
  • GET  /v2/admin/name-matching/preview
  • POST /v2/admin/name-matching/apply

All three must now route every CV/total computation through the
canonical scoring engine. These tests verify the projected/written
CV scores match `calculate_customer_voice_score` (NPS%/10 + +1 per
promoter + -2 per detractor) and never the legacy ±0.5/±1 math.
"""

import asyncio
import os
import sys
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

import routes.admin as admin_module  # noqa: E402
from routes.admin import (  # noqa: E402
    clear_all_detractors,
    preview_name_matching,
    apply_name_matching,
)
from scoring_engine import EmployeeV2, calculate_customer_voice_score  # noqa: E402


SENTINEL_YEAR = 9098


def _run(coro_factory):
    async def runner():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        # Pre-cleanup
        await db.employees_v2.delete_many({"year": SENTINEL_YEAR})
        await db.cv_nps.delete_many({"year": SENTINEL_YEAR})
        await db.quarter_settings.delete_many({"year": SENTINEL_YEAR})
        original = admin_module.get_db
        admin_module.get_db = lambda: db
        try:
            await coro_factory(db)
        finally:
            admin_module.get_db = original
            await db.employees_v2.delete_many({"year": SENTINEL_YEAR})
            await db.cv_nps.delete_many({"year": SENTINEL_YEAR})
            await db.quarter_settings.delete_many({"year": SENTINEL_YEAR})
            client.close()
    asyncio.run(runner())


def _canonical_cv(nps, promoters, detractors):
    """Replay the engine to get the canonical CV score for a given input."""
    e = EmployeeV2(
        name="probe", nps_score=nps,
        cv_promoters=promoters, cv_detractors=detractors,
    )
    calculate_customer_voice_score(e)
    return e.cv_score


def test_preview_uses_canonical_formula():
    """The preview's projected_cv_score must match calculate_customer_voice_score."""
    async def body(db):
        await db.quarter_settings.insert_one({
            "id": str(uuid.uuid4()),
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "weight_ppa": 0.25, "weight_lsc": 0.25,
            "weight_lbw": 0.20, "weight_glass": 0.15,
            "rt_points_per_mention": 0.33, "rt_max_points": 20,
            "cv_promoter_points": 1, "cv_detractor_points": 2,
            "bonus_rate": 0.25, "bonus_cap": 5,
            "benchmark_ppa": 55, "benchmark_lbw": 8,
            "benchmark_glass": 1.35, "benchmark_lsc": 100,
            "locked": False,
        })
        await db.employees_v2.insert_one({
            "id": str(uuid.uuid4()),
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "name": "Test Server", "display_name": "Test Server",
            "aliases": [],
            "nps_score": 0, "cv_promoters": 0, "cv_detractors": 0,
            "cv_score": 0,
        })
        await db.cv_nps.insert_one({
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "employee_name": "Test Server",
            "nps_score": 80, "promoters": 15, "detractors": 2,
        })

        result = await preview_name_matching(quarter="Q2", year=SENTINEL_YEAR)
        row = result["mapping"][0]
        # NPS 80 / 10 + 15*1 - 2*2 = 8 + 15 - 4 = 19
        expected = _canonical_cv(80, 15, 2)
        assert expected == 19.0, f"engine produced {expected}, expected 19.0"
        assert row["projected_cv_score"] == 19.0, \
            f"preview projected {row['projected_cv_score']} but engine says 19.0"
    _run(body)


def test_apply_writes_canonical_cv_score():
    """apply_name_matching must persist the engine's cv_score, never the legacy formula."""
    async def body(db):
        await db.quarter_settings.insert_one({
            "id": str(uuid.uuid4()),
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "weight_ppa": 0.25, "weight_lsc": 0.25,
            "weight_lbw": 0.20, "weight_glass": 0.15,
            "rt_points_per_mention": 0.33, "rt_max_points": 20,
            "cv_promoter_points": 1, "cv_detractor_points": 2,
            "bonus_rate": 0.25, "bonus_cap": 5,
            "benchmark_ppa": 55, "benchmark_lbw": 8,
            "benchmark_glass": 1.35, "benchmark_lsc": 100,
            "locked": False,
        })
        emp_id = str(uuid.uuid4())
        await db.employees_v2.insert_one({
            "id": emp_id,
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "name": "Diane Probe", "display_name": "Diane Probe",
            "aliases": [],
            "nps_score": 0, "cv_promoters": 0, "cv_detractors": 0,
            "guests": 100, "net_sales": 5500, "lsc_count": 1,
            "lbw": 800, "glassware_sales": 135,
        })
        await db.cv_nps.insert_one({
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "employee_name": "Diane Probe",
            "nps_score": 80, "promoters": 15, "detractors": 2,
        })

        result = await apply_name_matching(quarter="Q2", year=SENTINEL_YEAR)
        assert result["employees_updated"] == 1

        row = await db.employees_v2.find_one(
            {"id": emp_id}, {"_id": 0},
        )
        # Engine: 8 + 15 - 4 = 19.0  (legacy was 7.5 - 2 = 5.5)
        assert row["cv_score"] == 19.0, \
            f"apply wrote cv_score={row['cv_score']}, expected 19.0 (legacy: 5.5)"
        # The legacy stale-math contamination would have been ≤ 7.5 here.
        assert row["cv_score"] > 7.5, "looks like legacy formula leaked through"
    _run(body)


def test_clear_detractors_rescores_through_engine():
    """clear_all_detractors must not use cv = promoters × 0.5."""
    async def body(db):
        await db.quarter_settings.insert_one({
            "id": str(uuid.uuid4()),
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "weight_ppa": 0.25, "weight_lsc": 0.25,
            "weight_lbw": 0.20, "weight_glass": 0.15,
            "rt_points_per_mention": 0.33, "rt_max_points": 20,
            "cv_promoter_points": 1, "cv_detractor_points": 2,
            "bonus_rate": 0.25, "bonus_cap": 5,
            "benchmark_ppa": 55, "benchmark_lbw": 8,
            "benchmark_glass": 1.35, "benchmark_lsc": 100,
            "locked": False,
        })
        emp_id = str(uuid.uuid4())
        await db.employees_v2.insert_one({
            "id": emp_id,
            "quarter": "Q2", "year": SENTINEL_YEAR,
            "name": "Probe Two", "display_name": "Probe Two",
            "nps_score": 90, "cv_promoters": 10, "cv_detractors": 3,
            "cv_score": 99, "total_score": 50,
            "guests": 100, "net_sales": 5500, "lsc_count": 1,
        })

        await clear_all_detractors(year=SENTINEL_YEAR, quarter="Q2")
        row = await db.employees_v2.find_one({"id": emp_id}, {"_id": 0})
        # Detractors zeroed, engine: 90/10 + 10*1 - 0 = 19.0
        # Legacy formula would have produced: 10 * 0.5 = 5.0
        assert row["cv_detractors"] == 0
        assert row["cv_score"] == 19.0, \
            f"clear-detractors wrote cv_score={row['cv_score']}, expected 19.0"
        assert row["cv_score"] != 5.0, "legacy ±0.5 formula leaked through"
    _run(body)


if __name__ == "__main__":
    test_preview_uses_canonical_formula()
    test_apply_writes_canonical_cv_score()
    test_clear_detractors_rescores_through_engine()
    print("All admin-CV-math regression tests PASSED")
