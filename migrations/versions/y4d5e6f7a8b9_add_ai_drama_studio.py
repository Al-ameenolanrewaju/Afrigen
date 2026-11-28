"""Add AI Drama Studio series, episode, character, usage and job tables.

Revision ID: y4d5e6f7a8b9
Revises: x3c4d5e6f7a8, 8449b98dc5d7
"""

from alembic import op
import sqlalchemy as sa

revision = "y4d5e6f7a8b9"
down_revision = ("x3c4d5e6f7a8", "8449b98dc5d7")
branch_labels = None
depends_on = None


def _create_table(name, *columns, **kwargs):
    if not sa.inspect(op.get_bind()).has_table(name):
        op.create_table(name, *columns, **kwargs)


def _create_index(table, name, columns, unique=False):
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(table):
        existing = {item["name"] for item in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns, unique=unique)


def upgrade():
    _create_table(
        "drama_series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("logline", sa.Text()),
        sa.Column("synopsis", sa.Text()),
        sa.Column("genre", sa.String(100), nullable=False, server_default="Drama"),
        sa.Column("visual_style", sa.String(100), nullable=False, server_default="cinematic"),
        sa.Column("dialogue_language", sa.String(40), nullable=False, server_default="nigerian_pidgin"),
        sa.Column("aspect_ratio", sa.String(20), nullable=False, server_default="9:16"),
        sa.Column("episode_duration_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index("drama_series", "ix_drama_series_user_id", ["user_id"])
    _create_index("drama_series", "ix_drama_series_status", ["status"])

    _create_table(
        "drama_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("drama_series.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(100), nullable=False, server_default="Supporting"),
        sa.Column("description", sa.Text()),
        sa.Column("personality", sa.Text()),
        sa.Column("physical_appearance", sa.Text()),
        sa.Column("signature_clothing", sa.Text()),
        sa.Column("voice_id", sa.String(120)),
        sa.Column("reference_image_url", sa.String(1000)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("series_id", "name", name="uq_drama_character_series_name"),
    )
    _create_index("drama_characters", "ix_drama_characters_series_id", ["series_id"])

    _create_table(
        "drama_episodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("drama_series.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("movie_project_id", sa.Integer(), sa.ForeignKey("movie_projects.id"), unique=True),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("logline", sa.Text()),
        sa.Column("synopsis", sa.Text()),
        sa.Column("target_duration_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("quota_period_start", sa.Date()),
        sa.Column("quota_status", sa.String(20), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("series_id", "episode_number", name="uq_drama_episode_number"),
    )
    _create_index("drama_episodes", "ix_drama_episodes_series_id", ["series_id"])
    _create_index("drama_episodes", "ix_drama_episodes_user_id", ["user_id"])
    _create_index("drama_episodes", "ix_drama_episodes_status", ["status"])
    _create_index("drama_episodes", "ix_drama_episodes_quota_period_start", ["quota_period_start"])

    _create_table(
        "drama_episode_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("drama_episodes.id"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("drama_characters.id"), nullable=False),
        sa.Column("movie_character_id", sa.Integer(), sa.ForeignKey("movie_characters.id"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("episode_id", "character_id", name="uq_drama_episode_character"),
    )
    _create_index("drama_episode_characters", "ix_drama_episode_characters_episode_id", ["episode_id"])
    _create_index("drama_episode_characters", "ix_drama_episode_characters_character_id", ["character_id"])

    _create_table(
        "drama_shot_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("movie_shot_id", sa.Integer(), sa.ForeignKey("movie_shots.id"), nullable=False),
        sa.Column("episode_character_id", sa.Integer(), sa.ForeignKey("drama_episode_characters.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("movie_shot_id", "episode_character_id", name="uq_drama_shot_character"),
    )
    _create_index("drama_shot_characters", "ix_drama_shot_characters_movie_shot_id", ["movie_shot_id"])
    _create_index("drama_shot_characters", "ix_drama_shot_characters_episode_character_id", ["episode_character_id"])

    _create_table(
        "drama_monthly_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("episodes_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("episodes_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "period_start", name="uq_drama_usage_user_period"),
    )
    _create_index("drama_monthly_usage", "ix_drama_monthly_usage_user_id", ["user_id"])

    _create_table(
        "drama_production_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("drama_episodes.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(50), nullable=False, server_default="screenplay"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index("drama_production_jobs", "ix_drama_production_jobs_episode_id", ["episode_id"])
    _create_index("drama_production_jobs", "ix_drama_production_jobs_user_id", ["user_id"])
    _create_index("drama_production_jobs", "ix_drama_production_jobs_status", ["status"])

    _create_table(
        "drama_usage_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("drama_episodes.id")),
        sa.Column("usage_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="recorded"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(180), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index("drama_usage_ledger", "ix_drama_usage_ledger_user_id", ["user_id"])
    _create_index("drama_usage_ledger", "ix_drama_usage_ledger_episode_id", ["episode_id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in (
        "drama_usage_ledger", "drama_production_jobs", "drama_monthly_usage",
        "drama_shot_characters", "drama_episode_characters", "drama_episodes",
        "drama_characters", "drama_series",
    ):
        if inspector.has_table(table):
            op.drop_table(table)
