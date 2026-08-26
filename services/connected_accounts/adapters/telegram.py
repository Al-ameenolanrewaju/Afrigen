import json
import os
import secrets
from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount, User, db
from utils.encryption import encrypt_token
from utils.encryption import decrypt_token

class TelegramAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']
        
    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        bot_username = (os.environ.get("TELEGRAM_BOT_USERNAME", "AfrigenBot") or "AfrigenBot").lstrip("@")
        if not bot_token:
            return {"ok": False, "error": "Telegram bot is not configured."}
        code = secrets.token_hex(3).upper()
        user = User.query.get(user_id)
        user.telegram_link_code = code
        db.session.commit()
        return {
            "ok": True,
            "type": "redirect",
            "url": f"https://t.me/{bot_username}?startgroup={code}",
            "bot_username": bot_username,
            "start_url": f"https://t.me/{bot_username}?startgroup={code}",
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
        if not account or account.status != "connected":
            return {"ok": False, "error": "Not connected"}

        bot_token = decrypt_token(account.encrypted_access_token)
        metadata = decrypt_token(account.metadata_json) if account.metadata_json else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        chat_id = metadata.get("chat_id") or account.account_identifier
        text = getattr(content, "body", "") or getattr(content, "content", "")
        if not bot_token or not chat_id or not text:
            return {"ok": False, "error": "Telegram automation credentials or content are missing."}

        from scripts.platforms.telegram import post_to_channel
        return post_to_channel(text, concise=False, bot_token=bot_token, channel_id=chat_id)
