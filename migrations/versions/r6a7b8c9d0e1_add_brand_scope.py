"""add explicit brand scope to campaigns and workflows

Revision ID: r6a7b8c9d0e1
Revises: q5f6a7b8c9d0
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa


revision = "r6a7b8c9d0e1"
down_revision = "q5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("campaigns", sa.Column("brand_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_campaigns_brand_id", "campaigns", "brands", ["brand_id"], ["id"])
    op.add_column("workflows", sa.Column("brand_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_workflows_brand_id", "workflows", "brands", ["brand_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_workflows_brand_id", "workflows", type_="foreignkey")
    op.drop_column("workflows", "brand_id")
    op.drop_constraint("fk_campaigns_brand_id", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "brand_id")