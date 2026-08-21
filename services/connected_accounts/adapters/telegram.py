from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token

class TelegramAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['token', 'chat_id']
        
    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        token = kwargs.get("token")
        chat_id = kwargs.get("chat_id")
        if not token or not chat_id: return {"ok": False, "error": "Missing token or chat ID"}
        return {"ok": True, "token": token, "metadata": {"chat_id": chat_id}, "account_name": "Telegram Bot"}
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        return {"ok": False, "error": "Not implemented"}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="telegram").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        return {"ok": False, "error": "Publishing not implemented"}
