from datetime import datetime, timezone

from models import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MonitoringSnapshot(db.Model):
    __tablename__ = "monitoring_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    run_key = db.Column(db.String(120), unique=True, nullable=False)
    monitor_key = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False)
    summary = db.Column(db.String(255), nullable=False)
    metrics = db.Column(db.JSON, nullable=False, default=dict)
    observed_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)


class MonitoringIncident(db.Model):
    __tablename__ = "monitoring_incidents"

    id = db.Column(db.Integer, primary_key=True)
    fingerprint = db.Column(db.String(180), unique=True, nullable=False)
    source = db.Column(db.String(64), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    severity = db.Column(db.String(16), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    evidence = db.Column(db.JSON, nullable=False, default=dict)
    recommendation = db.Column(db.Text, nullable=False, default="")
    first_seen_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    occurrences = db.Column(db.Integer, nullable=False, default=1)
    assigned_to = db.Column(db.String(255))
    administrator_note = db.Column(db.Text)
    acknowledged_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def __repr__(self):
        return "<MonitoringIncident {} {}>".format(self.id, self.fingerprint)


class MonitoringIncidentEvent(db.Model):
    __tablename__ = "monitoring_incident_events"

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(
        db.Integer,
        db.ForeignKey("monitoring_incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.String(32), nullable=False, index=True)
    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
    )
    note = db.Column(db.String(1000))
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)


class MonitoringDailyReport(db.Model):
    __tablename__ = "monitoring_daily_reports"

    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.Date, nullable=False, unique=True)
    facts = db.Column(db.JSON, nullable=False, default=dict)
    recommendations = db.Column(db.JSON, nullable=False, default=list)
    generated_at = db.Column(db.DateTime, nullable=False, default=_utcnow)


def ensure_monitoring_tables(engine=None):
    """Ensure all monitoring tables exist in the database without requiring a separate migration."""
    try:
        if engine is None:
            engine = db.engine
        inspector = db.inspect(engine)
        for model in (MonitoringSnapshot, MonitoringIncident, MonitoringIncidentEvent, MonitoringDailyReport):
            if not inspector.has_table(model.__tablename__):
                model.__table__.create(bind=engine, checkfirst=True)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("ensure_monitoring_tables check: %s", exc)
