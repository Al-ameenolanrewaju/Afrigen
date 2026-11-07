"""add newsletter delivery tracking

Revision ID: h6c7d8e9f0a1
Revises: g5b6c7d8e9f0
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa


revision = "h6c7d8e9f0a1"
down_revision = "g5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("newsletter_issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("attempted_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("failed_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("delivery_failures", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("newsletter_issues", schema=None) as batch_op:
        batch_op.drop_column("delivery_failures")
        batch_op.drop_column("failed_count")
        batch_op.drop_column("attempted_count")