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


def upgrade():
    op.create_index(
        "ix_generations_status_created_at",
        "generations",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_generations_created_at",
        "generations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_provider_logs_timestamp",
        "provider_logs",
        ["timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_paystack_webhook_logs_created_at",
        "paystack_webhook_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_payments_created_at",
        "payments",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_credit_ledger_created_at_user_id",
        "credit_ledger",
        ["created_at", "user_id"],
        unique=False,
    )
    op.create_table(
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
    op.create_index(
        "ix_monitoring_snapshots_monitor_key",
        "monitoring_snapshots",
        ["monitor_key"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_snapshots_observed_at",
        "monitoring_snapshots",
        ["observed_at"],
        unique=False,
    )
    op.create_table(
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
    op.create_index(
        "ix_monitoring_incidents_source",
        "monitoring_incidents",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_incidents_severity",
        "monitoring_incidents",
        ["severity"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_incidents_status",
        "monitoring_incidents",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_incidents_last_seen_at",
        "monitoring_incidents",
        ["last_seen_at"],
        unique=False,
    )
    op.create_table(
        "monitoring_incident_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["monitoring_incidents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitoring_incident_events_incident_id",
        "monitoring_incident_events",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_incident_events_event_type",
        "monitoring_incident_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_monitoring_incident_events_created_at",
        "monitoring_incident_events",
        ["created_at"],
        unique=False,
    )
    op.create_table(
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
    op.drop_table("monitoring_daily_reports")
    op.drop_index("ix_monitoring_incident_events_created_at", table_name="monitoring_incident_events")
    op.drop_index("ix_monitoring_incident_events_event_type", table_name="monitoring_incident_events")
    op.drop_index("ix_monitoring_incident_events_incident_id", table_name="monitoring_incident_events")
    op.drop_table("monitoring_incident_events")
    op.drop_index("ix_monitoring_incidents_last_seen_at", table_name="monitoring_incidents")
    op.drop_index("ix_monitoring_incidents_status", table_name="monitoring_incidents")
    op.drop_index("ix_monitoring_incidents_severity", table_name="monitoring_incidents")
    op.drop_index("ix_monitoring_incidents_source", table_name="monitoring_incidents")
    op.drop_table("monitoring_incidents")
    op.drop_index("ix_monitoring_snapshots_observed_at", table_name="monitoring_snapshots")
    op.drop_index("ix_monitoring_snapshots_monitor_key", table_name="monitoring_snapshots")
    op.drop_table("monitoring_snapshots")
    op.drop_index("ix_payments_created_at", table_name="payments")
    op.drop_index("ix_paystack_webhook_logs_created_at", table_name="paystack_webhook_logs")
    op.drop_index("ix_provider_logs_timestamp", table_name="provider_logs")
    op.drop_index("ix_credit_ledger_created_at_user_id", table_name="credit_ledger")
    op.drop_index("ix_generations_created_at", table_name="generations")
    op.drop_index("ix_generations_status_created_at", table_name="generations")
