"""track website visits by source

Revision ID: t8c9d0e1f2a3
Revises: s7b8c9d0e1f2
Create Date: 2026-11-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 't8c9d0e1f2a3'
down_revision = 's7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('website_visits'):
        op.create_table(
            'website_visits',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source', sa.String(length=120), nullable=False),
            sa.Column('landing_page', sa.String(length=500), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_index('website_visits', 'ix_website_visits_source'):
        op.create_index('ix_website_visits_source', 'website_visits', ['source'])
    if not inspector.has_index('website_visits', 'ix_website_visits_created_at'):
        op.create_index('ix_website_visits_created_at', 'website_visits', ['created_at'])


def downgrade():
    op.drop_index('ix_website_visits_created_at', table_name='website_visits')
    op.drop_index('ix_website_visits_source', table_name='website_visits')
    op.drop_table('website_visits')