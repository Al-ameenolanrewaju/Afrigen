from types import SimpleNamespace
from unittest.mock import patch

from services.video import generate_video_from_image_async


def test_image_to_video_submits_to_fal_with_webhook():
    with patch(
        "services.video.fal_client.submit",
        return_value=SimpleNamespace(request_id="fal-request-123"),
    ) as submit:
        result = generate_video_from_image_async(
            "https://example.com/image.png",
            "A person waves at the camera",
            webhook_url="https://example.com/fal/webhook",
            duration="10",
            aspect_ratio="9:16",
            allow_fal=True,
        )

    assert result == {"success": True, "request_id": "fal-request-123"}
    submit.assert_called_once_with(
        "fal-ai/kling-video/v3/pro/image-to-video",
        arguments={
            "prompt": "A person waves at the camera",
            "image_url": "https://example.com/image.png",
            "duration": "10",
            "aspect_ratio": "9:16",
        },
        webhook_url="https://example.com/fal/webhook",
    )


def test_image_to_video_rejects_empty_prompt_without_submitting():
    with patch("services.video.fal_client.submit") as submit:
        result = generate_video_from_image_async(
            "https://example.com/image.png",
            " ",
            webhook_url="https://example.com/fal/webhook",
            allow_fal=True,
        )

    assert result["success"] is False
    assert "prompt was empty" in result["error"]
    submit.assert_not_called()
