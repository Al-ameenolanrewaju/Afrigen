"""
Publish an article to Dev.to via the Dev.to Articles API.

The canonical URL MUST point back to afrigen.com.ng/blog/{slug} to protect SEO —
Dev.to respects the `canonical_url` field so the original post stays the source
of truth for search engines.

Secrets required:
  DEVTO_API_KEY  — From https://dev.to/settings/extensions ("DEV Community API Keys")

API docs: https://developers.forem.com/api/v1#tag/articles/operation/createArticle
"""

import os
import requests


DEVTO_API = "https://dev.to/api"


def publish_article(title: str, content: str, tags: list[str],
                    canonical_url: str, description: str = "", api_key: str = None) -> dict:
    """Publish a Markdown article on Dev.to with a canonical URL back to Afrigen.

    Args:
        title: Article title.
        content: Article body in Markdown.
        tags: Up to 4 lowercase alphanumeric tags.
        canonical_url: The original blog URL on afrigen.com.ng (SEO canonical).
        description: Optional short description/summary.
        api_key: Optional API key. If not provided, falls back to DEVTO_API_KEY env var.

    Returns:
        {ok: bool, post_id, post_url, error}
    """
    api_key = api_key or os.environ.get("DEVTO_API_KEY", "")

    if not api_key:
        # Graceful skip — missing credentials must not crash the pipeline.
        print("[devto] ❌ missing credentials: DEVTO_API_KEY")
        return {
            "ok": False,
            "error": "Missing DEVTO_API_KEY",
            "post_id": None,
            "post_url": None,
        }

    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "set"
    print(f"[devto] credentials OK (api-key={masked_key})")

    # Dev.to tags: lowercase, alphanumeric, max 4.
    clean_tags = [t.lower() for t in (tags or []) if t][:4]

    article = {
        "title": title,
        "body_markdown": content,
        "published": True,
        "canonical_url": canonical_url,
        "tags": clean_tags,
    }
    if description:
        article["description"] = description[:250]

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/vnd.forem.api-v1+json",
    }

    print(
        f"[devto] publishing '{title}' "
        f"(content={len(content)} chars, tags={clean_tags}, canonical={canonical_url})"
    )

    try:
        resp = requests.post(
            f"{DEVTO_API}/articles",
            headers=headers,
            json={"article": article},
            timeout=20,
        )

        # Log HTTP status + raw body before parsing so a non-JSON response
        # (HTML error page, empty body) is visible instead of a cryptic decode error.
        raw_body = resp.text or ""
        print(f"[devto] HTTP {resp.status_code} ({len(raw_body)} bytes)")
        print(f"[devto] response body: {raw_body[:1000]}")

        if resp.status_code in (200, 201):
            try:
                data = resp.json()
            except ValueError:
                return {
                    "ok": False,
                    "error": (
                        f"Dev.to returned non-JSON response (HTTP {resp.status_code}): "
                        f"{raw_body[:300] or '<empty body>'}"
                    ),
                    "post_id": None,
                    "post_url": None,
                }
            post_id = str(data.get("id", ""))
            post_url = data.get("url") or f"https://dev.to/p/{post_id}"
            print(f"[devto] published (id={post_id}) url={post_url}")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        # Surface the API's own error message when available.
        try:
            error_msg = resp.json().get("error", raw_body)
        except ValueError:
            error_msg = raw_body or "<empty body>"
            
        # Detect "Canonical url has already been taken"
        if resp.status_code == 422 and "Canonical url has already been taken" in str(error_msg):
            print(f"[devto] article already published (canonical URL exists). Skipping gracefully.")
            return {"ok": True, "post_id": None, "post_url": "already published", "error": None}

        print(f"[devto] API error ({resp.status_code}): {error_msg}")
        return {
            "ok": False,
            "error": f"Dev.to API error ({resp.status_code}): {error_msg}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Dev.to exception: {e}",
            "post_id": None,
            "post_url": None,
        }
