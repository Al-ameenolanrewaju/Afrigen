"""add social automation engine models

Revision ID: u9d0e1f2a3b4
Revises: t8c9d0e1f2a3
Create Date: 2026-11-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'u9d0e1f2a3b4'
down_revision = 't8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('social_campaigns'):
        op.create_table(
            'social_campaigns',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('objective', sa.String(length=100), nullable=True),
            sa.Column('target_audience', sa.String(length=255), nullable=True),
            sa.Column('start_date', sa.DateTime(), nullable=True),
            sa.Column('end_date', sa.DateTime(), nullable=True),
            sa.Column('platforms_json', sa.Text(), nullable=True),
            sa.Column('content_strategy', sa.Text(), nullable=True),
            sa.Column('creative_requirements', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_social_campaigns_user_id', 'social_campaigns', ['user_id'])
        op.create_index('ix_social_campaigns_status', 'social_campaigns', ['status'])

    if not inspector.has_table('social_posts'):
        op.create_table(
            'social_posts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('campaign_id', sa.Integer(), nullable=True),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=True),
            sa.Column('content_pillar', sa.String(length=50), nullable=True),
            sa.Column('marketing_objective', sa.String(length=50), nullable=True),
            sa.Column('target_audience', sa.String(length=255), nullable=True),
            sa.Column('content_format', sa.String(length=50), nullable=True),
            sa.Column('caption', sa.Text(), nullable=False),
            sa.Column('hashtags', sa.String(length=500), nullable=True),
            sa.Column('call_to_action', sa.String(length=255), nullable=True),
            sa.Column('creative_instructions', sa.Text(), nullable=True),
            sa.Column('media_url', sa.Text(), nullable=True),
            sa.Column('media_type', sa.String(length=50), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=True),
            sa.Column('scheduled_at', sa.DateTime(), nullable=True),
            sa.Column('published_at', sa.DateTime(), nullable=True),
            sa.Column('remote_post_id', sa.String(length=255), nullable=True),
            sa.Column('published_url', sa.String(length=500), nullable=True),
            sa.Column('attempt_count', sa.Integer(), nullable=True),
            sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
            sa.Column('error_details', sa.Text(), nullable=True),
            sa.Column('quality_score', sa.Integer(), nullable=True),
            sa.Column('quality_checks_json', sa.Text(), nullable=True),
            sa.Column('idempotency_key', sa.String(length=120), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['campaign_id'], ['social_campaigns.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('idempotency_key')
        )
        op.create_index('ix_social_posts_user_id', 'social_posts', ['user_id'])
        op.create_index('ix_social_posts_campaign_id', 'social_posts', ['campaign_id'])
        op.create_index('ix_social_posts_platform', 'social_posts', ['platform'])
        op.create_index('ix_social_posts_status', 'social_posts', ['status'])
        op.create_index('ix_social_posts_scheduled_at', 'social_posts', ['scheduled_at'])

    if not inspector.has_table('social_media_assets'):
        op.create_table(
            'social_media_assets',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=True),
            sa.Column('campaign_id', sa.Integer(), nullable=True),
            sa.Column('media_type', sa.String(length=50), nullable=False),
            sa.Column('storage_path', sa.String(length=500), nullable=True),
            sa.Column('public_url', sa.Text(), nullable=False),
            sa.Column('provider', sa.String(length=50), nullable=True),
            sa.Column('model_name', sa.String(length=150), nullable=True),
            sa.Column('dimensions', sa.String(length=50), nullable=True),
            sa.Column('duration_seconds', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['campaign_id'], ['social_campaigns.id'], ),
            sa.ForeignKeyConstraint(['post_id'], ['social_posts.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_social_media_assets_user_id', 'social_media_assets', ['user_id'])
        op.create_index('ix_social_media_assets_post_id', 'social_media_assets', ['post_id'])

    if not inspector.has_table('social_publishing_jobs'):
        op.create_table(
            'social_publishing_jobs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('status', sa.String(length=30), nullable=True),
            sa.Column('scheduled_time', sa.DateTime(), nullable=False),
            sa.Column('locked_at', sa.DateTime(), nullable=True),
            sa.Column('locked_by', sa.String(length=100), nullable=True),
            sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
            sa.Column('attempt_count', sa.Integer(), nullable=True),
            sa.Column('max_attempts', sa.Integer(), nullable=True),
            sa.Column('next_retry_at', sa.DateTime(), nullable=True),
            sa.Column('idempotency_key', sa.String(length=120), nullable=False),
            sa.Column('response_data_json', sa.Text(), nullable=True),
            sa.Column('error_details', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['post_id'], ['social_posts.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('idempotency_key')
        )
        op.create_index('ix_social_publishing_jobs_user_id', 'social_publishing_jobs', ['user_id'])
        op.create_index('ix_social_publishing_jobs_post_id', 'social_publishing_jobs', ['post_id'])
        op.create_index('ix_social_publishing_jobs_status', 'social_publishing_jobs', ['status'])
        op.create_index('ix_social_publishing_jobs_scheduled_time', 'social_publishing_jobs', ['scheduled_time'])
        op.create_index('ix_social_publishing_jobs_lease_expires_at', 'social_publishing_jobs', ['lease_expires_at'])

    if not inspector.has_table('social_analytics'):
        op.create_table(
            'social_analytics',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('remote_post_id', sa.String(length=255), nullable=True),
            sa.Column('impressions', sa.Integer(), nullable=True),
            sa.Column('reactions', sa.Integer(), nullable=True),
            sa.Column('comments', sa.Integer(), nullable=True),
            sa.Column('shares', sa.Integer(), nullable=True),
            sa.Column('clicks', sa.Integer(), nullable=True),
            sa.Column('engagement_rate', sa.Float(), nullable=True),
            sa.Column('raw_metrics_json', sa.Text(), nullable=True),
            sa.Column('synced_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['post_id'], ['social_posts.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('post_id')
        )
        op.create_index('ix_social_analytics_user_id', 'social_analytics', ['user_id'])
        op.create_index('ix_social_analytics_platform', 'social_analytics', ['platform'])

    if not inspector.has_table('social_automation_settings'):
        op.create_table(
            'social_automation_settings',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=True),
            sa.Column('emergency_paused', sa.Boolean(), nullable=True),
            sa.Column('facebook_enabled', sa.Boolean(), nullable=True),
            sa.Column('linkedin_enabled', sa.Boolean(), nullable=True),
            sa.Column('daily_limit_facebook', sa.Integer(), nullable=True),
            sa.Column('daily_limit_linkedin', sa.Integer(), nullable=True),
            sa.Column('preferred_posting_hours_json', sa.Text(), nullable=True),
            sa.Column('timezone_str', sa.String(length=50), nullable=True),
            sa.Column('pillar_ratios_json', sa.Text(), nullable=True),
            sa.Column('allow_video_generation', sa.Boolean(), nullable=True),
            sa.Column('allow_image_generation', sa.Boolean(), nullable=True),
            sa.Column('hf_image_model', sa.String(length=150), nullable=True),
            sa.Column('hf_video_model', sa.String(length=150), nullable=True),
            sa.Column('max_monthly_video_budget', sa.Integer(), nullable=True),
            sa.Column('notify_on_publish', sa.Boolean(), nullable=True),
            sa.Column('notify_on_failure', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id')
        )
        op.create_index('ix_social_automation_settings_user_id', 'social_automation_settings', ['user_id'])

    if not inspector.has_table('ai_content_history'):
        op.create_table(
            'ai_content_history',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=True),
            sa.Column('platform', sa.String(length=50), nullable=False),
            sa.Column('caption_hash', sa.String(length=64), nullable=False),
            sa.Column('hook_text', sa.String(length=255), nullable=True),
            sa.Column('topic', sa.String(length=150), nullable=True),
            sa.Column('keywords_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['post_id'], ['social_posts.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_ai_content_history_user_id', 'ai_content_history', ['user_id'])
        op.create_index('ix_ai_content_history_caption_hash', 'ai_content_history', ['caption_hash'])


def downgrade():
    op.drop_table('ai_content_history')
    op.drop_table('social_automation_settings')
    op.drop_table('social_analytics')
    op.drop_table('social_publishing_jobs')
    op.drop_table('social_media_assets')
    op.drop_table('social_posts')
    op.drop_table('social_campaigns')
