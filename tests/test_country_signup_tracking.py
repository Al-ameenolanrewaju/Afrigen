from flask import Flask

from routes.main import get_real_ip, get_country_from_ip


def test_get_real_ip_prefers_cloudflare_client_ip():
    app = Flask(__name__)
    with app.test_request_context(
        "/",
        headers={
            "CF-Connecting-IP": "8.8.8.8",
            "X-Forwarded-For": "1.1.1.1, 10.0.0.2",
        },
        environ_base={"REMOTE_ADDR": "10.0.0.3"},
    ):
        assert get_real_ip() == "8.8.8.8"


def test_get_real_ip_uses_first_public_forwarded_address():
    app = Flask(__name__)
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "1.1.1.1, 10.0.0.2"},
        environ_base={"REMOTE_ADDR": "10.0.0.3"},
    ):
        assert get_real_ip() == "1.1.1.1"


def test_get_real_ip_ignores_private_and_invalid_forwarded_values():
    app = Flask(__name__)
    with app.test_request_context(
        "/",
        headers={
            "CF-Connecting-IP": "10.0.0.5",
            "True-Client-IP": "not-an-ip",
            "X-Forwarded-For": "unknown, 172.16.0.2",
        },
        environ_base={"REMOTE_ADDR": "10.0.0.3"},
    ):
        assert get_real_ip() is None


def test_get_real_ip_falls_back_to_public_remote_addr():
    app = Flask(__name__)
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "9.9.9.9"},
    ):
        assert get_real_ip() == "9.9.9.9"


def test_country_lookup_skips_non_public_ip(monkeypatch):
    import requests

    app = Flask(__name__)
    with app.app_context():
        def unexpected_request(*args, **kwargs):
            raise AssertionError("Geo-IP provider must not receive a private IP")

        monkeypatch.setattr(requests, "get", unexpected_request)
        assert get_country_from_ip("10.197.123.222") == "Unknown"


def test_country_lookup_uses_fallback_after_primary_provider_rate_limit(monkeypatch):
    import requests

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = ""

        def raise_for_status(self):
            if self.status_code >= 400:
                error = requests.HTTPError("rate limited")
                error.response = self
                raise error

        def json(self):
            return self._payload

    responses = [
        FakeResponse(429, {"error": True}),
        FakeResponse(200, {"status": "success", "country": "Nigeria"}),
    ]
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(requests, "get", fake_get)
    app = Flask(__name__)
    with app.app_context():
        assert get_country_from_ip("8.8.8.8") == "Nigeria"

    assert len(calls) == 2
    assert calls[0].startswith("https://ipapi.co/")
    assert calls[1].startswith("http://ip-api.com/")
