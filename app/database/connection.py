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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

class PostgreSQLConnectionManager:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    def connect(self):
        try:
            logger.info("Initializing PostgreSQL database engine...")
            connect_args = {
                "statement_cache_size": 0
            }
            if "localhost" not in settings.DATABASE_URL and "127.0.0.1" not in settings.DATABASE_URL:
                connect_args["ssl"] = True

            # pool_pre_ping=True checks connection health before executing queries (useful for Neon)
            self.engine = create_async_engine(
                settings.ASYNC_DATABASE_URL,
                pool_pre_ping=True,
                echo=False,
                connect_args=connect_args
            )
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                class_=AsyncSession
            )
            logger.info("PostgreSQL database engine initialized.")
        except Exception as e:
            logger.error(f"Error initializing PostgreSQL engine: {e}")
            raise e

    async def create_tables(self):
        """Creates tables dynamically in the PostgreSQL database if they don't exist."""
        from app.database.models import Base
        import app.auth.model  # Register auth models (User, Session, Role)
        import app.business.models  # Register business models with Base.metadata
        import app.business.invite_model  # Register invite models
        if self.engine is None:
            raise RuntimeError("Database engine not initialized. Please call connect() first.")
        try:
            logger.info("Creating database tables...")
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Running database column migrations and role seeding...")
                
                async def column_exists(table: str, col: str) -> bool:
                    res = await conn.execute(text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name = '{table}' AND column_name = '{col}';"
                    ))
                    return res.fetchone() is not None

                # Seed roles table with 4 rows if empty or missing entries
                for role_name in ["ceo", "cfo", "hr", "admin"]:
                    check_role = await conn.execute(text(f"SELECT 1 FROM roles WHERE name = '{role_name}';"))
                    if not check_role.fetchone():
                        await conn.execute(text(f"INSERT INTO roles (name) VALUES ('{role_name}');"))

                if not await column_exists("documents", "business_id"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE CASCADE;"))
                if not await column_exists("accounts", "business_id"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE CASCADE;"))
                if not await column_exists("accounts", "account_type"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN account_type VARCHAR(50) DEFAULT 'savings';"))
                if not await column_exists("transactions", "merchant_id"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN merchant_id UUID REFERENCES merchants(id) ON DELETE SET NULL;"))
                if not await column_exists("transactions", "classification"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN classification VARCHAR(50) DEFAULT 'expense';"))

                if not await column_exists("users", "business_id"):
                    await conn.execute(text("ALTER TABLE users ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE SET NULL;"))
                if not await column_exists("users", "invited_by_user_id"):
                    await conn.execute(text("ALTER TABLE users ADD COLUMN invited_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;"))
                if not await column_exists("users", "role_id"):
                    await conn.execute(text("ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL;"))
                
                # Backfill role_id on users based on role name
                await conn.execute(text("UPDATE users SET role_id = roles.id FROM roles WHERE users.role = roles.name AND users.role_id IS NULL;"))

                if not await column_exists("team_invites", "additional_info"):
                    try:
                        await conn.execute(text("ALTER TABLE team_invites ADD COLUMN additional_info VARCHAR(1000);"))
                    except Exception:
                        pass

                if not await column_exists("team_invites", "expires_at"):
                    try:
                        await conn.execute(text("ALTER TABLE team_invites ADD COLUMN expires_at TIMESTAMP;"))
                    except Exception:
                        pass
                
                # LeadershipInfo schema updates
                if not await column_exists("leadership_info", "founder_ceo_designation"):
                    await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN founder_ceo_designation VARCHAR(100);"))

                # Drop columns removed from LeadershipInfo
                for col in ["primary_contact_person", "designation", "years_in_business", "cfo_additional_info", "hr_additional_info"]:
                    if await column_exists("leadership_info", col):
                        await conn.execute(text(f"ALTER TABLE leadership_info DROP COLUMN {col};"))

            logger.info("Database tables, roles seeding, and migrations verified/created successfully.")
        except Exception as e:
            logger.error(f"Error creating database tables and running migrations: {e}")
            raise e

    async def disconnect(self):
        if self.engine is not None:
            logger.info("Disposing PostgreSQL database engine...")
            await self.engine.dispose()
            logger.info("PostgreSQL database engine disposed.")
            self.engine = None
            self.session_factory = None

db_manager = PostgreSQLConnectionManager()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for accessing the asynchronous database session."""
    if db_manager.session_factory is None:
        raise RuntimeError("Database session factory not initialized. Call connect() first.")
    
    async with db_manager.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

async def init_db() -> None:
    """Initialize database connection manager and verify tables/migrations."""
    db_manager.connect()
    await db_manager.create_tables()

async def close_db() -> None:
    """Dispose of the database connection pool."""
    await db_manager.disconnect()
