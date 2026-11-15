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
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(sa.Column("brand_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_campaigns_brand_id",
            "brands",
            ["brand_id"],
            ["id"],
        )
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.add_column(sa.Column("brand_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_workflows_brand_id",
            "brands",
            ["brand_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_constraint("fk_workflows_brand_id", type_="foreignkey")
        batch_op.drop_column("brand_id")
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_constraint("fk_campaigns_brand_id", type_="foreignkey")
        batch_op.drop_column("brand_id")