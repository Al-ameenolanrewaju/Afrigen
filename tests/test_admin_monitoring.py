from datetime import datetime, timedelta, timezone
import re

from app import app
from models import CreditLedger, Generation, Payment, User, db
from monitoring_models import (
    MonitoringDailyReport,
    MonitoringIncident,
    MonitoringIncidentEvent,
    MonitoringSnapshot,
)
from services.monitoring import (
    CHECKS,
    generate_daily_intelligence_report,
    run_monitoring_cycle,
)


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def _admin_client(monkeypatch):
    from routes import main as main_routes

    monkeypatch.setattr(main_routes, "is_admin_user", lambda user: True)
    with app.app_context():
        admin = User(username="monitor_admin", email="monitor-admin@example.test", password="test")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["_user_id"] = str(admin_id)
        browser_session["_fresh"] = True
    return client


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_health_endpoint_reports_only_readiness_status(monkeypatch):
    client = app.test_client()
    healthy = client.get("/healthz")
    assert healthy.status_code == 200
    assert healthy.json == {"status": "ok"}

    def fail_probe(*_args, **_kwargs):
        raise RuntimeError("database password must not be exposed")

    monkeypatch.setattr(db.session, "execute", fail_probe)
    unhealthy = client.get("/healthz")
    assert unhealthy.status_code == 503
    assert unhealthy.json == {"status": "unhealthy", "dependency": "database"}
    assert b"password" not in unhealthy.data


def test_health_endpoint_is_not_ready_before_monitoring_migration(monkeypatch):
    class IncompleteSchemaInspector:
        @staticmethod
        def get_table_names():
            return ["users", "generations"]

    monkeypatch.setattr(db, "inspect", lambda _engine: IncompleteSchemaInspector())
    response = app.test_client().get("/healthz")
    assert response.status_code == 503
    assert response.json == {"status": "unhealthy", "dependency": "schema"}


def test_monitoring_cycle_persists_snapshots_and_deduplicates_incidents():
    now = _utcnow()
    with app.app_context():
        user = User(username="monitor_user", email="monitor-user@example.test", password="test")
        db.session.add(user)
        db.session.commit()
        db.session.add(
            Generation(
                user_id=user.id,
                original_prompt="private prompt must not be stored in monitoring data",
                refined_prompt="private prompt must not be stored in monitoring data",
                generation_type="video",
                status="processing",
                created_at=now - timedelta(minutes=20),
            )
        )
        db.session.commit()

        first = run_monitoring_cycle(now=now)
        second = run_monitoring_cycle(now=now + timedelta(seconds=30))

        assert len(first) == len(second) == len(CHECKS)
        generation_snapshot = MonitoringSnapshot.query.filter_by(
            monitor_key="generation_lifecycle"
        ).one()
        assert generation_snapshot.status == "critical"
        incident = MonitoringIncident.query.filter_by(
            fingerprint="generation_lifecycle"
        ).one()
        assert incident.occurrences == 2
        assert "private prompt" not in str(generation_snapshot.metrics)
        assert MonitoringSnapshot.query.count() == len(CHECKS)
        assert "ix_generations_status_created_at" in {
            index.name for index in Generation.__table__.indexes
        }


def test_recovered_monitor_incident_is_resolved_and_can_be_reopened():
    now = _utcnow()
    with app.app_context():
        user = User(username="recovery_user", email="recovery@example.test", password="test")
        db.session.add(user)
        db.session.commit()
        generation = Generation(
            user_id=user.id,
            original_prompt="test",
            refined_prompt="test",
            generation_type="video",
            status="processing",
            created_at=now - timedelta(minutes=20),
        )
        db.session.add(generation)
        db.session.commit()

        run_monitoring_cycle(now=now)
        incident = MonitoringIncident.query.filter_by(
            fingerprint="generation_lifecycle"
        ).one()
        assert incident.status == "open"

        generation.status = "completed"
        generation.video_url = "https://media.example.test/completed.mp4"
        db.session.commit()
        run_monitoring_cycle(now=now + timedelta(minutes=1))
        assert incident.status == "resolved"

        generation.status = "processing"
        db.session.commit()
        run_monitoring_cycle(now=now + timedelta(minutes=2))
        assert incident.status == "open"
        assert [event.event_type for event in MonitoringIncidentEvent.query.filter_by(
            incident_id=incident.id
        ).order_by(MonitoringIncidentEvent.created_at.asc()).all()] == [
            "detected",
            "resolved",
            "reopened",
        ]


def test_stale_pending_generation_creates_abandonment_alert():
    now = _utcnow()
    with app.app_context():
        user = User(username="pending_user", email="pending@example.test", password="test")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            Generation(
                user_id=user.id,
                original_prompt="test",
                refined_prompt="test",
                generation_type="image",
                status="pending",
                created_at=now - timedelta(minutes=15),
            )
        )
        db.session.commit()

        results = run_monitoring_cycle(now=now)
        result = next(
            item for item in results if item["monitor_key"] == "generation_abandonment"
        )

        assert result["status"] == "warning"
        assert result["metrics"]["stale_pending"] == 1
        incident = MonitoringIncident.query.filter_by(
            fingerprint="generation_abandonment"
        ).one()
        assert incident.status == "open"


def test_revenue_check_uses_recorded_payment_amounts_and_periods():
    now = _utcnow()
    with app.app_context():
        user = User(username="revenue_user", email="revenue@example.test", password="test")
        db.session.add(user)
        db.session.commit()
        db.session.add_all(
            [
                Payment(
                    user_id=user.id,
                    reference="monitor-current",
                    amount=12500,
                    plan="creator",
                    created_at=now - timedelta(days=2),
                ),
                Payment(
                    user_id=user.id,
                    reference="monitor-previous",
                    amount=5000,
                    plan="creator",
                    created_at=now - timedelta(days=45),
                ),
            ]
        )
        db.session.commit()

        results = run_monitoring_cycle(now=now)
        revenue = next(item for item in results if item["monitor_key"] == "confirmed_revenue")

        assert revenue["status"] == "healthy"
        assert revenue["metrics"]["confirmed_revenue_ngn_30d"] == 125
        assert revenue["metrics"]["confirmed_revenue_ngn_previous_30d"] == 50
        assert revenue["metrics"]["payment_records_30d"] == 1


def test_command_centre_requires_admin_and_renders_persisted_data(monkeypatch):
    client = app.test_client()
    assert client.get("/admin/command-centre").status_code == 302

    admin_client = _admin_client(monkeypatch)
    with app.app_context():
        db.session.add(
            MonitoringSnapshot(
                run_key="database:test-window",
                monitor_key="database",
                status="healthy",
                summary="Database query succeeded.",
                metrics={"query_ok": True},
                observed_at=_utcnow(),
            )
        )
        db.session.commit()

    response = admin_client.get("/admin/command-centre")
    assert response.status_code == 200
    assert b"Command Centre" in response.data
    assert b"Database query succeeded." in response.data
    assert b"Run checks now" in response.data
    assert b"Daily intelligence report" in response.data
    token = re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()

    generated = admin_client.post(
        "/admin/command-centre/daily-report",
        data={"csrf_token": token},
    )
    assert generated.status_code == 302
    with app.app_context():
        assert MonitoringDailyReport.query.count() == 1
    assert b"Command Centre" in admin_client.get("/admin/command-centre").data


def test_incident_updates_validate_status_and_save_assignment(monkeypatch):
    client = _admin_client(monkeypatch)
    with app.app_context():
        incident = MonitoringIncident(
            fingerprint="test_monitor",
            source="test_monitor",
            title="Test incident",
            severity="warning",
            status="open",
            evidence={"observed": 1},
        )
        db.session.add(incident)
        db.session.commit()
        incident_id = incident.id
        page = client.get("/admin/command-centre")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()

    response = client.post(
        "/admin/command-centre/incidents/{}".format(incident_id),
        data={
            "csrf_token": token,
            "status": "investigating",
            "assigned_to": "admin@example.test",
            "administrator_note": "Checking the monitor.",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        incident = db.session.get(MonitoringIncident, incident_id)
        assert incident.status == "investigating"
        assert incident.assigned_to == "admin@example.test"
        assert incident.administrator_note == "Checking the monitor."
        admin_id = User.query.filter_by(username="monitor_admin").one().id
        events = MonitoringIncidentEvent.query.filter_by(incident_id=incident_id).all()
        assert {event.event_type for event in events} == {
            "status_changed",
            "acknowledged",
            "assignment_changed",
            "note_updated",
        }
        assert all(event.actor_user_id == admin_id for event in events)
    assert b"Recent timeline" in client.get("/admin/command-centre").data

    invalid = client.post(
        "/admin/command-centre/incidents/{}".format(incident_id),
        data={"csrf_token": token, "status": "suspended"},
    )
    assert invalid.status_code == 302
    with app.app_context():
        assert db.session.get(MonitoringIncident, incident_id).status == "investigating"


def test_daily_report_is_idempotent_and_separates_recorded_facts_from_estimates(monkeypatch):
    now = _utcnow()
    monkeypatch.setenv("MONITORING_CREDIT_BURN_WARNING", "500")
    with app.app_context():
        user = User(
            username="report_user",
            email="report@example.test",
            password="test",
            signup_at=now,
        )
        db.session.add(user)
        db.session.flush()
        db.session.add_all(
            [
                Generation(
                    user_id=user.id,
                    original_prompt="do not store this",
                    refined_prompt="do not store this",
                    generation_type="image",
                    status="completed",
                    image_url=None,
                    created_at=now,
                ),
                Payment(
                    user_id=user.id,
                    reference="daily-report-payment",
                    amount=32000,
                    plan="creator",
                    created_at=now,
                ),
                CreditLedger(
                    user_id=user.id,
                    delta=-600,
                    reason="generation",
                    created_at=now,
                ),
            ]
        )
        db.session.commit()

        results = run_monitoring_cycle(now=now)
        generation_result = next(
            item for item in results if item["monitor_key"] == "generation_lifecycle"
        )
        credit_result = next(
            item for item in results if item["monitor_key"] == "credit_consumption"
        )
        report = generate_daily_intelligence_report(now=now)
        repeated = generate_daily_intelligence_report(now=now + timedelta(minutes=1))

        assert generation_result["status"] == "warning"
        assert generation_result["metrics"]["completed_missing_image"] == 1
        assert credit_result["status"] == "warning"
        assert credit_result["metrics"]["affected_accounts"] == [
            {"user_id": user.id, "credits_spent_24h": 600}
        ]
        assert report.id == repeated.id
        assert MonitoringDailyReport.query.count() == 1
        assert report.facts["user_signups"]["value"] == 1
        assert report.facts["payment_activity"]["recorded_revenue_ngn"] == 320
        assert report.facts["provider_cost"]["classification"] == "estimate"
        assert "do not store this" not in str(report.facts)
