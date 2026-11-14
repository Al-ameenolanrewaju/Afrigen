import re
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from flask import Response

from app import app
from models import db, Generation, User
from services.ai_products import (
    customer_error,
    product_label_for_provider,
    redact_secrets,
    sanitize_generated_text,
)
from services.media_proxy import _is_allowed_url
from services.provider_manager import AIProviderError, ProviderManager


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


_CUSTOMER_PROVIDER_NAMES = re.compile(
    r"groq|gemini|kling|flux|openai|anthropic|claude|replicate|fal(?:\.ai|-ai)|"
    r"hugging face|elevenlabs|deepseek|openrouter|mistral|llama|whisper|gpt-[0-9]",
    re.IGNORECASE,
)


def _manager_with_adapter(adapter):
    manager = ProviderManager()
    manager.adapters = {"Groq": adapter}
    manager.task_mappings = {"Default": "Groq"}
    manager.fallback_chain = []
    manager._get_health = lambda _provider: SimpleNamespace(
        status="healthy",
        last_error_at=None,
    )
    manager._update_health = Mock()
    manager._log_request = Mock()
    return manager


def test_generated_text_is_rebranded_before_returning_to_customer():
    result = sanitize_generated_text(
        "OpenAI GPT-4o, Google Gemini 2.5 Flash, Kling AI Pro, Flux.1 Dev, "
        "Claude Sonnet 4.5, fal.ai and Hugging Face."
    )

    assert not _CUSTOMER_PROVIDER_NAMES.search(result)
    assert "Afrigen Intelligence" in result
    assert "Afrigen Video Engine" in result
    assert "Afrigen Image Engine" in result
    assert "Afrigen Media Engine" in result


def test_provider_manager_sanitizes_adapter_output_and_returns_safe_errors():
    class SuccessfulAdapter:
        is_enabled = True

        def generate(self, *_args, **_kwargs):
            return "This draft was created with OpenAI GPT-4o."

    manager = _manager_with_adapter(SuccessfulAdapter())
    assert manager.generate_text("Default", []) == (
        "This draft was created with Afrigen Intelligence."
    )

    class FailedAdapter:
        is_enabled = True

        def generate(self, *_args, **_kwargs):
            raise RuntimeError("Groq returned error 429")

    manager = _manager_with_adapter(FailedAdapter())
    with pytest.raises(AIProviderError) as error:
        manager.generate_text("Default", [])

    assert str(error.value) == customer_error("text")
    assert not _CUSTOMER_PROVIDER_NAMES.search(str(error.value))
    assert "Groq" in manager._log_request.call_args.kwargs["error_msg"]


def test_provider_labels_errors_and_media_origins_are_customer_safe():
    assert product_label_for_provider("Fal (Image)") == "Afrigen Media Engine"
    assert product_label_for_provider("Kling Pro") == "Afrigen Video Engine"
    assert not _CUSTOMER_PROVIDER_NAMES.search(customer_error("video"))
    assert _is_allowed_url("https://v3.fal.media/files/generated.mp4")
    assert not _is_allowed_url("https://fal.media.attacker.example/file.mp4")
    assert not _is_allowed_url("http://fal.media/file.mp4")
    assert not _is_allowed_url("https://user@fal.media/file.mp4")


def test_internal_diagnostic_redaction_hides_api_credentials(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sensitive-test-token")

    assert redact_secrets("request failed with sensitive-test-token") == (
        "request failed with [REDACTED]"
    )


def test_generation_media_proxy_enforces_generation_ownership():
    with app.app_context():
        owner = User(username="media_owner", email="media-owner@example.test", password="pw")
        other = User(username="media_other", email="media-other@example.test", password="pw")
        db.session.add_all([owner, other])
        db.session.commit()
        generation = Generation(
            user_id=owner.id,
            original_prompt="A cinematic scene",
            refined_prompt="A cinematic scene",
            video_url="https://v3.fal.media/files/generated.mp4",
            generation_type="video",
            status="completed",
        )
        db.session.add(generation)
        db.session.commit()
        owner_id = owner.id
        generation_id = generation.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id)
        session["_fresh"] = True

    with patch(
        "services.media_proxy.proxy_media",
        return_value=Response(b"video", mimetype="video/mp4"),
    ) as proxy:
        response = client.get(
            f"/media/generation/{generation_id}/video"
        )
        assert response.status_code == 200
        assert b"fal.media" not in response.data
        proxy.assert_called_once_with(
            "https://v3.fal.media/files/generated.mp4",
            f"afrigen-video-{generation_id}",
            "video/mp4",
            as_attachment=False,
        )

    with client.session_transaction() as session:
        session["_user_id"] = str(owner_id + 1)
        session["_fresh"] = True
    assert client.get(
        f"/media/generation/{generation_id}/video"
    ).status_code == 404
