from unittest.mock import patch

from app import app
from models import db, Generation, Notification, User
from routes.main import _fal_webhook_token


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_successful_photo_generation_creates_linked_notification(monkeypatch):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    with app.app_context():
        user = User(
            username="photo_owner",
            email="photo-owner@example.test",
            password="pw",
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    _login(client, user_id)
    with patch("routes.main.image_gate", return_value=(True, None)), \
            patch("routes.main.refine_image_prompt", return_value="A bright landscape"), \
            patch("routes.main.generate_ai_image", return_value={
                "success": True,
                "image_url": "https://media.example.test/photo.png",
            }), \
            patch("routes.main.charge_image"):
        response = client.post("/generate-image", data={"prompt": "A bright landscape"})

    assert response.status_code == 302
    with app.app_context():
        generation = Generation.query.one()
        notification = Notification.query.one()
        assert notification.user_id == user_id
        assert notification.title == "Your photo is ready"
        assert notification.type == "success"
        assert notification.link == f"/result/image?generation_id={generation.id}"


def test_successful_video_webhook_notifies_once_and_links_to_result():
    with app.app_context():
        user = User(
            username="video_owner",
            email="video-owner@example.test",
            password="pw",
            plan="pro",
            credits=100,
        )
        db.session.add(user)
        db.session.flush()
        generation = Generation(
            user_id=user.id,
            original_prompt="A sunset",
            refined_prompt="A cinematic sunset",
            generation_type="video",
            status="processing",
            fal_request_id="fal-video-request",
        )
        db.session.add(generation)
        db.session.commit()
        user_id = user.id
        generation_id = generation.id
        webhook_token = _fal_webhook_token("client-video-request")

    webhook_url = (
        "/fal/webhook?client_request_id=client-video-request&token="
        f"{webhook_token}"
    )
    with patch("services.email.send_video_ready_email", return_value=True), \
            patch("routes.main.extract_on_screen_text", return_value=None):
        response = app.test_client().post(webhook_url, json={
            "request_id": "fal-video-request",
            "status": "COMPLETED",
            "payload": {"video": {"url": "https://media.example.test/video.mp4"}},
        })
        duplicate_response = app.test_client().post(webhook_url, json={
            "request_id": "fal-video-request",
            "status": "COMPLETED",
            "payload": {"video": {"url": "https://media.example.test/video.mp4"}},
        })

    assert response.status_code == 200
    assert duplicate_response.status_code == 200
    with app.app_context():
        notifications = Notification.query.filter_by(user_id=user_id).all()
        assert len(notifications) == 1
        assert notifications[0].title == "Your video is ready"
        assert notifications[0].link == f"/result/video?generation_id={generation_id}"
