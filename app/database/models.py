"""
SQLAlchemy ORM base and common model utilities for PostgreSQL.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Declarative base for all SQLAlchemy ORM models.
    Import this in every model file and register tables via subclassing.
    """
    pass


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at columns to any model.
    updated_at is automatically set on every UPDATE.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
