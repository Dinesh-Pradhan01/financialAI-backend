import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.business.invite_model import TeamInvite
from app.business.invite_service import create_invite_audit_log
from app.auth.model import User, UserRole, Role
from app.auth.dependencies import get_current_session_user
from app.business.models import GeneralInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invite", tags=["invites"])

from datetime import datetime, timedelta

@router.get("/verify/{token}")
async def verify_invite_token(token: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(TeamInvite).where(TeamInvite.invite_token == token))
    invite = res.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or invalid.")
    
    if invite.status == "accepted":
        raise HTTPException(status_code=400, detail="Invite has already been accepted.")
    if invite.status == "revoked":
        raise HTTPException(status_code=400, detail="This invitation has been revoked by the administrator.")
    if invite.status == "removed":
        raise HTTPException(status_code=400, detail="This membership has been removed.")
        
    now = datetime.utcnow()
    expires_at = invite.expires_at or (invite.created_at + timedelta(hours=24) if invite.created_at else None)
    if expires_at and now > expires_at:
        raise HTTPException(status_code=400, detail="Invitation link has expired (valid for 24 hours). Please request a new invitation.")

    biz_res = await db.execute(select(GeneralInfo).where(GeneralInfo.id == invite.business_id))
    biz = biz_res.scalar_one_or_none()
    
    return {
        "status": "success",
        "invite_id": invite.id,
        "role": invite.role,
        "full_name": invite.full_name,
        "email": invite.email,
        "company_name": biz.company_name if biz else "Unknown Company",
        "expires_at": expires_at.isoformat() if expires_at else None,
    }

@router.post("/accept/{token}")
async def accept_invite(token: str, current_user: User = Depends(get_current_session_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(TeamInvite).where(TeamInvite.invite_token == token))
    invite = res.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or invalid.")
        
    if invite.status == "accepted":
        raise HTTPException(status_code=400, detail="Invite has already been accepted.")
    if invite.status == "revoked":
        raise HTTPException(status_code=400, detail="This invitation has been revoked by the administrator.")
    if invite.status == "removed":
        raise HTTPException(status_code=400, detail="This membership has been removed.")

    now = datetime.utcnow()
    expires_at = invite.expires_at or (invite.created_at + timedelta(hours=24) if invite.created_at else None)
    if expires_at and now > expires_at:
        raise HTTPException(status_code=400, detail="Invitation link has expired (valid for 24 hours).")

    # Mark invite accepted
    invite.status = "accepted"
    invite.accepted_at = now
    
    # Update user role and link to business
    if invite.role == "cfo":
        current_user.role = UserRole.CFO.value
    elif invite.role == "hr":
        current_user.role = UserRole.HR.value
    else:
        current_user.role = invite.role

    role_res = await db.execute(select(Role.id).where(Role.name == current_user.role))
    current_user.role_id = role_res.scalar_one_or_none()
        
    current_user.business_id = invite.business_id
    current_user.invited_by_user_id = invite.invited_by_user_id
    
    await db.flush()

    await create_invite_audit_log(
        db=db,
        invite_id=invite.id,
        business_id=invite.business_id,
        actor_user_id=current_user.id,
        action="accept",
        target_email=invite.email,
        details={"role": invite.role}
    )

    return {"status": "success", "message": f"Successfully joined as {invite.role.upper()}."}

