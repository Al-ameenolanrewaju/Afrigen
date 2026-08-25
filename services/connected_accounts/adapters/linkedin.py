import os
import requests
from flask import request, session
from typing import Dict, Any
from urllib.parse import urlencode
from ..base import BaseProviderAdapter
from models import db, ConnectedAccount

class LinkedinAdapter(BaseProviderAdapter):

    def _get_redirect_uri(self):
        return request.url_root.rstrip("/") + "/connected-accounts/linkedin/callback"

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        client_id = os.environ.get("LINKEDIN_CLIENT_ID")
        if not client_id or not os.environ.get("LINKEDIN_CLIENT_SECRET"):
            return {"ok": False, "error": "LinkedIn OAuth is not configured."}

        state = os.urandom(32).hex()
        session["linkedin_oauth_state"] = state
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self._get_redirect_uri(),
            "state": state,
            "scope": "openid profile w_member_social",
        }
        return {
            "ok": True,
            "type": "redirect",
            "url": "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(params),
        }



    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        if request_args.get("error"):
            return {"ok": False, "error": request_args.get("error_description", request_args["error"])}
        if request_args.get("state") != session.pop("linkedin_oauth_state", None):
            return {"ok": False, "error": "Invalid OAuth state."}

        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No authorization code provided."}
            
        client_id = os.environ.get("LINKEDIN_CLIENT_ID")
        client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            return {"ok": False, "error": "LinkedIn OAuth is not configured."}

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._get_redirect_uri(),
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        try:
            resp = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=data, timeout=15)
            if resp.status_code == 200:
                token_data = resp.json()
                account_name = "LinkedIn User"
                account_identifier = None
                access_token = token_data.get("access_token")
                profile = requests.get(
                    "https://api.linkedin.com/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15,
                )
                if profile.status_code == 200:
                    profile_data = profile.json()
                    account_name = profile_data.get("name") or account_name
                    account_identifier = profile_data.get("sub")
                return {
                    "ok": True, 
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_in": token_data.get("expires_in"),
                    "account_name": account_name,
                    "account_identifier": account_identifier,
                }
            else:
                return {"ok": False, "error": resp.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="linkedin").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        from utils.encryption import decrypt_token
        access_token = decrypt_token(account.encrypted_access_token)
        
        # Import the platform script dynamically to avoid circular imports
        from scripts.platforms.linkedin import post_article
        
        # Determine if content is UserContent or GeneratedContent
        text = getattr(content, "body", "") or getattr(content, "content", "")
        if not text:
            return {"ok": False, "error": "No text content"}
            
        person_id = account.account_identifier or os.environ.get("LINKEDIN_PERSON_ID", "")
        media_url = getattr(content, "file_url", "") or ""
        media_type = "image" if (getattr(content, "content_type", "") or "").lower() == "image" else "video"
        return post_article(
            text,
            access_token=access_token,
            person_id=person_id,
            media_url=media_url,
            media_type=media_type,
        )
