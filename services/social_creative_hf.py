"""Hugging Face Creative Generation Engine for Afrigen Social Media Automation.

Provides AI image and video generation using Hugging Face Inference APIs,
with automatic fallback to Python PIL flyer design and existing video services.
Keeps Hugging Face details completely hidden from customer-facing content.
"""

import os
import time
import uuid
import logging
import tempfile
import requests
from io import BytesIO
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

SITE_URL = os.environ.get("BASE_URL", "https://www.afrigen.com.ng").rstrip("/")

DEFAULT_HF_IMAGE_MODEL = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
DEFAULT_HF_VIDEO_MODEL = os.environ.get("HF_VIDEO_MODEL", "damo-vilab/text-to-video-ms-1.7m")


def _get_hf_token() -> Optional[str]:
    """Retrieve Hugging Face API token from environment."""
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_API_KEY")
        or os.environ.get("HUGGINGFACE_TOKEN")
    )


def _persist_media_bytes(data: bytes, ext: str, prefix: str = "social") -> str:
    """Store generated media bytes and return a publicly accessible HTTPS URL."""
    # Try fal_client upload first (CDN-backed, persistent)
    try:
        import fal_client
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
            cdn_url = fal_client.upload_file(tmp_path)
            if cdn_url and cdn_url.startswith("http"):
                return cdn_url
        finally:
            os.close(tmp_fd)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as exc:
        logger.debug("Remote CDN upload skipped, using persistent local storage: %s", exc)

    # Fallback to local static directory served with full public URL
    static_dir = os.path.join(os.getcwd(), "static", "generated_social")
    os.makedirs(static_dir, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"
    dest_path = os.path.join(static_dir, filename)
    with open(dest_path, "wb") as f:
        f.write(data)

    return f"{SITE_URL}/static/generated_social/{filename}"


# ==============================================================================
# IMAGE GENERATION (HUGGING FACE + PIL FLYER FALLBACK)
# ==============================================================================

def generate_social_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    model_override: Optional[str] = None,
    style_hint: str = "marketing",
    fallback_to_flyer: bool = True,
) -> Dict[str, Any]:
    """Generate a marketing image using Hugging Face inference.

    If HF is unavailable or rate-limited, safely falls back to high-converting
    Python PIL branded flyer generation so posts are never blocked.
    """
    token = _get_hf_token()
    model = model_override or DEFAULT_HF_IMAGE_MODEL

    dimensions = {
        "1:1": (1080, 1080),
        "16:9": (1200, 675),
        "9:16": (720, 1280),
    }
    width, height = dimensions.get(aspect_ratio, (1080, 1080))

    # Refine prompt to inject Afrigen's brand aesthetic
    branded_prompt = (
        f"{prompt}. High-end commercial creative, professional lighting, rich textures, "
        f"subtle gold and warm amber cinematic tones, 8k resolution, authentic, stunning composition."
    )

    if token:
        try:
            from huggingface_hub import InferenceClient
            logger.info("Generating social creative via Hugging Face model: %s", model)
            client = InferenceClient(model=model, token=token, timeout=90)
            img = client.text_to_image(
                branded_prompt,
                width=width,
                height=height,
                num_inference_steps=4 if "schnell" in model.lower() else 25,
            )

            buf = BytesIO()
            img.save(buf, format="JPEG", quality=92)
            img_bytes = buf.getvalue()

            public_url = _persist_media_bytes(img_bytes, ext="jpg", prefix="hf_img")
            return {
                "ok": True,
                "media_url": public_url,
                "media_type": "image",
                "provider": "huggingface",
                "model_name": model,
                "dimensions": f"{width}x{height}",
            }
        except Exception as exc:
            logger.warning("Hugging Face image generation encountered an error: %s", exc)

    # Fallback to high-converting Python PIL promotional flyer
    if fallback_to_flyer:
        try:
            logger.info("Generating branded flyer fallback via Python PIL engine.")
            from services.promo_campaign import generate_promo_flyer
            flyer_url = generate_promo_flyer(prompt)
            if flyer_url:
                return {
                    "ok": True,
                    "media_url": flyer_url,
                    "media_type": "flyer",
                    "provider": "python_pil",
                    "model_name": "afrigen_pil_engine",
                    "dimensions": "1080x1080",
                }
        except Exception as flyer_exc:
            logger.error("Flyer fallback error: %s", flyer_exc)

    return {
        "ok": False,
        "error": "Creative generation could not complete. Retrying shortly.",
    }


# ==============================================================================
# VIDEO GENERATION (HUGGING FACE + AFRIGEN KLING/VIDEO FALLBACK)
# ==============================================================================

def generate_social_video(
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "16:9",
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a marketing video using Hugging Face text-to-video models.

    Falls back to existing video infrastructure if serverless HF video pipeline
    is loading or cold.
    """
    token = _get_hf_token()
    model = model_override or DEFAULT_HF_VIDEO_MODEL

    # 1. Try Hugging Face Video Inference API
    if token:
        try:
            logger.info("Generating social video via Hugging Face model: %s", model)
            api_url = f"https://api-inference.huggingface.co/models/{model}"
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "inputs": prompt,
                "parameters": {"num_frames": 16, "num_inference_steps": 25}
            }
            resp = requests.post(api_url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("video/"):
                public_url = _persist_media_bytes(resp.content, ext="mp4", prefix="hf_vid")
                return {
                    "ok": True,
                    "media_url": public_url,
                    "media_type": "video",
                    "provider": "huggingface",
                    "model_name": model,
                    "duration_seconds": duration_seconds,
                }
            elif resp.status_code == 503:
                # Model is currently loading on HF servers
                logger.info("HF video model is loading; deferring to standard video generator.")
        except Exception as exc:
            logger.warning("HF video inference error: %s", exc)

    # 2. Fallback to existing Afrigen video generation infrastructure
    try:
        logger.info("Utilizing Afrigen production video pipeline for social video.")
        from services.video import generate_video_async, KLING_T2V_MODEL
        res = generate_video_async(
            prompt=prompt,
            style="cinematic",
            aspect_ratio=aspect_ratio,
            extended=True,
            duration=str(duration_seconds),
            allow_fal=True,
        )
        if res.get("request_id"):
            # Poll or retrieve video url
            import fal_client
            status = fal_client.status(KLING_T2V_MODEL, res["request_id"])
            if status and isinstance(status, dict) and status.get("video", {}).get("url"):
                return {
                    "ok": True,
                    "media_url": status["video"]["url"],
                    "media_type": "video",
                    "provider": "afrigen_video_engine",
                    "model_name": KLING_T2V_MODEL,
                    "duration_seconds": duration_seconds,
                }
    except Exception as vid_exc:
        logger.error("Standard video generator error: %s", vid_exc)

    return {
        "ok": False,
        "error": "Video processing could not be completed within timeout window.",
    }


def validate_media_asset(url: str, expected_type: str) -> bool:
    """Validate that a generated media URL is live, reachable, and matches expected type."""
    if not url or not url.startswith("http"):
        return False
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("Content-Type", "").lower()
        if expected_type in ("image", "flyer"):
            return "image" in content_type or url.endswith((".jpg", ".jpeg", ".png", ".webp"))
        elif expected_type == "video":
            return "video" in content_type or url.endswith((".mp4", ".mov", ".webm"))
        return True
    except Exception:
        return False
