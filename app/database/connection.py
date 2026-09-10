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
        from app.db.base import Base as DbBase
        import app.auth.model  # Register auth models (User, Session, Role)
        import app.business.models  # Register business models with Base.metadata
        import app.business.invite_model  # Register invite models
        
        # Register HR/Vendor models
        import app.db.models.employee
        import app.db.models.vendor
        import app.db.models.upload

        import app.risk.models  # Register risk models (RiskRule, RiskDetection, RiskDetectionTransaction)
        if self.engine is None:
            raise RuntimeError("Database engine not initialized. Please call connect() first.")
        try:
            logger.info("Creating database tables...")
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.run_sync(DbBase.metadata.create_all)
                logger.info("Running database column migrations and role seeding...")
                
                async def column_exists(table: str, col: str) -> bool:
                    res = await conn.execute(text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name = '{table}' AND column_name = '{col}';"
                    ))
                    return res.fetchone() is not None

                async def table_exists(table: str) -> bool:
                    res = await conn.execute(text(
                        f"SELECT 1 FROM information_schema.tables "
                        f"WHERE table_name = '{table}';"
                    ))
                    return res.fetchone() is not None

                async def constraint_exists(constraint_name: str) -> bool:
                    res = await conn.execute(text(
                        f"SELECT 1 FROM information_schema.table_constraints "
                        f"WHERE constraint_name = '{constraint_name}';"
                    ))
                    return res.fetchone() is not None

                # Seed roles table with 4 rows if empty or missing entries
                for role_name in ["ceo", "cfo", "hr", "admin"]:
                    check_role = await conn.execute(text(f"SELECT 1 FROM roles WHERE name = '{role_name}';"))
                    if not check_role.fetchone():
                        await conn.execute(text(f"INSERT INTO roles (name) VALUES ('{role_name}');"))

                # ----- Document table migrations -----
                if not await column_exists("documents", "business_id"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE CASCADE;"))
                if not await column_exists("documents", "account_id"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN account_id UUID REFERENCES accounts(id) ON DELETE SET NULL;"))
                if not await column_exists("documents", "uploaded_by"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL;"))
                if not await column_exists("documents", "mime_type"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN mime_type VARCHAR(100);"))
                if not await column_exists("documents", "document_type"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN document_type VARCHAR(50) DEFAULT 'BANK_STATEMENT';"))
                if not await column_exists("documents", "updated_at"):
                    await conn.execute(text("ALTER TABLE documents ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();"))

                # ----- Account table migrations -----
                if not await column_exists("accounts", "business_id"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE CASCADE;"))
                if not await column_exists("accounts", "account_type"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN account_type VARCHAR(50) DEFAULT 'savings';"))
                if not await column_exists("accounts", "currency"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN currency VARCHAR(10) DEFAULT 'INR';"))
                if not await column_exists("accounts", "branch_name"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN branch_name VARCHAR(255);"))
                if not await column_exists("accounts", "status"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN status VARCHAR(30) DEFAULT 'ACTIVE';"))
                if not await column_exists("accounts", "updated_at"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();"))
                if not await column_exists("accounts", "created_at"):
                    await conn.execute(text("ALTER TABLE accounts ADD COLUMN created_at TIMESTAMP DEFAULT NOW();"))
                # Add unique constraint for account deduplication if not exists
                if not await constraint_exists("uq_account_business_number_bank"):
                    try:
                        await conn.execute(text(
                            "ALTER TABLE accounts ADD CONSTRAINT uq_account_business_number_bank "
                            "UNIQUE (business_id, account_number, bank_name);"
                        ))
                    except Exception as e:
                        logger.warning(f"Could not add unique constraint on accounts (may have duplicates): {e}")

                # ----- Transaction table migrations -----
                if not await column_exists("transactions", "merchant_id"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN merchant_id UUID REFERENCES merchants(id) ON DELETE SET NULL;"))
                if not await column_exists("transactions", "classification"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN classification VARCHAR(50) DEFAULT 'expense';"))
                if not await column_exists("transactions", "business_id"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE CASCADE;"))
                if not await column_exists("transactions", "category_id"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN category_id INTEGER REFERENCES transaction_categories(id) ON DELETE SET NULL;"))
                if not await column_exists("transactions", "raw_category"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN raw_category VARCHAR(100);"))
                if not await column_exists("transactions", "updated_at"):
                    await conn.execute(text("ALTER TABLE transactions ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();"))

                # ----- Merchant table migrations -----
                if not await column_exists("merchants", "business_id"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN business_id UUID REFERENCES general_info(id) ON DELETE CASCADE;"))
                if not await column_exists("merchants", "canonical_name"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN canonical_name VARCHAR(255);"))
                if not await column_exists("merchants", "category"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN category VARCHAR(100);"))
                if not await column_exists("merchants", "subcategory"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN subcategory VARCHAR(100);"))
                if not await column_exists("merchants", "city"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN city VARCHAR(100);"))
                if not await column_exists("merchants", "state"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN state VARCHAR(100);"))
                if not await column_exists("merchants", "country"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN country VARCHAR(100) DEFAULT 'India';"))
                if not await column_exists("merchants", "updated_at"):
                    await conn.execute(text("ALTER TABLE merchants ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();"))

                # ----- business_documents table updates -----
                if not await column_exists("business_documents", "file_hash"):
                    await conn.execute(text("ALTER TABLE business_documents ADD COLUMN file_hash VARCHAR(64);"))
                if not await column_exists("business_documents", "quality_score"):
                    await conn.execute(text("ALTER TABLE business_documents ADD COLUMN quality_score FLOAT;"))
                if not await column_exists("business_documents", "is_verified"):
                    await conn.execute(text("ALTER TABLE business_documents ADD COLUMN is_verified BOOLEAN DEFAULT FALSE NOT NULL;"))
                if not await column_exists("business_documents", "verification_notes"):
                    await conn.execute(text("ALTER TABLE business_documents ADD COLUMN verification_notes TEXT;"))

                # ----- User table migrations -----
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

                # ----- Seed Intelligence Groups & Transaction Categories -----
                await _seed_categories(conn, table_exists)

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


# ---------------------------------------------------------------------------
# Category Seed Data
# ---------------------------------------------------------------------------

# Simplified MSME categories - 8 main categories only
_SEED_DATA = {
    "Income": {
        "display_order": 1,
        "description": "Revenue and income",
        "categories": ["BUSINESS INCOME"],
    },
    "Expenses": {
        "display_order": 2,
        "description": "Business expenses",
        "categories": [
            "PAYROLL & EMPLOYEES",
            "SUPPLIERS & PROCUREMENT",
            "BUSINESS OPERATIONS",
            "SALES & MARKETING",
            "FINANCE, TAX & COMPLIANCE",
            "ASSETS & INVESTMENTS"
        ],
    },
    "Transfers": {
        "display_order": 3,
        "description": "Internal and owner transactions",
        "categories": ["TRANSFERS & OWNER TRANSACTIONS"],
    },
    "Uncategorized": {
        "display_order": 99,
        "description": "Uncategorized transactions",
        "categories": ["Uncategorized"],
    },
}


async def _seed_categories(conn, table_exists_fn):
    """Seed intelligence_groups and transaction_categories safely."""
    try:
        if not await table_exists_fn("intelligence_groups"):
            return  # Table not created yet

        # Clean up mixed categories if we have more than the 8 main categories
        count_res = await conn.execute(text("SELECT COUNT(*) FROM transaction_categories;"))
        count = count_res.scalar()
        if count > 8:
            logger.info("Found mixed/old categories (count > 8). Wiping to reset to 8 main categories...")
            await conn.execute(text("DELETE FROM transaction_categories;"))
            await conn.execute(text("DELETE FROM intelligence_groups;"))
            
        logger.info("Verifying intelligence_groups and transaction_categories...")
        for group_name, group_info in _SEED_DATA.items():
            # Check if group exists
            grp_result = await conn.execute(text(
                "SELECT id FROM intelligence_groups WHERE group_name = :name;"
            ), {"name": group_name})
            group_id = grp_result.scalar()

            if not group_id:
                # Insert group
                await conn.execute(text(
                    "INSERT INTO intelligence_groups (group_name, description, display_order, is_active) "
                    "VALUES (:name, :desc, :order, TRUE);"
                ), {
                    "name": group_name,
                    "desc": group_info["description"],
                    "order": group_info["display_order"],
                })
                grp_result = await conn.execute(text(
                    "SELECT id FROM intelligence_groups WHERE group_name = :name;"
                ), {"name": group_name})
                group_id = grp_result.scalar()

            # Insert categories if they don't exist under this group
            for cat_name in group_info["categories"]:
                cat_result = await conn.execute(text(
                    "SELECT id FROM transaction_categories WHERE category_name = :cname AND intelligence_group_id = :gid;"
                ), {"cname": cat_name, "gid": group_id})
                if not cat_result.scalar():
                    await conn.execute(text(
                        "INSERT INTO transaction_categories (intelligence_group_id, category_name, is_system_defined, is_active) "
                        "VALUES (:gid, :cname, TRUE, TRUE);"
                    ), {"gid": group_id, "cname": cat_name})

        logger.info("Intelligence groups and transaction categories verified/seeded successfully.")
    except Exception as e:
        logger.warning(f"Could not seed categories (non-fatal): {e}")
