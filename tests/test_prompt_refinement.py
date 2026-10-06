from unittest.mock import patch

from routes.main import _usable_refinement
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
