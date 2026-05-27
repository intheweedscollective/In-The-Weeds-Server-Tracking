"""
Regression test for GET /v2/admin/scoring-example.

Locks the contract:
  1. The endpoint runs the canonical engine and returns a breakdown.
  2. Every breakdown line reconciles to total_score (no drift between
     the line items the doc renders and the grand total the engine
     wrote).
  3. Default inputs produce the documented "Top Performer = 123.5" value.
"""

import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

import routes.admin as admin_module  # noqa: E402
from routes.admin import scoring_example  # noqa: E402


def _run(coro_factory):
    async def runner():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        original = admin_module.get_db
        admin_module.get_db = lambda: db
        try:
            await coro_factory(db)
        finally:
            admin_module.get_db = original
            client.close()
    asyncio.run(runner())


def test_breakdown_reconciles_to_total():
    """Sum every breakdown line — must equal total_score."""
    async def body(_db):
        r = await scoring_example()  # default args
        b = r["breakdown"]
        recon = (
            b["weighted_pos_subtotal"]
            + b["metric_bonuses"]["total"]
            + b["customer_voice"]["total"]
            + b["review_tracker"]["capped"]
        )
        assert abs(recon - r["total_score"]) < 0.01, \
            f"reconcile drift: lines sum to {recon}, engine says {r['total_score']}"
    _run(body)


def test_default_inputs_produce_123_50():
    """The doc's canonical Top Performer example: 123.5."""
    async def body(_db):
        r = await scoring_example()
        assert r["total_score"] == 123.5, \
            f"Top-Performer example drifted: got {r['total_score']}, expected 123.5"
    _run(body)


def test_engine_settings_are_canonical():
    """Endpoint must report the canonical 25/25/20/15 + 0.33/20 + 1/2."""
    async def body(_db):
        r = await scoring_example()
        s = r["settings"]
        assert s["weight_ppa"] == 0.25
        assert s["weight_lsc"] == 0.25
        assert s["weight_lbw"] == 0.20
        assert s["weight_glass"] == 0.15
        assert s["rt_points_per_mention"] == 0.33
        assert s["rt_max_points"] == 20.0
        assert s["cv_promoter_points"] == 1.0
        assert s["cv_detractor_points"] == 2
    _run(body)


def test_rt_caps_at_max_points():
    """200 mentions × 0.33 = 66 raw, must cap at rt_max_points (20)."""
    async def body(_db):
        r = await scoring_example(mentions=200)
        assert r["breakdown"]["review_tracker"]["raw"] == 66.0
        assert r["breakdown"]["review_tracker"]["capped"] == 20.0
    _run(body)


def test_pos_scores_cap_at_100_before_weight():
    """A 150% metric must contribute at most weight × 100, never more."""
    async def body(_db):
        r = await scoring_example(
            ppa_pct=150, lsc_pct=150, lbw_pct=150, glass_pct=150,
            promoters=0, detractors=0, mentions=0, nps=0,
        )
        b = r["breakdown"]["weighted_pos_contributions"]
        assert b["ppa"] == 25.0     # 100 × 0.25
        assert b["lsc"] == 25.0     # 100 × 0.25
        assert b["lbw"] == 20.0     # 100 × 0.20
        assert b["glass"] == 15.0   # 100 × 0.15
        assert r["breakdown"]["weighted_pos_subtotal"] == 85.0
    _run(body)


if __name__ == "__main__":
    test_breakdown_reconciles_to_total()
    test_default_inputs_produce_123_50()
    test_engine_settings_are_canonical()
    test_rt_caps_at_max_points()
    test_pos_scores_cap_at_100_before_weight()
    print("All scoring-example endpoint tests PASSED")
