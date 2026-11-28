"""Persist per-platform outcomes for unified marketing campaigns.

Revision ID: z5e6f7a8b9c0
Revises: y4d5e6f7a8b9
"""
from alembic import op
import sqlalchemy as sa

revision = "z5e6f7a8b9c0"
down_revision = "y4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("newsletter_campaigns"):
        columns = {column["name"] for column in inspector.get_columns("newsletter_campaigns")}
        if "social_results" not in columns:
            op.add_column(
                "newsletter_campaigns",
                sa.Column("social_results", sa.Text(), nullable=True),
            )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("newsletter_campaigns"):
        columns = {column["name"] for column in inspector.get_columns("newsletter_campaigns")}
        if "social_results" in columns:
            op.drop_column("newsletter_campaigns", "social_results")
