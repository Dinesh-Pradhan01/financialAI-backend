import secrets
import logging
import firebase_admin
from firebase_admin import auth
from app.config import settings

logger = logging.getLogger(__name__)

def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)

async def send_invite_email(email: str, full_name: str, role: str, invite_token: str, company_name: str):
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    action_code_settings = auth.ActionCodeSettings(
        url=f"{frontend_url}/accept-invite?token={invite_token}",
        handle_code_in_app=True,
    )
    
    try:
        # Use Firebase to generate an email link
        link = auth.generate_sign_in_with_email_link(email, action_code_settings)
        
        # In a real app, you would send this link via SMTP or SendGrid.
        # Since no email service is configured, we will log it.
        logger.info(f"\n"
                    f"====================================================\n"
                    f"INVITE LINK GENERATED FOR {full_name} ({role.upper()})\n"
                    f"Company: {company_name}\n"
                    f"Email: {email}\n"
                    f"Link: {link}\n"
                    f"====================================================")
                    
        return link
    except Exception as e:
        logger.error(f"Failed to generate Firebase email link for {email}: {e}")
        # Fallback raw link if Firebase admin fails
        raw_link = f"{frontend_url}/accept-invite?token={invite_token}"
        logger.info(f"FALLBACK RAW LINK: {raw_link}")
        return raw_link
