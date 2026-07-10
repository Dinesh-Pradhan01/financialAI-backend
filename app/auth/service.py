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
    Links the user to an isolated Person workspace record.
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
            
        # Backwards compatibility migration: Create & link a Person if person_id is null
        if existing.person_id is None:
            from app.database.models import Person
            # Check if a Person record with this email already exists
            person_stmt = select(Person).where(Person.email == email)
            person_res = await db.execute(person_stmt)
            person = person_res.scalar_one_or_none()

            if person is None:
                person = Person(
                    email=email,
                    full_name=email.split("@")[0].capitalize(),
                    created_at=datetime.utcnow()
                )
                db.add(person)
                await db.flush()
                logger.info("Created new Person %s for existing user %s", person.id, firebase_id)
            else:
                logger.info("Found existing Person record %s for existing user %s, reusing it", person.id, firebase_id)

            existing.person_id = person.id
            existing.updated_at = now
            await db.flush()
            logger.info("Migrated and linked Person %s for existing user %s", person.id, firebase_id)
            
        return existing

    # 1. Check if a Person record with this email already exists
    from app.database.models import Person
    person_stmt = select(Person).where(Person.email == email)
    person_res = await db.execute(person_stmt)
    person = person_res.scalar_one_or_none()

    if person is None:
        person = Person(
            email=email,
            full_name=email.split("@")[0].capitalize(),
            created_at=datetime.utcnow()
        )
        db.add(person)
        await db.flush()  # Populates person.id UUID
    else:
        logger.info("Found existing Person record %s for email %s, reusing it for user signup", person.id, email)

    # 2. Create the new User and link to Person
    user = User(
        firebase_id=firebase_id,
        email=email,
        email_verified=email_verified,
        person_id=person.id,
        role=UserRole.USER.value,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("Created new user %s (%s) linked to Person %s", firebase_id, email, person.id)
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
