import requests
from typing import Dict, Any

def publish_to_youtube(
    title: str,
    description: str,
    video_path: str,
    access_token: str
) -> Dict[str, Any]:
    """
    Publish a video to YouTube using the YouTube Data API v3.
    """
    url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22" # People & Blogs
        },
        "status": {
            "privacyStatus": "public"
        }
    }
    
    try:
        # 1. Start Resumable Session
        init_resp = requests.post(url, headers=headers, json=metadata, timeout=30)
        if init_resp.status_code != 200:
            return {"ok": False, "error": f"Failed to init upload: {init_resp.text}"}
            
        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            return {"ok": False, "error": "No upload URL provided by YouTube."}
            
        # 2. Upload Video Data
        with open(video_path, "rb") as f:
            upload_resp = requests.put(upload_url, headers={"Authorization": f"Bearer {access_token}"}, data=f)
            
        if upload_resp.status_code in (200, 201):
            result = upload_resp.json()
            video_id = result.get("id")
            return {
                "ok": True,
                "post_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}"
            }
        else:
            return {"ok": False, "error": f"Upload failed: {upload_resp.text}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
