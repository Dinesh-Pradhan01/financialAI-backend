import asyncio
from logging.config import fileConfig
import sys
import os

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add the project root to sys.path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

# Import Spotlite Base and Models
from app.database.models import Base as SpotliteBase
from app.auth.model import User, Session
from app.database.models import (
    Merchant, Document, Account, Transaction, ProcessingMetadata,
    BankStatementData, IntelligenceGroup, TransactionCategory, CategoryRule
)
from app.business.models import GeneralInfo, LeadershipInfo, FinancialInfo, BusinessVerification, BusinessVerificationDocument
from app.risk.models import RiskRule, RiskDetection, RiskDetectionTransaction

# Import HR/Vendor Base and Models
from app.db.base import Base as DbBase
from app.db.models.employee import EmployeeMaster
from app.db.models.vendor import VendorMaster
from app.db.models.upload import UploadHistory, ValidationLogs, ImportLogs

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic supports multiple metadata objects passed in a list/tuple
target_metadata = [SpotliteBase.metadata, DbBase.metadata]


def include_object(object, name, type_, reflected, compare_to):
    """
    Only include tables that are defined in our SQLAlchemy models.
    This prevents Alembic from generating DROP TABLE for tables
    that exist in the DB but aren't in our ORM (e.g. legacy tables).
    """
    if type_ == "table" and reflected:
        # Check if table name is in any of the metadata tables
        in_any = any(name in metadata.tables for metadata in target_metadata)
        if not in_any:
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
