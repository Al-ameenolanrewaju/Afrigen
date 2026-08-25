"""
Post to LinkedIn via the LinkedIn API v2.

⚠️  IMPORTANT: LinkedIn access tokens expire every 60 days.
    You must manually regenerate the token before it expires.
    Go to: https://www.linkedin.com/developers/apps
    Use the "Token Generator" tool under your app to get a fresh token.
    Update the LINKEDIN_ACCESS_TOKEN GitHub secret afterward.

Secrets required:
  LINKEDIN_ACCESS_TOKEN  — OAuth 2.0 access token with w_member_social scope
  LINKEDIN_PERSON_ID     — Your LinkedIn person URN (e.g., "urn:li:person:XXXXXX")

Get them at: https://www.linkedin.com/developers/apps
See: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
"""

import os
import requests
from urllib.parse import quote


LINKEDIN_API = "https://api.linkedin.com/v2"
LINKEDIN_REST_API = "https://api.linkedin.com/rest"
LINKEDIN_VERSION = os.environ.get("LINKEDIN_VERSION", "202608")


def _log_response(label: str, resp) -> None:
    """Log the raw HTTP response so non-JSON / empty bodies are debuggable."""
    raw = resp.text or ""
    print(f"[linkedin] {label}: status={resp.status_code}")
    print(f"[linkedin] {label}: headers={dict(resp.headers)}")
    # Truncate to keep logs readable; LinkedIn errors are short, success is empty.
    print(f"[linkedin] {label}: raw body={raw[:1000]!r}")


def _safe_json(resp) -> dict:
    """Parse a JSON body without throwing on empty / non-JSON responses.

    A successful LinkedIn create returns 201 with an EMPTY body (the post URN
    is in the `x-restli-id` header), so resp.json() would raise
    'Expecting value: line 1 column 1 (char 0)'. Return {} in that case.
    """
    if not (resp.text or "").strip():
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


def _upload_image(image_url: str, access_token: str, person_urn: str, headers: dict) -> str:
    """Download an image and upload it as a LinkedIn feed asset."""
    image_response = requests.get(image_url, timeout=30)
    image_response.raise_for_status()
    content_type = image_response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]
    if not content_type.startswith("image/"):
        raise ValueError("The selected media URL is not an image.")

    register_body = {"initializeUploadRequest": {"owner": person_urn}}
    register_headers = {
        **headers,
        "Linkedin-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    register_response = requests.post(
        f"{LINKEDIN_REST_API}/images?action=initializeUpload",
        headers=register_headers,
        json=register_body,
        timeout=15,
    )
    _log_response("initializeUpload", register_response)
    if register_response.status_code not in (200, 201):
        raise RuntimeError(
            f"LinkedIn image registration failed ({register_response.status_code}): "
            f"{register_response.text}"
        )

    register_data = register_response.json()
    value = register_data.get("value", {})
    upload_url = value.get("uploadUrl")
    image_urn = value.get("image")
    if not upload_url or not image_urn:
        raise RuntimeError("LinkedIn did not return an image upload URL and image URN.")

    upload_response = requests.put(
        upload_url,
        headers={"Content-Type": content_type},
        data=image_response.content,
        timeout=30,
    )
    if upload_response.status_code not in (200, 201, 202):
        raise RuntimeError(
            f"LinkedIn image upload failed ({upload_response.status_code}): "
            f"{upload_response.text}"
        )
    return image_urn


def _upload_video(video_url: str, person_urn: str, headers: dict) -> str:
    """Download and upload a video through LinkedIn's current Videos API."""
    video_response = requests.get(video_url, timeout=120)
    video_response.raise_for_status()
    video_data = video_response.content
    if not video_data:
        raise ValueError("The selected video URL returned an empty file.")

    initialize_response = requests.post(
        f"{LINKEDIN_REST_API}/videos?action=initializeUpload",
        headers=headers,
        json={"initializeUploadRequest": {
            "owner": person_urn,
            "fileSizeBytes": len(video_data),
            "uploadCaptions": False,
            "uploadThumbnail": False,
        }},
        timeout=30,
    )
    _log_response("initializeVideoUpload", initialize_response)
    if initialize_response.status_code not in (200, 201):
        raise RuntimeError(
            f"LinkedIn video registration failed ({initialize_response.status_code}): "
            f"{initialize_response.text}"
        )

    value = initialize_response.json().get("value", {})
    video_urn = value.get("video")
    upload_token = value.get("uploadToken", "")
    instructions = value.get("uploadInstructions", [])
    if not video_urn or not instructions:
        raise RuntimeError("LinkedIn did not return video upload instructions.")

    uploaded_part_ids = []
    for instruction in instructions:
        first_byte = int(instruction["firstByte"])
        last_byte = int(instruction["lastByte"])
        upload_url = instruction["uploadUrl"]
        video_part = video_data[first_byte:last_byte + 1]
        upload_response = requests.put(
            upload_url,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(video_part)),
                "Content-Range": f"bytes {first_byte}-{last_byte}/{len(video_data)}",
            },
            data=video_part,
            timeout=120,
        )
        if upload_response.status_code not in (200, 201, 202):
            raise RuntimeError(
                f"LinkedIn video upload failed ({upload_response.status_code}): "
                f"{upload_response.text}"
            )
        etag = upload_response.headers.get("ETag") or upload_response.headers.get("etag")
        if not etag:
            raise RuntimeError("LinkedIn did not return an ETag for the uploaded video part.")
        uploaded_part_ids.append(etag.strip('"'))

    finalize_response = requests.post(
        f"{LINKEDIN_REST_API}/videos?action=finalizeUpload",
        headers=headers,
        json={"finalizeUploadRequest": {
            "video": video_urn,
            "uploadToken": upload_token,
            "uploadedPartIds": uploaded_part_ids,
        }},
        timeout=30,
    )
    _log_response("finalizeVideoUpload", finalize_response)
    if finalize_response.status_code not in (200, 201):
        raise RuntimeError(
            f"LinkedIn video finalization failed ({finalize_response.status_code}): "
            f"{finalize_response.text}"
        )

    video_status_url = f"{LINKEDIN_REST_API}/videos/{quote(video_urn, safe='')}"
    for attempt in range(12):
        status_response = requests.get(video_status_url, headers=headers, timeout=15)
        if status_response.status_code == 200:
            status = status_response.json().get("status")
            if status == "AVAILABLE":
                return video_urn
            if status == "PROCESSING_FAILED":
                reason = status_response.json().get("processingFailureReason", "unknown reason")
                raise RuntimeError(f"LinkedIn rejected the video during processing: {reason}")
        if attempt < 11:
            import time
            time.sleep(5)

    raise RuntimeError("LinkedIn video is still processing; please try publishing again shortly.")

def post_article(text: str, access_token: str = None, person_id: str = None,
                 media_url: str = None, media_type: str = "video") -> dict:
    """Post text, optionally attaching a generated image to LinkedIn.

    Uses the /posts endpoint (new LinkedIn Posts API) which supports text-only
    posts. Falls back to /ugcPosts if needed.

    Args:
        text: The post body (max ~3000 chars for LinkedIn).
        access_token: Optional API token. Falls back to LINKEDIN_ACCESS_TOKEN.
        person_id: Optional person URN. Falls back to LINKEDIN_PERSON_ID.

    Returns:
        {ok: bool, post_id: str|None, post_url: str|None, error: str|None}
    """
    access_token = access_token or os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    person_id = person_id or os.environ.get("LINKEDIN_PERSON_ID", "")

    if not access_token or not person_id:
        return {
            "ok": False,
            "error": "Missing LINKEDIN_ACCESS_TOKEN or LINKEDIN_PERSON_ID",
            "post_id": None,
            "post_url": None,
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Linkedin-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }

    person_urn = f"urn:li:person:{person_id.replace('urn:li:person:', '')}"
    media_asset = None
    if media_url and media_type == "image":
        try:
            media_asset = _upload_image(media_url, access_token, person_urn, headers)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"LinkedIn image upload failed: {exc}",
                "post_id": None,
                "post_url": None,
            }
    elif media_url and media_type == "video":
        try:
            media_asset = _upload_video(media_url, person_urn, headers)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"LinkedIn video upload failed: {exc}",
                "post_id": None,
                "post_url": None,
            }

    # Try the newer /posts endpoint first
    body = {
        "author": person_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if media_asset:
        body["content"] = {"media": {"id": media_asset}}

    try:
        resp = requests.post(
            f"{LINKEDIN_REST_API}/posts",
            headers=headers,
            json=body,
            timeout=15,
        )

        _log_response("posts", resp)

        if resp.status_code in (200, 201):
            data = _safe_json(resp)
            # Extract the post URN to build a URL. On 201 the body is empty and
            # the URN comes back in the `x-restli-id` header, not the JSON.
            post_urn = resp.headers.get("x-restli-id") or data.get("id", "")
            post_id = post_urn
            # LinkedIn post URLs are typically:
            # https://www.linkedin.com/feed/update/{urn}
            post_url = f"https://www.linkedin.com/feed/update/{post_urn}"
            print(f"[linkedin] posted successfully (id={post_id})")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        # Fallback: some apps use the older UGC Posts API
        if resp.status_code in (401, 403, 404):
            return _post_ugc(text, access_token, person_id, headers, media_asset, media_type)

        error_body = resp.text
        return {
            "ok": False,
            "error": f"LinkedIn API error ({resp.status_code}): {error_body}",
            "post_id": None,
            "post_url": None,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"LinkedIn exception: {e}",
            "post_id": None,
            "post_url": None,
        }


def _post_ugc(text: str, access_token: str, person_id: str, headers: dict,
              media_asset: str = None, media_type: str = "image") -> dict:
    """Fallback: post via the older /ugcPosts endpoint."""
    share_content = {
        "shareCommentary": {"text": text},
        "shareMediaCategory": media_type.upper() if media_asset else "NONE",
    }
    if media_asset:
        share_content["media"] = [{
            "status": "READY",
            "media": media_asset,
            "title": {"text": "Created with Afrigen"},
        }]

    body = {
        "author": person_id,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": share_content
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    try:
        resp = requests.post(
            f"{LINKEDIN_API}/ugcPosts",
            headers=headers,
            json=body,
            timeout=15,
        )

        _log_response("ugcPosts", resp)

        if resp.status_code in (200, 201):
            data = _safe_json(resp)
            post_id = resp.headers.get("x-restli-id") or data.get("id", "")
            post_url = f"https://www.linkedin.com/feed/update/{post_id}"
            print(f"[linkedin] posted via UGC (id={post_id})")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        return {
            "ok": False,
            "error": f"LinkedIn UGC API error ({resp.status_code}): {resp.text}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"LinkedIn UGC exception: {e}",
            "post_id": None,
            "post_url": None,
        }
