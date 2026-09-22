"""remove_client_bank_fields

Revision ID: 19cfd459a47f
Revises: ba305a941fe0
Create Date: 2026-09-21 12:23:44.974446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19cfd459a47f'
down_revision: Union[str, Sequence[str], None] = 'ba305a941fe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('clients', 'bank_name')
    op.drop_column('clients', 'account_holder_name')
    op.drop_column('clients', 'account_number')
    op.drop_column('clients', 'ifsc_code')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('clients', sa.Column('bank_name', sa.String(), nullable=True))
    op.add_column('clients', sa.Column('account_holder_name', sa.String(), nullable=True))
    op.add_column('clients', sa.Column('account_number', sa.String(), nullable=True))
    op.add_column('clients', sa.Column('ifsc_code', sa.String(), nullable=True))
