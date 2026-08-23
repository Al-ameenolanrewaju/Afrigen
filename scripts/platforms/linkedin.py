"""
Post to LinkedIn via the LinkedIn API v2.

⚠️  IMPORTANT: LinkedIn access tokens expire every 60 days.
    You must manually regenerate the token before it expires.
    Go to: https://www.linkedin.com/developers/apps
    Use the "Token Generator" tool under your app to get a fresh token.
    Update the LINKEDIN_ACCESS_TOKEN GitHub secret afterward.

Secrets required:
  LINKEDIN_ACCESS_TOKEN  — OAuth 2.0 access token with w_member_social scope
  LINKEDIN_PERSON_ID     — Your LinkedIn person URN (e.g., "urn:li:person:XXXXXX")

Get them at: https://www.linkedin.com/developers/apps
See: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
"""

import os
import requests


LINKEDIN_API = "https://api.linkedin.com/v2"


def _log_response(label: str, resp) -> None:
    """Log the raw HTTP response so non-JSON / empty bodies are debuggable."""
    raw = resp.text or ""
    print(f"[linkedin] {label}: status={resp.status_code}")
    print(f"[linkedin] {label}: headers={dict(resp.headers)}")
    # Truncate to keep logs readable; LinkedIn errors are short, success is empty.
    print(f"[linkedin] {label}: raw body={raw[:1000]!r}")


def _safe_json(resp) -> dict:
    """Parse a JSON body without throwing on empty / non-JSON responses.

    A successful LinkedIn create returns 201 with an EMPTY body (the post URN
    is in the `x-restli-id` header), so resp.json() would raise
    'Expecting value: line 1 column 1 (char 0)'. Return {} in that case.
    """
    if not (resp.text or "").strip():
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


def post_article(text: str, access_token: str = None, person_id: str = None) -> dict:
    """Post a text article/share to LinkedIn.

    Uses the /posts endpoint (new LinkedIn Posts API) which supports text-only
    posts. Falls back to /ugcPosts if needed.

    Args:
        text: The post body (max ~3000 chars for LinkedIn).
        access_token: Optional API token. Falls back to LINKEDIN_ACCESS_TOKEN.
        person_id: Optional person URN. Falls back to LINKEDIN_PERSON_ID.

    Returns:
        {ok: bool, post_id: str|None, post_url: str|None, error: str|None}
    """
    access_token = access_token or os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    person_id = person_id or os.environ.get("LINKEDIN_PERSON_ID", "")

    if not access_token or not person_id:
        return {
            "ok": False,
            "error": "Missing LINKEDIN_ACCESS_TOKEN or LINKEDIN_PERSON_ID",
            "post_id": None,
            "post_url": None,
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Try the newer /posts endpoint first
    body = {
        "author": f"urn:li:person:{person_id.replace('urn:li:person:', '')}",
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    try:
        resp = requests.post(
            f"{LINKEDIN_API}/posts",
            headers=headers,
            json=body,
            timeout=15,
        )

        _log_response("posts", resp)

        if resp.status_code in (200, 201):
            data = _safe_json(resp)
            # Extract the post URN to build a URL. On 201 the body is empty and
            # the URN comes back in the `x-restli-id` header, not the JSON.
            post_urn = resp.headers.get("x-restli-id") or data.get("id", "")
            post_id = post_urn
            # LinkedIn post URLs are typically:
            # https://www.linkedin.com/feed/update/{urn}
            post_url = f"https://www.linkedin.com/feed/update/{post_urn}"
            print(f"[linkedin] posted successfully (id={post_id})")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        # Fallback: some apps use the older UGC Posts API
        if resp.status_code in (401, 403, 404):
            return _post_ugc(text, access_token, person_id, headers)

        error_body = resp.text
        return {
            "ok": False,
            "error": f"LinkedIn API error ({resp.status_code}): {error_body}",
            "post_id": None,
            "post_url": None,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"LinkedIn exception: {e}",
            "post_id": None,
            "post_url": None,
        }


def _post_ugc(text: str, access_token: str, person_id: str, headers: dict) -> dict:
    """Fallback: post via the older /ugcPosts endpoint."""
    body = {
        "author": person_id,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    try:
        resp = requests.post(
            f"{LINKEDIN_API}/ugcPosts",
            headers=headers,
            json=body,
            timeout=15,
        )

        _log_response("ugcPosts", resp)

        if resp.status_code in (200, 201):
            data = _safe_json(resp)
            post_id = resp.headers.get("x-restli-id") or data.get("id", "")
            post_url = f"https://www.linkedin.com/feed/update/{post_id}"
            print(f"[linkedin] posted via UGC (id={post_id})")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        return {
            "ok": False,
            "error": f"LinkedIn UGC API error ({resp.status_code}): {resp.text}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"LinkedIn UGC exception: {e}",
            "post_id": None,
            "post_url": None,
        }
