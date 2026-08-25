from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token

class FacebookAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['page_id', 'page_access_token']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        page_id = kwargs.get("page_id")
        page_access_token = kwargs.get("page_access_token")
        if not page_id or not page_access_token:
            return {"ok": False, "error": "Missing page ID or page access token"}
        return {
            "ok": True,
            "token": page_access_token,
            "metadata": {"page_id": page_id},
            "account_name": "Facebook Page"
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
        from routes.main import is_admin_user
        from models import User
        user = User.query.get(user_id)
        if user and is_admin_user(user):
            return {"ok": False, "error": "Facebook publishing is disabled for admin accounts."}

        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="facebook").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        access_token = decrypt_token(account.encrypted_access_token)
        metadata = account.metadata_json or {}
        import json
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        page_id = metadata.get("page_id")
        
        # Determine if content is UserContent or GeneratedContent
        text = getattr(content, "body", "") or getattr(content, "content", "")
        if not text:
            return {"ok": False, "error": "No text content"}
            
        file_url = getattr(content, "file_url", None)
        
        from scripts.platforms.facebook import post_to_page, post_photo_to_page
        
        if file_url:
            return post_photo_to_page(image_url=file_url, caption=text, access_token=access_token, page_id=page_id)
        else:
            return post_to_page(text=text, access_token=access_token, page_id=page_id)
