import secrets
import logging
import uuid
from typing import Optional, Dict, Any
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession


from app.config import settings
from app.business.models import TeamInviteAuditLog

logger = logging.getLogger(__name__)

def generate_invite_token() -> str:
    '''Generates token: str(32)'''
    return secrets.token_urlsafe(32)

async def generate_invite_email(email: str, full_name: str, role: str, invite_token: str, company_name: str):
    '''
    Generates an invite link with a validation token.
    Token should be registered in TeamInvite.
    '''
    
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:8080")
    direct_link = f"{frontend_url}/accept-invite/{invite_token}"
    
    logger.info(f"\n"
                f"====================================================\n"
                f"INVITE LINK GENERATED FOR {full_name} ({role.upper()})\n"
                f"Company: {company_name}\n"
                f"Email: {email}\n"
                f"Link: {direct_link}\n"
                f"====================================================")
                
    return direct_link


async def create_invite_audit_log(
    db: AsyncSession,
    invite_id: uuid.UUID,
    actor_user_id: Optional[int],
    action: str,
    target_email: Optional[str] = None,
    business_id: Optional[uuid.UUID] = None,
    details: Optional[Dict[str, Any]] = None,
) -> TeamInviteAuditLog:
    """Record an audit log entry for team invite and member state changes."""
    log = TeamInviteAuditLog(
        invite_id=invite_id,
        business_id=business_id,
        actor_user_id=actor_user_id,
        action=action,
        target_email=target_email,
        details=details,
    )
    db.add(log)
    await db.flush()
    return log

