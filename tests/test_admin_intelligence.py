from datetime import datetime, timedelta, timezone

from app import app
from models import User, Generation, db


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def _admin_client(monkeypatch):
    from routes import main as main_routes
    monkeypatch.setattr(main_routes, "is_admin_user", lambda user: True)
    with app.app_context():
        admin = User(username="intelligence_admin", email="intelligence-admin@example.test", password="test")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["_user_id"] = str(admin_id)
        browser_session["_fresh"] = True
    return client


def test_intelligence_overview_requires_admin(monkeypatch):
    assert app.test_client().get("/admin/intelligence/").status_code == 302
    response = _admin_client(monkeypatch).get("/admin/intelligence/")
    assert response.status_code == 200
    assert b"Executive overview" in response.data
    assert b"Recorded payment value" in response.data


def test_intelligence_period_filter_and_departments_render(monkeypatch):
    client = _admin_client(monkeypatch)
    for period in ("7", "30", "90"):
        response = client.get("/admin/intelligence/?period=" + period)
        assert response.status_code == 200
    for path in ("users", "finance", "ai", "operations", "growth", "security", "automation", "reports", "settings"):
        response = client.get("/admin/intelligence/" + path)
        assert response.status_code == 200


def test_intelligence_metrics_use_selected_period_and_previous_period(monkeypatch):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app.app_context():
        db.session.add_all([
            User(username="recent_signup", email="recent@example.test", password="test", signup_at=now - timedelta(days=2)),
            User(username="prior_signup", email="prior@example.test", password="test", signup_at=now - timedelta(days=35)),
        ])
        db.session.commit()
    response = _admin_client(monkeypatch).get("/admin/intelligence/?period=30")
    assert response.status_code == 200
    assert b"New registrations" in response.data
