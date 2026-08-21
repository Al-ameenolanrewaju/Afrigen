"""
Post to a Facebook Page via the Meta Graph API.

Secrets required:
  FACEBOOK_PAGE_ACCESS_TOKEN  — Page access token from Meta Graph API Explorer or
                             a Meta app with pages_manage_posts permission
  FACEBOOK_PAGE_ID            — Your Facebook Page ID (numeric)

Get them at: https://developers.facebook.com/tools/explorer/
1. Select your app
2. Add permissions: pages_manage_posts, pages_read_engagement
3. Generate a Page access token
4. Get Page ID from: GET /me/accounts
"""

import os
import requests


GRAPH_API = "https://graph.facebook.com/v19.0"


def post_to_page(text: str, link: str = None, access_token: str = None, page_id: str = None) -> dict:
    """Post a text update to a Facebook Page feed.

    Args:
        text: The post body.
        link: The link to include in the post.
        access_token: Optional API token. Falls back to FACEBOOK_PAGE_ACCESS_TOKEN.
        page_id: Optional page ID. Falls back to FACEBOOK_PAGE_ID.

    Returns:
        {ok: bool, post_id: str|None, post_url: str|None, error: str|None}
    """
    access_token = access_token or os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    page_id = page_id or os.environ.get("FACEBOOK_PAGE_ID", "")

    if not access_token or not page_id:
        return {
            "ok": False,
            "error": "Missing FACEBOOK_PAGE_ACCESS_TOKEN or FACEBOOK_PAGE_ID",
            "post_id": None,
            "post_url": None,
        }

    try:
        data = {
            "message": text,
            "access_token": access_token,
        }
        if link:
            data["link"] = link
        resp = requests.post(
            f"{GRAPH_API}/{page_id}/feed",
            data=data,
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and "id" in data:
            post_id = data["id"]
            post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
            print(f"[facebook] posted text (id={post_id})")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        error_msg = data.get("error", {}).get("message", str(data))
        return {
            "ok": False,
            "error": f"Facebook API error: {error_msg}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Facebook exception: {e}",
            "post_id": None,
            "post_url": None,
        }

def post_photo_to_page(image_url: str, caption: str, access_token: str = None, page_id: str = None) -> dict:
    """Post an image with a caption to a Facebook Page.

    Args:
        image_url: URL of the image to post.
        caption: The text caption.
        access_token: Optional API token.
        page_id: Optional page ID.

    Returns:
        {ok: bool, post_id: str|None, post_url: str|None, error: str|None}
    """
    access_token = access_token or os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    page_id = page_id or os.environ.get("FACEBOOK_PAGE_ID", "")

    if not access_token or not page_id:
        return {
            "ok": False,
            "error": "Missing FACEBOOK_PAGE_ACCESS_TOKEN or FACEBOOK_PAGE_ID",
            "post_id": None,
            "post_url": None,
        }

    try:
        resp = requests.post(
            f"{GRAPH_API}/{page_id}/photos",
            data={
                "url": image_url,
                "message": caption,
                "access_token": access_token,
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and "id" in data and "post_id" in data:
            post_id = data["post_id"]
            post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
            print(f"[facebook] posted photo (id={post_id})")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}
        
        # Sometimes post_id isn't returned for photos, only id
        if resp.status_code == 200 and "id" in data:
            photo_id = data["id"]
            post_url = f"https://www.facebook.com/{page_id}/photos/{photo_id}/"
            print(f"[facebook] posted photo (id={photo_id})")
            return {"ok": True, "post_id": photo_id, "post_url": post_url, "error": None}

        error_msg = data.get("error", {}).get("message", str(data))
        return {
            "ok": False,
            "error": f"Facebook API error: {error_msg}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Facebook exception: {e}",
            "post_id": None,
            "post_url": None,
        }
