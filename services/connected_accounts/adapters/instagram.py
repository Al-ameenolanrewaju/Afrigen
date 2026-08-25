from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token
import json

class InstagramAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['ig_user_id', 'access_token']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        ig_user_id = kwargs.get("ig_user_id")
        access_token = kwargs.get("access_token")
        if not ig_user_id or not access_token:
            return {"ok": False, "error": "Missing Instagram user ID or access token"}
        return {
            "ok": True,
            "token": access_token,
            "metadata": {"ig_user_id": ig_user_id},
            "account_name": "Instagram Business"
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
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="instagram").first()
        if not account:
            return {"ok": False, "error": "Not connected"}

        access_token = decrypt_token(account.encrypted_access_token)
        metadata = decrypt_token(account.metadata_json) if account.metadata_json else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        ig_user_id = metadata.get("ig_user_id") or account.account_identifier
        image_url = getattr(content, "file_url", None)
        caption = getattr(content, "body", "") or getattr(content, "content", "")
        if not image_url:
            return {"ok": False, "error": "Instagram requires an image URL."}
        if not caption:
            caption = getattr(content, "title", "") or "Created with Afrigen"

        from scripts.platforms.instagram import post_caption
        return post_caption(
            caption=caption,
            image_url=image_url,
            title=getattr(content, "title", "Created with Afrigen"),
            access_token=access_token,
            ig_account_id=ig_user_id,
        )
