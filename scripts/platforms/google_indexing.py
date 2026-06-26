"""
Ping Google Indexing API with a new blog post URL so Google crawls it faster.

Uses the Google Indexing API (free tier: 200 URLs/day per service account).
This is the same API Google uses for job postings and livestreams — it tells
the crawler "there's new content here, come index it now."

Secrets required:
  GOOGLE_SERVICE_ACCOUNT_JSON  — Full JSON key for a service account with the
                                  Indexing API enabled

Setup:
1. Go to https://console.cloud.google.com/
2. Create a project (or use an existing one)
3. Enable the Indexing API: APIs & Services > Library > "Indexing API"
4. Create a service account: IAM & Admin > Service Accounts > Create
5. Add the service account as an Owner in Google Search Console for afrigen.com.ng
6. Generate a JSON key: Service Account > Keys > Add Key > JSON
7. Copy the ENTIRE JSON as the GOOGLE_SERVICE_ACCOUNT_JSON secret
"""

import os
import json
import time
import requests


# OAuth scopes for the Indexing API
SCOPES = ["https://www.googleapis.com/auth/indexing"]
INDEXING_API = "https://indexing.googleapis.com/v3/urlNotifications:publish"


def _get_access_token(sa_input: str) -> str:
    """Exchange a service account JSON key for an OAuth 2.0 access token."""
    sa_input = sa_input.strip()
    
    # 1. Parse SA JSON from file or string
    if os.path.exists(sa_input):
        try:
            with open(sa_input, 'r', encoding='utf-8') as f:
                sa_info = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to read SA JSON file at {sa_input}: {e}")
    else:
        try:
            sa_info = json.loads(sa_input)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Malformed GOOGLE_SERVICE_ACCOUNT_JSON. The provided string is not valid JSON. Ensure it is properly formatted (e.g., no unescaped quotes). JSON Error: {e}")
            
    # 2. Exchange token
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        import base64
        import jwt  # PyJWT
    except ImportError:
        # Fallback: use google-auth if available
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request

        credentials = service_account.Credentials.from_service_account_info(
            sa_info, scopes=SCOPES
        )
        credentials.refresh(Request())
        return credentials.token

    # Manual JWT signing approach

    now = int(time.time())
    payload = {
        "iss": sa_info["client_email"],
        "scope": " ".join(SCOPES),
        "aud": sa_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        "exp": now + 3600,
        "iat": now,
    }

    private_key = sa_info["private_key"].encode("utf-8")

    signed_jwt = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": sa_info.get("private_key_id", "")},
    )

    resp = requests.post(
        sa_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": signed_jwt,
        },
        timeout=15,
    )

    # The token endpoint returns JSON on both success and failure. Surface
    # Google's own error/error_description (e.g. "invalid_grant", clock skew,
    # API not enabled) instead of letting raise_for_status() discard the body.
    auth_body = resp.text or ""
    print(f"[google_indexing] auth response: HTTP {resp.status_code} ({len(auth_body)} bytes) body={auth_body[:500]}")
    try:
        token_data = resp.json()
    except ValueError:
        raise RuntimeError(
            f"token endpoint returned non-JSON (HTTP {resp.status_code}): "
            f"{(resp.text or '')[:300] or '<empty body>'}"
        )

    if resp.status_code != 200 or "access_token" not in token_data:
        err = token_data.get("error", "unknown_error")
        desc = token_data.get("error_description", "")
        raise RuntimeError(
            f"token exchange failed (HTTP {resp.status_code}): {err}"
            + (f" - {desc}" if desc else "")
        )

    return token_data["access_token"]


def notify_url(url: str) -> dict:
    """Ping the Google Indexing API to notify Google of a new/updated URL.

    Args:
        url: The full URL to index (e.g., https://afrigen.com.ng/blog/my-post).

    Returns:
        {ok: bool, notified: bool, error: str|None}
    """
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    if not sa_json:
        print("[google_indexing] ❌ missing credentials: GOOGLE_SERVICE_ACCOUNT_JSON")
        return {
            "ok": False,
            "notified": False,
            "error": "Missing GOOGLE_SERVICE_ACCOUNT_JSON",
        }

    try:
        access_token = _get_access_token(sa_json)
        print("[google_indexing] access token obtained")
    except Exception as e:
        print(f"[google_indexing] ❌ auth failed: {e}")
        return {
            "ok": False,
            "notified": False,
            "error": f"Google auth failed: {e}",
        }

    print(f"[google_indexing] notifying URL_UPDATED for {url}")
    try:
        resp = requests.post(
            INDEXING_API,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "type": "URL_UPDATED",
            },
            timeout=15,
        )

        # Log status + raw body before parsing so a non-JSON response (gateway
        # error, HTML) is visible instead of a cryptic JSON decode error.
        raw_body = resp.text or ""
        print(f"[google_indexing] API response HTTP {resp.status_code} for URL: {url}")
        print(f"[google_indexing] response body: {raw_body[:1000]}")

        try:
            data = resp.json()
        except ValueError:
            return {
                "ok": False,
                "notified": False,
                "error": (
                    f"Google Indexing returned non-JSON response (HTTP {resp.status_code}): "
                    f"{raw_body[:300] or '<empty body>'}"
                ),
            }

        if resp.status_code == 200:
            notified = data.get("urlNotificationMetadata") is not None
            print(f"[google_indexing] notified for {url}: {data}")
            return {"ok": True, "notified": notified, "error": None}

        error_msg = data.get("error", {}).get("message", str(data))

        # 403 usually means the service account isn't an owner in Search Console
        if resp.status_code == 403:
            return {
                "ok": False,
                "notified": False,
                "error": (
                    f"Google Indexing API 403: {error_msg}. "
                    "Make sure the service account email is added as an Owner "
                    "in Google Search Console for afrigen.com.ng."
                ),
            }

        return {
            "ok": False,
            "notified": False,
            "error": f"Google Indexing API error ({resp.status_code}): {error_msg}",
        }

    except Exception as e:
        return {
            "ok": False,
            "notified": False,
            "error": f"Google Indexing exception: {e}",
        }
