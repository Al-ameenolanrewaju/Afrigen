import services.video as video_service
from app import app, get_missing_required_env_vars
from routes.main import is_admin_user


class DummyUser:
    is_authenticated = True
    email = "  ADMIN@EXAMPLE.COM  "
    username = " AdminUser "
    id = 42


def test_generate_video_from_image_falls_back_to_next_model(monkeypatch):
    calls = []

    def fake_subscribe(model, arguments):
        calls.append(model)
        if model == "fal-ai/kling-video/v1.6/pro/image-to-video":
            raise Exception("Exhausted balance")
        if model == "fal-ai/ltx-video-v095/image-to-video":
            return {"video": {"url": "https://example.com/fallback-video.mp4"}}
        raise AssertionError(f"Unexpected model: {model}")

    monkeypatch.setattr(video_service.fal_client, "subscribe", fake_subscribe)

    result = video_service.generate_video_from_image(
        "https://example.com/image.jpg",
        "A cinematic city at sunset",
        duration="5",
        aspect_ratio="16:9",
    )

    assert result == "https://example.com/fallback-video.mp4"
    assert calls == [
        "fal-ai/kling-video/v1.6/pro/image-to-video",
        "fal-ai/ltx-video-v095/image-to-video",
    ]


def test_text_to_video_cost_increases_for_extended_duration():
    assert video_service.text_to_video_cost("cinematic", extended=True) == 10
    assert video_service.text_to_video_cost("anime", extended=True) == 5
    assert video_service.text_to_video_cost("cinematic", extended=False) == 5


def test_generate_route_uses_duration_choice_for_extended_video(monkeypatch):
    from app import app
    from models import db, User
    from uuid import uuid4

    with app.app_context():
        user = User(username=f"extend_{uuid4().hex[:8]}", email=f"extend_{uuid4().hex[:8]}@example.com", password="pw", plan="pro", credits=20)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    captured = {}

    monkeypatch.setattr("routes.main.refine_prompt", lambda prompt, style: "refined prompt")
    monkeypatch.setattr("routes.main.video_gate", lambda user, style, extended=False, duration="5": (True, None, 10 if extended else 5))
    monkeypatch.setattr(
        "routes.main.generate_video_async",
        lambda prompt, style, aspect_ratio, webhook_url=None, extended=False, duration="5": captured.setdefault("extended", extended) or {"success": True, "request_id": "req_123"},
    )

    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True

    response = client.post('/generate', data={
        'prompt': 'A cinematic street scene',
        'style': 'cinematic',
        'aspect_ratio': '16:9',
        'duration': '10',
    }, follow_redirects=False)

    assert response.status_code == 200
    assert captured['extended'] is True


def test_is_admin_user_accepts_case_and_whitespace_normalization(monkeypatch):
    monkeypatch.setattr("routes.main.ADMIN_EMAILS", {"admin@example.com"})
    monkeypatch.setattr("routes.main.ADMIN_USERNAMES", {"adminuser"})
    monkeypatch.setattr("routes.main.ADMIN_IDS", {42})

    user = DummyUser()
    assert is_admin_user(user) is True

    user.email = "someone@example.com"
    user.username = "guest"
    user.id = 99
    assert is_admin_user(user) is False


def test_admin_route_accepts_trailing_slash():
    match = app.url_map.bind("localhost").match("/admin/")
    assert match[0] == "main.admin"


def test_login_accepts_legacy_plaintext_passwords():
    from uuid import uuid4
    from app import app
    from models import db, User

    with app.app_context():
        user = User(
            username=f"legacy_login_{uuid4().hex[:8]}",
            email=f"legacy_login_{uuid4().hex[:8]}@example.com",
            password="legacy-pass-123",
            plan="pro",
            credits=50,
        )
        db.session.add(user)
        db.session.commit()
        email = user.email

    client = app.test_client()
    response = client.post('/auth/login', data={
        'email': email,
        'password': 'legacy-pass-123',
    }, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/dashboard')


def test_delete_user_removes_connected_account_rows():
    from uuid import uuid4
    from app import app
    from models import db, User, ConnectedAccount

    with app.app_context():
        user = User(username=f'linked_delete_{uuid4().hex[:8]}', email=f'linked_delete_{uuid4().hex[:8]}@example.com', password='pw')
        db.session.add(user)
        db.session.flush()

        account = ConnectedAccount(
            user_id=user.id,
            provider='whatsapp',
            status='connected',
            account_identifier='+15550000001',
        )
        db.session.add(account)
        db.session.commit()

        db.session.delete(user)
        db.session.commit()

        assert ConnectedAccount.query.filter_by(user_id=user.id).count() == 0
        assert User.query.get(user.id) is None


def test_favicon_route_redirects_to_static_asset():
    client = app.test_client()
    response = client.get('/favicon.ico')
    assert response.status_code in (200, 302)
    assert b'favicon.png' in response.data or response.location.endswith('/static/favicon.png')


def test_automation_run_route_exists_and_starts_workflow():
    from services.automation import save_workflow

    wf = {
        "id": "wf_test_run",
        "name": "Test Workflow",
        "trigger": "manual",
        "nodes": [{"type": "generate_content", "label": "Generate Copy", "prompt": "Write a short marketing blurb"}],
        "user_id": 1,
    }
    save_workflow(wf)

    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = '1'
        session['_fresh'] = True

    response = client.post('/api/automations/run/wf_test_run')
    assert response.status_code == 200
    assert response.get_json()['ok'] is True


def test_whatsapp_webhook_auto_reply(monkeypatch):
    calls = []

    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'AC_test')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'token_test')
    monkeypatch.setenv('TWILIO_WHATSAPP_NUMBER', '+15551234567')
    monkeypatch.setenv('WHATSAPP_AUTO_REPLY_ENABLED', 'true')
    monkeypatch.setenv('WHATSAPP_AWAY_MESSAGE', 'Thanks for contacting us. We are away right now and will reply soon.')

    class FakeResponse:
        status_code = 201
        text = 'queued'

    def fake_post(url, data=None, auth=None, timeout=10):
        calls.append({
            'url': url,
            'data': data,
            'auth': auth,
            'timeout': timeout,
        })
        return FakeResponse()

    monkeypatch.setattr('services.whatsapp.requests.post', fake_post)

    client = app.test_client()
    response = client.post('/api/v1/whatsapp/webhook', data={
        'From': 'whatsapp:+2348123456789',
        'Body': 'Hello, are you open today?'
    })

    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    assert len(calls) == 1
    assert calls[0]['data']['To'] == 'whatsapp:+2348123456789'
    assert 'away right now' in calls[0]['data']['Body']


def test_whatsapp_uses_connected_user_settings(monkeypatch):
    from uuid import uuid4

    monkeypatch.setenv('CONNECTED_ACCOUNTS_ENCRYPTION_KEY', '3AWvXRb2OHgV-h5m5o5H9uXw2A6Xc7U8Q6vLr6P1Q-0=')

    from app import app
    from models import db, User, ConnectedAccount
    from utils.encryption import encrypt_token
    from services.whatsapp import get_auto_reply_settings, get_user_for_whatsapp_number
    import json

    with app.app_context():
        username = f'whatsapp_user_{uuid4().hex[:8]}'
        email = f'{username}@example.com'
        business_number = f'+1555{uuid4().hex[:7]}'

        user = User(username=username, email=email, password='pw')
        db.session.add(user)
        db.session.flush()

        metadata = {
            'phone_number': business_number,
            'auto_reply': True,
            'away_message': 'We are offline right now. We will respond soon.'
        }
        account = ConnectedAccount(
            user_id=user.id,
            provider='whatsapp',
            status='connected',
            account_identifier=business_number,
            encrypted_access_token=encrypt_token('AC_user_token'),
            metadata_json=encrypt_token(json.dumps(metadata)),
        )
        db.session.add(account)
        db.session.commit()

        assert get_user_for_whatsapp_number(business_number) == user.id
        settings = get_auto_reply_settings(user.id)
        assert settings['enabled'] is True
        assert settings['away_message'] == 'We are offline right now. We will respond soon.'
        assert settings['auth_token'] == 'AC_user_token'


def test_settings_save_whatsapp_auto_reply(monkeypatch):
    from uuid import uuid4
    import json

    monkeypatch.setenv('CONNECTED_ACCOUNTS_ENCRYPTION_KEY', '3AWvXRb2OHgV-h5m5o5H9uXw2A6Xc7U8Q6vLr6P1Q-0=')

    from app import app
    from models import db, User, ConnectedAccount

    with app.app_context():
        user = User(username=f'wa_settings_{uuid4().hex[:8]}', email=f'wa_settings_{uuid4().hex[:8]}@example.com', password='pw')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True

    response = client.post('/settings', data={
        'section': 'whatsapp_auto_reply',
        'phone_number': '+2348000000001',
        'twilio_token': 'AC_whatsapp_settings_test',
        'away_message': 'We are offline right now. We will reply soon.',
        'auto_reply': 'on',
    }, follow_redirects=False)

    assert response.status_code in (200, 302)

    with app.app_context():
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider='whatsapp').first()
        assert account is not None
        assert account.account_identifier == '+2348000000001'
        assert account.status == 'connected'
        assert account.metadata_json is not None
        from utils.encryption import decrypt_token
        parsed = json.loads(decrypt_token(account.metadata_json) or '{}')
        assert parsed['auto_reply'] is True
        assert 'reply soon' in parsed['away_message']


def test_whatsapp_business_hours_auto_reply(monkeypatch):
    from datetime import datetime, timezone
    from uuid import uuid4
    import json

    monkeypatch.setenv('CONNECTED_ACCOUNTS_ENCRYPTION_KEY', '3AWvXRb2OHgV-h5m5o5H9uXw2A6Xc7U8Q6vLr6P1Q-0=')

    from app import app
    from models import db, User, ConnectedAccount
    from utils.encryption import encrypt_token
    import services.whatsapp as whatsapp_service

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2024, 1, 1, 20, 0, 0, tzinfo=timezone.utc)
            if tz is None:
                return base.replace(tzinfo=None)
            return base

    monkeypatch.setattr(whatsapp_service, 'datetime', FixedDateTime)

    with app.app_context():
        user = User(username=f'wa_hours_{uuid4().hex[:8]}', email=f'wa_hours_{uuid4().hex[:8]}@example.com', password='pw')
        db.session.add(user)
        db.session.flush()

        metadata = {
            'phone_number': '+2348000000099',
            'auto_reply': True,
            'away_message': 'We are offline. We will reply soon.',
            'business_hours_enabled': True,
            'business_hours_start': '09:00',
            'business_hours_end': '17:00',
            'timezone': 'UTC',
        }

        account = ConnectedAccount(
            user_id=user.id,
            provider='whatsapp',
            status='connected',
            account_identifier='+2348000000099',
            encrypted_access_token=encrypt_token('AC_business_hours_test'),
            metadata_json=encrypt_token(json.dumps(metadata)),
        )
        db.session.add(account)
        db.session.commit()

        settings = whatsapp_service.get_auto_reply_settings(user.id)
        assert settings['enabled'] is True
        assert settings['away_message'] == 'We are offline. We will reply soon.'


def test_missing_required_env_vars_is_detected(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.delenv('FAL_KEY', raising=False)
    monkeypatch.delenv('PAYSTACK_SECRET_KEY', raising=False)
    monkeypatch.delenv('PAYSTACK_PUBLIC_KEY', raising=False)

    missing = get_missing_required_env_vars()
    assert 'SECRET_KEY' in missing
    assert 'DATABASE_URL' in missing
    assert 'GROQ_API_KEY' in missing
    assert 'FAL_KEY' in missing
    assert 'PAYSTACK_SECRET_KEY' in missing
    assert 'PAYSTACK_PUBLIC_KEY' in missing
