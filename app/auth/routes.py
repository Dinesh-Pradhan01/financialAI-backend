"""
Auth API routes.

- POST /auth/sync   — Sync the currently authenticated Firebase user to the local DB, create a session, and set cookie
- GET  /auth/me     — Return the current user's profile based on session cookie
- POST /auth/logout — Revoke session and clear cookie
"""

import logging
import os
import uuid

from fastapi import APIRouter, Depends, Response, Request, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
from firebase_admin import auth as firebase_auth

from app.auth.dependencies import get_firebase_synced_user, get_current_session_user
from app.auth.firebase import verify_firebase_token
from app.auth.model import User, UserResponse, GoogleTokenPayload
from app.auth.service import create_session, revoke_session, update_last_login, get_or_create_user
from app.database.connection import get_db
from app.config import settings
from app.email_service.service import send_email_async

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


# ---------------------------------------------------------------------------
# Manual HR / CFO Invite Endpoints (CEO / Admin functionality)
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.auth.dependencies import require_role
from app.business.invite_model import TeamInvite
from app.business.invite_service import generate_invite_token, generate_invite_email, create_invite_audit_log
from app.auth.service import revoke_all_user_sessions
from app.auth.model import Role, UserRole

class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # 'hr' or 'cfo'
    full_name: str = ""

class InviteAcceptPasswordRequest(BaseModel):
    token: str
    password: str
    email: EmailStr
    full_name: str = ""

class TeamInviteItemResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    status: str
    invite_token: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    updated_at: Optional[str] = None
    message: Optional[str] = None

    model_config = {"from_attributes": True}


@router.post(
    "/invite",
    summary="CEO/Admin manual invitation of HR or CFO",
    description="Considers logged in user as CEO/Admin and sends an invite email to specified HR or CFO email address with 24-hour expiration.",
)
async def create_role_invite(
    payload: InviteRequest,
    current_user: User = Depends(require_role("ceo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    role_clean = payload.role.strip().lower()
    if role_clean not in ["hr", "cfo"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Designated role must be either 'hr' or 'cfo'."
        )

    # Resolve business_id from current_user
    business_id = current_user.business_id
    if not business_id:
        from app.business.models import GeneralInfo
        biz = GeneralInfo(
            company_name="My Company",
            business_category="Services",
            business_type="LLP",
            business_pan="AAAAA0000A",
            registered_address="Address",
            state="State",
            city="City",
            pincode="000000",
            official_email=current_user.email,
            official_phone="0000000000",
            onboarding_completed=False
        )
        db.add(biz)
        await db.flush()
        business_id = biz.id
        current_user.business_id = business_id
        await db.flush()
        await db.flush()

    # Get company name
    from app.business.models import GeneralInfo
    biz_stmt = select(GeneralInfo).where(GeneralInfo.id == business_id)
    biz_res = await db.execute(biz_stmt)
    biz_obj = biz_res.scalar_one_or_none()
    company_name = biz_obj.company_name if biz_obj else "Company"

    now = datetime.utcnow()
    expires_at = now + timedelta(hours=24)

    # Check for existing invite for this email
    existing_stmt = select(TeamInvite).where(
        TeamInvite.business_id == business_id,
        TeamInvite.email == payload.email
    )
    res = await db.execute(existing_stmt)
    invite = res.scalar_one_or_none()

    token = generate_invite_token()

    if invite:
        invite.role = role_clean
        invite.full_name = payload.full_name or payload.email.split("@")[0]
        invite.invite_token = token
        invite.status = "pending"
        invite.expires_at = expires_at
        invite.updated_at = now
    else:
        invite = TeamInvite(
            business_id=business_id,
            invited_by_user_id=current_user.id,
            role=role_clean,
            full_name=payload.full_name or payload.email.split("@")[0],
            email=payload.email,
            invite_token=token,
            status="pending",
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        db.add(invite)

    await db.flush()

    await create_invite_audit_log(
        db=db,
        invite_id=invite.id,
        business_id=business_id,
        actor_user_id=current_user.id,
        action="send",
        target_email=payload.email,
        details={"role": role_clean}
    )
    
    vlink = await generate_invite_email(
        email=payload.email,
        full_name=invite.full_name,
        role=role_clean,
        invite_token=token,
        company_name=company_name
    )
    #send email via sendgrid
    try:
        cntxt = {"action_url": vlink, "role":role_clean.upper(),
                 "org_name":company_name if company_name else "SpotLite Platform"}
        rspns = await send_email_async(payload.email,"user_invitation","User Invitation",cntxt)

        logger.info(
            "=========================="
            "SendGrid Email Service Status : \n"
            "%s\n"
            "==========================",
            rspns
        )
    except Exception as e:
        logger.warning(f"Encountered : {e}")

    return {
        "status": "success",
        "message": f"Invitation sent to {payload.email} as {role_clean.upper()}.",
        "invite_id": str(invite.id),
        "email": payload.email,
        "role": role_clean,
        "invite_token": token,
        "expires_at": expires_at.isoformat(),
        "invite_link": vlink
    }


@router.get(
    "/invites",
    summary="List all sent team invites for CEO/Admin",
)
async def list_role_invites(
    current_user: User = Depends(require_role("ceo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TeamInvite).where(TeamInvite.invited_by_user_id == current_user.id)
    if current_user.business_id:
        stmt = select(TeamInvite).where(
            (TeamInvite.invited_by_user_id == current_user.id) | (TeamInvite.business_id == current_user.business_id)
        )
    res = await db.execute(stmt)
    invites = res.scalars().all()

    now = datetime.utcnow()
    result = []
    for inv in invites:
        is_expired = inv.expires_at is not None and now > inv.expires_at
        result.append({
            "id": str(inv.id),
            "email": inv.email,
            "full_name": inv.full_name,
            "role": inv.role,
            "status": "expired" if (is_expired and inv.status == "pending") else inv.status,
            "invite_token": inv.invite_token,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        })
    return result


@router.delete(
    "/invite/{invite_id}",
    response_model=TeamInviteItemResponse,
    summary="CEO/Admin revoke a pending or expired invitation (R8-1)",
    description="Soft-deletes the invitation by setting status='revoked'. Retains row for audit history.",
)
async def revoke_invite(
    invite_id: uuid.UUID,
    current_user: User = Depends(require_role("ceo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TeamInvite).where(TeamInvite.id == invite_id)
    if current_user.business_id:
        stmt = stmt.where(
            (TeamInvite.business_id == current_user.business_id) | (TeamInvite.invited_by_user_id == current_user.id)
        )
    else:
        stmt = stmt.where(TeamInvite.invited_by_user_id == current_user.id)

    res = await db.execute(stmt)
    invite = res.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found."
        )

    if invite.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke an already accepted invitation. Use remove member instead."
        )
    if invite.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is already revoked."
        )
    if invite.status == "removed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Member was already removed."
        )

    previous_status = invite.status
    now = datetime.utcnow()
    invite.status = "revoked"
    invite.updated_at = now
    await db.flush()

    await create_invite_audit_log(
        db=db,
        invite_id=invite.id,
        business_id=invite.business_id,
        actor_user_id=current_user.id,
        action="revoke",
        target_email=invite.email,
        details={"previous_status": previous_status}
    )

    return TeamInviteItemResponse(
        id=str(invite.id),
        email=invite.email,
        full_name=invite.full_name,
        role=invite.role,
        status=invite.status,
        invite_token=invite.invite_token,
        created_at=invite.created_at.isoformat() if invite.created_at else None,
        expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
        updated_at=invite.updated_at.isoformat() if invite.updated_at else None,
        message="Invitation successfully revoked."
    )


@router.post(
    "/invite/{invite_id}/remove",
    response_model=TeamInviteItemResponse,
    summary="CEO/Admin remove an accepted team member (R8-2)",
    description="Disassociates member from business, resets role to 'user', revokes active sessions and Firebase tokens, and sets invite status='removed'.",
)
async def remove_team_member(
    invite_id: uuid.UUID,
    current_user: User = Depends(require_role("ceo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TeamInvite).where(TeamInvite.id == invite_id)
    if current_user.business_id:
        stmt = stmt.where(
            (TeamInvite.business_id == current_user.business_id) | (TeamInvite.invited_by_user_id == current_user.id)
        )
    else:
        stmt = stmt.where(TeamInvite.invited_by_user_id == current_user.id)

    res = await db.execute(stmt)
    invite = res.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found."
        )

    if invite.status != "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot remove member with invite status '{invite.status}'. Member must have accepted the invitation first."
        )

    # Find the corresponding User
    user_stmt = select(User).where(User.email == invite.email)
    user_res = await db.execute(user_stmt)
    target_user = user_res.scalar_one_or_none()

    if target_user and target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself from the business."
        )

    now = datetime.utcnow()
    revoked_sessions_count = 0

    if target_user:
        # Reset business association & role
        target_user.business_id = None
        target_user.invited_by_user_id = None
        target_user.role = UserRole.USER.value
        
        role_res = await db.execute(select(Role.id).where(Role.name == UserRole.USER.value))
        target_user.role_id = role_res.scalar_one_or_none()
        target_user.updated_at = now

        # Invalidate all active backend cookie sessions
        revoked_sessions_count = await revoke_all_user_sessions(db, target_user.id)

        # Invalidate Firebase tokens
        if target_user.firebase_id:
            try:
                firebase_auth.revoke_refresh_tokens(target_user.firebase_id)
                logger.info("Revoked Firebase refresh tokens for user %s", target_user.firebase_id)
            except Exception as e:
                logger.warning("Could not revoke Firebase refresh tokens for %s: %s", target_user.firebase_id, e)

    invite.status = "removed"
    invite.updated_at = now
    await db.flush()

    await create_invite_audit_log(
        db=db,
        invite_id=invite.id,
        business_id=invite.business_id,
        actor_user_id=current_user.id,
        action="remove",
        target_email=invite.email,
        details={
            "removed_user_id": target_user.id if target_user else None,
            "revoked_sessions_count": revoked_sessions_count,
        }
    )

    return TeamInviteItemResponse(
        id=str(invite.id),
        email=invite.email,
        full_name=invite.full_name,
        role=invite.role,
        status=invite.status,
        invite_token=invite.invite_token,
        created_at=invite.created_at.isoformat() if invite.created_at else None,
        expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
        updated_at=invite.updated_at.isoformat() if invite.updated_at else None,
        message=f"Member {invite.email} successfully removed from the organization."
    )


@router.post(
    "/invite/{invite_id}/resend",
    response_model=TeamInviteItemResponse,
    summary="CEO/Admin resend invitation",
)
async def resend_role_invite(
    invite_id: uuid.UUID,
    current_user: User = Depends(require_role("ceo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TeamInvite).where(TeamInvite.id == invite_id)
    if current_user.business_id:
        stmt = stmt.where(
            (TeamInvite.business_id == current_user.business_id) | (TeamInvite.invited_by_user_id == current_user.id)
        )
    else:
        stmt = stmt.where(TeamInvite.invited_by_user_id == current_user.id)

    res = await db.execute(stmt)
    invite = res.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found."
        )

    if invite.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite has already been accepted."
        )
    if invite.status == "removed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot resend invite for a removed member. Please create a new invitation."
        )

    # Get company name
    from app.business.models import GeneralInfo
    company_name = "SpotLite Platform"
    if invite.business_id:
        biz_stmt = select(GeneralInfo).where(GeneralInfo.id == invite.business_id)
        biz_res = await db.execute(biz_stmt)
        biz_obj = biz_res.scalar_one_or_none()
        if biz_obj and biz_obj.company_name:
            company_name = biz_obj.company_name

    now = datetime.utcnow()
    expires_at = now + timedelta(hours=24)
    token = generate_invite_token()

    invite.invite_token = token
    invite.status = "pending"
    invite.expires_at = expires_at
    invite.updated_at = now
    await db.flush()

    vlink = await generate_invite_email(
        email=invite.email,
        full_name=invite.full_name,
        role=invite.role,
        invite_token=token,
        company_name=company_name
    )

    try:
        cntxt = {"action_url": vlink, "role": invite.role.upper(), "org_name": company_name}
        await send_email_async(invite.email, "user_invitation", "User Invitation", cntxt)
    except Exception as e:
        logger.warning(f"Encountered SendGrid email error on resend: {e}")

    await create_invite_audit_log(
        db=db,
        invite_id=invite.id,
        business_id=invite.business_id,
        actor_user_id=current_user.id,
        action="resend",
        target_email=invite.email,
    )

    return TeamInviteItemResponse(
        id=str(invite.id),
        email=invite.email,
        full_name=invite.full_name,
        role=invite.role,
        status=invite.status,
        invite_token=invite.invite_token,
        created_at=invite.created_at.isoformat() if invite.created_at else None,
        expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
        updated_at=invite.updated_at.isoformat() if invite.updated_at else None,
        message="Invitation successfully resent."
    )


@router.get(
    "/invite/verify/{token}",
    summary="Verify invitation token and expiration",
)
async def verify_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TeamInvite).where(TeamInvite.invite_token == token)
    res = await db.execute(stmt)
    invite = res.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or link is invalid."
        )

    if invite.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link has already been used and accepted."
        )
    if invite.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has been revoked by the administrator."
        )
    if invite.status == "removed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This membership has been removed."
        )

    # Check 24-hour expiration
    now = datetime.utcnow()
    expires_at = invite.expires_at or (invite.created_at + timedelta(hours=24) if invite.created_at else None)
    if expires_at and now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link has expired (valid for 24 hours). Please request a new invitation."
        )

    from app.business.models import GeneralInfo
    biz_stmt = select(GeneralInfo).where(GeneralInfo.id == invite.business_id)
    biz_res = await db.execute(biz_stmt)
    biz = biz_res.scalar_one_or_none()

    return {
        "status": "valid",
        "invite_id": str(invite.id),
        "email": invite.email,
        "full_name": invite.full_name,
        "role": invite.role,
        "company_name": biz.company_name if biz else "SpotLite Platform",
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.post(
    "/invite/accept-with-password",
    summary="Set password and accept HR/CFO invitation",
)
async def accept_invite_with_password(
    payload: InviteAcceptPasswordRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TeamInvite).where(TeamInvite.invite_token == payload.token)
    res = await db.execute(stmt)
    invite = res.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or link is invalid."
        )

    if invite.status == "accepted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link has already been used and accepted."
        )
    if invite.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has been revoked by the administrator."
        )
    if invite.status == "removed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This membership has been removed."
        )


    now = datetime.utcnow()
    expires_at = invite.expires_at or (invite.created_at + timedelta(hours=24) if invite.created_at else None)
    if expires_at and now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link has expired (valid for 24 hours)."
        )

    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )

    target_email = payload.email.strip() if payload.email else invite.email
    target_name = payload.full_name.strip() if payload.full_name else invite.full_name

    # Create or fetch Firebase User using Firebase Admin SDK with fallback
    firebase_uid = f"usr_{uuid.uuid4().hex[:16]}"
    try:
        fb_user = firebase_auth.get_user_by_email(target_email)
        firebase_uid = fb_user.uid
        firebase_auth.update_user(firebase_uid, password=payload.password, email_verified=True)
    except firebase_auth.UserNotFoundError:
        try:
            new_fb_user = firebase_auth.create_user(
                email=target_email,
                password=payload.password,
                display_name=target_name,
                email_verified=True
            )
            firebase_uid = new_fb_user.uid
        except Exception as e:
            logger.warning("Firebase Admin create_user fallback: %s", e)
    except Exception as e:
        logger.warning("Firebase Admin error: %s", e)

    # Update or create User in PostgreSQL DB
    role_res = await db.execute(select(Role.id).where(Role.name == invite.role))
    role_id = role_res.scalar_one_or_none()

    user_stmt = select(User).where(User.email == invite.email)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if user:
        user.firebase_id = firebase_uid
        user.email = target_email
        user.role = invite.role
        user.role_id = role_id
        user.business_id = invite.business_id
        user.invited_by_user_id = invite.invited_by_user_id
        user.email_verified = False  # Pending email verification
        user.updated_at = now
    else:
        user = User(
            firebase_id=firebase_uid,
            email=target_email,
            email_verified=False,  # Pending email verification
            role=invite.role,
            role_id=role_id,
            business_id=invite.business_id,
            invited_by_user_id=invite.invited_by_user_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)

    invite.status = "accepted"
    invite.accepted_at = now
    await db.flush()

    await create_invite_audit_log(
        db=db,
        invite_id=invite.id,
        business_id=invite.business_id,
        actor_user_id=user.id,
        action="accept",
        target_email=target_email,
        details={"accepted_role": invite.role}
    )

    from app.business.models import GeneralInfo
    biz_stmt = select(GeneralInfo).where(GeneralInfo.id == invite.business_id)
    biz_res = await db.execute(biz_stmt)
    biz = biz_res.scalar_one_or_none()

    # Generate verification link
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:8080")
    verification_link = f"{frontend_url}/verify-email?email={target_email}"
    
    try:
        fb_link = firebase_auth.generate_email_verification_link(target_email)
        logger.info("Firebase verification link generated: %s", fb_link)
        
    except Exception:
        pass

    logger.info(
        "\n====================================================\n"
        "VERIFICATION MAIL FOR %s (%s)\n"
        "Email: %s\n"
        "Verification Link: %s\n"
        "====================================================",
        target_name, invite.role.upper(), target_email, verification_link
    )

    # Create session cookie
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    session_token = await create_session(db=db, user_id=user.id, ip_address=ip_address, user_agent=user_agent)
    await update_last_login(db, user)

    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )

    return UserResponse.from_user(user, profile_completed=True, full_name=target_name)


@router.post(
    "/verify-email",
    summary="Mark current user email as verified in database",
)
async def mark_email_verified(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.email_verified = True
    await db.flush()
    logger.info("User %s email_verified set to True", current_user.email)
    return {"status": "success", "email_verified": True, "user_id": current_user.id}


@router.get(
    "/verify-email-token/{email}",
    summary="Verification email link callback - sets is_verified/email_verified to True",
)
async def verify_email_token_callback(
    email: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.email == email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.email_verified = True
    await db.flush()
    logger.info("User %s verified via email link! email_verified=True", email)
    return {"status": "success", "message": f"Email {email} verified successfully.", "email_verified": True}

