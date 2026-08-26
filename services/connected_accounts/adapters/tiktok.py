import os
import math
import tempfile
import base64
import hashlib
import secrets
import requests
from datetime import datetime, timezone, timedelta
from flask import request, session
from typing import Dict, Any
from urllib.parse import urlencode
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token
from utils.encryption import encrypt_token
from models import db

class TiktokAdapter(BaseProviderAdapter):
    def _get_redirect_uri(self):
        configured_uri = os.environ.get("TIKTOK_REDIRECT_URI")
        if configured_uri:
            return configured_uri.strip()
        base_url = os.environ.get("APP_BASE_URL")
        if base_url:
            return base_url.strip().rstrip("/") + "/connected-accounts/tiktok/callback"
        return request.url_root.rstrip("/") + "/connected-accounts/tiktok/callback"

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        client_key = os.environ.get("TIKTOK_CLIENT_KEY")
        client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
        missing = [name for name, value in {
            "TIKTOK_CLIENT_KEY": client_key,
            "TIKTOK_CLIENT_SECRET": client_secret,
        }.items() if not value]
        if missing:
            return {"ok": False, "error": f"TikTok OAuth is not configured. Missing: {', '.join(missing)}. Add them to the deployment environment and restart the app."}

        state = os.urandom(32).hex()
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        session["tiktok_oauth_state"] = state
        session["tiktok_oauth_code_verifier"] = code_verifier
        scope = os.environ.get("TIKTOK_SCOPE", "user.info.basic,video.publish")
        params = {
            "client_key": client_key,
            "response_type": "code",
            "scope": scope,
            "redirect_uri": self._get_redirect_uri(),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return {
            "ok": True,
            "type": "redirect",
            "url": "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params),
        }
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        if request_args.get("error"):
            return {"ok": False, "error": request_args.get("error_description", request_args["error"])}
        if request_args.get("state") != session.pop("tiktok_oauth_state", None):
            return {"ok": False, "error": "Invalid OAuth state."}
        code_verifier = session.pop("tiktok_oauth_code_verifier", None)
        if not code_verifier:
            return {"ok": False, "error": "TikTok OAuth verifier is missing. Please try connecting again."}

        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No authorization code provided."}

        try:
            response = requests.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                data={
                    "client_key": os.environ.get("TIKTOK_CLIENT_KEY"),
                    "client_secret": os.environ.get("TIKTOK_CLIENT_SECRET"),
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._get_redirect_uri(),
                    "code_verifier": code_verifier,
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {"ok": False, "error": f"TikTok token exchange failed: {response.text}"}

            token_data = response.json()
            access_token = token_data.get("access_token")
            open_id = token_data.get("open_id")
            account_name = "TikTok User"
            if access_token:
                profile = requests.get(
                    "https://open.tiktokapis.com/v2/user/info/",
                    params={"fields": "display_name"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15,
                )
                if profile.status_code == 200:
                    account_name = profile.json().get("data", {}).get("user", {}).get("display_name") or account_name

            return {
                "ok": True,
                "access_token": access_token,
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in"),
                "account_identifier": open_id,
                "account_name": account_name,
            }
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="tiktok").first()
        if not account or not account.encrypted_refresh_token:
            return {"ok": False, "error": "TikTok refresh token is unavailable. Reconnect TikTok."}
        try:
            response = requests.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                data={
                    "client_key": os.environ.get("TIKTOK_CLIENT_KEY"),
                    "client_secret": os.environ.get("TIKTOK_CLIENT_SECRET"),
                    "grant_type": "refresh_token",
                    "refresh_token": decrypt_token(account.encrypted_refresh_token),
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {"ok": False, "error": f"TikTok token refresh failed: {response.text[:500]}"}
            token_data = response.json()
            if not token_data.get("access_token"):
                return {"ok": False, "error": "TikTok token refresh returned no access token."}
            account.encrypted_access_token = encrypt_token(token_data["access_token"])
            if token_data.get("refresh_token"):
                account.encrypted_refresh_token = encrypt_token(token_data["refresh_token"])
            if token_data.get("expires_in"):
                account.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
            db.session.commit()
            return {"ok": True, "access_token": token_data["access_token"]}
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="tiktok").first()
        if not account:
            return {"ok": False, "error": "Not connected"}
            
        access_token = decrypt_token(account.encrypted_access_token)
        expiry = account.token_expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if account.encrypted_refresh_token and (
            not expiry or expiry <= datetime.now(timezone.utc)
        ):
            refreshed = self.refresh(user_id)
            if not refreshed.get("ok"):
                return refreshed
            access_token = refreshed["access_token"]
        video_url = getattr(content, "file_url", None) or getattr(content, "video_url", None)
        if not video_url:
            return {"ok": False, "error": "TikTok requires a public video URL."}

        temp_path = None
        try:
            print(f"TIKTOK publish start user_id={user_id} media_url_host={video_url.split('/')[2] if '://' in video_url else 'invalid'}")
            with requests.get(video_url, stream=True, timeout=120) as video_response:
                print(f"TIKTOK media download status={video_response.status_code}")
                video_response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as video_file:
                    temp_path = video_file.name
                    for chunk in video_response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            video_file.write(chunk)

            video_size = os.path.getsize(temp_path)
            if video_size <= 0:
                return {"ok": False, "error": "TikTok video download was empty."}

            # TikTok requires files under 5 MB to be uploaded whole. Larger
            # videos use sequential chunks no larger than 64 MB.
            chunk_size = video_size if video_size < 5 * 1024 * 1024 else 10 * 1024 * 1024
            total_chunk_count = math.ceil(video_size / chunk_size)
            init_response = requests.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"},
                json={
                    "post_info": {
                        "title": (getattr(content, "title", None) or "Created with Afrigen")[:150],
                        "privacy_level": (preferences or {}).get("privacy_level", "SELF_ONLY"),
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": video_size,
                        "chunk_size": chunk_size,
                        "total_chunk_count": total_chunk_count,
                    },
                },
                timeout=30,
            )
            print(f"TIKTOK init status={init_response.status_code} response={init_response.text[:500]}")
            if init_response.status_code not in (200, 201):
                return {"ok": False, "error": f"TikTok publish failed ({init_response.status_code}): {init_response.text[:500]}"}
            data = init_response.json().get("data", {})
            upload_url = data.get("upload_url")
            publish_id = data.get("publish_id")
            if not upload_url or not publish_id:
                return {"ok": False, "error": "TikTok did not return an upload URL and publish ID."}

            with open(temp_path, "rb") as video_file:
                for chunk_number in range(total_chunk_count):
                    first_byte = chunk_number * chunk_size
                    chunk = video_file.read(chunk_size)
                    last_byte = first_byte + len(chunk) - 1
                    upload_response = requests.put(
                        upload_url,
                        headers={
                            "Content-Type": "video/mp4",
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {first_byte}-{last_byte}/{video_size}",
                        },
                        data=chunk,
                        timeout=120,
                    )
                    print(
                        f"TIKTOK upload chunk={chunk_number + 1}/{total_chunk_count} "
                        f"status={upload_response.status_code} response={upload_response.text[:500]}"
                    )
                    if upload_response.status_code not in (200, 201, 206):
                        return {"ok": False, "error": f"TikTok video upload failed ({upload_response.status_code}): {upload_response.text[:500]}"}

            return {"ok": True, "post_id": publish_id, "status": "processing"}
        except requests.RequestException as exc:
            print(f"TIKTOK publish request error type={type(exc).__name__} error={exc}")
            return {"ok": False, "error": f"TikTok publish failed: {exc}"}
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
