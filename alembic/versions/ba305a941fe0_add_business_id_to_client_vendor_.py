"""add_business_id_to_client_vendor_employee

Revision ID: ba305a941fe0
Revises: f891024_vendor_composite_pk
Create Date: 2026-09-18 15:23:29.766778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba305a941fe0'
down_revision: Union[str, Sequence[str], None] = 'f891024_vendor_composite_pk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add column as nullable
    op.add_column('clients', sa.Column('business_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('vendor_master', sa.Column('business_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('employee_master', sa.Column('business_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))

    # 2. Backfill with a general_info id if available
    op.execute("UPDATE clients SET business_id = (SELECT id FROM general_info LIMIT 1) WHERE business_id IS NULL;")
    op.execute("UPDATE vendor_master SET business_id = (SELECT id FROM general_info LIMIT 1) WHERE business_id IS NULL;")
    op.execute("UPDATE employee_master SET business_id = (SELECT id FROM general_info LIMIT 1) WHERE business_id IS NULL;")

    # 3. Clean up orphans
    op.execute("DELETE FROM clients WHERE business_id IS NULL;")
    op.execute("DELETE FROM vendor_master WHERE business_id IS NULL;")
    op.execute("DELETE FROM employee_master WHERE business_id IS NULL;")

    # 4. Alter column to nullable=False
    op.alter_column('clients', 'business_id', existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    op.alter_column('vendor_master', 'business_id', existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    op.alter_column('employee_master', 'business_id', existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)

    # 5. Add foreign keys
    op.create_foreign_key('fk_clients_business_id', 'clients', 'general_info', ['business_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_vendors_business_id', 'vendor_master', 'general_info', ['business_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_employees_business_id', 'employee_master', 'general_info', ['business_id'], ['id'], ondelete='CASCADE')

    # 6. Update Constraints / Primary Keys
    
    # Client
    op.drop_constraint('uq_client_id_category', 'clients', type_='unique')
    op.create_unique_constraint('uq_business_client_id_category', 'clients', ['business_id', 'client_id', 'category'])
    op.create_index(op.f('ix_clients_business_id'), 'clients', ['business_id'], unique=False)
    
    # Vendor
    op.drop_constraint('vendor_master_pkey', 'vendor_master', type_='primary')
    op.create_primary_key('vendor_master_pkey', 'vendor_master', ['business_id', 'vendor_id', 'category'])
    op.create_unique_constraint('uq_business_vendor_id_category', 'vendor_master', ['business_id', 'vendor_id', 'category'])
    
    # Employee
    op.drop_constraint('employee_master_pkey', 'employee_master', type_='primary')
    op.create_primary_key('employee_master_pkey', 'employee_master', ['business_id', 'employee_id'])


def downgrade() -> None:
    # Client
    op.drop_index(op.f('ix_clients_business_id'), table_name='clients')
    op.drop_constraint('uq_business_client_id_category', 'clients', type_='unique')
    op.create_unique_constraint('uq_client_id_category', 'clients', ['client_id', 'category'])
    op.drop_constraint('fk_clients_business_id', 'clients', type_='foreignkey')
    op.drop_column('clients', 'business_id')

    # Vendor
    op.drop_constraint('uq_business_vendor_id_category', 'vendor_master', type_='unique')
    op.drop_constraint('vendor_master_pkey', 'vendor_master', type_='primary')
    op.create_primary_key('vendor_master_pkey', 'vendor_master', ['vendor_id', 'category'])
    op.create_unique_constraint('uq_vendor_id_category', 'vendor_master', ['vendor_id', 'category'])
    op.drop_constraint('fk_vendors_business_id', 'vendor_master', type_='foreignkey')
    op.drop_column('vendor_master', 'business_id')

    # Employee
    op.drop_constraint('employee_master_pkey', 'employee_master', type_='primary')
    op.create_primary_key('employee_master_pkey', 'employee_master', ['employee_id'])
    op.drop_constraint('fk_employees_business_id', 'employee_master', type_='foreignkey')
    op.drop_column('employee_master', 'business_id')
