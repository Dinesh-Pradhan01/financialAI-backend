"""
Auth API routes.

- POST /auth/sync   — Sync the currently authenticated Firebase user to the local DB, create a session, and set cookie
- GET  /auth/me     — Return the current user's profile based on session cookie
- POST /auth/logout — Revoke session and clear cookie
"""

import logging
import os

from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_firebase_synced_user, get_current_session_user
from app.auth.model import User, UserResponse
from app.auth.service import create_session, revoke_session, update_last_login
from app.database.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "session"
# On localhost (HTTP), Secure must be False or the browser silently drops the cookie.
# In production (HTTPS), set ENVIRONMENT=production in your .env.
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"


@router.post(
    "/sync",
    response_model=UserResponse,
    summary="Sync Firebase user to local database and create session",
    description=(
        "Called by the frontend after a user logs in or registers. "
        "Creates the user in the local database if they don't already exist, "
        "creates a backend session, and sets an HTTP-only cookie."
    ),
)
async def sync_user(
    request: Request,
    response: Response,
    current_user: User = Depends(get_firebase_synced_user),
    db: AsyncSession = Depends(get_db),
):
    """
    The get_firebase_synced_user dependency handles the upsert logic.
    We create a session and set the cookie here.
    """
    # Create backend session
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    session_token = await create_session(
        db=db,
        user_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Update last login
    await update_last_login(db, current_user)

    # Set HTTP-only cookie.
    # - secure=False on localhost (HTTP) so the cookie is actually set.
    # - samesite="lax" is required for cross-port local dev (different ports = different origins).
    #   "strict" blocks cookies on cross-origin requests entirely.
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
        path="/",
    )

    profile_completed = False
    if current_user.person_id:
        from app.database.models import Person
        stmt = select(Person.profile_completed).where(Person.id == current_user.person_id)
        res = await db.execute(stmt)
        profile_completed = res.scalar_one_or_none() or False

    user_resp = UserResponse.model_validate(current_user)
    user_resp.profile_completed = profile_completed
    return user_resp


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    profile_completed = False
    if current_user.person_id:
        from app.database.models import Person
        stmt = select(Person.profile_completed).where(Person.id == current_user.person_id)
        res = await db.execute(stmt)
        profile_completed = res.scalar_one_or_none() or False

    user_resp = UserResponse.model_validate(current_user)
    user_resp.profile_completed = profile_completed
    return user_resp


@router.post(
    "/logout",
    summary="Logout and revoke session",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    session_token = request.cookies.get(COOKIE_NAME)
    if session_token:
        await revoke_session(db, session_token)

    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="lax",
        path="/",
    )

    return {"success": True}
