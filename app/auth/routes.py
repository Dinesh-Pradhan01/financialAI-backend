"""
Auth API routes.

- POST /auth/sync   — Sync the currently authenticated Firebase user to the local DB, create a session, and set cookie
- GET  /auth/me     — Return the current user's profile based on session cookie
- POST /auth/logout — Revoke session and clear cookie
"""

import logging
import os

from fastapi import APIRouter, Depends, Response, Request, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
from firebase_admin import auth as firebase_auth

from app.auth.dependencies import get_firebase_synced_user, get_current_session_user
from app.auth.firebase import verify_firebase_token
from app.auth.model import User, UserResponse, GoogleTokenPayload
from app.auth.service import create_session, revoke_session, update_last_login, get_or_create_user
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
    full_name = None
    
    if current_user.business_id:
        from app.business.models import GeneralInfo, LeadershipInfo
        stmt = select(GeneralInfo.onboarding_completed, LeadershipInfo.founder_ceo_name).outerjoin(
            LeadershipInfo, LeadershipInfo.business_id == GeneralInfo.id
        ).where(GeneralInfo.id == current_user.business_id)
        res = await db.execute(stmt)
        row = res.fetchone()
        if row:
            profile_completed = row[0] or False
            full_name = row[1]

    logger.info(
        "SYNC response for user %s: profile_completed=%s, business_id=%s",
        current_user.email, profile_completed, current_user.business_id,
    )

    return UserResponse.from_user(current_user, profile_completed=profile_completed, full_name=full_name)

@router.post(
    "/google",
    summary="Sign in with Google",
    description="Verify Google Firebase token, sync user to db, and create session.",
)
async def google_sign_in(
    payload: GoogleTokenPayload,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        decoded = await verify_firebase_token(payload.token)
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    except Exception as e:
        logger.error("Google token verification failed: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed.")

    uid = decoded.get("uid")
    email = decoded.get("email")

    if not uid or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing uid or email.")

    # Sync against the internal PostgreSQL database
    user = await get_or_create_user(
        db=db,
        firebase_id=uid,
        email=email,
        email_verified=decoded.get("email_verified", True)
    )
    
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    # Create backend session
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    session_token = await create_session(
        db=db,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await update_last_login(db, user)

    # Set HTTP-only cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )

    return {"status": "success", "uid": uid, "email": email}


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
    full_name = None
    
    if current_user.business_id:
        from app.business.models import GeneralInfo, LeadershipInfo
        stmt = select(GeneralInfo.onboarding_completed, LeadershipInfo.founder_ceo_name).outerjoin(
            LeadershipInfo, LeadershipInfo.business_id == GeneralInfo.id
        ).where(GeneralInfo.id == current_user.business_id)
        res = await db.execute(stmt)
        row = res.fetchone()
        if row:
            profile_completed = row[0] or False
            full_name = row[1]

    return UserResponse.from_user(current_user, profile_completed=profile_completed, full_name=full_name)


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
