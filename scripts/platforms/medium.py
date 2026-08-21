"""
Cross-post to Medium via the Medium API.

The canonical URL MUST point back to afrigen.com.ng/blog/{slug} to protect SEO.
Medium respects the canonicalUrl field for this purpose.

Secrets required:
  MEDIUM_INTEGRATION_TOKEN  — From Medium Settings > Security and apps > Integration tokens
  MEDIUM_AUTHOR_ID          — Your Medium user/author ID

Get them at: https://medium.com/me/settings (Integration tokens section)
Your author ID can be found at: GET https://api.medium.com/v1/me
"""

import os
import requests


MEDIUM_API = "https://api.medium.com/v1"


def publish_article(
    title: str, 
    content: str, 
    tags: list[str], 
    canonical_url: str,
    access_token: str = None,
    author_id: str = None
) -> dict:
    """Publish a full article on Medium with a canonical URL back to Afrigen.

    Args:
        title: Article title.
        content: Article body in markdown or HTML.
        tags: List of up to 5 topic tags.
        canonical_url: The original blog URL on afrigen.com.ng (SEO canonical).
        access_token: User access token
        author_id: User author ID

    Returns:
        {ok: bool, post_id: str|None, post_url: str|None, error: str|None}
    """
    access_token = access_token or os.environ.get("MEDIUM_INTEGRATION_TOKEN", "")
    author_id = author_id or os.environ.get("MEDIUM_AUTHOR_ID", "")

    if not access_token or not author_id:
        return {
            "ok": False,
            "error": "Missing MEDIUM_INTEGRATION_TOKEN or MEDIUM_AUTHOR_ID",
            "post_id": None,
            "post_url": None,
        }

    # Medium publishes under "draft" by default unless publishStatus is "public".
    # Always publish as "public" for this pipeline — the admin already approved it.
    body = {
        "title": title,
        "contentFormat": "markdown",
        "content": content,
        "tags": (tags or [])[:5],
        "canonicalUrl": canonical_url,
        "publishStatus": "public",
        "license": "all-rights-reserved",
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{MEDIUM_API}/users/{author_id}/posts",
            headers=headers,
            json=body,
            timeout=20,
        )
        data = resp.json()

        if resp.status_code in (200, 201) and "data" in data:
            post_data = data["data"]
            post_id = post_data.get("id", "")
            post_url = post_data.get("url", f"https://medium.com/p/{post_id}")
            print(f"[medium] published (id={post_id}) url={post_url}")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        error_msg = data.get("errors", [{}])[0].get("message", str(data))
        return {
            "ok": False,
            "error": f"Medium API error: {error_msg}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Medium exception: {e}",
            "post_id": None,
            "post_url": None,
        }
