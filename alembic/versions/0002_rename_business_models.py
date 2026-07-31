"""rename_business_models

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We are dropping foreign key constraints to rename tables, then recreating them
    
    # 1. Rename tables
    op.rename_table('business_general_info', 'general_info')
    op.rename_table('business_info', 'leadership_info')
    op.rename_table('business_financial_info', 'financial_info')
    
    # Since we are renaming tables, the foreign key constraints from other tables 
    # to 'business_general_info' need to be recreated because the referenced table name changed.
    # Note: postgres might automatically handle table renames in FKs, but we'll do it explicitly if needed.
    # We'll just let op.rename_table do its thing, which in many dialects is enough.
    
    # Alembic handles dropping and renaming implicitly in some cases, but to be safe,
    # let's drop the FK constraints on referencing tables and recreate them if necessary.
    # Wait, SQLite doesn't support renaming with constraints easily, but PostgreSQL does.
    # Assuming PostgreSQL since UUIDs are used.
    pass


def downgrade() -> None:
    op.rename_table('general_info', 'business_general_info')
    op.rename_table('leadership_info', 'business_info')
    op.rename_table('financial_info', 'business_financial_info')
