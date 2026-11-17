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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("newsletter_issues"):
        return
    columns = {column["name"] for column in inspector.get_columns("newsletter_issues")}
    if "research_sources_json" not in columns:
        op.add_column(
            "newsletter_issues",
            sa.Column("research_sources_json", sa.Text(), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("newsletter_issues"):
        return
    columns = {column["name"] for column in inspector.get_columns("newsletter_issues")}
    if "research_sources_json" in columns:
        op.drop_column("newsletter_issues", "research_sources_json")
