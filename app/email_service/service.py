import os
import asyncio
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from python_http_client.exceptions import HTTPError
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Targets exactly: app/email_service/templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR)
)
# Ensure you have these environment variables set
SENDGRID_API_KEY = settings.SENDGRID_API_KEY
FROM_EMAIL = settings.SENDER_EMAIL

async def send_email_async(
    to_email: str, 
    template_name: str,
    subject: str,
    context: Dict[str, Any]
) -> dict:
    """
    Non-blocking async function to render an HTML template and send it via SendGrid.
    
    :param to_email: The recipient's email address.
    :param subject: The subject line of the email.
    :param template_name: [password_reset, user_invitation, user_registration]
    :param context: A dictionary containing dynamic data for the template. Fields = [recipent_name, action_url, org_name, role]
    :return: A dictionary defining the status of the operation.
    """
    try:
        # Load and render the HTML template with the provided dictionary context
        template = jinja_env.get_template(f"{template_name}.html")
        html_content = template.render(**context)
        logger.info("mail tmplate acquired: %s",template_name)
        # Build the SendGrid Mail object
        message = Mail(
            from_email=FROM_EMAIL,
            subject= subject,
            to_emails=to_email,
            html_content=html_content
        )

        # Initialize the SendGrid client
        sg = SendGridAPIClient(SENDGRID_API_KEY)

        # EXECUTE ASYNC: 
        # sg.send() is a blocking synchronous call. 
        # asyncio.to_thread() runs it safely without blocking FastAPI.
        response = await asyncio.to_thread(sg.send, message)

        # SendGrid returns HTTP 202 on a successful handoff
        if response.status_code in [200, 201, 202]:
            return {
                "success": True,
                "status_code": response.status_code,
                "message": "Email sent successfully",
                "error": None
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "message": "Failed to send email",
                "error": "Unknown error occurred"
            }

    except HTTPError as e:
        # Catch specific SendGrid API errors
        error_msg = e.body.decode('utf-8') if e.body else str(e)
        return {
            "success": False,
            "status_code": e.status_code,
            "message": "SendGrid API Error",
            "error": error_msg
        }
    except Exception as e:
        # Catch Jinja2 rendering errors or other unexpected errors
        return {
            "success": False,
            "status_code": 500,
            "message": "Internal Server Error",
            "error": str(e)
        }