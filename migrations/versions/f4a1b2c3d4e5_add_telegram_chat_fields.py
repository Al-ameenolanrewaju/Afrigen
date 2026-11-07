"""add Telegram chat fields

Revision ID: f4a1b2c3d4e5
Revises: ea67622a5e45
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a1b2c3d4e5"
down_revision = "ea67622a5e45"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("telegram_users", sa.Column("chat_id", sa.String(length=80), nullable=True))
    op.add_column("telegram_users", sa.Column("chat_title", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("telegram_users", "chat_title")
    op.drop_column("telegram_users", "chat_id")
