from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token

class YoutubeAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['client_id', 'client_secret', 'refresh_token']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")
        refresh_token = kwargs.get("refresh_token")
        if not all([client_id, client_secret, refresh_token]):
            return {"ok": False, "error": "Missing one or more required YouTube credentials"}
        return {
            "ok": True,
            "token": refresh_token,
            "metadata": {
                "client_id": client_id,
                "client_secret": client_secret,
            },
            "account_name": "YouTube User"
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
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="youtube").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        return {"ok": False, "error": "Publishing not implemented"}
