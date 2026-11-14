import re

from flask import render_template

from app import app
from models import db, Notification, User


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_notification_center_history_and_read_actions_are_user_scoped():
    with app.app_context():
        owner = User(username="notification_owner", email="owner@example.test", password="pw", plan="spark")
        other = User(username="notification_other", email="other@example.test", password="pw", plan="creator")
        db.session.add_all([owner, other])
        db.session.commit()
        own_unread = Notification(
            user_id=owner.id,
            title="Payment successful",
            message="Your subscription payment was successful.",
            link="/upgrade",
            type="success",
        )
        own_read = Notification(
            user_id=owner.id,
            title="Video generation completed",
            message="Your video is ready.",
            type="success",
            is_read=True,
        )
        other_unread = Notification(
            user_id=other.id,
            title="Password changed",
            message="Your password was changed.",
            type="info",
        )
        db.session.add_all([own_unread, own_read, other_unread])
        db.session.commit()
        owner_id = owner.id
        own_unread_id = own_unread.id
        own_read_id = own_read.id
        other_unread_id = other_unread.id

    client = app.test_client()
    page = client.get("/notifications")
    assert page.status_code == 302
    page = client.get("/login")
    token_match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data)
    assert token_match
    csrf_value = token_match.group(1).decode()

    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id)
        session["_fresh"] = True

    page = client.get("/notifications")
    assert page.status_code == 200
    assert b"Notification history" in page.data
    assert b"notificationPanel" in page.data
    assert page.data.count(b"data-notification-trigger") == 2

    unread_response = client.get("/api/notifications")
    assert unread_response.status_code == 200
    assert unread_response.headers["X-Unread-Count"] == "1"
    assert [item["id"] for item in unread_response.get_json()] == [own_unread_id]

    filtered = client.get("/api/notifications/history?status=unread&category=billing")
    assert filtered.status_code == 200
    assert filtered.get_json()["total"] == 1
    assert filtered.get_json()["notifications"][0]["category"] == "billing"
    searched = client.get("/api/notifications/history?q=payment")
    assert searched.status_code == 200
    assert searched.get_json()["total"] == 1
    last_page = client.get("/api/notifications/history?per_page=1&page=999").get_json()
    assert last_page["page"] == last_page["pages"] == 2
    assert client.get("/api/notifications/history?category=unknown").status_code == 400

    marked_read = client.post(
        "/api/notifications/{}/read".format(own_unread_id),
        headers={"X-CSRFToken": csrf_value},
    )
    assert marked_read.status_code == 200
    foreign_read = client.post(
        "/api/notifications/{}/read".format(other_unread_id),
        headers={"X-CSRFToken": csrf_value},
    )
    assert foreign_read.status_code == 404
    read_items = client.get("/api/notifications/history?status=read").get_json()
    assert {item["id"] for item in read_items["notifications"]} == {own_unread_id, own_read_id}
    assert all(item["id"] != other_unread_id for item in read_items["notifications"])

    with app.app_context():
        remaining = Notification(
            user_id=owner_id,
            title="Image generation completed",
            message="Your image is ready.",
            type="success",
        )
        db.session.add(remaining)
        db.session.commit()

    marked_all = client.post("/api/notifications/read-all", headers={"X-CSRFToken": csrf_value})
    assert marked_all.status_code == 200
    assert marked_all.get_json()["updated"] == 1
    assert client.get("/api/notifications").headers["X-Unread-Count"] == "0"
    assert client.post("/api/notifications/read-all", headers={"X-CSRFToken": csrf_value}).get_json()["updated"] == 0
    with app.app_context():
        assert db.session.get(Notification, other_unread_id).is_read is False

    with app.test_request_context("/admin"):
        admin_layout = render_template("admin_base.html")
    assert admin_layout.count('data-notification-trigger') == 2
    assert 'id="notificationPanel"' in admin_layout
