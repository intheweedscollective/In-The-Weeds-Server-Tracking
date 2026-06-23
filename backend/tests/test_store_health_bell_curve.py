"""
Regression: Store Health Index — Upsell as bell-curve PPA+LBW+Glass
(equal thirds) vs concept averages, and Guest Experience flipped to
70% RT + 30% CV (operator request 2026-06-11).

These tests pin the math against the user-stated bell-curve shape:
  x ≤ low         →   0..60
  low < x ≤ avg   →   60..80
  avg < x ≤ high  →   80..100
  x > high        →   100  (cap — top-end stores can't go higher)
"""

import asyncio
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def loop():
    L = asyncio.new_event_loop()
    yield L
    L.close()


@pytest.fixture
def synthetic_quarter(loop):
    """Insert 3 employees in a synthetic quarter with controlled PPA /
    LBW / Glass numbers so we can assert the bell curve precisely.

    Three employees with identical scoring inputs except each lands
    cleanly on a known anchor: one at concept-low, one at concept-avg,
    one at concept-high. Aggregated avg should be exactly at concept-avg.
    """
    q, y = "QX", 2999
    cids = [f"sh-bell-{uuid.uuid4().hex[:6]}" for _ in range(3)]

    async def _seed():
        db = _db()
        # PPA: low 35.40, avg 45.71, high 55.72 → mean of three = 45.61
        # LBW: low 6.40,  avg 8.00,  high 9.60  → mean = 8.00
        # Glass: low 1.08, avg 1.35, high 1.62  → mean = 1.35
        rows = [
            {"id": cids[0], "name": f"Low {cids[0][-4:]}", "name_normalized": f"low {cids[0]}",
             "quarter": q, "year": y, "status": "active",
             "ppa": 35.40, "lbw_per_guest": 6.40, "glassware_per_guest": 1.08,
             "score_ppa": 70, "score_lsc": 70,
             "guests": 1000, "lsc_count": 10,
             "nps_score": 50, "rt_mentions": 5},
            {"id": cids[1], "name": f"Avg {cids[1][-4:]}", "name_normalized": f"avg {cids[1]}",
             "quarter": q, "year": y, "status": "active",
             "ppa": 45.71, "lbw_per_guest": 8.00, "glassware_per_guest": 1.35,
             "score_ppa": 85, "score_lsc": 85,
             "guests": 1000, "lsc_count": 10,
             "nps_score": 60, "rt_mentions": 15},
            {"id": cids[2], "name": f"Hi {cids[2][-4:]}", "name_normalized": f"hi {cids[2]}",
             "quarter": q, "year": y, "status": "active",
             "ppa": 55.72, "lbw_per_guest": 9.60, "glassware_per_guest": 1.62,
             "score_ppa": 100, "score_lsc": 100,
             "guests": 1000, "lsc_count": 10,
             "nps_score": 80, "rt_mentions": 30},
        ]
        await db.employees_v2.insert_many(rows)
    loop.run_until_complete(_seed())
    yield q, y

    async def _wipe():
        await _db().employees_v2.delete_many({"id": {"$in": cids}})
    loop.run_until_complete(_wipe())


def _fetch(q, y):
    r = requests.get(
        f"{BASE}/api/v2/insights/store-health",
        params={"quarter": q, "year": y},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_upsell_bell_curve_at_concept_average(synthetic_quarter):
    """3 employees evenly spaced (low / avg / high) → store mean lands at
    concept avg on all three legs → each leg scores ~80 → upsell ~80."""
    q, y = synthetic_quarter
    d = _fetch(q, y)
    up = d["categories"]["upsell_performance"]
    legs = up["breakdown"]
    # PPA store mean = 45.61 ≈ 45.71 (avg). Score should be ~80.
    assert 78 <= legs["ppa"]["score"]   <= 82, legs["ppa"]
    assert 78 <= legs["lbw"]["score"]   <= 82, legs["lbw"]
    assert 78 <= legs["glass"]["score"] <= 82, legs["glass"]
    # Equal-thirds aggregate.
    assert 78 <= up["score"] <= 82


def test_upsell_caps_at_high_end_no_infinite_bonus(loop):
    """A store far above the concept high gets exactly 100 — no
    overflow above 100."""
    q, y = "QY", 2999
    cid = f"sh-cap-{uuid.uuid4().hex[:6]}"
    db = _db()
    async def _seed():
        await db.employees_v2.insert_one({
            "id": cid, "name": "Cap Test", "name_normalized": "cap test",
            "quarter": q, "year": y, "status": "active",
            "ppa": 99.99, "lbw_per_guest": 50.0, "glassware_per_guest": 10.0,
            "score_ppa": 100, "score_lsc": 100,
            "guests": 1000, "lsc_count": 10,
            "nps_score": 100, "rt_mentions": 100,
        })
    loop.run_until_complete(_seed())
    try:
        d = _fetch(q, y)
        legs = d["categories"]["upsell_performance"]["breakdown"]
        assert legs["ppa"]["score"]   == 100.0
        assert legs["lbw"]["score"]   == 100.0
        assert legs["glass"]["score"] == 100.0
        assert d["categories"]["upsell_performance"]["score"] == 100.0
    finally:
        async def _wipe():
            await db.employees_v2.delete_many({"id": cid})
        loop.run_until_complete(_wipe())


def test_guest_experience_weights_flipped_to_rt_70_cv_30(loop):
    """Weights flipped: RT 70% + CV 30%. We construct a store with
    high RT (100% normalized) and zero NPS (50% normalized after the
    -100..100 → 0..100 shift). Expected score = 0.7*100 + 0.3*50 = 85.
    Under the OLD weights it would have been 65."""
    q, y = "QZ", 2999
    cid = f"sh-flip-{uuid.uuid4().hex[:6]}"
    db = _db()
    async def _seed():
        await db.employees_v2.insert_one({
            "id": cid, "name": "Flip Test", "name_normalized": "flip test",
            "quarter": q, "year": y, "status": "active",
            "ppa": 45.71, "lbw_per_guest": 8.0, "glassware_per_guest": 1.35,
            "score_ppa": 85, "score_lsc": 85,
            "guests": 1000, "lsc_count": 10,
            "nps_score": 0,         # → 50 normalized
            "rt_mentions": 30,       # → 100 normalized (cap)
        })
    loop.run_until_complete(_seed())
    try:
        d = _fetch(q, y)
        ge = d["categories"]["guest_experience"]
        # 0.7 * 100 + 0.3 * 50 = 85
        assert 84.5 <= ge["score"] <= 85.5, ge
        assert "RT mentions (70%)" in ge["source"]
        assert "CV / NPS (30%)" in ge["source"]
    finally:
        async def _wipe():
            await db.employees_v2.delete_many({"id": cid})
        loop.run_until_complete(_wipe())


def test_category_weights_match_explainer(loop, synthetic_quarter):
    """Weights returned by API must match the ScoringGuide.js table:
    Sales 25, Upsell 25, Loyalty 20, Guest 30."""
    q, y = synthetic_quarter
    d = _fetch(q, y)
    cats = d["categories"]
    assert cats["sales_execution"]["weight"]    == 25
    assert cats["upsell_performance"]["weight"] == 25
    assert cats["loyalty_engagement"]["weight"] == 20
    assert cats["guest_experience"]["weight"]   == 30
    # Sum must total 100.
    total = sum(c["weight"] for c in cats.values())
    assert total == 100
