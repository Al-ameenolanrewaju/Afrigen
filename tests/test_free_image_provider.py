from unittest.mock import patch

from services.video import generate_image


def test_free_huggingface_image_failure_does_not_fall_back_to_fal():
    failure = {"success": False, "error": "Hugging Face image service unavailable"}
    with patch("services.video._generate_image_huggingface", return_value=failure) as hf_generate, \
         patch("services.video.requests.post") as fal_image_request, \
         patch("services.video.fal_client.subscribe") as fal_model_request:
        result = generate_image(
            "A portrait of a woman in traditional attire",
            provider="huggingface",
            allow_fal=False,
        )

    assert result == failure
    hf_generate.assert_called_once()
    fal_image_request.assert_not_called()
    fal_model_request.assert_not_called()
