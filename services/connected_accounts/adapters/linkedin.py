import os
import requests
from typing import Dict, Any
from urllib.parse import urlencode
from ..base import BaseProviderAdapter
from models import db, ConnectedAccount

class LinkedinAdapter(BaseProviderAdapter):

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['access_token', 'author_urn']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        access_token = kwargs.get("access_token")
        author_urn = kwargs.get("author_urn")
        if not access_token or not author_urn:
            return {"ok": False, "error": "Missing access token or author URN"}
        return {
            "ok": True,
            "token": access_token,
            "metadata": {"author_urn": author_urn},
            "account_name": "LinkedIn User"
        }



    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No code provided"}
            
        client_id = os.environ.get("LINKEDIN_CLIENT_ID")
        client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
        
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
                return {
                    "ok": True, 
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_in": token_data.get("expires_in"),
                    "account_name": "LinkedIn User" # Ideally fetch from /v2/me
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
        from scripts.platforms.linkedin import publish_post
        
        # Determine if content is UserContent or GeneratedContent
        text = getattr(content, "body", "") or getattr(content, "content", "")
        if not text:
            return {"ok": False, "error": "No text content"}
            
        return publish_post(text, access_token=access_token)
