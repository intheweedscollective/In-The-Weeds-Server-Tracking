"""
Regression tests for two reported bugs:

1. "Terminated employees keep coming back after I save the snapshot."
   merge_snapshot_data must respect snapshot.deleted_names and skip those
   names when re-merging POS parsed_data.

2. "NPS Toolkit XLSX shows people with NPS percentages but no promoters
   or detractors."
   parse_cv_file must read true Promoter/Passive/Detractor columns when
   present, instead of estimating every time.
"""

import asyncio
from io import BytesIO

import pytest
import openpyxl


# ---------------------------------------------------------------------------
# Helper to run async code under pytest without a plugin
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1) Deletion blocklist: merge_snapshot_data must skip names in deleted_names
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def _merge_skips_deleted_names_impl(monkeypatch):
    """Names in snapshot.deleted_names must NOT be recreated by POS merge."""
    from snapshot_routes import merge_snapshot_data

    # Stub get_db / load_nickname_map so merge_snapshot_data has no real DB.
    class _FakeColl:
        async def find_one(self, *a, **kw):
            return None

    class _FakeDB:
        nickname_aliases = _FakeColl()

    monkeypatch.setattr("snapshot_routes.get_db", lambda: _FakeDB())

    async def _empty_map(_db):
        return {}

    monkeypatch.setattr("snapshot_routes.load_nickname_map", _empty_map)

    snapshot = {
        "id": "snap-1",
        "quarter": "Q2",
        "year": 2026,
        # Two employees in the POS upload, but Bob is on the deleted list.
        "deleted_names": ["Bob Smith"],
        "employees": [],
        "uploads": [
            {
                "upload_type": "pos_report",
                "parsed_data": {
                    "employees": [
                        {
                            "name": "Alice Adams",
                            "guests": 100, "net_sales": 5500.0, "ppa": 55.0,
                            "lbw": 800, "glassware_sales": 130, "lsc_count": 10,
                            "loyalty_sales": 0, "food_sales": 4000,
                            "liquor_sales": 500, "beer_sales": 200, "wine_sales": 100,
                            "job_title": "server",
                        },
                        {
                            "name": "Bob Smith",  # <-- terminated, should NOT come back
                            "guests": 80, "net_sales": 4000.0, "ppa": 50.0,
                            "lbw": 600, "glassware_sales": 100, "lsc_count": 8,
                            "loyalty_sales": 0, "food_sales": 3000,
                            "liquor_sales": 400, "beer_sales": 200, "wine_sales": 100,
                            "job_title": "server",
                        },
                    ]
                },
            }
        ],
    }

    result = await merge_snapshot_data(snapshot)
    names = {e.get("name") for e in result}
    assert "Alice Adams" in names
    assert "Bob Smith" not in names, (
        "Bob is on the snapshot's deleted_names blocklist and must NOT be "
        "re-created from POS parsed_data."
    )


def test_merge_skips_deleted_names(monkeypatch):
    """Sync wrapper so we don't need pytest-asyncio."""
    asyncio.get_event_loop().run_until_complete(
        _merge_skips_deleted_names_impl(monkeypatch)
    )


# ---------------------------------------------------------------------------
# 2) NPS Toolkit XLSX parser: read real Promoter/Passive/Detractor columns
# ---------------------------------------------------------------------------

def _make_nps_xlsx(rows):
    """Build a tiny in-memory NPS Toolkit-style XLSX for the parser."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Server Performance Report"])  # title row above headers
    ws.append(["Name", "Received", "Promoters", "Passives", "Detractors", "Avg Rating", "NPS"])
    for r in rows:
        ws.append(r)
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_parse_cv_uses_real_promoter_columns_when_present():
    """If the file has Promoter/Passive/Detractor columns, use them as-is."""
    from snapshot_routes import parse_cv_file

    contents = _make_nps_xlsx([
        # name,    received, prom, pass, det, avg, nps
        ["Alice",     10,       8,    1,   1,   4.6,  70],
        ["TK",         5,       3,    1,   1,   4.2,  40],   # <-- short name, must NOT be filtered
        ["Carla",      4,       0,    0,   4,   2.0, -100], # all detractors
    ])

    result = asyncio.get_event_loop().run_until_complete(
        parse_cv_file("nps_toolkit.xlsx", contents)
    )
    by_name = {e["name"]: e for e in result["employees"]}

    # All three present (TK was the user's reported missing case)
    assert set(by_name.keys()) == {"Alice", "TK", "Carla"}

    # Real counts must be honored — not estimated.
    assert by_name["Alice"]["promoters"] == 8
    assert by_name["Alice"]["passives"] == 1
    assert by_name["Alice"]["detractors"] == 1
    assert by_name["Alice"]["nps_score"] == 70

    assert by_name["TK"]["promoters"] == 3
    assert by_name["TK"]["passives"] == 1
    assert by_name["TK"]["detractors"] == 1

    # Carla has all detractors — must be reflected (was the bug: NPS shown
    # but promoters/detractors all zero).
    assert by_name["Carla"]["promoters"] == 0
    assert by_name["Carla"]["detractors"] == 4


def test_parse_cv_falls_back_to_estimation_when_no_pcd_columns():
    """When Promoter/Passive/Detractor columns are missing, estimate from NPS."""
    from snapshot_routes import parse_cv_file

    wb = openpyxl.Workbook()
    ws = wb.active
    # Bare-bones header WITHOUT promoter/passive/detractor columns
    ws.append(["Name", "Received", "NPS"])
    ws.append(["Alice", 10, 80])  # Should estimate ~9 promoters at NPS 80
    bio = BytesIO()
    wb.save(bio)

    result = asyncio.get_event_loop().run_until_complete(
        parse_cv_file("legacy.xlsx", bio.getvalue())
    )
    e = result["employees"][0]
    assert e["name"] == "Alice"
    # Estimation only — just ensure it didn't drop to zero
    assert e["promoters"] > 0
    assert e["promoters"] + e["passives"] + e["detractors"] == 10
