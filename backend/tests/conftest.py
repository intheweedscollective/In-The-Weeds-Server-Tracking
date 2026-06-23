"""
Shared pytest configuration for backend tests.

Loads /app/backend/.env automatically so MONGO_URL / DB_NAME / REACT_APP_BACKEND_URL
are available to tests without forcing the user to export them manually.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend env first (DB credentials)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
# Then frontend env (REACT_APP_BACKEND_URL) — backend wins on conflicts
frontend_env = Path(__file__).resolve().parent.parent.parent / "frontend" / ".env"
if frontend_env.exists():
    # Don't override values already loaded from backend/.env
    load_dotenv(frontend_env, override=False)

# Sanity: surface a clear error if required vars are missing
for required in ("MONGO_URL", "DB_NAME"):
    if not os.environ.get(required):
        raise RuntimeError(
            f"{required} is not set. Tests need backend/.env to load correctly."
        )


# ---------------------------------------------------------------------------
# Admin session fixture
# ---------------------------------------------------------------------------
# The recon / admin routes now go through `require_admin` (cookie OR
# Bearer header → user_sessions → user → ALLOWED_ADMIN_EMAILS). For
# tests to call those endpoints we seed one valid session at import
# time and expose its token via `ADMIN_TOKEN` / the `admin_headers`
# fixture. The session is shared across the whole test run and
# cleaned up at process exit.

import asyncio as _asyncio
import atexit as _atexit
import uuid as _uuid
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

import pytest as _pytest
from motor.motor_asyncio import AsyncIOMotorClient as _Motor

_ADMIN_EMAIL = (
    (os.environ.get("ALLOWED_ADMIN_EMAILS", "").split(",") or [""])[0]
).strip().lower() or "owner@intheweedscollective.com"
_ADMIN_USER_ID = "test-admin-" + _uuid.uuid4().hex[:8]
ADMIN_TOKEN = "test-session-" + _uuid.uuid4().hex


def _seed_admin_session():
    """Insert an admin user + a 7-day session for the test run."""
    async def _go():
        db = _Motor(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.users.update_one(
            {"user_id": _ADMIN_USER_ID},
            {"$set": {
                "user_id": _ADMIN_USER_ID,
                "email":   _ADMIN_EMAIL,
                "name":    "Test Admin",
                "picture": None,
            }},
            upsert=True,
        )
        await db.user_sessions.insert_one({
            "session_token": ADMIN_TOKEN,
            "user_id":       _ADMIN_USER_ID,
            "expires_at":    _dt.now(_tz.utc) + _td(days=7),
            "created_at":    _dt.now(_tz.utc),
        })
    _asyncio.run(_go())


def _wipe_admin_session():
    async def _go():
        db = _Motor(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.user_sessions.delete_many({"session_token": ADMIN_TOKEN})
        await db.users.delete_one({"user_id": _ADMIN_USER_ID})
    try:
        _asyncio.run(_go())
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass


_seed_admin_session()
_atexit.register(_wipe_admin_session)


@_pytest.fixture(scope="session")
def admin_headers():
    """`Authorization` headers good for the recon/admin routes."""
    return {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type":  "application/json",
    }
