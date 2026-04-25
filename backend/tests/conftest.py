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
