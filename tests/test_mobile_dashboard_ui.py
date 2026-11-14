from app import app
from models import db, User


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def _logged_in_client():
    with app.app_context():
        user = User(
            username="mobile_dashboard",
            email="mobile_dashboard@example.test",
            password="test-password",
            plan="spark",
            credits=18,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client


def test_dashboard_keeps_data_access_and_five_destination_mobile_navigation():
    response = _logged_in_client().get("/dashboard")
    assert response.status_code == 200
    assert b'class="metrics-row"' in response.data
    assert response.data.count(b'class="stat-metric-card"') == 4
    assert b"Available Credits" in response.data
    assert b"18" in response.data
    assert response.data.count(b'class="mobile-nav-item') == 5
    assert b">Plan</span>" not in response.data
    assert b"center-action" not in response.data
    assert b"copilot-launcher" not in response.data
    assert b'aria-label="Notifications"' in response.data
    assert b'aria-label="Search navigation"' in response.data
    assert b'aria-label="Close navigation"' in response.data
    assert b'>More</span>' in response.data
    assert b'href="/campaigns"' in response.data
    assert b'href="/movie-studio/"' in response.data
    assert response.data.count(b'class="mobile-topbar-logo') == 1
    assert b"Prompt Lab" in response.data
    assert b"AI Assistant" in response.data
    assert b"mobile-dashboard.css" in response.data


def test_more_menu_does_not_expose_admin_destinations_to_regular_users():
    response = _logged_in_client().get("/dashboard")
    assert response.status_code == 200
    assert b"Administration</h3>" not in response.data
    assert b"/admin/campaigns" not in response.data


def test_secondary_destination_marks_more_as_active():
    response = _logged_in_client().get("/upgrade")
    assert response.status_code == 200
    assert b'class="mobile-nav-item mobile-nav-more active"' in response.data
    assert b'href="/upgrade" data-nav-item aria-current="page"' in response.data


def test_admin_user_gets_admin_destinations_in_mobile_more_menu():
    with app.app_context():
        user = User(
            username="mobile_admin",
            email="oadedamola07@gmail.com",
            password="test-password",
            plan="spark",
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Administration</h3>" in response.data
    assert b'href="/admin/campaigns"' in response.data
    assert b'href="/admin/credits"' in response.data


def test_create_workspace_has_prompt_lab_shortcut():
    response = _logged_in_client().get("/create")
    assert response.status_code == 200
    assert b"Prompt Lab" in response.data
    assert b'href="/saved-prompts"' in response.data
