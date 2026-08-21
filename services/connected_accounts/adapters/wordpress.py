from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token

class WordpressAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['app_password'] 
        
    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        username = kwargs.get("username")
        app_password = kwargs.get("app_password")
        site_url = kwargs.get("site_url")
        if not username or not app_password or not site_url:
            return {"ok": False, "error": "Missing credentials"}
        return {"ok": True, "token": app_password, "metadata": {"site_url": site_url, "username": username}, "account_name": f"WordPress ({site_url})"}
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        return {"ok": False, "error": "Not implemented"}

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
            
        return {"ok": False, "error": "Publishing not implemented"}
