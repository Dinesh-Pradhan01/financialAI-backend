"""Merge migration branches

Revision ID: ab1c384f1872
Revises: 3596053d370f, 6177a233c1b6
Create Date: 2026-08-31 15:07:08.091502

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab1c384f1872'
down_revision: Union[str, Sequence[str], None] = ('3596053d370f', '6177a233c1b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
