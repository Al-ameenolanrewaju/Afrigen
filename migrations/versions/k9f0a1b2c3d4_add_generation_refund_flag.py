"""add generation refund idempotency flag

Revision ID: k9f0a1b2c3d4
Revises: j8e9f0a1b2c3
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = "k9f0a1b2c3d4"
down_revision = "j8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("generations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("refund_applied", sa.Boolean(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("generations", schema=None) as batch_op:
        batch_op.drop_column("refund_applied")