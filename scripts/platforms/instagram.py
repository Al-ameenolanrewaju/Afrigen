"""
Post to Instagram via the Meta Graph API.

⚠️  Instagram API only supports posting images/videos, not text-only posts.
    If no image is available, this module generates a text card image using
    Pillow (the blog title rendered as a styled image).

Secrets required:
  META_PAGE_ACCESS_TOKEN         — same token as Facebook
  META_INSTAGRAM_ACCOUNT_ID      — Instagram Business account ID

Get Instagram Account ID:
1. Connect your Instagram Professional account to your Facebook Page
2. GET /{page-id}?fields=instagram_business_account on Graph API Explorer
3. The returned ID is your META_INSTAGRAM_ACCOUNT_ID
"""

import os
import io
import requests
import tempfile

GRAPH_API = "https://graph.facebook.com/v19.0"


def post_caption(caption: str, image_url: str = None, title: str = "") -> dict:
    """Post to Instagram with an image + caption.

    Instagram requires an image. If image_url is not provided, a text card
    will be generated from the title using Pillow.

    Args:
        caption: Instagram caption text (max 2200 chars).
        image_url: Optional URL of an image to post (e.g., blog featured image).
        title: Blog post title (used for text card fallback).

    Returns:
        {ok: bool, media_id: str|None, post_url: str|None, error: str|None}
    """
    access_token = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
    ig_account_id = os.environ.get("META_INSTAGRAM_ACCOUNT_ID", "")

    if not access_token or not ig_account_id:
        return {
            "ok": False,
            "error": "Missing META_PAGE_ACCESS_TOKEN or META_INSTAGRAM_ACCOUNT_ID",
            "media_id": None,
            "post_url": None,
        }

    # Step 1: Get or create the image
    image_data = None

    if image_url:
        try:
            resp = requests.get(image_url, timeout=15)
            if resp.status_code == 200:
                image_data = resp.content
        except Exception as e:
            print(f"[instagram] failed to download image: {e}")

    if image_data is None and title:
        try:
            image_data = _generate_text_card(title)
            print(f"[instagram] generated text card for: {title[:60]}...")
        except Exception as e:
            print(f"[instagram] text card generation failed: {e}")

    if image_data is None:
        return {
            "ok": False,
            "error": "No image provided and text card generation failed. Instagram requires an image.",
            "media_id": None,
            "post_url": None,
        }

    # Step 2: Upload image as a media container
    try:
        # Instagram API needs multipart form upload
        files = {
            "image_url": (None, image_url) if image_url else None,
        }

        # Use the uploaded image bytes approach
        # Actually, let's use a two-step approach: upload file to a temp location
        # then reference it. Meta's Instagram API accepts either a URL or binary.

        # For binary upload, we POST to the media endpoint with multipart
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(image_data)
        tmp.close()

        with open(tmp.name, "rb") as f:
            resp = requests.post(
                f"{GRAPH_API}/{ig_account_id}/media",
                params={
                    "caption": caption[:2200],
                    "access_token": access_token,
                },
                files={"image": ("image.jpg", f, "image/jpeg")},
                timeout=30,
            )

        os.unlink(tmp.name)

        data = resp.json()
        if resp.status_code != 200 or "id" not in data:
            error_msg = data.get("error", {}).get("message", str(data))
            return {
                "ok": False,
                "error": f"Instagram media upload failed: {error_msg}",
                "media_id": None,
                "post_url": None,
            }

        creation_id = data["id"]
        print(f"[instagram] media container created (id={creation_id})")

    except Exception as e:
        return {
            "ok": False,
            "error": f"Instagram upload exception: {e}",
            "media_id": None,
            "post_url": None,
        }

    # Step 3: Publish the media container
    try:
        resp = requests.post(
            f"{GRAPH_API}/{ig_account_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": access_token,
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and "id" in data:
            media_id = data["id"]
            post_url = f"https://www.instagram.com/p/{media_id}/"
            print(f"[instagram] published (media_id={media_id})")
            return {"ok": True, "media_id": media_id, "post_url": post_url, "error": None}

        error_msg = data.get("error", {}).get("message", str(data))
        return {
            "ok": False,
            "error": f"Instagram publish failed: {error_msg}",
            "media_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Instagram publish exception: {e}",
            "media_id": None,
            "post_url": None,
        }


def _generate_text_card(title: str) -> bytes:
    """Generate a 1080x1080 image card from a blog title using Pillow.

    Returns the image as PNG bytes (Instagram accepts PNG/JPEG).
    """
    from PIL import Image, ImageDraw, ImageFont
    import textwrap

    W, H = 1080, 1080
    BG_COLOR = (26, 28, 36)        # Dark background (#1A1C24)
    ACCENT = (245, 166, 35)        # Gold (#F5A623) — Afrigen brand
    TEXT_COLOR = (255, 255, 255)
    SUBTITLE_COLOR = (201, 209, 217)

    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Try to load a font, fall back to default
    try:
        font_title = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 60)
        font_sub = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 36)
        font_small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28)
    except (OSError, IOError):
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Top accent bar
    draw.rectangle([0, 0, W, 8], fill=ACCENT)

    # Brand label
    draw.text((W // 2, 100), "AFRIGEN", fill=ACCENT, font=font_small, anchor="mt")

    # Decorative line
    y_line = 160
    draw.rectangle([W // 2 - 80, y_line, W // 2 + 80, y_line + 3], fill=ACCENT)

    # Title (wrapped to fit)
    y_text = 260
    wrapper = textwrap.TextWrapper(width=28)
    lines = wrapper.wrap(title)
    for line in lines[:6]:  # Max 6 lines
        draw.text((W // 2, y_text), line, fill=TEXT_COLOR, font=font_title, anchor="mt")
        y_text += 80

    # Subtitle
    y_sub = max(y_text + 60, 800)
    draw.text(
        (W // 2, y_sub),
        "Read the full article on afrigen.com.ng",
        fill=SUBTITLE_COLOR, font=font_sub, anchor="mt",
    )

    # Bottom accent bar
    draw.rectangle([0, H - 8, W, H], fill=ACCENT)

    # URL at bottom
    draw.text(
        (W // 2, H - 60),
        "afrigen.com.ng/blog",
        fill=SUBTITLE_COLOR, font=font_small, anchor="mt",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
