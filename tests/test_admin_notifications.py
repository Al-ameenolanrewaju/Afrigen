"""Tests for admin in-app notification dispatch and user reception."""
import pytest
from unittest.mock import patch
from app import app
from models import db, User, Notification


@pytest.fixture(autouse=True)
def setup_db():
    with app.app_context():
        db.create_all()
        yield
        db.session.rollback()


def _create_user(email, username, plan="free"):
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            email=email,
            username=username,
            password="testpassword",
            plan=plan,
        )
        db.session.add(user)
        db.session.commit()
    return user


def test_admin_broadcast_notification():
    """Verify admin can broadcast an in-app notification to all users."""
    with app.test_client() as client:
        with app.app_context():
            admin_user = _create_user("oadedamola07@gmail.com", "superadmin", plan="pro")
            user1 = _create_user("user1_notif@afrigen.com", "user1_notif", plan="free")
            user2 = _create_user("user2_notif@afrigen.com", "user2_notif", plan="director")

            # Login as admin
            with client.session_transaction() as sess:
                sess['_user_id'] = str(admin_user.id)
                sess['_fresh'] = True

            with patch("routes.main.is_admin_user", return_value=True):
                # Send broadcast
                resp = client.post("/admin/notifications/send", json={
                    "target": "all",
                    "title": "Welcome to Afrigen 2.0",
                    "message": "New AI models are now available in your studio workspace.",
                    "link": "/dashboard",
                    "type": "info"
                })
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["ok"] is True
                assert data["sent_to"] >= 3

            # Check that user1 and user2 received the notification
            notifs1 = Notification.query.filter_by(user_id=user1.id, title="Welcome to Afrigen 2.0").all()
            assert len(notifs1) == 1
            assert notifs1[0].message == "New AI models are now available in your studio workspace."
            assert notifs1[0].link == "/dashboard"
            assert notifs1[0].is_read is False


def test_admin_send_notification_to_plan():
    """Verify admin can send a targeted notification to a specific tier (e.g. director)."""
    with app.test_client() as client:
        with app.app_context():
            admin_user = _create_user("admin_plan@afrigen.com", "admin_plan", plan="pro")
            free_user = _create_user("free_target@afrigen.com", "free_target", plan="free")
            director_user = _create_user("director_target@afrigen.com", "director_target", plan="director")

            with client.session_transaction() as sess:
                sess['_user_id'] = str(admin_user.id)
                sess['_fresh'] = True

            with patch("routes.main.is_admin_user", return_value=True):
                resp = client.post("/admin/notifications/send", json={
                    "target": "plan",
                    "plan": "director",
                    "title": "Exclusive Director Update",
                    "message": "Your 30 monthly drama episodes quota has refreshed.",
                    "link": "/drama-studio",
                    "type": "promo"
                })
                assert resp.status_code == 200

            # Director receives it
            notif_dir = Notification.query.filter_by(user_id=director_user.id, title="Exclusive Director Update").first()
            assert notif_dir is not None
            assert notif_dir.type == "promo"

            # Free user does NOT receive it
            notif_free = Notification.query.filter_by(user_id=free_user.id, title="Exclusive Director Update").first()
            assert notif_free is None


def test_admin_send_notification_single_user():
    """Verify admin can send a 1-on-1 direct message notification to a specific user."""
    with app.test_client() as client:
        with app.app_context():
            admin_user = _create_user("admin_single@afrigen.com", "admin_single", plan="pro")
            target_user = _create_user("target_single@afrigen.com", "target_creator", plan="creator")

            with client.session_transaction() as sess:
                sess['_user_id'] = str(admin_user.id)
                sess['_fresh'] = True

            with patch("routes.main.is_admin_user", return_value=True):
                resp = client.post("/admin/notifications/send", json={
                    "target": "single",
                    "user_id": target_user.id,
                    "title": "Account Bonus Granted",
                    "message": "We have credited your account with 50 bonus credits.",
                    "type": "success"
                })
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["ok"] is True
                assert data["sent_to"] == 1

            notif = Notification.query.filter_by(user_id=target_user.id, title="Account Bonus Granted").first()
            assert notif is not None
            assert notif.type == "success"
            assert notif.message == "We have credited your account with 50 bonus credits."
            assert notif.is_read is False


def test_non_admin_cannot_send_notifications():
    """Verify non-admin users cannot access the send endpoint."""
    with app.test_client() as client:
        with app.app_context():
            regular_user = _create_user("regular_user@afrigen.com", "regular_user", plan="free")

            with client.session_transaction() as sess:
                sess['_user_id'] = str(regular_user.id)
                sess['_fresh'] = True

            with patch("routes.main.is_admin_user", return_value=False):
                resp = client.post("/admin/notifications/send", json={
                    "target": "all",
                    "title": "Hacked",
                    "message": "This should not work."
                })
                # Should be forbidden or redirect
                assert resp.status_code in (302, 403)
