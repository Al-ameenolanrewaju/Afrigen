"""add newsletter send attempt time

Revision ID: i7d8e9f0a1b2
Revises: h6c7d8e9f0a1
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa


revision = "i7d8e9f0a1b2"
down_revision = "h6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("newsletter_issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("send_attempted_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("newsletter_issues", schema=None) as batch_op:
        batch_op.drop_column("send_attempted_at")