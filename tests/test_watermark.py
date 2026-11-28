"""Tests for free user branding watermark on images and videos."""
from io import BytesIO
from unittest.mock import patch, MagicMock
from PIL import Image
import pytest

from services.video import add_watermark_to_image, add_watermark_to_video, generate_image


def _create_test_image_bytes(width=800, height=800):
    """Helper to create dummy in-memory image bytes."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_add_watermark_to_image_success():
    """Verify add_watermark_to_image fetches image, draws watermark, and uploads result."""
    test_bytes = _create_test_image_bytes(600, 600)
    mock_resp = MagicMock()
    mock_resp.content = test_bytes
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    uploaded_url = "https://cdn.fal.media/watermarked_image_123.png"

    with patch("requests.get", return_value=mock_resp), \
         patch("fal_client.upload_file", return_value=uploaded_url) as mock_upload:
        result = add_watermark_to_image("https://original.com/raw.png")

        assert result == uploaded_url
        assert mock_upload.called


def test_add_watermark_to_image_error_fallback():
    """If downloading or processing fails, return original URL gracefully."""
    with patch("requests.get", side_effect=Exception("Network error")):
        original = "https://original.com/raw.png"
        result = add_watermark_to_image(original)
        assert result == original


def test_generate_image_watermark_flag_free_vs_paid():
    """Verify generate_image applies watermark only when watermark=True (free users)."""
    with patch("services.video._generate_image_huggingface") as mock_hf, \
         patch("services.video.add_watermark_to_image") as mock_watermark:

        mock_hf.return_value = {
            "success": True,
            "image_url": "https://fal.media/raw_gen.png"
        }
        mock_watermark.return_value = "https://fal.media/watermarked_gen.png"

        # 1. Free user (watermark=True) -> watermarked
        res_free = generate_image("Lagos sunrise", watermark=True)
        assert res_free["success"] is True
        assert res_free["image_url"] == "https://fal.media/watermarked_gen.png"
        mock_watermark.assert_called_once_with("https://fal.media/raw_gen.png")

        # 2. Paid user (watermark=False) -> clean image
        mock_watermark.reset_mock()
        res_paid = generate_image("Lagos sunrise", watermark=False)
        assert res_paid["success"] is True
        assert res_paid["image_url"] == "https://fal.media/raw_gen.png"
        mock_watermark.assert_not_called()
