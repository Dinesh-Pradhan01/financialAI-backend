"""
Firebase Admin SDK initialization and token verification.

This module initializes the Firebase Admin SDK once at app startup and provides
a function to verify Firebase ID tokens from incoming API requests.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from app.config import settings

logger = logging.getLogger(__name__)

_firebase_app: Optional[firebase_admin.App] = None


def initialize_firebase() -> None:
    """
    Initialize the Firebase Admin SDK.

    Uses the service account JSON file at FIREBASE_CREDENTIALS_PATH if set,
    otherwise falls back to Application Default Credentials (ADC).
    Must be called once during application startup.
    """
    global _firebase_app

    if _firebase_app is not None:
        logger.warning("Firebase Admin SDK already initialized — skipping.")
        return

    try:
        if settings.FIREBASE_CREDENTIALS_PATH:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info(
                "Firebase Admin SDK initialized with service account: %s",
                settings.FIREBASE_CREDENTIALS_PATH,
            )
        else:
            # Fallback: use Application Default Credentials (e.g. GCP environments)
            _firebase_app = firebase_admin.initialize_app()
            logger.info(
                "Firebase Admin SDK initialized with Application Default Credentials."
            )
    except Exception as e:
        logger.error("Failed to initialize Firebase Admin SDK: %s", e)
        raise


async def verify_firebase_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a Firebase ID token.

    Checks:
    - Token signature and format
    - Token expiration
    - Token revocation

    Args:
        token: The raw Firebase ID token string from the Authorization header.

    Returns:
        Decoded token claims dictionary containing uid, email, email_verified, etc.

    Raises:
        firebase_admin.auth.InvalidIdTokenError: Token is invalid.
        firebase_admin.auth.ExpiredIdTokenError: Token has expired.
        firebase_admin.auth.RevokedIdTokenError: Token has been revoked.
        firebase_admin.auth.CertificateFetchError: Could not fetch certs.
    """
    # check_revoked=True adds an extra call to Firebase but ensures tokens
    # that were revoked (e.g. via admin panel or password change) are rejected.
    # Run in threadpool so synchronous HTTP calls do not block the asyncio event loop.
    decoded = await asyncio.to_thread(
        firebase_auth.verify_id_token, token, check_revoked=True, clock_skew_seconds=10
    )
    return decoded
