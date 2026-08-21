from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token

class TiktokAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['client_key', 'client_secret', 'access_token', 'open_id']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        client_key = kwargs.get("client_key")
        client_secret = kwargs.get("client_secret")
        access_token = kwargs.get("access_token")
        open_id = kwargs.get("open_id")
        if not all([client_key, client_secret, access_token, open_id]):
            return {"ok": False, "error": "Missing one or more required TikTok credentials"}
        return {
            "ok": True,
            "token": access_token,
            "metadata": {
                "client_key": client_key,
                "client_secret": client_secret,
                "open_id": open_id,
            },
            "account_name": "TikTok User"
        }
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        return {"ok": False, "error": "Not implemented"}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="tiktok").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        return {"ok": False, "error": "Publishing not implemented"}
