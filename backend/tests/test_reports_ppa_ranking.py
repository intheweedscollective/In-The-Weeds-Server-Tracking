"""
Regression: PPA Ranking report
=================================

Operator request (2026-06): Reports tab card listing every active
employee ranked by PPA, plus a branded PDF download.

These tests pin:
  1. Sort order = PPA high → low.
  2. Location average = mean of all positive PPAs (zero/null excluded).
  3. vs_location = ppa − location_average; pct = diff / location_avg * 100.
  4. Quarter/year defaults resolve from is_current snapshot.
  5. PDF endpoint returns `application/pdf` with the %PDF header.
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


# ---------------------------------------------------------------------------
# Live-data smoke tests — these run against the active production-like
# data in the preview env so they double as a deploy gate.
# ---------------------------------------------------------------------------


def test_active_quarter_json_sorted_descending():
    r = requests.get(f"{BASE}/api/v2/reports/ppa-ranking", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body["rows"]
    assert rows, "expected at least one row in the active quarter"
    ppas = [row["ppa"] for row in rows]
    # Sorted high → low.
    assert ppas == sorted(ppas, reverse=True), (
        f"rows are not PPA-sorted desc: {ppas[:5]}"
    )
    # Rank starts at 1 and increments by 1.
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_location_average_matches_mean_of_rows():
    r = requests.get(f"{BASE}/api/v2/reports/ppa-ranking", timeout=15)
    body = r.json()
    rows = body["rows"]
    mean = sum(r["ppa"] for r in rows) / len(rows)
    assert abs(body["location_average_ppa"] - round(mean, 2)) < 0.05, (
        f"location_average_ppa={body['location_average_ppa']} but rows mean="
        f"{mean:.2f}"
    )


def test_vs_location_arithmetic():
    r = requests.get(f"{BASE}/api/v2/reports/ppa-ranking", timeout=15)
    body = r.json()
    loc = body["location_average_ppa"]
    for row in body["rows"][:5]:
        expected = round(row["ppa"] - loc, 2)
        assert abs(row["vs_location"] - expected) < 0.02, (
            f"{row['name']}: vs_location={row['vs_location']} but expected "
            f"{expected}"
        )
        if loc > 0:
            expected_pct = round((row["ppa"] - loc) / loc * 100, 1)
            assert abs(row["vs_location_pct"] - expected_pct) < 0.2


# ---------------------------------------------------------------------------
# Synthetic fixture: deterministic math against known data
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_ppa_quarter(loop):
    """4 employees in QR2/2999 with known PPAs:
       Alice 60, Bob 50, Carl 40, Dawn 30. Mean = 45.
       Snapshot is_current=True so the endpoint resolves to this quarter.
    """
    db = _db()
    q, y = "QR2", 2999
    cids = [f"ppa-test-{i}-{uuid.uuid4().hex[:6]}" for i in range(4)]
    snap_id = f"ppa-snap-{uuid.uuid4().hex[:8]}"

    async def _seed():
        # Move any other is_current snapshot out of the way so our test
        # one is the unique active. Restore in teardown.
        prior = await db.snapshot_workflow.find_one(
            {"is_current": True}, {"_id": 0, "id": 1},
        )
        if prior:
            await db.snapshot_workflow.update_one(
                {"id": prior["id"]}, {"$set": {"is_current": False}},
            )
        await db.employees_v2.insert_many([
            {"id": cids[0], "name": "Alice PPA",
             "name_normalized": "alice ppa",
             "quarter": q, "year": y, "status": "active",
             "ppa": 60, "tier_label": "A-Server"},
            {"id": cids[1], "name": "Bob PPA",
             "name_normalized": "bob ppa",
             "quarter": q, "year": y, "status": "active",
             "ppa": 50, "tier_label": "B-Server"},
            {"id": cids[2], "name": "Carl PPA",
             "name_normalized": "carl ppa",
             "quarter": q, "year": y, "status": "active",
             "ppa": 40, "tier_label": "B-Server"},
            {"id": cids[3], "name": "Dawn PPA",
             "name_normalized": "dawn ppa",
             "quarter": q, "year": y, "status": "active",
             "ppa": 30, "tier_label": "C-Server"},
        ])
        await db.snapshot_workflow.insert_one({
            "id": snap_id, "name": "PPA Test Snapshot",
            "quarter": q, "year": y, "status": "completed",
            "is_current": True,
            "rows": [
                {"employee_id": cids[i],
                 "frozen_display_name": f"{name} PPA",
                 "frozen_score": ppa,
                 "frozen_tier": tier,
                 "frozen_metrics": {"ppa": ppa, "tier_label": tier}}
                for i, (name, ppa, tier) in enumerate([
                    ("Alice", 60, "A-Server"),
                    ("Bob",   50, "B-Server"),
                    ("Carl",  40, "B-Server"),
                    ("Dawn",  30, "C-Server"),
                ])
            ],
            "employees": [],
            "deleted_names": [],
        })
        await db.employees.insert_many([
            {"id": cids[i], "name": n, "status": "active",
             "aliases": [], "legacy_ids": []}
            for i, n in enumerate(["Alice PPA", "Bob PPA",
                                   "Carl PPA", "Dawn PPA"])
        ])
        return prior

    prior = loop.run_until_complete(_seed())
    yield q, y

    async def _wipe():
        await db.snapshot_workflow.delete_one({"id": snap_id})
        await db.employees_v2.delete_many({"id": {"$in": cids}})
        await db.employees.delete_many({"id": {"$in": cids}})
        # Restore the original is_current snapshot.
        if prior:
            await db.snapshot_workflow.update_one(
                {"id": prior["id"]}, {"$set": {"is_current": True}},
            )
    loop.run_until_complete(_wipe())


def test_synthetic_location_average_is_45(synthetic_ppa_quarter):
    q, y = synthetic_ppa_quarter
    r = requests.get(
        f"{BASE}/api/v2/reports/ppa-ranking",
        params={"quarter": q, "year": y},
        timeout=15,
    )
    body = r.json()
    assert body["location_average_ppa"] == 45.0
    # Ordering: Alice 60, Bob 50, Carl 40, Dawn 30.
    names = [r["name"] for r in body["rows"]]
    assert names == ["Alice PPA", "Bob PPA", "Carl PPA", "Dawn PPA"]
    # vs_location for Alice = +15; Dawn = -15.
    assert body["rows"][0]["vs_location"] == 15.0
    assert body["rows"][-1]["vs_location"] == -15.0


def test_synthetic_default_resolves_active_snapshot(synthetic_ppa_quarter):
    """No quarter/year params — must resolve to is_current snapshot."""
    r = requests.get(f"{BASE}/api/v2/reports/ppa-ranking", timeout=15)
    body = r.json()
    q, y = synthetic_ppa_quarter
    assert body["quarter"] == q
    assert body["year"] == y


# ---------------------------------------------------------------------------
# PDF endpoint
# ---------------------------------------------------------------------------


def test_pdf_endpoint_returns_real_pdf():
    r = requests.get(
        f"{BASE}/api/v2/reports/ppa-ranking/pdf",
        timeout=20,
    )
    assert r.status_code == 200, r.text[:400]
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF"), (
        f"response is not a PDF: first bytes={r.content[:8]!r}"
    )
    # Sanity: not a tiny empty PDF.
    assert len(r.content) > 1000


def test_pdf_filename_has_quarter_and_year():
    r = requests.get(
        f"{BASE}/api/v2/reports/ppa-ranking/pdf",
        timeout=20,
    )
    cd = r.headers.get("content-disposition", "")
    assert "ppa_ranking_" in cd
    assert ".pdf" in cd


# ---------------------------------------------------------------------------
# Yodeck slide endpoint
# ---------------------------------------------------------------------------


def test_slide_endpoint_returns_1920x1080_png():
    r = requests.get(
        f"{BASE}/api/v2/reports/ppa-ranking/slide",
        timeout=20,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"] == "image/png"
    # PNG magic bytes
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # Sanity: dimensions should be exactly 1920x1080
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(r.content))
    assert img.size == (1920, 1080), (
        f"slide must be 1920x1080 for Yodeck, got {img.size}"
    )


def test_slide_filename_has_quarter_and_year():
    r = requests.get(
        f"{BASE}/api/v2/reports/ppa-ranking/slide",
        timeout=20,
    )
    cd = r.headers.get("content-disposition", "")
    assert "ppa_ranking_" in cd
    assert ".png" in cd
