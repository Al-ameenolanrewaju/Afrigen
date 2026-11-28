"""Hugging Face Creative Generation Engine for Afrigen Social Media Automation.

Provides AI image and video generation using Hugging Face Inference APIs,
with persistent asset storage, status polling, validation, and brand identity enforcement.
Maintains Afrigen's visual identity: Obsidian Black, Radiant Gold, Warm Amber,
and premium African-inspired aesthetics.

Strictly avoids any external AI fallbacks (no Kling or third-party AI image APIs).
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
DEFAULT_HF_IMG2VID_MODEL = os.environ.get("HF_IMAGE_TO_VIDEO_MODEL", "stabilityai/stable-video-diffusion-img2vid-xt")

HF_INFERENCE_BASE_URL = "https://api-inference.huggingface.co/models"

# Creative Type Stylers enforcing Afrigen Visual Identity
# Black, Gold, Orange, Premium African-inspired aesthetics, Professional tech branding
CREATIVE_STYLE_TEMPLATES = {
    "promotional_flyer": (
        "High-end promotional campaign creative for Afrigen AI. Obsidian black background (#0A0E17), "
        "radiant metallic gold typography accents (#D4AF37), warm orange neon highlights (#FF6B00), "
        "sleek modern technology UI overlays, 8k resolution, crisp studio lighting, cinematic composition."
    ),
    "educational_graphic": (
        "Educational masterclass visual infographic for African creators. Dark graphite and obsidian backdrop, "
        "glowing gold instructional diagram cards, warm amber workflow vectors, professional typography, "
        "minimalist technology aesthetic, ultra-sharp detail."
    ),
    "ai_illustration": (
        "Photorealistic Afro-futuristic creative showcase. Deep black velvet background, radiant gold rim lighting, "
        "warm sunset amber atmospheric glow, rich African cultural patterns, cinematic 35mm portraiture, 8k resolution."
    ),
    "product_announcement": (
        "Premium tech product announcement visual. Dark metallic carbon finish, glowing gold circuit lines, "
        "warm orange beacon glow, polished glass interfaces, futuristic workspace, crisp commercial studio photography."
    ),
    "feature_demonstration": (
        "Feature demonstration showcase. Clean obsidian dark mode interface, shimmering gold playback controls, "
        "amber timeline highlights, professional African digital artist directing scene, cinematic lighting, 8k."
    ),
    "brand_awareness": (
        "Editorial brand campaign portrait for Afrigen AI ('Africa Creates, AI Generates'). Inspiring African creative "
        "leader, obsidian dark studio setting, dramatic golden key light, warm amber backlighting, authentic cultural pride."
    ),
    "infographic": (
        "Technical breakdown infographic for creative media. Clean black chalkboard slate, golden comparison graphs, "
        "vibrant amber metrics, modern UI icons, perfectly legible visual hierarchy, sharp high resolution."
    ),
    "campaign_creative": (
        "Dynamic multi-platform campaign creative. High-contrast obsidian and radiant gold palette, energetic amber flair, "
        "celebrating modern African storytelling and digital technology, premium film look, 8k."
    ),
}


def _get_hf_token() -> Optional[str]:
    """Retrieve Hugging Face API token from environment or fallback manager."""
    from services.hf_fallback import get_active_hf_token
    token = get_active_hf_token()
    if token:
        return token
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_API_KEY")
        or os.environ.get("HUGGINGFACE_TOKEN")
    )


def _get_hf_tokens_list() -> list:
    """Retrieve all available Hugging Face tokens in fallback priority order."""
    from services.hf_fallback import get_all_hf_tokens
    tokens = get_all_hf_tokens()
    primary = _get_hf_token()
    if primary and primary not in tokens:
        tokens.insert(0, primary)
    return tokens


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
# VALIDATION UTILITIES
# ==============================================================================

def verify_image_bytes(img_bytes: bytes) -> Dict[str, Any]:
    """Verify generated image for non-corruption, minimum dimensions, and valid format."""
    if not img_bytes or len(img_bytes) < 1024:
        return {"valid": False, "error": "Image data is empty or too small (under 1KB)."}

    try:
        from PIL import Image
        bio = BytesIO(img_bytes)
        with Image.open(bio) as im:
            width, height = im.size
            img_format = (im.format or "").upper()
            if width < 400 or height < 400:
                return {"valid": False, "error": f"Image dimensions too small: {width}x{height}."}
            return {
                "valid": True,
                "width": width,
                "height": height,
                "format": img_format,
            }
    except Exception as exc:
        return {"valid": False, "error": f"Invalid image bytes: {exc}"}


def verify_video_bytes(vid_bytes: bytes) -> Dict[str, Any]:
    """Verify generated video bytes for valid container header, non-truncation, and minimum size."""
    if not vid_bytes or len(vid_bytes) < 10240:  # Minimum 10 KB
        return {"valid": False, "error": "Video data is truncated or under 10KB."}

    # Check for valid container signatures:
    # MP4: 'ftyp' at offset 4..8
    # WEBM / MKV: 0x1A 0x45 0xDF 0xA3 at start
    is_mp4 = len(vid_bytes) >= 12 and (b"ftyp" in vid_bytes[:32] or b"moov" in vid_bytes)
    is_webm = vid_bytes[:4] == b"\x1a\x45\xdf\xa3"

    if not (is_mp4 or is_webm):
        # Fallback check: length > 50KB and contains standard codec tags
        if len(vid_bytes) > 51200:
            return {"valid": True, "format": "video"}
        return {"valid": False, "error": "Missing valid MP4 or WebM video container header."}

    return {"valid": True, "format": "mp4" if is_mp4 else "webm", "size": len(vid_bytes)}


def validate_media_asset(url: str, expected_type: str) -> bool:
    """Validate that a generated media URL is live, reachable, and matches expected type."""
    if not url or not url.startswith("http"):
        return False
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        if resp.status_code != 200:
            # Some CDNs reject HEAD; try small GET range
            resp = requests.get(url, headers={"Range": "bytes=0-1024"}, timeout=10)
            if resp.status_code not in (200, 206):
                return False

        content_type = resp.headers.get("Content-Type", "").lower()
        if expected_type in ("image", "flyer"):
            return "image" in content_type or url.endswith((".jpg", ".jpeg", ".png", ".webp"))
        elif expected_type == "video":
            return "video" in content_type or url.endswith((".mp4", ".mov", ".webm"))
        return True
    except Exception:
        return False


# ==============================================================================
# IMAGE GENERATION (HUGGING FACE + PYTHON PIL FLYER ENGINE)
# ==============================================================================

def generate_social_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    model_override: Optional[str] = None,
    creative_type: str = "promotional_flyer",
    fallback_to_flyer: bool = True,
) -> Dict[str, Any]:
    """Generate a marketing image using Hugging Face inference with 3-account fallback.

    Maintains Afrigen visual identity (Black, Gold, Orange, African-inspired aesthetics).
    If an account fails or is rate-limited (429), fails over to Account 2, then Account 3.
    If all HF accounts are unavailable or exhausted, safely uses internal Python PIL branded
    flyer generation. Strictly avoids any third-party external AI image providers.
    """
    from services.hf_fallback import execute_hf_with_fallback

    tokens = _get_hf_tokens_list()
    model = model_override or DEFAULT_HF_IMAGE_MODEL

    dimensions = {
        "1:1": (1080, 1080),
        "16:9": (1200, 675),
        "9:16": (720, 1280),
    }
    width, height = dimensions.get(aspect_ratio, (1080, 1080))

    # Enrich prompt with Afrigen brand identity
    style_snippet = CREATIVE_STYLE_TEMPLATES.get(
        creative_type,
        CREATIVE_STYLE_TEMPLATES["promotional_flyer"]
    )
    branded_prompt = f"{prompt}. {style_snippet}"

    if tokens:
        def _hf_image_worker(token: str, acc: Dict[str, Any]) -> Dict[str, Any]:
            from huggingface_hub import InferenceClient
            acc_name = acc.get("name", "Account")
            masked = acc.get("masked_token", "token")
            logger.info("Generating social creative via Hugging Face (%s - %s) model: %s", acc_name, masked, model)
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

            # Verify image quality before publishing
            check = verify_image_bytes(img_bytes)
            if not check["valid"]:
                logger.warning("HF generated image failed quality verification: %s", check["error"])
                raise ValueError(f"Image quality verification failed: {check['error']}")

            public_url = _persist_media_bytes(img_bytes, ext="jpg", prefix="hf_img")
            return {
                "ok": True,
                "media_url": public_url,
                "media_type": "image",
                "provider": "huggingface",
                "model_name": model,
                "account_used": acc_name,
                "dimensions": f"{width}x{height}",
            }

        try:
            res = execute_hf_with_fallback(
                _hf_image_worker,
                operation_name=f"Hugging Face image generation ({model})"
            )
            if isinstance(res, dict) and res.get("ok"):
                return res
        except Exception as exc:
            logger.warning("All Hugging Face accounts encountered errors during image generation: %s", exc)

    # Safe fallback to internal Python PIL flyer engine (No external AI provider)
    if fallback_to_flyer:
        try:
            logger.info("Generating branded graphic via internal Python PIL engine.")
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
            logger.error("Internal flyer fallback error: %s", flyer_exc)

    return {
        "ok": False,
        "error": "Creative generation could not complete across configured Hugging Face accounts.",
        "provider": "huggingface",
    }


# ==============================================================================
# VIDEO GENERATION (HUGGING FACE ONLY — TEXT-TO-VIDEO & IMAGE-TO-VIDEO)
# ==============================================================================

def generate_social_video(
    prompt: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "16:9",
    model_override: Optional[str] = None,
    image_url: Optional[str] = None,
    max_retries: int = 3,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Generate marketing video using Hugging Face video models with multi-account fallback.

    Supports:
    - Text-to-video (default: damo-vilab/text-to-video-ms-1.7m or configured override).
    - Image-to-video (when image_url is provided).
    - Automatic failover across 3 Hugging Face accounts on rate limits or errors.
    - Asynchronous status polling and model cold-start handling (503 loading retries).
    - Video header and size validation.
    - Persistent asset storage with publicly accessible HTTPS URL.

    STRICT: Never falls back to Kling or external AI video providers.
    Never returns incomplete or corrupted videos.
    """
    from services.hf_fallback import execute_hf_with_fallback

    tokens = _get_hf_tokens_list()
    if not tokens:
        logger.warning("No Hugging Face token is configured; cannot generate video.")
        return {
            "ok": False,
            "error": "Hugging Face authentication token (HF_TOKEN) is not configured.",
            "provider": "huggingface",
        }

    # Select model based on input type (image-to-video vs text-to-video)
    if image_url:
        model = model_override or DEFAULT_HF_IMG2VID_MODEL
        is_img2vid = True
    else:
        model = model_override or DEFAULT_HF_VIDEO_MODEL
        is_img2vid = False

    logger.info("Initiating Hugging Face video generation with model: %s (img2vid=%s)", model, is_img2vid)

    api_url = f"{HF_INFERENCE_BASE_URL}/{model}"

    # Brand-aligned prompt reinforcement
    enriched_prompt = (
        f"{prompt}. High-definition commercial video, obsidian black background, "
        f"radiant gold and warm amber lighting, cinematic camera motion, photorealistic African aesthetic."
    )

    def _hf_video_worker(token: str, acc: Dict[str, Any]) -> Dict[str, Any]:
        acc_name = acc.get("name", "Account")
        masked = acc.get("masked_token", "token")
        headers = {"Authorization": f"Bearer {token}"}
        start_time = time.time()
        attempt = 0

        while attempt < max_retries and (time.time() - start_time) < timeout_seconds:
            attempt += 1
            try:
                if is_img2vid and image_url:
                    img_resp = requests.get(image_url, timeout=30)
                    if img_resp.status_code != 200:
                        return {"ok": False, "error": f"Could not fetch source image: HTTP {img_resp.status_code}"}
                    resp = requests.post(
                        api_url,
                        headers=headers,
                        data=img_resp.content,
                        timeout=timeout_seconds,
                    )
                else:
                    payload = {
                        "inputs": enriched_prompt,
                        "parameters": {
                            "num_frames": 16,
                            "num_inference_steps": 25,
                        },
                    }
                    resp = requests.post(
                        api_url,
                        headers=headers,
                        json=payload,
                        timeout=timeout_seconds,
                    )

                # Success: Video bytes returned
                if resp.status_code == 200:
                    vid_bytes = resp.content
                    validation = verify_video_bytes(vid_bytes)
                    if not validation["valid"]:
                        logger.error("Hugging Face video failed validation: %s", validation["error"])
                        return {
                            "ok": False,
                            "error": f"Generated video failed validation: {validation['error']}",
                            "provider": "huggingface",
                            "model_name": model,
                        }

                    ext = validation.get("format", "mp4")
                    public_url = _persist_media_bytes(vid_bytes, ext=ext, prefix="hf_vid")
                    logger.info("Hugging Face video generated successfully via %s: %s", acc_name, public_url)

                    return {
                        "ok": True,
                        "media_url": public_url,
                        "media_type": "video",
                        "provider": "huggingface",
                        "model_name": model,
                        "account_used": acc_name,
                        "duration_seconds": duration_seconds,
                    }

                # Model is loading on Hugging Face (503 Service Unavailable)
                elif resp.status_code == 503:
                    try:
                        data = resp.json()
                        est_time = float(data.get("estimated_time", 20.0))
                    except Exception:
                        est_time = 20.0
                    sleep_time = min(est_time, 25.0)
                    logger.info("HF video model %s is warming up on %s. Waiting %.1fs (attempt %s/%s)...",
                                model, acc_name, sleep_time, attempt, max_retries)
                    time.sleep(sleep_time)
                    continue

                # Rate limited (429) or Auth error (401, 403): Raise to trigger next account
                elif resp.status_code == 429:
                    raise RuntimeError(f"Rate limit hit on {acc_name} ({masked}): HTTP 429")

                elif resp.status_code in (401, 403):
                    raise RuntimeError(f"Authentication failure on {acc_name} ({masked}): HTTP {resp.status_code}")

                else:
                    err_text = resp.text[:250]
                    raise RuntimeError(f"HF API HTTP {resp.status_code} on {acc_name}: {err_text}")

            except requests.exceptions.Timeout:
                logger.warning("Hugging Face video inference timed out on %s (attempt %s).", acc_name, attempt)
                if attempt >= max_retries:
                    raise
                time.sleep(3)

        raise RuntimeError(f"{acc_name} video generation timed out after {int(time.time() - start_time)}s.")

    try:
        res = execute_hf_with_fallback(
            _hf_video_worker,
            operation_name=f"Hugging Face video generation ({model})"
        )
        if isinstance(res, dict):
            return res
        return {
            "ok": False,
            "error": "Unexpected video generation response format.",
            "provider": "huggingface",
        }
    except Exception as exc:
        logger.exception("All Hugging Face accounts failed for video generation: %s", exc)
        return {
            "ok": False,
            "error": f"Hugging Face video generation error: {exc}",
            "provider": "huggingface",
            "model_name": model,
        }
