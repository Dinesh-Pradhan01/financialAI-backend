"""
Async SQLAlchemy database connection for NeonDB PostgreSQL.

Provides:
- async engine (singleton)
- async session factory
- get_db() FastAPI dependency yielding AsyncSession
- init_db() to create tables on startup
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine & session factory (module-level singletons)
# ---------------------------------------------------------------------------

# NeonDB requires sslmode=require and works best with NullPool for serverless
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    # NullPool is recommended for serverless Postgres (NeonDB)
    # to avoid idle connection issues
    poolclass=NullPool,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async SQLAlchemy session.
    Commits on success, rolls back on exception, always closes.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Initialize database connection. Automatic table creation is disabled in favor of Alembic."""
    logger.info("Database engine initialized. Schema migrations are managed by Alembic.")


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    await engine.dispose()
    logger.info("Database engine disposed.")
