"""
FastAPI authentication and authorisation dependencies.

- get_firebase_synced_user: Extracts & verifies the Firebase ID token, syncs the user
  to the local PostgreSQL database, and returns the User ORM instance. Used for /sync.
- get_current_session_user: Extracts the session cookie, verifies it against the DB,
  and returns the User ORM instance. Used for most authenticated endpoints.
- require_role: Returns a dependency that additionally checks the user's role.
"""

import logging
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.firebase import verify_firebase_token
from app.auth.model import TokenPayload, User
from app.auth.service import get_or_create_user, verify_session
from app.database.connection import get_db

logger = logging.getLogger(__name__)

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
_bearer_scheme = HTTPBearer(auto_error=True)
_bearer_scheme_optional = HTTPBearer(auto_error=False)


async def get_firebase_synced_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that authenticates the request using Firebase token and syncs the user.
    Only used for the login/registration sync step.
    """
    token = credentials.credentials

    # --- 1. Verify the Firebase token ---
    try:
        decoded = await verify_firebase_token(token)
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please re-authenticate.",
        )
    except firebase_auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please sign in again.",
        )
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )
    except Exception as e:
        logger.error("Token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        )

    # --- 2. Parse token payload ---
    payload = TokenPayload(
        uid=decoded["uid"],
        email=decoded.get("email"),
        email_verified=decoded.get("email_verified", False),
    )

    # --- 3. Reject unverified emails ---
    # Optional: If you strictly want verified emails before they can access the app
    # uncomment below. We'll store the state in the database for now.
    # if not payload.email_verified:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Email not verified. Please verify your email before accessing this resource.",
    #     )

    if not payload.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain an email claim.",
        )

    # --- 4. Upsert user in local database ---
    user = await get_or_create_user(
        db=db, 
        firebase_id=payload.uid, 
        email=payload.email,
        email_verified=payload.email_verified
    )

    # --- 5. Reject deactivated users ---
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact support.",
        )

    return user


async def get_current_session_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates either the session cookie or the Firebase Bearer token and returns the current user.
    """
    # 1. Try session cookie authentication first
    session_token = request.cookies.get("session")
    if session_token:
        user = await verify_session(db, session_token)
        if user:
            return user

    # 2. Fallback to Firebase Bearer Token authentication (e.g. for Swagger UI / API consumers)
    token = credentials.credentials if credentials else None
    if not token:
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if token:
        try:
            decoded = await verify_firebase_token(token)
            uid = decoded.get("uid")
            email = decoded.get("email")
            email_verified = decoded.get("email_verified", False)

            if uid and email:
                user = await get_or_create_user(
                    db=db,
                    firebase_id=uid,
                    email=email,
                    email_verified=email_verified,
                )
                if not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Your account has been deactivated. Contact support.",
                    )
                return user
        except HTTPException:
            raise
        except firebase_auth.ExpiredIdTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please re-authenticate.",
            )
        except firebase_auth.InvalidIdTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
            )
        except Exception as e:
            logger.error("Bearer token verification failed in get_current_session_user: %s", e)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Missing or invalid session cookie / Bearer token.",
    )


def require_role(
    *allowed_roles: str,
) -> Callable:
    """
    Returns a FastAPI dependency that verifies the current session user has one of
    the allowed roles.
    """
    async def _role_checker(
        current_user: User = Depends(get_current_session_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(allowed_roles)}.",
            )
        return current_user

    return _role_checker
