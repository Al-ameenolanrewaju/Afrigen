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
    bind = op.get_bind()
    existing_ids = set(
        bind.execute(sa.text("SELECT legacy_id FROM workflows WHERE legacy_id IS NOT NULL"))
        .scalars()
        .all()
    )
    missing_workflows = bind.execute(
        sa.text("SELECT id FROM workflows WHERE legacy_id IS NULL OR name IS NULL OR trigger IS NULL")
    ).all()
    for row in missing_workflows:
        workflow_id = row[0]
        legacy_id = "legacy-migrated-{}".format(workflow_id)
        suffix = 1
        while legacy_id in existing_ids:
            legacy_id = "legacy-migrated-{}-{}".format(workflow_id, suffix)
            suffix += 1
        existing_ids.add(legacy_id)
        bind.execute(
            sa.text(
                "UPDATE workflows SET legacy_id = COALESCE(legacy_id, :legacy_id), "
                "name = COALESCE(name, :name), trigger = COALESCE(trigger, 'manual') "
                "WHERE id = :workflow_id"
            ),
            {
                "legacy_id": legacy_id,
                "name": "Legacy workflow {}".format(workflow_id),
                "workflow_id": workflow_id,
            },
        )
    bind.execute(
        sa.text("UPDATE workflow_tasks SET node_index = 0 WHERE node_index IS NULL")
    )
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.alter_column("legacy_id", existing_type=sa.String(length=100), nullable=False)
        batch_op.alter_column("name", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("trigger", existing_type=sa.String(length=50), nullable=False)
    with op.batch_alter_table("workflow_tasks") as batch_op:
        batch_op.alter_column("node_index", existing_type=sa.Integer(), nullable=False)


def downgrade():
    with op.batch_alter_table("workflow_tasks") as batch_op:
        batch_op.alter_column("node_index", existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.alter_column("trigger", existing_type=sa.String(length=50), nullable=True)
        batch_op.alter_column("name", existing_type=sa.String(length=255), nullable=True)
        batch_op.alter_column("legacy_id", existing_type=sa.String(length=100), nullable=True)
