"""Set (vendor_id, category) as PK and make contract_id optional

Revision ID: f891024_vendor_composite_pk
Revises: e7182903_employee_id_pk
Create Date: 2026-09-10 12:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f891024_vendor_composite_pk'
down_revision: Union[str, Sequence[str], None] = 'e7182903_employee_id_pk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Make contract_id optional
    op.execute(sa.text("ALTER TABLE vendor_master ALTER COLUMN contract_id DROP NOT NULL;"))

    # 2. Drop old PK/id if exists and set (vendor_id, category) PK
    op.execute(sa.text("""
        DO $$
        DECLARE
            pk_name text;
        BEGIN
            SELECT constraint_name INTO pk_name
            FROM information_schema.table_constraints
            WHERE table_name = 'vendor_master' AND constraint_type = 'PRIMARY KEY';

            IF pk_name IS NOT NULL THEN
                EXECUTE 'ALTER TABLE vendor_master DROP CONSTRAINT ' || quote_ident(pk_name);
            END IF;
        END $$;
    """))
    op.execute(sa.text("ALTER TABLE vendor_master DROP COLUMN IF EXISTS id;"))
    op.execute(sa.text("ALTER TABLE vendor_master DROP COLUMN IF EXISTS row_id;"))
    op.execute(sa.text("ALTER TABLE vendor_master ALTER COLUMN vendor_id SET NOT NULL;"))
    op.execute(sa.text("ALTER TABLE vendor_master ALTER COLUMN category SET NOT NULL;"))
    op.execute(sa.text("ALTER TABLE vendor_master ADD PRIMARY KEY (vendor_id, category);"))

def downgrade() -> None:
    pass
