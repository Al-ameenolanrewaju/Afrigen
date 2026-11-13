import json
import pytest
from unittest.mock import patch, MagicMock
from app import app
from models import db, User, TelegramUser
from services.telegram_bot import telegram_bot


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_telegram_webhook_empty_payload():
    client = app.test_client()
    resp = client.post('/telegram/webhook', json={})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == "Empty payload"


def test_telegram_webhook_start_command():
    client = app.test_client()
    update = {
        "update_id": 10001,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": 12345, "type": "private"},
            "from": {"id": 12345, "first_name": "Test", "username": "testuser"},
            "text": "/start"
        }
    }

    with patch.object(telegram_bot, 'send_message') as mock_send:
        resp = client.post('/telegram/webhook', json=update)
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        assert mock_send.called
        args, kwargs = mock_send.call_args
        assert args[0] == 12345
        assert "Welcome to Afrigen AI" in args[1]


def test_telegram_webhook_link_account():
    # 1. Create a website user with a link code
    with app.app_context():
        user = User(
            username="web_user",
            email="web_user@example.com",
            password="hashpassword",
            telegram_link_code="ABCDEF",
            plan="free",
            credits=20
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    update = {
        "update_id": 10002,
        "message": {
            "message_id": 2,
            "date": 1700000000,
            "chat": {"id": 99999, "type": "private"},
            "from": {"id": 99999, "first_name": "Linked", "username": "linkedtg"},
            "text": "/link ABCDEF"
        }
    }

    with patch.object(telegram_bot, 'send_message') as mock_send:
        resp = client.post('/telegram/webhook', json=update)
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        assert mock_send.called
        args, _ = mock_send.call_args
        assert args[0] == 99999
        assert "is now connected to" in args[1]

    # Verify database state
    with app.app_context():
        tg_user = TelegramUser.query.filter_by(telegram_id=99999).first()
        assert tg_user is not None
        assert tg_user.user_id == user_id
        db_user = db.session.get(User, user_id)
        assert db_user.telegram_link_code is None


def test_telegram_webhook_start_with_code():
    # Test deeplink: /start ABCDEF
    with app.app_context():
        user = User(
            username="deeplink_user",
            email="deeplink@example.com",
            password="hashpassword",
            telegram_link_code="XYZ123",
            plan="free",
            credits=15
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    update = {
        "update_id": 10003,
        "message": {
            "message_id": 3,
            "date": 1700000000,
            "chat": {"id": 88888, "type": "private"},
            "from": {"id": 88888, "first_name": "DeeplinkUser", "username": "deeplink"},
            "text": "/start XYZ123"
        }
    }

    with patch.object(telegram_bot, 'send_message') as mock_send:
        resp = client.post('/telegram/webhook', json=update)
        assert resp.status_code == 200
        assert mock_send.called
        args, _ = mock_send.call_args
        assert "is now connected to" in args[1]

    with app.app_context():
        tg_user = TelegramUser.query.filter_by(telegram_id=88888).first()
        assert tg_user is not None
        assert tg_user.user_id == user_id


def test_telegram_webhook_callback_query_mode_switch():
    client = app.test_client()
    update = {
        "update_id": 10004,
        "callback_query": {
            "id": "cb123",
            "from": {"id": 77777, "first_name": "CBUser", "username": "cbuser"},
            "message": {
                "message_id": 10,
                "chat": {"id": 77777}
            },
            "data": "menu_image"
        }
    }

    with patch.object(telegram_bot, 'answer_callback_query') as mock_answer, \
         patch.object(telegram_bot, 'edit_message_text') as mock_edit:
        resp = client.post('/telegram/webhook', json=update)
        assert resp.status_code == 200
        assert mock_answer.called
        assert mock_edit.called

    with app.app_context():
        tg_user = TelegramUser.query.filter_by(telegram_id=77777).first()
        assert tg_user is not None
        assert tg_user.mode == "image"


def test_telegram_webhook_secret_token_protection():
    with patch.dict("os.environ", {"TELEGRAM_WEBHOOK_SECRET": "super_secret_token_123"}):
        client = app.test_client()

        # Without header
        resp = client.post('/telegram/webhook', json={"update_id": 1})
        assert resp.status_code == 403

        # With wrong header
        resp = client.post('/telegram/webhook', json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
        assert resp.status_code == 403

        # With correct header
        with patch.object(telegram_bot, 'send_message'):
            resp = client.post(
                '/telegram/webhook',
                json={"update_id": 1, "message": {"chat": {"id": 1}, "text": "/help"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "super_secret_token_123"}
            )
            assert resp.status_code == 200
