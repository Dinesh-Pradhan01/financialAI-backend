"""Set employee_id as PK and create employee_versions table

Revision ID: e7182903_employee_id_pk
Revises: ab1c384f1872
Create Date: 2026-09-09 11:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e7182903_employee_id_pk'
down_revision: Union[str, Sequence[str], None] = 'ab1c384f1872'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Add version column if not exists & drop NOT NULL from id if present
    op.execute(sa.text("ALTER TABLE employee_master ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;"))
    op.execute(sa.text("ALTER TABLE employee_master ALTER COLUMN id DROP NOT NULL;"))

    # 2. Create employee_versions table
    op.create_table(
        'employee_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('emp_id', sa.String(), nullable=False, index=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('employee_name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('joining_date', sa.String(), nullable=False),
        sa.Column('department', sa.String(), nullable=False),
        sa.Column('designation', sa.String(), nullable=False),
        sa.Column('salary', sa.String(), nullable=False),
        sa.Column('account_number', sa.String(), nullable=False),
        sa.Column('ifsc_code', sa.String(), nullable=False),
        sa.Column('bank_name', sa.String(), nullable=False),
        sa.Column('employment_type', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('salary_frequency', sa.String(), nullable=True),
        sa.Column('account_holder_name', sa.String(), nullable=True),
        sa.Column('payment_mode', sa.String(), nullable=True),
        sa.Column('change_type', sa.String(), nullable=False),
        sa.Column('changed_fields', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
    )

def downgrade() -> None:
    op.drop_table('employee_versions')
    with op.batch_alter_table('employee_master') as batch_op:
        batch_op.drop_column('version')
