"""
Pinterest publisher — ACTIVE.

Creates a Pin from Afrigen-generated content, linking back to afrigen.com.ng.
Afrigen blog posts have no per-post image, so when no image_url is supplied we
render a branded 1080x1080 card from the title (via the shared Pillow text-card
generator) and upload it to Pinterest as base64 — no image hosting required.

A Pinterest failure (missing token, API error, image failure) returns
{ok: False, ...} and NEVER raises, so it can't block the other platforms.

Secrets:
  PINTEREST_ACCESS_TOKEN   — REQUIRED. OAuth access token (scopes: pins:write, boards:read)
  PINTEREST_BOARD_ID       — OPTIONAL. If unset, the first available board is fetched
                             from the API and used automatically.

API docs: https://developers.pinterest.com/docs/api/v5/pins-create/
"""

import os
import base64
import requests


PINTEREST_API = "https://api.pinterest.com/v5"


def _render_card_base64(title: str) -> tuple[str, str] | None:
    """Render a branded Afrigen card for `title` and return (content_type, base64).

    Reuses the Pillow text-card generator so Pinterest and Instagram share one
    branded look. Returns None if image generation isn't available."""
    try:
        from platforms.instagram import _generate_text_card
        png_bytes = _generate_text_card(title or "Afrigen")
        return "image/png", base64.b64encode(png_bytes).decode("ascii")
    except Exception as e:
        print(f"[pinterest] card generation failed: {e}")
        return None


def _resolve_board_id(access_token: str) -> str:
    """Auto-select a board when PINTEREST_BOARD_ID isn't set.

    Fetches the account's boards via the API and returns the first one. This
    removes the need to manually look up and configure a board id. Returns ""
    (and logs the reason) when no board can be resolved."""
    try:
        resp = requests.get(
            f"{PINTEREST_API}/boards",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"page_size": 25},
            timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                board = items[0]
                print(f"[pinterest] auto-selected board "
                      f"'{board.get('name', '?')}' (id={board.get('id', '')})")
                return board.get("id", "")
            print("[pinterest] no boards found on this account")
        else:
            print(f"[pinterest] board lookup failed "
                  f"({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"[pinterest] board lookup failed: {e}")
    return ""


def create_pin(
    title: str, 
    description: str, 
    link: str,
    image_url: str = "", 
    image_title: str = "",
    access_token: str = None,
    board_id: str = None
) -> dict:
    """Create a Pin linking back to an Afrigen blog post.

    Args:
        title: Pin title (max 100 chars).
        description: Pin description (max 500 chars).
        link: Destination URL (the Afrigen blog post).
        image_url: Optional hosted image URL to pin.
        image_title: Title used to render a branded card when image_url is absent.
        access_token: User access token
        board_id: Optional board ID

    Returns:
        {ok, post_id, post_url, error} — skips gracefully, never raises.
    """
    access_token = access_token or os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    if not access_token:
        return {
            "ok": False,
            "error": "Missing PINTEREST_ACCESS_TOKEN",
            "post_id": None,
            "post_url": None,
        }

    board_id = board_id or os.environ.get("PINTEREST_BOARD_ID", "") or _resolve_board_id(access_token)
    if not board_id:
        return {
            "ok": False,
            "error": "Missing PINTEREST_BOARD_ID and no board could be resolved",
            "post_id": None,
            "post_url": None,
        }

    # Build the media source: a hosted URL if given, else a branded base64 card.
    if image_url:
        media_source = {"source_type": "image_url", "url": image_url}
    else:
        card = _render_card_base64(image_title or title)
        if not card:
            return {
                "ok": False,
                "error": "Pinterest requires an image and card generation failed",
                "post_id": None,
                "post_url": None,
            }
        content_type, data = card
        media_source = {
            "source_type": "image_base64",
            "content_type": content_type,
            "data": data,
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {
        "board_id": board_id,
        "title": (title or "")[:100],
        "description": (description or "")[:500],
        "link": link,
        "media_source": media_source,
    }

    try:
        resp = requests.post(
            f"{PINTEREST_API}/pins",
            headers=headers,
            json=body,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            pin_id = data.get("id", "")
            post_url = f"https://www.pinterest.com/pin/{pin_id}/"
            print(f"[pinterest] pinned (id={pin_id})")
            return {"ok": True, "post_id": pin_id, "post_url": post_url, "error": None}

        return {
            "ok": False,
            "error": f"Pinterest API error ({resp.status_code}): {resp.text}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Pinterest exception: {e}",
            "post_id": None,
            "post_url": None,
        }
