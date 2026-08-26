import os
import json
import requests
from flask import request, session
from typing import Dict, Any
from urllib.parse import urlencode
from ..base import BaseProviderAdapter
from models import ConnectedAccount
from utils.encryption import decrypt_token
from utils.encryption import encrypt_token
from models import db
from datetime import datetime, timezone, timedelta

class YoutubeAdapter(BaseProviderAdapter):
    def _get_redirect_uri(self):
        return request.url_root.rstrip("/") + "/connected-accounts/youtube/callback"

    @classmethod
    def get_auth_methods(cls) -> list[str]:
        return ['oauth']

    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        redirect_uri = self._get_redirect_uri()
        if not client_id:
            return {"ok": False, "error": "Google OAuth is not configured."}

        state = os.urandom(32).hex()
        session["youtube_oauth_state"] = state
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return {
            "ok": True,
            "type": "redirect",
            "url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params),
        }
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        if request_args.get("error"):
            return {"ok": False, "error": request_args.get("error_description", request_args["error"])}
        if request_args.get("state") != session.pop("youtube_oauth_state", None):
            return {"ok": False, "error": "Invalid OAuth state."}

        code = request_args.get("code")
        if not code:
            return {"ok": False, "error": "No authorization code provided."}

        redirect_uri = self._get_redirect_uri()
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
                    "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {"ok": False, "error": f"Google token exchange failed: {response.text}"}
            token_data = response.json()
            channel_response = requests.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {token_data.get('access_token')}"},
                timeout=15,
            )
            if channel_response.status_code != 200:
                return {"ok": False, "error": f"YouTube channel lookup failed ({channel_response.status_code}): {channel_response.text[:300]}"}
            channels = channel_response.json().get("items", [])
            if not channels:
                return {"ok": False, "error": "This Google account does not have a YouTube channel. Create a YouTube channel and reconnect."}
            channel = channels[0]
            channel_id = channel.get("id")
            channel_title = channel.get("snippet", {}).get("title")
            return {
                "ok": True,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in"),
                "account_identifier": channel_id,
                "account_name": channel_title or "YouTube channel",
            }
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

    def disconnect(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def refresh(self, user_id: int) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="youtube").first()
        if not account or not account.encrypted_refresh_token:
            return {"ok": False, "error": "Google refresh token is unavailable. Reconnect YouTube."}
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
                    "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
                    "grant_type": "refresh_token",
                    "refresh_token": decrypt_token(account.encrypted_refresh_token),
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {"ok": False, "error": f"Google token refresh failed: {response.text[:500]}"}
            token_data = response.json()
            if not token_data.get("access_token"):
                return {"ok": False, "error": "Google token refresh returned no access token."}
            account.encrypted_access_token = encrypt_token(token_data["access_token"])
            if token_data.get("expires_in"):
                account.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
            db.session.commit()
            return {"ok": True, "access_token": token_data["access_token"]}
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

    def test_connection(self, user_id: int) -> Dict[str, Any]:
        return {"ok": True}

    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        account = ConnectedAccount.query.filter_by(user_id=user_id, provider="youtube").first()
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
            return {"ok": False, "error": "YouTube requires a video file URL."}

        try:
            video = requests.get(video_url, timeout=60)
            video.raise_for_status()
            title = getattr(content, "title", None) or "Afrigen video"
            description = getattr(content, "description", None) or "Created with Afrigen"
            metadata = {
                "snippet": {"title": title[:100], "description": description[:5000]},
                "status": {"privacyStatus": (preferences or {}).get("privacy_status", "private")},
            }
            metadata_response = requests.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"part": "snippet,status", "uploadType": "resumable"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Upload-Content-Type": video.headers.get("Content-Type", "video/mp4"),
                    "X-Upload-Content-Length": str(len(video.content)),
                    "Content-Type": "application/json",
                },
                data=json.dumps(metadata),
                timeout=120,
            )
            if metadata_response.status_code not in (200, 201):
                return {"ok": False, "error": f"YouTube upload initialization failed ({metadata_response.status_code}): {metadata_response.text[:500]}"}

            upload_url = metadata_response.headers.get("Location")
            if not upload_url:
                return {"ok": False, "error": "YouTube did not return an upload URL."}
            response = requests.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": video.headers.get("Content-Type", "video/mp4"),
                },
                data=video.content,
                timeout=300,
            )
            if response.status_code not in (200, 201):
                return {"ok": False, "error": f"YouTube upload failed ({response.status_code}): {response.text[:500]}"}
            data = response.json()
            video_id = data.get("id")
            return {"ok": True, "post_id": video_id, "url": f"https://youtu.be/{video_id}"}
        except requests.RequestException as exc:
            return {"ok": False, "error": f"YouTube upload failed: {exc}"}
