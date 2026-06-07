"""add telegram account link

Revision ID: c3e7a1b9d2f4
Revises: b1c2d3e4f5a6
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e7a1b9d2f4'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    # One-time code (shown on the dashboard) used to link a Telegram account.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('telegram_link_code', sa.String(length=20), nullable=True)
        )

    # The website account a Telegram user is linked to; generation through the
    # bot draws from this user's plan / credits / limits.
    with op.batch_alter_table('telegram_users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('user_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_telegram_users_user_id_users',
            'users',
            ['user_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('telegram_users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_telegram_users_user_id_users', type_='foreignkey')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('telegram_link_code')
