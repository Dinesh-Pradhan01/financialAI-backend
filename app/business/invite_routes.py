import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.business.invite_model import TeamInvite
from app.auth.model import User, UserRole
from app.auth.dependencies import get_current_session_user
from app.business.models import GeneralInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invite", tags=["invites"])

@router.get("/verify/{token}")
async def verify_invite_token(token: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(TeamInvite).where(TeamInvite.invite_token == token))
    invite = res.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or invalid.")
    
    if invite.status == "accepted":
        raise HTTPException(status_code=400, detail="Invite has already been accepted.")
        
    biz_res = await db.execute(select(GeneralInfo).where(GeneralInfo.id == invite.business_id))
    biz = biz_res.scalar_one_or_none()
    
    return {
        "status": "success",
        "invite_id": invite.id,
        "role": invite.role,
        "full_name": invite.full_name,
        "email": invite.email,
        "company_name": biz.company_name if biz else "Unknown Company"
    }

@router.post("/accept/{token}")
async def accept_invite(token: str, current_user: User = Depends(get_current_session_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(TeamInvite).where(TeamInvite.invite_token == token))
    invite = res.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or invalid.")
        
    if invite.status == "accepted":
        raise HTTPException(status_code=400, detail="Invite has already been accepted.")

    # Mark invite accepted
    invite.status = "accepted"
    invite.accepted_at = datetime.utcnow()
    
    # Update user role and link to business
    if invite.role == "cfo":
        current_user.role = UserRole.CFO.value
    elif invite.role == "hr":
        current_user.role = UserRole.HR.value
        
    current_user.business_id = invite.business_id
    current_user.invited_by_user_id = invite.invited_by_user_id
    
    await db.flush()
    return {"status": "success", "message": f"Successfully joined as {invite.role.upper()}."}
