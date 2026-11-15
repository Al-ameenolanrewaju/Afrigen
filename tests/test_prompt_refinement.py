from unittest.mock import patch

from app import app
from routes.main import _usable_refinement, refine_prompt_free
from services.claude import _refinement_is_usable, refine_prompt


def test_refinement_rejects_clarification_instead_of_prompt():
    response = (
        "I’m sorry, but I need more details about what you’d like to animate. "
        "Could you please describe the subject, setting, and mood?"
    )

    assert not _refinement_is_usable("Animate this", response)
    assert _usable_refinement("Animate this", response) == "Animate this"


def test_video_refinement_falls_back_to_usable_prompt():
    response = (
        "I’m sorry, but I need more details about what you’d like to animate. "
        "Could you please describe the subject, setting, and mood?"
    )

    with patch(
        "services.claude.provider_manager.generate_text",
        return_value=response,
    ):
        refined = refine_prompt("Animate this", style="cinematic")

    assert refined.startswith("Animate this.")
    assert "clear main subject and action" in refined


def test_free_prompt_refinement_returns_homepage_response_key_and_style():
    with app.test_request_context(
        "/refine-prompt",
        method="POST",
        json={"prompt": "A woman walking through Lagos", "style": "realistic"},
    ):
        with patch("routes.main.refine_prompt", return_value="A refined video prompt.") as refine:
            response = refine_prompt_free()

    assert response.get_json()["refined_prompt"] == "A refined video prompt."
    assert response.get_json()["refined"] == "A refined video prompt."
    refine.assert_called_once()
    assert refine.call_args.args == ("A woman walking through Lagos", "realistic")
