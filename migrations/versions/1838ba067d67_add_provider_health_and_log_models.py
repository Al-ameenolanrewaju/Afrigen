"""Add provider health and log models

Revision ID: 1838ba067d67
Revises: 7dbdc62e7d17
Create Date: 2026-07-16 15:52:24.192457

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1838ba067d67'
down_revision = '7dbdc62e7d17'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('provider_health',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider_name', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('success_count', sa.Integer(), nullable=True),
    sa.Column('failure_count', sa.Integer(), nullable=True),
    sa.Column('total_latency', sa.Float(), nullable=True),
    sa.Column('total_requests', sa.Integer(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_name')
    )
    op.create_table('provider_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_type', sa.String(length=50), nullable=False),
    sa.Column('provider_used', sa.String(length=50), nullable=False),
    sa.Column('fallback_triggered', sa.Boolean(), nullable=True),
    sa.Column('latency', sa.Float(), nullable=True),
    sa.Column('estimated_tokens', sa.Integer(), nullable=True),
    sa.Column('estimated_cost', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('provider_logs')
    op.drop_table('provider_health')
