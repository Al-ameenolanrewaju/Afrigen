"""add alert incident state

Revision ID: o3d4e5f6a7b8
Revises: n2c3d4e5f6a7
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

revision = "o3d4e5f6a7b8"
down_revision = "n2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_states",
        sa.Column("alert_type", sa.String(length=100), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("last_alerted_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("alert_states")