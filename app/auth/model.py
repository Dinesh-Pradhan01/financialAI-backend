"""
User and Session models for authentication and authorisation.

- SQLAlchemy ORM models: User, Session
- Pydantic schemas: UserResponse, TokenPayload
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Integer, String, DateTime, ForeignKey, BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------

class User(TimestampMixin, Base):
    """Represents a row in the `users` PostgreSQL table."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    firebase_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    person_id: Mapped[Optional[int]] = mapped_column(
        Integer, unique=True, nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), default=UserRole.USER.value, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """Represents an active user session based on an HTTP-only cookie."""
    
    __tablename__ = "sessions"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    user: Mapped["User"] = relationship("User", back_populates="sessions")


# ---------------------------------------------------------------------------
# Pydantic API response schemas
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    """Safe public representation of a user (returned by API endpoints)."""

    id: int
    email: str
    role: str
    email_verified: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Token payload (decoded Firebase token)
# ---------------------------------------------------------------------------

class TokenPayload(BaseModel):
    """Relevant fields extracted from a verified Firebase ID token."""

    uid: str
    email: Optional[str] = None
    email_verified: bool = False
