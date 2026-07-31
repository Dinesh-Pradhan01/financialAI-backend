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
        import app.business.models  # Register business models with Base.metadata
        if self.engine is None:
            raise RuntimeError("Database engine not initialized. Please call connect() first.")
        try:
            logger.info("Creating database tables...")
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Running database column migrations...")
                
                async def column_exists(table: str, col: str) -> bool:
                    res = await conn.execute(text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name = '{table}' AND column_name = '{col}';"
                    ))
                    return res.fetchone() is not None

                if not await column_exists("documents", "person_id"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN person_id UUID REFERENCES persons(id) ON DELETE CASCADE;"))
                if not await column_exists("accounts", "person_id"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN person_id UUID REFERENCES persons(id) ON DELETE CASCADE;"))
                if not await column_exists("accounts", "account_type"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN account_type VARCHAR(50) DEFAULT 'savings';"))
                if not await column_exists("transactions", "merchant_id"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN merchant_id UUID REFERENCES merchants(id) ON DELETE SET NULL;"))
                if not await column_exists("transactions", "classification"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN classification VARCHAR(50) DEFAULT 'expense';"))

                # New onboarding columns on persons table
                if not await column_exists("persons", "phone"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN phone VARCHAR(20);"))
                if not await column_exists("persons", "date_of_birth"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN date_of_birth TIMESTAMP;"))
                if not await column_exists("persons", "gender"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN gender VARCHAR(20);"))
                if not await column_exists("persons", "address"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN address VARCHAR(500);"))
                if not await column_exists("persons", "city"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN city VARCHAR(100);"))
                if not await column_exists("persons", "state"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN state VARCHAR(100);"))
                if not await column_exists("persons", "pincode"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN pincode VARCHAR(10);"))
                if not await column_exists("persons", "pan_number"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN pan_number VARCHAR(10);"))
                if not await column_exists("persons", "occupation"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN occupation VARCHAR(100);"))
                if not await column_exists("persons", "bank_count"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN bank_count INTEGER;"))
                if not await column_exists("persons", "primary_bank"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN primary_bank VARCHAR(100);"))
                if not await column_exists("persons", "profile_completed"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN profile_completed BOOLEAN DEFAULT FALSE NOT NULL;"))
                if not await column_exists("persons", "business_id"):
                    await conn.execute(text("ALTER TABLE persons ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE SET NULL;"))
                if not await column_exists("users", "business_id"):
                    await conn.execute(text("ALTER TABLE users ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE SET NULL;"))

                # Alter users.person_id type from INTEGER to UUID and configure foreign key safely
                result = await conn.execute(text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'person_id';"
                ))
                row = result.fetchone()
                if row and row[0] != 'uuid':
                    logger.info("Migrating users.person_id from INTEGER to UUID...")
                    await conn.execute(text("ALTER TABLE users ALTER COLUMN person_id TYPE UUID USING person_id::text::uuid;"))
                    await conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_person_id;"))
                    await conn.execute(text("ALTER TABLE users ADD CONSTRAINT fk_users_person_id FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE SET NULL;"))
                    logger.info("users.person_id column successfully migrated to UUID.")
            logger.info("Database tables and migrations verified/created successfully.")
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
