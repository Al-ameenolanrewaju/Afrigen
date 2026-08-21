from typing import Dict, Any
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token

class XAdapter(BaseProviderAdapter):
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['consumer_key', 'consumer_secret', 'access_token', 'access_token_secret']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        consumer_key = kwargs.get("consumer_key")
        consumer_secret = kwargs.get("consumer_secret")
        access_token = kwargs.get("access_token")
        access_token_secret = kwargs.get("access_token_secret")
        if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
            return {"ok": False, "error": "Missing one or more required X API credentials"}
        return {
            "ok": True,
            "token": access_token,
            "metadata": {
                "consumer_key": consumer_key,
                "consumer_secret": consumer_secret,
                "access_token_secret": access_token_secret,
            },
            "account_name": "X User"
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
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="x").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        access_token = decrypt_token(account.encrypted_access_token)
        metadata = account.metadata_json or {}
        import json
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
            
        api_key = metadata.get("consumer_key")
        api_secret = metadata.get("consumer_secret")
        access_secret = metadata.get("access_token_secret")
        
        # Determine if content is UserContent or GeneratedContent
        text = getattr(content, "body", "") or getattr(content, "content", "")
        if not text:
            return {"ok": False, "error": "No text content"}
            
        from scripts.platforms.twitter import post_thread
        
        # Free-tier X API doesn't allow media upload, so we just post text
        return post_thread(
            tweets=[text],
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            access_secret=access_secret
        )
