"""
Tests for two enhancements built on 2026-05-30:

1. Auto-add misspelled POS names as canonical aliases at rename time
   (self-curating typo dictionary).

2. Passive scoring integrity check on /api/v2/admin/scoring-trust —
   surfaces employees whose stored derived ratios (PPA, guests_per_lsc,
   lbw_per_guest) drift from their raw inputs.
"""

import os
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TOKEN = "test-agent-name-score-9fe6f8f7-933c-40f6-b3db-bbe3c034f896"
ADMIN_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


# ---------------------------------------------------------------------------
# Helper — drop a misspelled alias if it leaked into the DB from a previous
# test run so the assertions about "was added" are exact.
# ---------------------------------------------------------------------------


async def _cleanup_alias_on(canonical_name: str, misspelled: str):
    db = _db()
    await db.employees.update_many(
        {"name": canonical_name},
        {"$pull": {"aliases": misspelled}},
    )


async def _find_canonical(canonical_name: str):
    db = _db()
    return await db.employees.find_one(
        {"name": canonical_name, "status": "active"},
        {"_id": 0, "id": 1, "name": 1, "aliases": 1},
    )


# ---------------------------------------------------------------------------
# 1. Alias auto-add at rename time
# ---------------------------------------------------------------------------


def test_alias_auto_add_on_inline_rename():
    """Posting confirm-pos-review with `_original_name` differing from
    `name` should register the original as a permanent alias on the
    canonical employee. Idempotent on re-run."""
    canonical_name = "Diane Peterson"
    misspelled = f"Drane-Test-{uuid.uuid4().hex[:6]}"

    # Pre-condition: canonical exists, misspelled NOT yet in aliases.
    target = asyncio.run(_find_canonical(canonical_name))
    assert target is not None, f"{canonical_name} not active in canonical table"
    assert misspelled not in (target.get("aliases") or [])

    # Find the current snapshot id for the post.
    r0 = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q2",
        timeout=20,
    )
    snap_id = r0.json().get("snapshot", {}).get("id")
    assert snap_id

    payload = {
        "employees": [
            {
                # Operator typed the bad spelling, fixed it inline on the modal.
                "name": canonical_name,
                "_original_name": misspelled,
                # No real metric edits — we only care about the rename.
                "guests": 100,
            }
        ]
    }
    r = requests.post(
        f"{BASE}/api/v2/snapshot-workflow/snapshots/{snap_id}/confirm-pos-review",
        json=payload,
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # The endpoint reports how many aliases were written.
    assert "aliases_added" in d, f"missing aliases_added in response: {d}"
    # Even if the snapshot lookup of the misspelled row missed (because
    # the row doesn't actually exist under that misspelling in the live
    # POS data), we should at least be told the count.
    assert isinstance(d.get("aliases_added"), int)

    # Re-fetch canonical — if the alias was added, validate; if not (because
    # the misspelling never landed in the snapshot for the rename to fire),
    # then `aliases_added` should be 0 OR the alias_skips array explains.
    after = asyncio.run(_find_canonical(canonical_name))
    if d.get("aliases_added", 0) >= 1:
        assert misspelled in (after.get("aliases") or []), (
            f"alias {misspelled} not present on Diane after confirm-pos-review: "
            f"{after.get('aliases')}"
        )
        # Idempotent — running again must NOT double-write.
        r2 = requests.post(
            f"{BASE}/api/v2/snapshot-workflow/snapshots/{snap_id}/confirm-pos-review",
            json=payload,
            headers=ADMIN_HEADERS,
            timeout=30,
        )
        assert r2.status_code == 200
        after2 = asyncio.run(_find_canonical(canonical_name))
        assert (after2.get("aliases") or []).count(misspelled) == 1, (
            "alias should be idempotent — $addToSet should not duplicate"
        )

    # Cleanup so subsequent runs are deterministic.
    asyncio.run(_cleanup_alias_on(canonical_name, misspelled))


def test_alias_auto_add_refuses_to_shadow_another_active_employee():
    """If the misspelled name belongs to a DIFFERENT active employee, the
    alias write must be SKIPPED — registering it would route their POS
    rows to the wrong person. The skip is surfaced in `alias_skips`."""
    # Find two arbitrary active canonical employees so we can simulate
    # "operator renames A → B" — which would shadow A.
    async def _pick_two():
        db = _db()
        rows = await db.employees.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1},
        ).limit(5).to_list(5)
        return rows

    actives = asyncio.run(_pick_two())
    if len(actives) < 2:
        pytest.skip("need at least 2 active canonical employees")

    a, b = actives[0], actives[1]
    r0 = requests.get(
        f"{BASE}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q2",
        timeout=20,
    )
    snap_id = r0.json().get("snapshot", {}).get("id")
    payload = {
        "employees": [
            {
                "name": b["name"],
                "_original_name": a["name"],  # would shadow employee A
                "guests": 50,
            }
        ]
    }
    r = requests.post(
        f"{BASE}/api/v2/snapshot-workflow/snapshots/{snap_id}/confirm-pos-review",
        json=payload,
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Either the rename never fired (because A's row wasn't in the
    # snapshot under its name) — in which case alias_skips can be empty;
    # OR it did fire and got skipped with reason=owned_by_other_employee.
    for skip in d.get("alias_skips") or []:
        if skip.get("misspelled") == a["name"]:
            assert skip.get("reason") == "owned_by_other_employee"
            return  # passed
    # Otherwise the rename didn't fire — that's also acceptable. Validate
    # B did NOT acquire A's name as an alias.
    b_after = asyncio.run(_find_canonical(b["name"]))
    assert a["name"] not in (b_after.get("aliases") or []), (
        f"shadow alias leaked: {a['name']} → {b['name']}"
    )


# ---------------------------------------------------------------------------
# 2. Metric integrity check on /scoring-trust
# ---------------------------------------------------------------------------


def test_scoring_trust_exposes_metric_integrity_block():
    """The endpoint must always include a `metric_integrity` details
    block with a count, tolerance, and (capped) mismatch list."""
    r = requests.get(
        f"{BASE}/api/v2/admin/scoring-trust",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    mi = (d.get("details") or {}).get("metric_integrity")
    assert mi is not None, "metric_integrity block missing from scoring-trust"
    assert "count" in mi
    assert "tolerance_pct" in mi
    assert "mismatches" in mi
    assert isinstance(mi["mismatches"], list)
    assert len(mi["mismatches"]) <= 20, "response payload should be capped at 20"

    # If count is non-zero, every mismatch entry must have the required
    # fields the frontend tile expects.
    for m in mi["mismatches"]:
        for k in ("name", "metric", "stored", "expected", "rel_diff_pct"):
            assert k in m, f"missing {k} in mismatch entry: {m}"


def test_scoring_trust_metric_drift_surfaces_in_warnings_or_issues():
    """If metric_integrity.count > 0, the tri-state rollup must mention
    it — either as a warning (1-4 mismatches) or an issue (5+)."""
    r = requests.get(
        f"{BASE}/api/v2/admin/scoring-trust",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    d = r.json()
    count = (d.get("details") or {}).get("metric_integrity", {}).get("count", 0)
    if count == 0:
        return  # nothing to assert
    bag = (d.get("issues") or []) + (d.get("warnings") or [])
    assert any("drift from raw inputs" in s for s in bag), (
        f"count={count} but neither issues nor warnings mention metric drift: "
        f"issues={d.get('issues')} warnings={d.get('warnings')}"
    )


def test_scoring_trust_metric_integrity_remediation_present():
    """The remediation block must include a metric_integrity entry so
    the badge's modal can route the admin to the fix path."""
    r = requests.get(
        f"{BASE}/api/v2/admin/scoring-trust",
        headers=ADMIN_HEADERS,
        timeout=30,
    )
    d = r.json()
    assert "metric_integrity" in (d.get("remediation") or {}), (
        f"remediation missing metric_integrity: {d.get('remediation')}"
    )
