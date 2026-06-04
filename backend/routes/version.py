"""
Build version endpoint — exposes the running container's git SHA,
commit timestamp, and process-start time so operators can verify with
a glance whether a deploy actually landed.

Pain point this solves: the user has clicked Deploy multiple times in
the past week with no visible change on `intheweedscollective.com`,
and had no objective way to check whether the live site was running
the latest code. A tiny chip in the corner now answers that question
in one look.

Approach
--------
On the very first request the endpoint shells out to `git log -1` /
`git rev-parse` against the running working tree, caches the result
in-process (the running container never changes its own commit), and
returns:

    {
      "sha":          "97cd509",          # short SHA
      "sha_full":     "97cd509abc...",
      "branch":       "main",
      "committed_at": "2026-06-04T22:40:52+00:00",
      "subject":      "auto-commit for ...",
      "started_at":   "2026-06-04T22:41:18Z",  # process boot time
    }

If git is unavailable (e.g. someone strips .git on a production
image), the endpoint degrades to `"sha": "unknown"` with the
process-start timestamp so the chip still answers "did I redeploy?"
based on `started_at`.

The endpoint is public on purpose — it's the same info we want the
user to paste into a support email. No secrets are exposed.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

version_router = APIRouter(tags=["Version"])

# Captured once, the first time anyone calls /version. The container's
# git state doesn't change during its lifetime so this is safe to cache.
_cached: Optional[Dict[str, str]] = None
_started_at = datetime.now(timezone.utc).isoformat()


def _git(*args) -> Optional[str]:
    """Run a git command and return stdout, or None if anything fails.

    Run from /app where the repo lives. We don't want a noisy stderr
    leaking into supervisor logs, hence `stderr=DEVNULL`.
    """
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd="/app",
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return out.decode("utf-8").strip() or None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def _read_version() -> Dict[str, str]:
    global _cached
    if _cached is not None:
        return _cached

    sha       = _git("rev-parse", "--short", "HEAD") or "unknown"
    sha_full  = _git("rev-parse", "HEAD") or "unknown"
    branch    = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    committed = _git("log", "-1", "--format=%cI") or None
    subject   = _git("log", "-1", "--format=%s") or None

    _cached = {
        "sha":          sha,
        "sha_full":     sha_full,
        "branch":       branch,
        "committed_at": committed,
        "subject":      (subject or "")[:140],  # cap for chip display
        "started_at":   _started_at,
        # Helpful when triaging the recurring deploy-sync issue — lets
        # the user tell at a glance whether they're hitting prod, the
        # preview, or something exotic.
        "hostname":     os.environ.get("HOSTNAME", "unknown"),
        "env":          os.environ.get("EMERGENT_ENV", "preview"),
    }
    return _cached


@version_router.get("/version")
async def get_version() -> Dict[str, str]:
    """Public — no auth gating. Same info you'd paste into a support
    email, no secrets exposed. Used by the on-screen version chip."""
    return _read_version()
