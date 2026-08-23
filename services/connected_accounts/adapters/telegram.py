import os
import secrets
from flask import session
from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount, User
from utils.encryption import decrypt_token

class TelegramAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']
        
    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        code = secrets.token_hex(3).upper()
        user = User.query.get(user_id)
        if not user:
            return {"ok": False, "error": "Afrigen user was not found."}
        user.telegram_link_code = code
        from models import db
        db.session.commit()
        bot_username = (os.environ.get("TELEGRAM_BOT_USERNAME", "AfrigenBot") or "AfrigenBot").lstrip("@")
        session["telegram_connect_code"] = code
        return {
            "ok": True,
            "type": "redirect",
            "url": f"https://t.me/{bot_username}?startgroup={code}",
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
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="telegram").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        return {"ok": False, "error": "Publishing not implemented"}
