import os
import json
import requests
from flask import request, session
from typing import Dict, Any
from urllib.parse import urlencode
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token

class WordpressAdapter(BaseProviderAdapter):
    def _get_redirect_uri(self):
        return request.url_root.rstrip("/") + "/connected-accounts/wordpress/callback"

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']
        
    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        client_id = os.environ.get("WORDPRESS_CLIENT_ID")
        redirect_uri = self._get_redirect_uri()
        if not client_id:
            return {"ok": False, "error": "WordPress OAuth is not configured."}

        state = os.urandom(32).hex()
        session["wordpress_oauth_state"] = state
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "global",
            "state": state,
        }
        return {
            "ok": True,
            "type": "redirect",
            "url": "https://public-api.wordpress.com/oauth2/authorize?" + urlencode(params),
        }
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        if request_args.get("error"):
            return {"ok": False, "error": request_args.get("error_description", request_args["error"])}
        if request_args.get("state") != session.pop("wordpress_oauth_state", None):
            return {"ok": False, "error": "Invalid OAuth state."}

        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No authorization code provided."}

        redirect_uri = self._get_redirect_uri()
        try:
            response = requests.post(
                "https://public-api.wordpress.com/oauth2/token",
                data={
                    "client_id": os.environ.get("WORDPRESS_CLIENT_ID"),
                    "client_secret": os.environ.get("WORDPRESS_CLIENT_SECRET"),
                    "redirect_uri": redirect_uri,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {"ok": False, "error": f"WordPress token exchange failed: {response.text}"}
            token_data = response.json()
            account_name = "WordPress.com"
            profile = requests.get(
                "https://public-api.wordpress.com/rest/v1.1/me",
                headers={"Authorization": f"Bearer {token_data.get('access_token')}"},
                timeout=15,
            )
            if profile.status_code == 200:
                profile_data = profile.json()
                account_name = profile_data.get("display_name") or account_name
                primary_blog = profile_data.get("primary_blog")
                account_identifier = (
                    primary_blog.get("id")
                    if isinstance(primary_blog, dict)
                    else primary_blog
                )
            else:
                account_identifier = None
            return {
                "ok": True,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "account_identifier": account_identifier,
                "account_name": account_name,
            }
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="wordpress").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        access_token = decrypt_token(account.encrypted_access_token)
        site_id = account.account_identifier
        if not site_id:
            return {"ok": False, "error": "WordPress site was not identified during OAuth."}

        title = getattr(content, "title", None) or "Afrigen article"
        body = getattr(content, "body", None) or getattr(content, "content", None) or str(content)
        try:
            response = requests.post(
                f"https://public-api.wordpress.com/rest/v1.1/sites/{site_id}/posts/new",
                headers={"Authorization": f"Bearer {access_token}"},
                data={"title": title, "content": body, "status": "publish"},
                timeout=30,
            )
            if response.status_code not in (200, 201):
                return {"ok": False, "error": f"WordPress publish failed ({response.status_code}): {response.text[:500]}"}
            data = response.json()
            return {"ok": True, "post_id": data.get("ID"), "url": data.get("URL")}
        except requests.RequestException as exc:
            return {"ok": False, "error": f"WordPress publish failed: {exc}"}
