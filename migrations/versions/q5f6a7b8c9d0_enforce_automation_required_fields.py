"""enforce required automation fields

Revision ID: q5f6a7b8c9d0
Revises: p4e5f6a7b8c9
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa


revision = "q5f6a7b8c9d0"
down_revision = "p4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("workflows", "legacy_id", existing_type=sa.String(length=100), nullable=False)
    op.alter_column("workflows", "name", existing_type=sa.String(length=255), nullable=False)
    op.alter_column("workflows", "trigger", existing_type=sa.String(length=50), nullable=False)
    op.alter_column("workflow_tasks", "node_index", existing_type=sa.Integer(), nullable=False)


def downgrade():
    op.alter_column("workflow_tasks", "node_index", existing_type=sa.Integer(), nullable=True)
    op.alter_column("workflows", "trigger", existing_type=sa.String(length=50), nullable=True)
    op.alter_column("workflows", "name", existing_type=sa.String(length=255), nullable=True)
    op.alter_column("workflows", "legacy_id", existing_type=sa.String(length=100), nullable=True)
