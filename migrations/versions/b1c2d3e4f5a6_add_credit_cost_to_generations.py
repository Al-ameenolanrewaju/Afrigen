"""add credit_cost to generations

Revision ID: b1c2d3e4f5a6
Revises: 45767f11d60d
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = '45767f11d60d'
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows default to the old flat price of 5 credits.
    with op.batch_alter_table('generations', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('credit_cost', sa.Integer(), nullable=False, server_default='5')
        )


def downgrade():
    with op.batch_alter_table('generations', schema=None) as batch_op:
        batch_op.drop_column('credit_cost')
