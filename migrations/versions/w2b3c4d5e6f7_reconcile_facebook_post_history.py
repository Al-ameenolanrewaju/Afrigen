"""Ensure the legacy Facebook post history table exists on fresh installs.

Revision ID: w2b3c4d5e6f7
Revises: v1a2b3c4d5e6
"""

from alembic import op
import sqlalchemy as sa


revision = "w2b3c4d5e6f7"
down_revision = "v1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("facebook_post_history"):
        op.create_table(
            "facebook_post_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("content_type", sa.String(length=50), nullable=False),
            sa.Column("blog_url", sa.String(length=500), nullable=True),
            sa.Column("post_text", sa.Text(), nullable=False),
            sa.Column("facebook_post_id", sa.String(length=200), nullable=False),
            sa.Column("image_used", sa.String(length=500), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade():
    # This legacy table may predate the migration and contain publishing history.
    pass
