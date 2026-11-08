"""add free_video_allowance to users

Revision ID: s7b8c9d0e1f2
Revises: r6a7b8c9d0e1
Create Date: 2026-11-07 15:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 's7b8c9d0e1f2'
down_revision = 'r6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('users')}
    if 'free_video_allowance' not in columns:
        op.add_column(
            'users',
            sa.Column('free_video_allowance', sa.Integer(), nullable=False, server_default='0')
        )


def downgrade():
    op.drop_column('users', 'free_video_allowance')

