"""LinkedIn OAuth 2.0 and REST Posts API adapter for Afrigen Connected Accounts.

Supports official LinkedIn OAuth 2.0, profile retrieval, organization page checking,
and publishing using the current LinkedIn REST Posts API (/rest/posts).
"""

import os
import json
import logging
import requests
from flask import request, session
from typing import Dict, Any
from urllib.parse import urlencode

from ..base import BaseProviderAdapter
from models import db, ConnectedAccount
from utils.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

LINKEDIN_API = "https://api.linkedin.com/v2"
LINKEDIN_REST_API = "https://api.linkedin.com/rest"
LINKEDIN_VERSION = os.environ.get("LINKEDIN_VERSION", "202608")


class LinkedinAdapter(BaseProviderAdapter):
    """Adapter for connecting LinkedIn personal/company profiles and publishing content."""

    def _get_redirect_uri(self) -> str:
        configured_uri = os.environ.get("LINKEDIN_REDIRECT_URI")
        if configured_uri:
            return configured_uri.strip()
        base_url = os.environ.get("APP_BASE_URL")
        if base_url:
            return base_url.strip().rstrip("/") + "/connected-accounts/linkedin/callback"
        return request.url_root.rstrip("/") + "/connected-accounts/linkedin/callback"

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        """Initiate LinkedIn OAuth 2.0 flow."""
        client_id = os.environ.get("LINKEDIN_CLIENT_ID")
        client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
        missing = [name for name, value in {
            "LINKEDIN_CLIENT_ID": client_id,
            "LINKEDIN_CLIENT_SECRET": client_secret,
        }.items() if not value]
        if missing:
            return {
                "ok": False,
                "error": f"LinkedIn OAuth is not configured. Missing: {', '.join(missing)}."
            }

        state = os.urandom(32).hex()
        session["linkedin_oauth_state"] = state
        session["linkedin_oauth_user_id"] = user_id

        # w_member_social is standard for personal posting
        # r_organization_social and w_organization_social if developer app is configured for orgs
        scope = os.environ.get("LINKEDIN_SCOPE", "openid profile email w_member_social")

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self._get_redirect_uri(),
            "state": state,
            "scope": scope,
        }
        return {
            "ok": True,
            "type": "redirect",
            "url": "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(params),
        }

    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Exchange LinkedIn authorization code for tokens and member identity."""
        if request_args.get("error"):
            err_desc = request_args.get("error_description", request_args["error"])
            return {"ok": False, "error": f"LinkedIn authorization denied: {err_desc}"}

        state = request_args.get("state")
        expected_state = session.pop("linkedin_oauth_state", None)
        if not state or state != expected_state:
            return {"ok": False, "error": "Invalid OAuth state or CSRF validation failed."}

        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No authorization code provided by LinkedIn."}

        client_id = os.environ.get("LINKEDIN_CLIENT_ID")
        client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
        if not client_id or not client_secret:
            return {"ok": False, "error": "LinkedIn OAuth credentials are not configured."}

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._get_redirect_uri(),
            "client_id": client_id,
            "client_secret": client_secret
        }

        try:
            resp = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=data, timeout=15)
            if resp.status_code != 200:
                logger.error("LinkedIn token exchange error: %s", resp.text)
                return {"ok": False, "error": f"LinkedIn token exchange failed: {resp.text}"}

            token_data = resp.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")

            # Query userinfo for identity and picture
            account_name = "LinkedIn Member"
            account_identifier = None
            picture_url = None
            email = None

            profile_resp = requests.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if profile_resp.status_code == 200:
                profile_data = profile_resp.json()
                account_name = profile_data.get("name") or account_name
                account_identifier = profile_data.get("sub")
                picture_url = profile_data.get("picture")
                email = profile_data.get("email")

            # Check for authorized organizations if permissions allow
            organizations = []
            try:
                org_resp = requests.get(
                    f"{LINKEDIN_API}/organizationAcls?q=roleAssignee",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                    timeout=10,
                )
                if org_resp.status_code == 200:
                    elements = org_resp.json().get("elements", [])
                    for elem in elements:
                        org_urn = elem.get("organization")
                        role = elem.get("role")
                        if org_urn:
                            organizations.append({"urn": org_urn, "role": role})
            except Exception:
                pass  # Organization ACL query is optional and requires additional permissions

            metadata = {
                "sub": account_identifier,
                "name": account_name,
                "email": email,
                "picture_url": picture_url,
                "organizations": organizations,
                "publishing_identity": f"urn:li:person:{account_identifier}" if account_identifier else None,
                "permissions": ["w_member_social"],
            }

            return {
                "ok": True,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "account_name": account_name,
                "account_identifier": account_identifier,
                "metadata": metadata,
            }

        except Exception as exc:
            logger.exception("LinkedIn OAuth callback exception: %s", exc)
            return {"ok": False, "error": str(exc)}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        """Disconnect LinkedIn account for this user."""
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        """Test token validity."""
        return self.test_connection(user_id)

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        """Verify that the stored LinkedIn token is valid and active."""
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="linkedin").first()
        if not account or not account.encrypted_access_token:
            return {"ok": False, "error": "LinkedIn is not connected."}

        try:
            token = decrypt_token(account.encrypted_access_token)
            resp = requests.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True,
                    "name": data.get("name"),
                    "sub": data.get("sub"),
                    "active": True,
                }
            if resp.status_code == 401:
                return {"ok": False, "error": "LinkedIn access token has expired. Please reconnect your account."}
            return {"ok": False, "error": f"LinkedIn returned HTTP {resp.status_code}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        """Publish post (text, image, or video) to LinkedIn via REST Posts API."""
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="linkedin").first()
        if not account or not account.encrypted_access_token:
            return {"ok": False, "error": "LinkedIn is not connected."}

        access_token = decrypt_token(account.encrypted_access_token)

        # Retrieve text from various content object structures
        text = (
            getattr(content, "caption", "")
            or getattr(content, "body", "")
            or getattr(content, "content", "")
            or ""
        ).strip()

        if not text:
            return {"ok": False, "error": "No text content provided for LinkedIn publication."}

        # Add CTA and hashtags if present
        cta = getattr(content, "call_to_action", "") or ""
        hashtags = getattr(content, "hashtags", "") or ""
        post_message = text
        if cta and cta not in post_message:
            post_message = f"{post_message}\n\n👉 {cta}"
        if hashtags and hashtags not in post_message:
            post_message = f"{post_message}\n\n{hashtags}"

        # Resolve person/organization URN
        metadata = self._parse_metadata(account.metadata_json)
        person_id = (
            metadata.get("publishing_identity")
            or account.account_identifier
            or metadata.get("sub")
            or os.environ.get("LINKEDIN_PERSON_ID", "")
        )
        media_url = getattr(content, "media_url", "") or getattr(content, "file_url", "") or ""
        media_type = (getattr(content, "media_type", "") or getattr(content, "content_type", "") or "").lower()

        # Dynamic import to use existing platform script
        from scripts.platforms.linkedin import post_article
        return post_article(
            post_message,
            access_token=access_token,
            person_id=person_id,
            media_url=media_url,
            media_type=media_type if media_url else None,
        )

    def _parse_metadata(self, metadata_val: Any) -> dict:
        if not metadata_val:
            return {}
        if isinstance(metadata_val, dict):
            return metadata_val
        try:
            try:
                decrypted = decrypt_token(metadata_val)
                return json.loads(decrypted)
            except Exception:
                return json.loads(metadata_val)
        except Exception:
            return {}
