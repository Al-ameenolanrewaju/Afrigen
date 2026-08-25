from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token
import json

class PinterestAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['access_token', 'board_id']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        access_token = kwargs.get("access_token")
        board_id = kwargs.get("board_id")
        if not access_token or not board_id:
            return {"ok": False, "error": "Missing access token or board ID"}
        return {
            "ok": True,
            "token": access_token,
            "metadata": {"board_id": board_id},
            "account_name": "Pinterest User"
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
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="pinterest").first()
        if not account:
            return {"ok": False, "error": "Not connected"}

        access_token = decrypt_token(account.encrypted_access_token)
        metadata = decrypt_token(account.metadata_json) if account.metadata_json else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        board_id = metadata.get("board_id") or account.account_identifier
        title = getattr(content, "title", None) or "Created with Afrigen"
        description = getattr(content, "body", "") or getattr(content, "content", "") or title
        image_url = getattr(content, "file_url", None) or ""

        from scripts.platforms.pinterest import create_pin
        return create_pin(
            title=title,
            description=description,
            link="https://afrigen.com.ng",
            image_url=image_url,
            image_title=title,
            access_token=access_token,
            board_id=board_id,
        )
