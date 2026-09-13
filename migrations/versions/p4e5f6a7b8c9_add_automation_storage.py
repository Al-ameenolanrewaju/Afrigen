"""add database storage for automations

Revision ID: p4e5f6a7b8c9
Revises: o3d4e5f6a7b8
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa


revision = "p4e5f6a7b8c9"
down_revision = "o3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.add_column(sa.Column("legacy_id", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("trigger", sa.String(length=50), nullable=True))
        batch_op.alter_column("campaign_id", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_constraint("workflows_campaign_id_key", type_="unique")
        batch_op.create_foreign_key("fk_workflows_user_id", "users", ["user_id"], ["id"])
        batch_op.create_unique_constraint("uq_workflows_legacy_id", ["legacy_id"])

    with op.batch_alter_table("workflow_tasks") as batch_op:
        batch_op.add_column(sa.Column("node_index", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("node_config", sa.Text(), nullable=True))

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("legacy_id", sa.String(length=100), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("workflow_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("credits_used", sa.Integer(), nullable=False),
        sa.Column("nodes_executed", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_id"),
    )
    op.create_table(
        "workflow_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("legacy_id", sa.String(length=100), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=True),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("provider_used", sa.String(length=100), nullable=True),
        sa.Column("generation_time", sa.Float(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_id"),
    )


def downgrade():
    op.drop_table("workflow_assets")
    op.drop_table("workflow_runs")
    with op.batch_alter_table("workflow_tasks") as batch_op:
        batch_op.drop_column("node_config")
        batch_op.drop_column("node_index")
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_constraint("uq_workflows_legacy_id", type_="unique")
        batch_op.drop_constraint("fk_workflows_user_id", type_="foreignkey")
        batch_op.create_unique_constraint("uq_workflows_campaign_id", ["campaign_id"])
        batch_op.alter_column("campaign_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("trigger")
        batch_op.drop_column("name")
        batch_op.drop_column("user_id")
        batch_op.drop_column("legacy_id")