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
            connect_args = {}
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
        if self.engine is None:
            raise RuntimeError("Database engine not initialized. Please call connect() first.")
        try:
            logger.info("Creating database tables...")
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Running database column migrations...")
                await conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS person_id UUID REFERENCES persons(id) ON DELETE CASCADE;"))
                await conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS person_id UUID REFERENCES persons(id) ON DELETE CASCADE;"))
                await conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS account_type VARCHAR(50) DEFAULT 'savings';"))
                await conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_id UUID REFERENCES merchants(id) ON DELETE SET NULL;"))
                await conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS classification VARCHAR(50) DEFAULT 'expense';"))
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
