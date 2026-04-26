"""Iteration 26 backend tests: parse_rt_file fixes.

Covers:
1. parse_rt_file resolves quarter/year from snapshot_id (was hardcoded Q1 2026).
2. Nickname expansion via DEFAULT_NICKNAME_MAP + explicit user mappings:
   Trey -> Treyanna, Tad/Thad -> Thaddeus, Keisha -> Lakeisha,
   Ikey -> Eric, Matt -> Matthew.
3. Status guard: 400 on completed snapshot, accepts in_progress.
4. After RT upload + /process, rt_mentions and review_tracker_bonus
   (= min(mentions*0.5, 15)) populated for matched employees.
5. Regression: P0 sync-from-employees safety guard, nickname CRUD endpoint,
   CV adjustment upload original_nps + non-nan comments.

Strategy: All snapshot-mutation tests use a temporary in_progress snapshot
seeded directly into Mongo (id prefixed with `iter26-`) and cleaned up in
finally blocks. We avoid touching the production Q2 2026 snapshot.
"""
import os
import io
import sys
import uuid
import json
import asyncio
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    fe_env = Path("/app/frontend/.env").read_text()
    for line in fe_env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
BASE_URL = BASE_URL.rstrip("/")

WF = f"{BASE_URL}/api/v2/snapshot-workflow"

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def db():
    return AsyncIOMotorClient(MONGO_URL)[DB_NAME]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _seed_pos_employees():
    """Five POS employees representing names with nickname expansion paths."""
    return [
        {"name": "Treyanna Quick", "first_name": "Treyanna", "last_name": "Quick",
         "report_name": "Treyanna Quick", "display_name": "Treyanna Quick",
         "transactions": 50, "sales": 500.0,
         "guest_count": 50, "net_sales": 500.0, "food_sales": 400.0,
         "liquor_sales": 50.0, "beer_sales": 25.0, "wine_sales": 25.0,
         "bar_glassware_sales": 0, "loyalty_sales": 0, "ppa": 10.0,
         "job_title": "Server"},
        {"name": "Thaddeus Hashey", "first_name": "Thaddeus", "last_name": "Hashey",
         "report_name": "Thaddeus Hashey", "display_name": "Thaddeus Hashey",
         "transactions": 50, "sales": 500.0,
         "guest_count": 50, "net_sales": 500.0, "food_sales": 400.0,
         "liquor_sales": 50.0, "beer_sales": 25.0, "wine_sales": 25.0,
         "bar_glassware_sales": 0, "loyalty_sales": 0, "ppa": 10.0,
         "job_title": "Server"},
        {"name": "Lakeisha Martin", "first_name": "Lakeisha", "last_name": "Martin",
         "report_name": "Lakeisha Martin", "display_name": "Lakeisha Martin",
         "transactions": 50, "sales": 500.0,
         "guest_count": 50, "net_sales": 500.0, "food_sales": 400.0,
         "liquor_sales": 50.0, "beer_sales": 25.0, "wine_sales": 25.0,
         "bar_glassware_sales": 0, "loyalty_sales": 0, "ppa": 10.0,
         "job_title": "Server"},
        {"name": "Eric Ostgarden", "first_name": "Eric", "last_name": "Ostgarden",
         "report_name": "Eric Ostgarden", "display_name": "Eric Ostgarden",
         "transactions": 50, "sales": 500.0,
         "guest_count": 50, "net_sales": 500.0, "food_sales": 400.0,
         "liquor_sales": 50.0, "beer_sales": 25.0, "wine_sales": 25.0,
         "bar_glassware_sales": 0, "loyalty_sales": 0, "ppa": 10.0,
         "job_title": "Server"},
        {"name": "Matthew Spath", "first_name": "Matthew", "last_name": "Spath",
         "report_name": "Matthew Spath", "display_name": "Matthew Spath",
         "transactions": 50, "sales": 500.0,
         "guest_count": 50, "net_sales": 500.0, "food_sales": 400.0,
         "liquor_sales": 50.0, "beer_sales": 25.0, "wine_sales": 25.0,
         "bar_glassware_sales": 0, "loyalty_sales": 0, "ppa": 10.0,
         "job_title": "Server"},
    ]


def _make_temp_snapshot(db, quarter: str, year: int, status: str = "in_progress"):
    """Insert a temp snapshot doc directly into mongo. Returns snapshot_id."""
    sid = f"iter26-{uuid.uuid4().hex[:12]}"
    pos_emps = _seed_pos_employees()
    snap = {
        "id": sid,
        "quarter": quarter,
        "year": year,
        "status": status,
        "is_current": False,
        "employees": pos_emps,
        "uploads": [{
            "upload_type": "pos_report",
            "filename": f"seed-{sid}.csv",
            "status": "parsed",
            "parsed_data": {"employees": pos_emps, "record_count": len(pos_emps)},
        }],
        "upload_progress": {"pos_report": True, "customer_voice": False, "review_tracker": False},
    }
    _run(db.snapshot_workflow.insert_one(snap))
    return sid


def _delete_snapshot(db, sid):
    _run(db.snapshot_workflow.delete_one({"id": sid}))


def _rt_csv_bytes(reviews):
    """Build a minimal RT-style CSV with required columns."""
    header = "Review ID,Published,Author,Source,Location,Rating,Review\n"
    rows = []
    for i, text in enumerate(reviews):
        # quote the review text
        safe = text.replace('"', '""')
        rows.append(f'r{i},2026-04-01,Anon,Google,LV,5,"{safe}"')
    return (header + "\n".join(rows) + "\n").encode("utf-8")


# ===========================================================================
# 1. parse_rt_file resolves quarter/year from snapshot_id (Q2 not hardcoded Q1)
# ===========================================================================
class TestRTQuarterResolution:
    def test_q2_snapshot_upload_uses_q2_employees(self, db):
        """Upload RT with various nicknames to a Q2 in_progress snapshot.
        Validates parse_rt_file picked the snapshot's actual employees
        (5 seeded names) and matched nicknames -> formal names."""
        sid = _make_temp_snapshot(db, "Q2", 2026)
        try:
            csv_bytes = _rt_csv_bytes([
                "Trey was amazing tonight!",
                "Tad delivered great food",
                "Thad really knows wine",
                "Keisha rocked our table",
                "Ikey nailed it again",
                "Matt was great with the kids",
                "Treyanna was terrific",
                "Treyana spelt funny but lovely",
                "irrelevant noise review with no names",
            ])
            files = {"file": ("rt_q2.csv", csv_bytes, "text/csv")}
            r = requests.post(f"{WF}/snapshots/{sid}/upload/review_tracker",
                              files=files, timeout=60)
            assert r.status_code == 200, r.text[:500]
            body = r.json()
            assert body.get("success") is True

            snap = _run(db.snapshot_workflow.find_one({"id": sid}, {"_id": 0}))
            rt_upload = next(u for u in snap["uploads"]
                             if u["upload_type"] == "review_tracker")
            emps = {e["name"]: e["mentions"]
                    for e in rt_upload["parsed_data"]["employees"]}

            # Nickname expansion assertions
            assert emps.get("Treyanna Quick", 0) >= 3, emps  # trey + treyanna + treyana
            assert emps.get("Thaddeus Hashey", 0) >= 2, emps  # tad + thad
            assert emps.get("Lakeisha Martin", 0) >= 1, emps  # keisha
            assert emps.get("Eric Ostgarden", 0) >= 1, emps   # ikey
            assert emps.get("Matthew Spath", 0) >= 1, emps    # matt
        finally:
            _delete_snapshot(db, sid)

    def test_q1_snapshot_upload_still_works_regression(self, db):
        """Q1 was the old hardcoded value. Make sure Q1 still parses fine."""
        sid = _make_temp_snapshot(db, "Q1", 2026)
        try:
            csv_bytes = _rt_csv_bytes([
                "Treyanna was great",
                "Matthew was professional",
            ])
            files = {"file": ("rt_q1.csv", csv_bytes, "text/csv")}
            r = requests.post(f"{WF}/snapshots/{sid}/upload/review_tracker",
                              files=files, timeout=60)
            assert r.status_code == 200, r.text[:500]
            snap = _run(db.snapshot_workflow.find_one({"id": sid}, {"_id": 0}))
            rt_upload = next(u for u in snap["uploads"]
                             if u["upload_type"] == "review_tracker")
            emps = {e["name"]: e["mentions"]
                    for e in rt_upload["parsed_data"]["employees"]}
            assert emps.get("Treyanna Quick", 0) >= 1, emps
            assert emps.get("Matthew Spath", 0) >= 1, emps
        finally:
            _delete_snapshot(db, sid)


# ===========================================================================
# 2. Status guard
# ===========================================================================
class TestStatusGuard:
    def test_rt_upload_to_completed_returns_400(self, db):
        sid = _make_temp_snapshot(db, "Q2", 2026, status="completed")
        try:
            csv_bytes = _rt_csv_bytes(["Trey was amazing"])
            files = {"file": ("rt.csv", csv_bytes, "text/csv")}
            r = requests.post(f"{WF}/snapshots/{sid}/upload/review_tracker",
                              files=files, timeout=30)
            assert r.status_code == 400, r.text[:300]
            assert "completed snapshot" in r.text.lower()
        finally:
            _delete_snapshot(db, sid)

    def test_rt_upload_to_in_progress_accepted(self, db):
        sid = _make_temp_snapshot(db, "Q2", 2026, status="in_progress")
        try:
            csv_bytes = _rt_csv_bytes(["Trey was amazing"])
            files = {"file": ("rt.csv", csv_bytes, "text/csv")}
            r = requests.post(f"{WF}/snapshots/{sid}/upload/review_tracker",
                              files=files, timeout=30)
            assert r.status_code == 200, r.text[:300]
        finally:
            _delete_snapshot(db, sid)


# ===========================================================================
# 3. After /process: rt_mentions + review_tracker_bonus populated
# ===========================================================================
class TestProcessPopulatesRTFields:
    def test_process_populates_rt_mentions_and_bonus(self, db):
        sid = _make_temp_snapshot(db, "Q2", 2026)
        try:
            # 4 mentions of Treyanna -> bonus 4*0.5=2.0
            # 32 mentions of Thaddeus -> bonus capped at 15.0
            reviews = (
                ["Trey was amazing"] * 2
                + ["Treyanna was awesome"] * 2
                + ["Thad delivered well"] * 32
                + ["Matt was great"] * 1
            )
            csv_bytes = _rt_csv_bytes(reviews)
            files = {"file": ("rt.csv", csv_bytes, "text/csv")}
            r = requests.post(f"{WF}/snapshots/{sid}/upload/review_tracker",
                              files=files, timeout=60)
            assert r.status_code == 200, r.text[:300]

            r2 = requests.post(f"{WF}/snapshots/{sid}/process", timeout=120)
            assert r2.status_code == 200, r2.text[:500]

            snap = _run(db.snapshot_workflow.find_one({"id": sid}, {"_id": 0}))
            by_name = {e.get("display_name") or e.get("name"): e
                       for e in snap.get("employees", [])}

            trey = by_name.get("Treyanna Quick")
            thad = by_name.get("Thaddeus Hashey")
            matt = by_name.get("Matthew Spath")
            assert trey, list(by_name.keys())
            assert thad, list(by_name.keys())
            assert matt, list(by_name.keys())

            assert trey.get("rt_mentions", 0) >= 4
            assert thad.get("rt_mentions", 0) >= 32
            assert matt.get("rt_mentions", 0) >= 1

            # bonus = min(mentions * 0.5, 15)
            assert abs(trey.get("review_tracker_bonus", 0) - min(trey["rt_mentions"] * 0.5, 15)) < 0.01
            # capped at 15
            assert thad.get("review_tracker_bonus", 0) == 15.0
            assert abs(matt.get("review_tracker_bonus", 0) - min(matt["rt_mentions"] * 0.5, 15)) < 0.01
        finally:
            _delete_snapshot(db, sid)


# ===========================================================================
# 4. Regressions
# ===========================================================================
class TestRegressions:
    def test_nickname_get_endpoint(self):
        r = requests.get(f"{WF}/nicknames", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "defaults" in body and "user" in body
        assert len(body["defaults"]) == 31
        # Spot-check explicit mappings
        nicks = {d["nickname"]: d["formal"] for d in body["defaults"]}
        assert nicks["keisha"] == "lakeisha"
        assert nicks["trey"] == "treyanna"
        assert nicks["matt"] == "matthew"
        assert nicks["thad"] == "thaddeus"
        assert nicks["ikey"] == "eric"

    def test_nickname_post_then_delete(self, db):
        nick = f"itr26{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{WF}/nicknames",
                          json={"nickname": nick, "formal": "lakeisha"},
                          timeout=20)
        assert r.status_code == 200, r.text
        alias_id = r.json()["id"]
        try:
            r2 = requests.delete(f"{WF}/nicknames/{alias_id}", timeout=20)
            assert r2.status_code == 200
            assert r2.json().get("success") is True
        finally:
            _run(db.nickname_aliases.delete_many({"id": alias_id}))
            _run(db.nickname_aliases.delete_many({"nickname": nick}))

    def test_p0_sync_safety_guard(self):
        """Active Q1 2026 snapshot. Either 200 (employees_v2 healthy)
        or 409 (guard kicked in) is acceptable."""
        snap_id = "e20ede2c-1bb1-4b2f-85e2-81d99a7243de"
        url = f"{WF}/snapshots/{snap_id}/sync-from-employees"
        r = requests.post(url, timeout=30)
        assert r.status_code in (200, 409, 404), \
            f"unexpected status {r.status_code}: {r.text[:300]}"
        if r.status_code == 409:
            assert ("employees_v2" in r.text
                    or "aborted" in r.text.lower()
                    or "safety" in r.text.lower())

    def test_cv_adjustment_upload_returns_nps(self):
        feedback = Path("/tmp/feedback.xlsx")
        if not feedback.exists():
            pytest.skip("/tmp/feedback.xlsx not available")
        url = f"{BASE_URL}/api/v2/cv/adjustment/upload"
        with feedback.open("rb") as f:
            files = {"file": ("feedback.xlsx", f,
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            data = {"quarter": "2", "year": "2026"}
            r = requests.post(url, files=files, data=data, timeout=60)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("original_nps") is not None
        assert isinstance(body.get("original_nps"), (int, float))
        # JSON-safe (no NaN)
        json.dumps(body)
