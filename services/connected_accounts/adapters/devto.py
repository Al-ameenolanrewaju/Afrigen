from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token
import requests

class DevtoAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['token']
        
    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        token = kwargs.get("token")
        if not token:
            return {"ok": False, "error": "Missing API key"}
            
        # Test connection
        resp = requests.get("https://dev.to/api/users/me", headers={"api-key": token}, timeout=15)
        if resp.status_code == 200:
            user_data = resp.json()
            return {
                "ok": True,
                "token": token,
                "account_name": user_data.get("username", "Dev.to User")
            }
        else:
            return {"ok": False, "error": f"Invalid API key: {resp.text}"}
        
    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="devto").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        token = decrypt_token(account.encrypted_access_token)
        resp = requests.get("https://dev.to/api/users/me", headers={"api-key": token}, timeout=15)
        return {"ok": resp.status_code == 200}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="devto").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        access_token = decrypt_token(account.encrypted_access_token)
        from scripts.platforms.devto import publish_article
        
        # In a real app, content would be a model. Assuming it has title, content attributes.
        title = getattr(content, "title", "Draft")
        body = getattr(content, "text_content", "") or getattr(content, "generated_content", "")
        tags = ["afrigen"]
        canonical_url = f"https://afrigen.com.ng/blog/{getattr(content, 'slug', 'draft')}"
        
        return publish_article(title, body, tags, canonical_url, api_key=access_token)
