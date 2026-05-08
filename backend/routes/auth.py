"""
Authentication routes + session middleware.

Architecture:
  • Public READ access — all GET endpoints stay open so the rankings page
    can be shared as a public link.
  • Protected WRITE access — POST/PUT/DELETE endpoints under /api/v2/* are
    gated behind `require_admin` so only whitelisted Google emails can
    modify data.
  • Session storage — MongoDB `user_sessions` collection, 7-day rolling
    expiry. Session token is set as an httpOnly Secure SameSite=None cookie
    so it survives the cross-origin redirect from auth.emergentagent.com.

Whitelist: see ALLOWED_EMAILS below. Edit that list to grant additional
managers admin access.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel

from database import get_database


auth_router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Email whitelist — only these Google accounts get admin/edit privileges.
# Anyone else who logs in is treated as a viewer (effectively the same as
# being signed out for the purposes of write endpoints).
# ---------------------------------------------------------------------------
ALLOWED_EMAILS = {
    e.strip().lower()
    for e in (
        os.environ.get("ALLOWED_ADMIN_EMAILS")
        or "owner@intheweedscollective.com"
    ).split(",")
    if e.strip()
}


class AuthUser(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    is_admin: bool = False


class SessionRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_session_user(
    db,
    session_token: Optional[str],
    auth_header: Optional[str],
) -> Optional[AuthUser]:
    """Resolve a session_token (cookie or `Authorization: Bearer ...` header)
    to the underlying user document. Returns None if no/invalid/expired."""
    token = session_token
    if not token and auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        return None

    expires_at = sess.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            return None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        # Lazy cleanup of expired session
        await db.user_sessions.delete_one({"session_token": token})
        return None

    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        return None

    email = (user.get("email") or "").lower()
    return AuthUser(
        user_id=user["user_id"],
        email=user["email"],
        name=user.get("name") or user["email"],
        picture=user.get("picture"),
        is_admin=email in ALLOWED_EMAILS,
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies — used by protected routes
# ---------------------------------------------------------------------------

async def get_current_user(
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = None,
) -> Optional[AuthUser]:
    """Return the logged-in user (or None for anonymous)."""
    db = get_database()
    return await _get_session_user(db, session_token, authorization)


async def require_admin(request: Request) -> AuthUser:
    """Gate that 401s anonymous and 403s non-whitelisted users.

    Wired in as `Depends(require_admin)` on every state-changing route.
    """
    db = get_database()
    session_token = request.cookies.get("session_token")
    authorization = request.headers.get("authorization")
    user = await _get_session_user(db, session_token, authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required to make changes.",
        )
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{user.email} is not authorized to edit this app. Contact the owner to be added.",
        )
    return user


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@auth_router.post("/session")
async def create_session(payload: SessionRequest, response: Response):
    """Exchange a one-shot Emergent `session_id` (received in the URL fragment
    after Google auth) for a 7-day persistent `session_token` cookie.
    """
    if not payload.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    # Call Emergent's auth service from the BACKEND only (never the frontend).
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": payload.session_id},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Auth service unreachable: {exc}")

    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session_id")

    data = r.json()
    email = (data.get("email") or "").strip()
    name = data.get("name") or email
    picture = data.get("picture")
    session_token = data.get("session_token")
    if not email or not session_token:
        raise HTTPException(status_code=502, detail="Auth service returned incomplete data")

    db = get_database()
    # Upsert the user (don't create a duplicate if they've signed in before).
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture, "last_login_at": datetime.now(timezone.utc)}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "created_at": datetime.now(timezone.utc),
            "last_login_at": datetime.now(timezone.utc),
        })

    # Persist the session.
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    })

    # httpOnly cookie that survives the cross-origin redirect from
    # auth.emergentagent.com. samesite=None requires secure=True.
    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )

    is_admin = email.lower() in ALLOWED_EMAILS
    return {
        "user_id": user_id,
        "email": email,
        "name": name,
        "picture": picture,
        "is_admin": is_admin,
    }


@auth_router.get("/me")
async def get_me(request: Request):
    """Return the current logged-in user (or 401 if not authenticated).

    Used by the React AuthContext to decide whether to show the login splash
    or the app shell on initial page load.
    """
    db = get_database()
    user = await _get_session_user(
        db,
        request.cookies.get("session_token"),
        request.headers.get("authorization"),
    )
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user.dict()


@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """Delete the server-side session and clear the cookie."""
    token = request.cookies.get("session_token")
    if token:
        db = get_database()
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
    return {"success": True}
