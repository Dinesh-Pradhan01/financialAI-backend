import secrets
import logging
import firebase_admin
from firebase_admin import auth
from app.config import settings

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
