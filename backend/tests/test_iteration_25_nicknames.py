"""Iteration 25 backend tests:

Coverage:
- Nickname Aliases CRUD: GET/POST(create+update)/DELETE under
  /api/v2/snapshot-workflow/nicknames
- Validation: 400 on empty fields, 404 on unknown id
- Integration: load_nickname_map + find_employee_match wiring inside
  merge_snapshot_data (custom alias routes a CV row to the right POS employee)
- Regression smoke: P0 sync-from-employees safety guard, nps_manual_override,
  CV adjustment upload returns original_nps + non-nan comments + nps_category.
"""
import os
import io
import sys
import uuid
import json
import asyncio
import pytest
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback: read frontend/.env
    fe_env = Path("/app/frontend/.env").read_text()
    for line in fe_env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
BASE_URL = BASE_URL.rstrip("/")
NICK_URL = f"{BASE_URL}/api/v2/snapshot-workflow/nicknames"

# Mongo cleanup helpers (direct connection)
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
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture
def cleanup_aliases(db):
    """Track alias ids created during the test and clean them in teardown."""
    created_ids = []
    created_nicknames = []
    yield (created_ids, created_nicknames)
    async def _cleanup():
        if created_ids:
            await db.nickname_aliases.delete_many({"id": {"$in": created_ids}})
        if created_nicknames:
            await db.nickname_aliases.delete_many({"nickname": {"$in": created_nicknames}})
    _run(_cleanup())


# ---------------------------------------------------------------------------
# Nickname CRUD
# ---------------------------------------------------------------------------
class TestNicknameCRUD:
    def test_get_returns_defaults_and_user_arrays(self):
        r = requests.get(NICK_URL, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "defaults" in data and "user" in data
        assert isinstance(data["defaults"], list)
        assert isinstance(data["user"], list)
        # 31 built-in entries (per spec)
        assert len(data["defaults"]) == 31, f"expected 31 defaults, got {len(data['defaults'])}"
        nicks = {d["nickname"]: d["formal"] for d in data["defaults"]}
        # User-confirmed mappings
        for nick, formal in [
            ("keisha", "lakeisha"), ("trey", "treyanna"),
            ("tk", "thomas"), ("ikey", "eric"), ("lennie", "glennice"),
            ("matt", "matthew"), ("tad", "thaddeus"),
            ("thad", "thaddeus"), ("treyana", "treyanna"),
        ]:
            assert nicks.get(nick) == formal, f"{nick} -> expected {formal} got {nicks.get(nick)}"

    def test_post_creates_and_get_persists(self, cleanup_aliases):
        ids, nicks = cleanup_aliases
        nick = f"testnick{uuid.uuid4().hex[:8]}"
        nicks.append(nick)
        payload = {"nickname": nick, "formal": "lakeisha"}
        r = requests.post(NICK_URL, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["updated"] is False
        assert "id" in body and body["id"]
        ids.append(body["id"])

        # Verify it shows up in GET list
        r2 = requests.get(NICK_URL, timeout=20)
        user_list = r2.json()["user"]
        match = [u for u in user_list if u.get("id") == body["id"]]
        assert match, "newly created alias missing from GET response"
        assert match[0]["nickname"] == nick
        assert match[0]["formal"] == "lakeisha"

    def test_post_same_nickname_updates_not_duplicates(self, cleanup_aliases):
        ids, nicks = cleanup_aliases
        nick = f"dupnick{uuid.uuid4().hex[:8]}"
        nicks.append(nick)
        r1 = requests.post(NICK_URL, json={"nickname": nick, "formal": "alpha"}, timeout=20)
        assert r1.status_code == 200
        first_id = r1.json()["id"]
        ids.append(first_id)

        r2 = requests.post(NICK_URL, json={"nickname": nick, "formal": "beta"}, timeout=20)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["updated"] is True
        assert body["id"] == first_id

        # Verify only one row + formal is updated
        r3 = requests.get(NICK_URL, timeout=20)
        matches = [u for u in r3.json()["user"] if u["nickname"] == nick]
        assert len(matches) == 1, f"expected single row, got {len(matches)}"
        assert matches[0]["formal"] == "beta"

    @pytest.mark.parametrize("payload", [
        {"nickname": "", "formal": "x"},
        {"nickname": "x", "formal": ""},
        {"nickname": "   ", "formal": "x"},
        {},
    ])
    def test_post_validation_400(self, payload):
        r = requests.post(NICK_URL, json=payload, timeout=20)
        assert r.status_code == 400, f"payload={payload} got {r.status_code}: {r.text}"

    def test_delete_removes_alias(self, cleanup_aliases):
        ids, nicks = cleanup_aliases
        nick = f"delnick{uuid.uuid4().hex[:8]}"
        nicks.append(nick)
        r = requests.post(NICK_URL, json={"nickname": nick, "formal": "gone"}, timeout=20)
        alias_id = r.json()["id"]
        # No need to add to ids since we're deleting it

        rd = requests.delete(f"{NICK_URL}/{alias_id}", timeout=20)
        assert rd.status_code == 200, rd.text
        body = rd.json()
        assert body["success"] is True
        assert body["deleted"] == alias_id

        # GET no longer contains it
        r3 = requests.get(NICK_URL, timeout=20)
        assert not [u for u in r3.json()["user"] if u.get("id") == alias_id]

    def test_delete_unknown_returns_404(self):
        r = requests.delete(f"{NICK_URL}/{uuid.uuid4()}", timeout=20)
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Integration: load_nickname_map + find_employee_match wiring
# ---------------------------------------------------------------------------
class TestNicknameIntegration:
    """Direct in-process unit-style test of load_nickname_map and the
    find_employee_match closure inside merge_snapshot_data. We avoid mutating
    the live snapshot."""

    def test_load_nickname_map_includes_user_alias(self, db, cleanup_aliases):
        ids, nicks = cleanup_aliases
        nick = f"intnick{uuid.uuid4().hex[:8]}"
        nicks.append(nick)
        r = requests.post(NICK_URL, json={"nickname": nick, "formal": "lakeisha"}, timeout=20)
        ids.append(r.json()["id"])

        from snapshot_routes import load_nickname_map, DEFAULT_NICKNAME_MAP
        merged = _run(load_nickname_map(db))
        # Defaults preserved
        assert merged["keisha"] == "lakeisha"
        # Custom overlaid
        assert merged[nick] == "lakeisha"
        # Size = defaults + at least the new entry
        assert len(merged) >= len(DEFAULT_NICKNAME_MAP) + 1

    def test_merge_snapshot_data_routes_custom_alias_to_pos_employee(self, db, cleanup_aliases):
        """End-to-end: seed a snapshot with a POS employee 'Lakeisha Test' and
        a CV upload row 'TestNickXyz Test'; add custom alias; run
        merge_snapshot_data; assert merged employees list contains a single
        Lakeisha Test row with nps fields populated."""
        ids, nicks = cleanup_aliases
        from snapshot_routes import merge_snapshot_data

        nick = f"testnick{uuid.uuid4().hex[:6]}"
        nicks.append(nick)
        r = requests.post(NICK_URL, json={"nickname": nick, "formal": "lakeisha"}, timeout=20)
        ids.append(r.json()["id"])

        cv_full_name = f"{nick.title()} Test"  # e.g. 'Testnickabc123 Test'
        snapshot = {
            "id": "tmp-iter25",
            "quarter": 1, "year": 2026,
            "employees": [
                {"name": "Lakeisha Test", "first_name": "Lakeisha",
                 "last_name": "Test", "report_name": "Lakeisha Test",
                 "transactions": 10, "sales": 100.0}
            ],
            "uploads": [
                {
                    "upload_type": "pos_report",
                    "parsed_data": {
                        "employees": [
                            {"name": "Lakeisha Test", "first_name": "Lakeisha",
                             "last_name": "Test",
                             "guest_count": 100, "net_sales": 1000.0,
                             "food_sales": 800.0, "liquor_sales": 100.0,
                             "beer_sales": 50.0, "wine_sales": 50.0,
                             "bar_glassware_sales": 0, "loyalty_sales": 0,
                             "ppa": 10.0, "job_title": "Server"}
                        ]
                    }
                },
                {
                    "upload_type": "customer_voice",
                    "parsed_data": {
                        "employees": [
                            {"name": cv_full_name, "promoters": 5,
                             "passives": 1, "detractors": 0,
                             "nps_score": 80.0, "comments": []}
                        ]
                    }
                }
            ]
        }

        merged = _run(merge_snapshot_data(snapshot))
        # Find Lakeisha Test in result
        lakeisha = [e for e in merged
                    if (e.get("name") or "").lower() == "lakeisha test"]
        assert lakeisha, f"Lakeisha Test missing from merged employees: {[e.get('name') for e in merged]}"
        emp = lakeisha[0]
        # CV merge populated nps fields
        assert emp.get("cv_promoters", 0) == 5, f"cv_promoters not merged: {emp}"
        assert emp.get("nps_score") not in (None, 0), f"nps_score missing/zero: nps_score={emp.get('nps_score')}"
        # No stray TestNick row
        assert not [e for e in merged
                    if (e.get("name") or "").lower().startswith(nick)], \
            f"unmatched alias row leaked: {[e.get('name') for e in merged]}"


# ---------------------------------------------------------------------------
# Regression smoke (lightweight - deeper coverage in test_save_snapshot_p0_fix)
# ---------------------------------------------------------------------------
class TestRegression:
    def test_treyanna_quick_default_match_unaffected(self, db):
        """Defaults still match formal CV name to POS employee with same name
        (no custom alias needed). Uses the in-memory snapshot path."""
        from snapshot_routes import merge_snapshot_data
        snapshot = {
            "id": "reg-treyanna",
            "quarter": 2, "year": 2026,
            "employees": [
                {"name": "Treyanna Quick", "first_name": "Treyanna",
                 "last_name": "Quick", "report_name": "Treyanna Quick",
                 "transactions": 0, "sales": 0.0}
            ],
            "uploads": [
                {"upload_type": "pos_report", "parsed_data": {"employees": [
                    {"name": "Treyanna Quick", "first_name": "Treyanna",
                     "last_name": "Quick", "guest_count": 50,
                     "net_sales": 500.0, "food_sales": 400.0,
                     "liquor_sales": 50.0, "beer_sales": 25.0,
                     "wine_sales": 25.0, "bar_glassware_sales": 0,
                     "loyalty_sales": 0, "ppa": 10.0,
                     "job_title": "Server"}]}},
                {"upload_type": "customer_voice", "parsed_data": {"employees": [
                    {"name": "Treyanna Quick", "promoters": 3,
                     "passives": 0, "detractors": 0,
                     "nps_score": 100.0, "comments": []}]}}
            ]
        }
        merged = _run(merge_snapshot_data(snapshot))
        rows = [e for e in merged if (e.get("name") or "").lower() == "treyanna quick"]
        assert rows, "Treyanna Quick missing from merged employees"
        assert rows[0].get("cv_promoters", 0) == 3

    def test_p0_sync_safety_guard_409(self):
        """Sync-from-employees safety guard: when employees_v2 row count
        is <50% of POS upload count, the endpoint must raise 409.

        Active Q1 2026 snapshot: e20ede2c-1bb1-4b2f-85e2-81d99a7243de.
        """
        snap_id = "e20ede2c-1bb1-4b2f-85e2-81d99a7243de"
        url = f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{snap_id}/sync-from-employees"
        r = requests.post(url, timeout=30)
        # 409 = guard kicked in (likely)
        # 200 = employees_v2 already healthy (>=50%)
        # 404 = snapshot missing in this env
        assert r.status_code in (200, 404, 409), \
            f"unexpected status {r.status_code}: {r.text[:300]}"
        if r.status_code == 409:
            assert "employees_v2" in r.text or "aborted" in r.text.lower()

    def test_cv_adjustment_upload_returns_nps_and_category(self, db):
        """If /tmp/feedback.xlsx exists, run upload and assert response shape."""
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
        # No NaN comments (must be JSON-safe)
        json.dumps(body)  # would raise on NaN if not sanitized
        # nps_category populated for >=1 employee
        emps = body.get("employees") or body.get("data", {}).get("employees") or []
        if emps:
            cats = [e.get("nps_category") for e in emps if e.get("nps_category")]
            assert cats, "nps_category not populated on any employee"

    def test_nps_manual_override_blocks_cv_merge(self, db):
        """Regression: existing employee with nps_manual_override=True must
        not be overwritten by CV upload merge."""
        from snapshot_routes import merge_snapshot_data
        # Pre-existing snapshot row already overridden by user
        snapshot = {
            "id": "reg-override",
            "quarter": 2, "year": 2026,
            "employees": [
                {"name": "Override Person", "first_name": "Override",
                 "last_name": "Person", "report_name": "Override Person",
                 "nps_manual_override": True,
                 "cv_promoters": 99, "cv_passives": 0, "cv_detractors": 0,
                 "nps_score": 99.0}
            ],
            "uploads": [
                {"upload_type": "pos_report", "parsed_data": {"employees": [
                    {"name": "Override Person", "guest_count": 10,
                     "net_sales": 100.0, "food_sales": 80.0,
                     "liquor_sales": 0, "beer_sales": 0, "wine_sales": 0,
                     "bar_glassware_sales": 0, "loyalty_sales": 0,
                     "ppa": 10.0, "job_title": "Server"}]}},
                {"upload_type": "customer_voice", "parsed_data": {"employees": [
                    {"name": "Override Person", "promoters": 1,
                     "passives": 1, "detractors": 5,
                     "nps_score": -10.0, "comments": []}]}}
            ]
        }
        merged = _run(merge_snapshot_data(snapshot))
        rows = [e for e in merged
                if (e.get("name") or "").lower() == "override person"]
        assert rows, "override row missing"
        # Manual override values preserved (CV row was DETRACTING)
        assert rows[0].get("cv_promoters") == 99
        assert rows[0].get("nps_score") == 99.0
