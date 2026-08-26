import os
import requests
from datetime import datetime, timezone, timedelta
from flask import request, session
from typing import Dict, Any
from urllib.parse import urlencode
from ..base import BaseProviderAdapter
from models import ConnectedAccount, db
from utils.encryption import decrypt_token
from utils.encryption import encrypt_token
import json

class PinterestAdapter(BaseProviderAdapter):
    def _get_redirect_uri(self):
        configured_uri = os.environ.get("PINTEREST_REDIRECT_URI")
        if configured_uri:
            return configured_uri.strip()
        base_url = os.environ.get("APP_BASE_URL")
        if base_url:
            return base_url.strip().rstrip("/") + "/connected-accounts/pinterest/callback"
        return request.url_root.rstrip("/") + "/connected-accounts/pinterest/callback"

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        client_id = os.environ.get("PINTEREST_APP_ID")
        client_secret = os.environ.get("PINTEREST_APP_SECRET")
        if not client_id or not client_secret:
            missing = [name for name, value in {
                "PINTEREST_APP_ID": client_id,
                "PINTEREST_APP_SECRET": client_secret,
            }.items() if not value]
            return {"ok": False, "error": f"Pinterest OAuth is not configured. Missing: {', '.join(missing)}."}
        state = os.urandom(32).hex()
        session["pinterest_oauth_state"] = state
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self._get_redirect_uri(),
            "scope": "user_accounts:read,boards:read,pins:write",
            "state": state,
        }
        return {
            "ok": True,
            "type": "redirect",
            "url": "https://www.pinterest.com/oauth/?" + urlencode(params),
        }
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        if request_args.get("error"):
            return {"ok": False, "error": request_args.get("error_description", request_args["error"])}
        if request_args.get("state") != session.pop("pinterest_oauth_state", None):
            return {"ok": False, "error": "Invalid OAuth state."}
        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No authorization code provided."}
        try:
            response = requests.post(
                "https://api.pinterest.com/v5/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._get_redirect_uri(),
                },
                auth=(os.environ.get("PINTEREST_APP_ID"), os.environ.get("PINTEREST_APP_SECRET")),
                timeout=15,
            )
            if response.status_code != 200:
                return {"ok": False, "error": f"Pinterest token exchange failed ({response.status_code}): {response.text[:500]}"}
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return {"ok": False, "error": "Pinterest token exchange returned no access token."}
            user_response = requests.get(
                "https://api.pinterest.com/v5/user_account",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if user_response.status_code != 200:
                return {"ok": False, "error": f"Pinterest account lookup failed ({user_response.status_code}): {user_response.text[:300]}"}
            user_data = user_response.json()
            boards_response = requests.get(
                "https://api.pinterest.com/v5/boards",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"page_size": 1},
                timeout=15,
            )
            board_id = os.environ.get("PINTEREST_BOARD_ID")
            if boards_response.status_code == 200:
                boards = boards_response.json().get("items", [])
                if boards:
                    board_id = boards[0].get("id") or board_id
            if not board_id:
                return {"ok": False, "error": "Pinterest connected, but no board was found. Create a board and reconnect."}
            return {
                "ok": True,
                "access_token": access_token,
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in"),
                "account_identifier": board_id,
                "account_name": user_data.get("username") or "Pinterest User",
            }
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="pinterest").first()
        if not account or not account.encrypted_refresh_token:
            return {"ok": False, "error": "Pinterest refresh token is unavailable. Reconnect Pinterest."}
        try:
            response = requests.post(
                "https://api.pinterest.com/v5/oauth/token",
                data={"grant_type": "refresh_token", "refresh_token": decrypt_token(account.encrypted_refresh_token)},
                auth=(os.environ.get("PINTEREST_APP_ID"), os.environ.get("PINTEREST_APP_SECRET")),
                timeout=15,
            )
            if response.status_code != 200:
                return {"ok": False, "error": f"Pinterest token refresh failed ({response.status_code}): {response.text[:500]}"}
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return {"ok": False, "error": "Pinterest token refresh returned no access token."}
            account.encrypted_access_token = encrypt_token(access_token)
            if token_data.get("refresh_token"):
                account.encrypted_refresh_token = encrypt_token(token_data["refresh_token"])
            if token_data.get("expires_in"):
                account.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
            db.session.commit()
            return {"ok": True, "access_token": access_token}
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

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
