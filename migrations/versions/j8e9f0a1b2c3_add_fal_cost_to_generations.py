"""add estimated Fal cost to generations

Revision ID: j8e9f0a1b2c3
Revises: i7d8e9f0a1b2
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = "j8e9f0a1b2c3"
down_revision = "i7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("generations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("fal_cost_usd", sa.Float(), nullable=False, server_default="0")
        )


def downgrade():
    with op.batch_alter_table("generations", schema=None) as batch_op:
        batch_op.drop_column("fal_cost_usd")