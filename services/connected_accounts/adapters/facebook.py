"""Facebook Page native Graph API adapter for Afrigen Connected Accounts.

Supports official Meta OAuth 2.0 flow for Page Access Tokens and direct Page credentials.
Uses Meta Graph API v19.0.
"""

import os
import json
import logging
import requests
from typing import Dict, Any
from urllib.parse import urlencode
from flask import request, session

from ..base import BaseProviderAdapter
from models import db, ConnectedAccount
from utils.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = os.environ.get("FACEBOOK_GRAPH_API_VERSION", "v19.0")
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class FacebookAdapter(BaseProviderAdapter):
    """Adapter for connecting Facebook Pages and publishing content autonomously."""

    def _get_redirect_uri(self) -> str:
        configured_uri = os.environ.get("FACEBOOK_REDIRECT_URI")
        if configured_uri:
            return configured_uri.strip()
        base_url = os.environ.get("APP_BASE_URL")
        if base_url:
            return base_url.strip().rstrip("/") + "/connected-accounts/facebook/callback"
        return request.url_root.rstrip("/") + "/connected-accounts/facebook/callback"

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth', 'page_id', 'page_access_token']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        """Initiate OAuth flow or connect directly via manual page credentials."""
        # 1. Direct form credential support (fallback/testing)
        page_id = kwargs.get("page_id")
        page_access_token = kwargs.get("page_access_token")
        if page_id and page_access_token:
            # Test token directly
            test_res = self._verify_page_access(page_id, page_access_token)
            if not test_res.get("ok"):
                return {"ok": False, "error": f"Invalid Page credentials: {test_res.get('error')}"}

            page_info = test_res.get("page_info", {})
            return {
                "ok": True,
                "token": page_access_token,
                "metadata": {
                    "page_id": page_id,
                    "page_name": page_info.get("name", "Facebook Page"),
                    "picture_url": page_info.get("picture", {}).get("data", {}).get("url"),
                    "permissions": ["pages_manage_posts", "pages_read_engagement"],
                    "auth_type": "manual_token",
                },
                "account_name": page_info.get("name", "Facebook Page"),
                "account_identifier": str(page_id),
            }

        # 2. Native Meta OAuth Flow
        client_id = os.environ.get("FACEBOOK_APP_ID") or os.environ.get("META_APP_ID")
        client_secret = os.environ.get("FACEBOOK_APP_SECRET") or os.environ.get("META_APP_SECRET")

        if not client_id or not client_secret:
            return {
                "ok": False,
                "error": "Facebook OAuth is not configured. Missing FACEBOOK_APP_ID or FACEBOOK_APP_SECRET."
            }

        state = os.urandom(32).hex()
        session["facebook_oauth_state"] = state
        session["facebook_oauth_user_id"] = user_id

        params = {
            "client_id": client_id,
            "redirect_uri": self._get_redirect_uri(),
            "state": state,
            "scope": "pages_show_list,pages_read_engagement,pages_manage_posts,public_profile",
            "response_type": "code",
        }

        oauth_url = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?" + urlencode(params)
        return {
            "ok": True,
            "type": "redirect",
            "url": oauth_url,
        }

    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Exchange authorization code for a long-lived Page Access Token."""
        if request_args.get("error"):
            err_desc = request_args.get("error_description", request_args.get("error"))
            return {"ok": False, "error": f"Meta authorization denied: {err_desc}"}

        state = request_args.get("state")
        expected_state = session.pop("facebook_oauth_state", None)
        if not state or state != expected_state:
            return {"ok": False, "error": "Invalid OAuth state or CSRF validation failed."}

        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No authorization code returned from Meta."}

        client_id = os.environ.get("FACEBOOK_APP_ID") or os.environ.get("META_APP_ID")
        client_secret = os.environ.get("FACEBOOK_APP_SECRET") or os.environ.get("META_APP_SECRET")

        if not client_id or not client_secret:
            return {"ok": False, "error": "Facebook OAuth credentials are missing."}

        try:
            # 1. Exchange code for short-lived user access token
            token_url = f"{GRAPH_BASE_URL}/oauth/access_token"
            token_params = {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": self._get_redirect_uri(),
                "code": code,
            }
            token_resp = requests.get(token_url, params=token_params, timeout=15)
            if token_resp.status_code != 200:
                logger.error("Meta access token exchange failed: %s", token_resp.text)
                return {"ok": False, "error": f"Failed to exchange token with Meta: {token_resp.text}"}

            token_data = token_resp.json()
            short_lived_token = token_data.get("access_token")

            # 2. Exchange for long-lived user token (60-day)
            long_lived_params = {
                "grant_type": "fb_exchange_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "fb_exchange_token": short_lived_token,
            }
            long_resp = requests.get(f"{GRAPH_BASE_URL}/oauth/access_token", params=long_lived_params, timeout=15)
            long_token = short_lived_token
            if long_resp.status_code == 200:
                long_token = long_resp.json().get("access_token", short_lived_token)

            # 3. Retrieve user's accessible Pages
            pages_resp = requests.get(
                f"{GRAPH_BASE_URL}/me/accounts",
                params={
                    "access_token": long_token,
                    "fields": "id,name,access_token,category,tasks,perms,picture{url}",
                },
                timeout=15,
            )
            if pages_resp.status_code != 200:
                logger.error("Failed to query Facebook pages: %s", pages_resp.text)
                return {"ok": False, "error": f"Could not retrieve Facebook Pages: {pages_resp.text}"}

            pages_data = pages_resp.json().get("data", [])
            if not pages_data:
                return {
                    "ok": False,
                    "error": "No Facebook Pages found. You must be an administrator or editor of at least one Facebook Page."
                }

            # Select page (default to first page with publishing perms)
            selected_page = None
            for p in pages_data:
                tasks = p.get("tasks", []) or p.get("perms", [])
                if any(t in ("CREATE_CONTENT", "MANAGE", "MODERATE") for t in tasks) or p.get("access_token"):
                    selected_page = p
                    break

            if not selected_page:
                selected_page = pages_data[0]

            page_id = selected_page["id"]
            page_name = selected_page.get("name", "Facebook Page")
            page_access_token = selected_page.get("access_token")
            picture_url = selected_page.get("picture", {}).get("data", {}).get("url")

            if not page_access_token:
                return {"ok": False, "error": f"Meta did not return an access token for Page '{page_name}'."}

            return {
                "ok": True,
                "access_token": page_access_token,
                "account_name": page_name,
                "account_identifier": str(page_id),
                "token_expiry": None,  # Page access tokens derived from long-lived user tokens typically do not expire
                "metadata": {
                    "page_id": str(page_id),
                    "page_name": page_name,
                    "picture_url": picture_url,
                    "category": selected_page.get("category"),
                    "tasks": selected_page.get("tasks", []),
                    "auth_type": "meta_oauth",
                }
            }

        except Exception as exc:
            logger.exception("Facebook OAuth callback error: %s", exc)
            return {"ok": False, "error": str(exc)}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        """Disconnect Facebook account for this user."""
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        """Verify token connectivity; if invalid, trigger reconnection prompt."""
        return self.test_connection(user_id)

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        """Verify that the stored Page token is valid and can read the page."""
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="facebook").first()
        if not account or not account.encrypted_access_token:
            return {"ok": False, "error": "Facebook Page is not connected."}

        try:
            token = decrypt_token(account.encrypted_access_token)
            metadata = self._parse_metadata(account.metadata_json)
            page_id = account.account_identifier or metadata.get("page_id")

            if not page_id:
                return {"ok": False, "error": "Missing Facebook Page ID."}

            resp = requests.get(
                f"{GRAPH_BASE_URL}/{page_id}",
                params={"access_token": token, "fields": "id,name,fan_count,is_published"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True,
                    "page_id": data.get("id"),
                    "name": data.get("name"),
                    "fans": data.get("fan_count", 0),
                    "published": data.get("is_published", True),
                }

            err_data = resp.json().get("error", {})
            return {
                "ok": False,
                "error": err_data.get("message", f"HTTP {resp.status_code} from Graph API"),
                "error_code": err_data.get("code"),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        """Publish text, image, or video directly to the connected Facebook Page."""
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="facebook").first()
        if not account or not account.encrypted_access_token:
            return {"ok": False, "error": "Facebook Page is not connected."}

        token = decrypt_token(account.encrypted_access_token)
        metadata = self._parse_metadata(account.metadata_json)
        page_id = account.account_identifier or metadata.get("page_id")

        if not page_id:
            return {"ok": False, "error": "Missing Facebook Page ID."}

        text = (
            getattr(content, "caption", "")
            or getattr(content, "body", "")
            or getattr(content, "content", "")
            or ""
        ).strip()

        media_url = getattr(content, "media_url", None) or getattr(content, "file_url", None)
        media_type = (getattr(content, "media_type", "") or getattr(content, "content_type", "") or "").lower()

        # Handle hashtags and CTA if available
        hashtags = getattr(content, "hashtags", "") or ""
        cta = getattr(content, "call_to_action", "") or ""
        post_message = text
        if cta and cta not in post_message:
            post_message = f"{post_message}\n\n👉 {cta}"
        if hashtags and hashtags not in post_message:
            post_message = f"{post_message}\n\n{hashtags}"

        try:
            # 1. Video Publishing
            if media_url and ("video" in media_type or media_url.endswith((".mp4", ".mov", ".webm"))):
                video_payload = {
                    "file_url": media_url,
                    "description": post_message,
                    "access_token": token,
                }
                title = getattr(content, "title", None)
                if title:
                    video_payload["title"] = title[:255]

                resp = requests.post(
                    f"{GRAPH_BASE_URL}/{page_id}/videos",
                    data=video_payload,
                    timeout=60,
                )
                res_data = resp.json()
                if resp.status_code in (200, 201) and "id" in res_data:
                    video_id = res_data["id"]
                    post_url = f"https://www.facebook.com/{page_id}/videos/{video_id}/"
                    logger.info("Facebook video published successfully: %s", video_id)
                    return {"ok": True, "post_id": video_id, "post_url": post_url}
                error_msg = res_data.get("error", {}).get("message", resp.text)
                return {"ok": False, "error": f"Facebook video publish failed: {error_msg}"}

            # 2. Image / Photo Publishing
            elif media_url and any(t in media_type for t in ("image", "flyer", "photo") or media_url.endswith((".jpg", ".jpeg", ".png", ".webp"))):
                photo_payload = {
                    "url": media_url,
                    "message": post_message,
                    "access_token": token,
                }
                resp = requests.post(
                    f"{GRAPH_BASE_URL}/{page_id}/photos",
                    data=photo_payload,
                    timeout=30,
                )
                res_data = resp.json()
                if resp.status_code in (200, 201) and "id" in res_data:
                    post_id = res_data.get("post_id") or res_data.get("id")
                    post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
                    logger.info("Facebook photo published successfully: %s", post_id)
                    return {"ok": True, "post_id": post_id, "post_url": post_url}
                error_msg = res_data.get("error", {}).get("message", resp.text)
                return {"ok": False, "error": f"Facebook photo publish failed: {error_msg}"}

            # 3. Text Post
            else:
                feed_payload = {
                    "message": post_message,
                    "access_token": token,
                }
                resp = requests.post(
                    f"{GRAPH_BASE_URL}/{page_id}/feed",
                    data=feed_payload,
                    timeout=20,
                )
                res_data = resp.json()
                if resp.status_code in (200, 201) and "id" in res_data:
                    post_id = res_data["id"]
                    post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
                    logger.info("Facebook feed post published successfully: %s", post_id)
                    return {"ok": True, "post_id": post_id, "post_url": post_url}
                error_msg = res_data.get("error", {}).get("message", resp.text)
                return {"ok": False, "error": f"Facebook feed publish failed: {error_msg}"}

        except Exception as exc:
            logger.exception("Facebook publishing exception: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _verify_page_access(self, page_id: str, access_token: str) -> Dict[str, Any]:
        """Check if a manual page ID and access token can access Graph API."""
        try:
            resp = requests.get(
                f"{GRAPH_BASE_URL}/{page_id}",
                params={"access_token": access_token, "fields": "id,name,picture"},
                timeout=10,
            )
            if resp.status_code == 200:
                return {"ok": True, "page_info": resp.json()}
            return {"ok": False, "error": resp.json().get("error", {}).get("message", resp.text)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _parse_metadata(self, metadata_val: Any) -> dict:
        if not metadata_val:
            return {}
        if isinstance(metadata_val, dict):
            return metadata_val
        try:
            # Check if it was encrypted
            try:
                decrypted = decrypt_token(metadata_val)
                return json.loads(decrypted)
            except Exception:
                return json.loads(metadata_val)
        except Exception:
            return {}
