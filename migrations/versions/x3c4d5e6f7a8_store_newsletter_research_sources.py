"""Persist newsletter research sources for editorial approval.

Revision ID: x3c4d5e6f7a8
Revises: w2b3c4d5e6f7
"""

from alembic import op
import sqlalchemy as sa


revision = "x3c4d5e6f7a8"
down_revision = "w2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("newsletter_issues") as batch_op:
        batch_op.add_column(sa.Column("research_sources_json", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("newsletter_issues") as batch_op:
        batch_op.drop_column("research_sources_json")
