"""Add persistent monitoring snapshots and incidents.

Revision ID: v1a2b3c4d5e6
Revises: u9d0e1f2a3b4
"""

from alembic import op
import sqlalchemy as sa


revision = "v1a2b3c4d5e6"
down_revision = "u9d0e1f2a3b4"
branch_labels = None
depends_on = None


def _create_index_if_missing(table_name, index_name, columns):
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        raise RuntimeError(
            "Cannot create index {}: table {} does not exist.".format(index_name, table_name)
        )
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=False)


def _create_table_if_missing(name, *columns_and_constraints):
    if not sa.inspect(op.get_bind()).has_table(name):
        op.create_table(name, *columns_and_constraints)


def upgrade():
    for table_name, index_name, columns in (
        ("generations", "ix_generations_status_created_at", ["status", "created_at"]),
        ("generations", "ix_generations_created_at", ["created_at"]),
        ("provider_logs", "ix_provider_logs_timestamp", ["timestamp"]),
        ("paystack_webhook_logs", "ix_paystack_webhook_logs_created_at", ["created_at"]),
        ("payments", "ix_payments_created_at", ["created_at"]),
        ("credit_ledger", "ix_credit_ledger_created_at_user_id", ["created_at", "user_id"]),
    ):
        _create_index_if_missing(table_name, index_name, columns)

    _create_table_if_missing(
        "monitoring_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=120), nullable=False),
        sa.Column("monitor_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key"),
    )
    _create_index_if_missing(
        "monitoring_snapshots", "ix_monitoring_snapshots_monitor_key", ["monitor_key"]
    )
    _create_index_if_missing(
        "monitoring_snapshots", "ix_monitoring_snapshots_observed_at", ["observed_at"]
    )

    _create_table_if_missing(
        "monitoring_incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=180), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False, server_default=""),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("administrator_note", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    for index_name, columns in (
        ("ix_monitoring_incidents_source", ["source"]),
        ("ix_monitoring_incidents_severity", ["severity"]),
        ("ix_monitoring_incidents_status", ["status"]),
        ("ix_monitoring_incidents_last_seen_at", ["last_seen_at"]),
    ):
        _create_index_if_missing("monitoring_incidents", index_name, columns)

    _create_table_if_missing(
        "monitoring_incident_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["monitoring_incidents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns in (
        ("ix_monitoring_incident_events_incident_id", ["incident_id"]),
        ("ix_monitoring_incident_events_event_type", ["event_type"]),
        ("ix_monitoring_incident_events_created_at", ["created_at"]),
    ):
        _create_index_if_missing("monitoring_incident_events", index_name, columns)

    _create_table_if_missing(
        "monitoring_daily_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_date"),
    )


def downgrade():
    # These tables are also provisioned by application startup before migrations
    # run. Their provenance is therefore unknown here, and dropping them could
    # destroy monitoring data that predates this revision.
    pass
