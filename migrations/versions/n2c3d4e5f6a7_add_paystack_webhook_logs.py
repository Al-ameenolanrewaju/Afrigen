"""add Paystack webhook logs

Revision ID: n2c3d4e5f6a7
Revises: m1b2c3d4e5f6
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

revision = "n2c3d4e5f6a7"
down_revision = "m1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paystack_webhook_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_body", sa.Text(), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("paystack_webhook_logs")