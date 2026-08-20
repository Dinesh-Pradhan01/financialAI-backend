"""
User and Session service — handles user lookup, creation, and session management in PostgreSQL.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.model import User, UserRole, Session

logger = logging.getLogger(__name__)

SESSION_EXPIRY_DAYS = 7


def hash_token(token: str) -> str:
    """Generate SHA256 hash of a session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_user_by_firebase_id(
    db: AsyncSession,
    firebase_id: str,
) -> Optional[User]:
    """
    Look up a user by their Firebase UID.
    """
    stmt = select(User).where(User.firebase_id == firebase_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_user(
    db: AsyncSession,
    firebase_id: str,
    email: str,
    email_verified: bool = False,
) -> User:
    """
    Find an existing user by firebase_id, or create a new one.
    """
    existing = await get_user_by_firebase_id(db, firebase_id)

    if existing is None:
        # Try to find by email to prevent duplicate key unique constraint violations
        email_stmt = select(User).where(User.email == email)
        email_res = await db.execute(email_stmt)
        existing = email_res.scalar_one_or_none()
        if existing is not None:
            logger.info("Linking existing user with email %s to new firebase_id %s", email, firebase_id)
            existing.firebase_id = firebase_id
            existing.email_verified = email_verified or existing.email_verified
            await db.flush()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if existing is not None:
        # Update email/verification if changed on the Firebase side
        if existing.email != email or existing.email_verified != email_verified:
            existing.email = email
            existing.email_verified = email_verified
            existing.updated_at = now
            await db.flush()
            logger.info("Updated email info for user %s", firebase_id)
            
        # Check if they have a pending invite and accept it (update role & business)
        from app.business.invite_model import TeamInvite
        from app.auth.model import Role
        invite_stmt = select(TeamInvite).where(TeamInvite.email == email, TeamInvite.status == "pending")
        invite_res = await db.execute(invite_stmt)
        invite = invite_res.scalar_one_or_none()
        if invite:
            existing.role = invite.role
            existing.business_id = invite.business_id
            invite.status = "accepted"
            role_res = await db.execute(select(Role.id).where(Role.name == invite.role))
            existing.role_id = role_res.scalar_one_or_none()
            await db.flush()
            logger.info("Accepted invite for existing user %s and updated role to %s", firebase_id, invite.role)
        elif existing.role_id is None:
            role_res = await db.execute(select(Role.id).where(Role.name == existing.role))
            existing.role_id = role_res.scalar_one_or_none()
            await db.flush()
            
        return existing

    from sqlalchemy.exc import IntegrityError
    from app.auth.model import Role

    # Create the new User
    try:
        async with db.begin_nested():
            # Check if this email was invited to a team
            from app.business.invite_model import TeamInvite
            invite_stmt = select(TeamInvite).where(TeamInvite.email == email, TeamInvite.status == "pending")
            invite_res = await db.execute(invite_stmt)
            invite = invite_res.scalar_one_or_none()

            role = UserRole.CEO.value
            business_id = None

            if invite:
                role = invite.role
                business_id = invite.business_id
                invite.status = "accepted"

            role_res = await db.execute(select(Role.id).where(Role.name == role))
            role_id = role_res.scalar_one_or_none()

            user = User(
                firebase_id=firebase_id,
                email=email,
                email_verified=email_verified,
                business_id=business_id,
                role=role,
                role_id=role_id,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            await db.flush()
    except IntegrityError:
        user_stmt = select(User).where(User.firebase_id == firebase_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            user_stmt = select(User).where(User.email == email)
            user_res = await db.execute(user_stmt)
            user = user_res.scalar_one()
        logger.info("User record was created concurrently for %s", email)

    await db.refresh(user)

    logger.info("Created new user %s (%s)", firebase_id, email)
    return user


async def update_last_login(db: AsyncSession, user: User) -> None:
    """Update last_login_at timestamp for a user."""
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()


async def create_session(
    db: AsyncSession,
    user_id: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """
    Generate a secure session token, hash it, store the session, and return the raw token.
    """
    raw_token = secrets.token_urlsafe(64)
    hashed_token = hash_token(raw_token)
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(days=SESSION_EXPIRY_DAYS)
    
    session_record = Session(
        user_id=user_id,
        session_token_hash=hashed_token,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=now,
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(session_record)
    await db.flush()
    
    return raw_token


async def verify_session(db: AsyncSession, raw_token: str) -> Optional[User]:
    """
    Hash the raw token, look up the session.
    If valid, return the associated User. Otherwise return None.
    """
    hashed_token = hash_token(raw_token)
    
    stmt = select(Session).where(
        Session.session_token_hash == hashed_token,
        Session.is_revoked == False
    )
    result = await db.execute(stmt)
    session_record = result.scalar_one_or_none()
    
    if not session_record:
        return None
        
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Ensure both datetimes are naive (strip tzinfo if DB returns aware)
    db_expires = session_record.expires_at
    if db_expires.tzinfo is not None:
        db_expires = db_expires.replace(tzinfo=None)
    if db_expires < now:
        # Session expired, mark it revoked
        session_record.is_revoked = True
        await db.flush()
        return None
        
    # Get user
    user_stmt = select(User).where(User.id == session_record.user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if not user or not user.is_active:
        return None
        
    return user


async def revoke_session(db: AsyncSession, raw_token: str) -> bool:
    """
    Mark a session as revoked.
    """
    hashed_token = hash_token(raw_token)
    stmt = (
        update(Session)
        .where(Session.session_token_hash == hashed_token)
        .values(is_revoked=True)
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount > 0
