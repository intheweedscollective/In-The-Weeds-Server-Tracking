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
Resolution order — first hit wins:

1. `/app/backend/.version.json` (preferred for production)
   Written at backend startup whenever git IS available (i.e. in the
   preview environment). The deploy pipeline copies this file along
   with the rest of /app/backend/, so production reads the SHA that
   was current at the moment the deploy was packaged.

   This is the ONLY path that works in production — the prod container
   strips `.git`, so `git rev-parse` returns nothing. Before this
   file-based fallback the prod chip showed all "unknown" / empty
   values, which is exactly what the operator reported.

2. Live `git log` against /app (works in preview, fails in prod).

3. Final fallback: `sha="unknown"` with `started_at` populated. The
   chip still answers "did I redeploy?" via the process-start
   timestamp even when everything else is unavailable.

If git is unavailable AND the version file is missing the endpoint
still returns a useful payload — never errors out.

The endpoint is public on purpose — it's the same info we want the
user to paste into a support email. No secrets are exposed.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

version_router = APIRouter(tags=["Version"])

VERSION_FILE = Path("/app/backend/.version.json")

# Captured once, the first time anyone calls /version. The container's
# git state doesn't change during its lifetime so this is safe to cache.
_cached: Optional[Dict[str, Any]] = None
_started_at = datetime.now(timezone.utc).isoformat()


def _git(*args) -> Optional[str]:
    """Run a git command and return stdout, or None if anything fails."""
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


def _from_git() -> Optional[Dict[str, Any]]:
    """Pull the version triple straight from `git`. Used both at
    /version request time (preview) AND at backend startup to write
    the version file consumed in production."""
    sha = _git("rev-parse", "--short", "HEAD")
    if not sha:
        return None
    return {
        "sha":          sha,
        "sha_full":     _git("rev-parse", "HEAD") or sha,
        "branch":       _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "committed_at": _git("log", "-1", "--format=%cI"),
        "subject":      (_git("log", "-1", "--format=%s") or "")[:140],
    }


def _from_file() -> Optional[Dict[str, Any]]:
    """Read the version JSON that backend startup baked into the
    deploy artifact. Survives the prod container's stripped .git."""
    try:
        if not VERSION_FILE.exists():
            return None
        with VERSION_FILE.open() as f:
            data = json.load(f)
        # Tag the source so support diagnostics know where the SHA came
        # from — useful when triaging a chip that shows "unknown".
        data.setdefault("source", "version_file")
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("could not read %s: %s", VERSION_FILE, e)
        return None


def write_version_file() -> None:
    """Called from server.py startup. In environments where git is
    available (preview), captures the current SHA into
    /app/backend/.version.json so production — where git is stripped
    — can still answer /api/version correctly after the next deploy.

    No-op when git isn't available."""
    info = _from_git()
    if not info:
        return
    info["written_at"] = datetime.now(timezone.utc).isoformat()
    try:
        VERSION_FILE.write_text(json.dumps(info, indent=2) + "\n")
        logger.info(
            "wrote build version sha=%s branch=%s → %s",
            info["sha"], info["branch"], VERSION_FILE,
        )
    except OSError as e:
        logger.warning("could not write %s: %s", VERSION_FILE, e)


def _read_version() -> Dict[str, Any]:
    global _cached
    if _cached is not None:
        return _cached

    # File first so the prod container — which has no .git — gets the
    # SHA that was current at deploy-packaging time.
    info = _from_file() or _from_git() or {}

    _cached = {
        "sha":          info.get("sha")          or "unknown",
        "sha_full":     info.get("sha_full")     or "unknown",
        "branch":       info.get("branch")       or "unknown",
        "committed_at": info.get("committed_at"),
        "subject":      (info.get("subject") or "")[:140],
        "started_at":   _started_at,
        "hostname":     os.environ.get("HOSTNAME", "unknown"),
        "env":          os.environ.get("EMERGENT_ENV", "preview"),
        "source":       info.get("source") or ("git" if info else "none"),
    }
    return _cached


@version_router.get("/version")
async def get_version() -> Dict[str, Any]:
    """Public — no auth gating. Same info you'd paste into a support
    email, no secrets exposed. Used by the on-screen version chip."""
    return _read_version()
