import requests
from typing import Dict, Any

def publish_to_tiktok(
    video_path: str,
    access_token: str,
    creator_id: str
) -> Dict[str, Any]:
    """
    Publish a video to TikTok using the Direct Post API.
    """
    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Needs actual video size/chunking logic according to TikTok API docs
    # Simplified here for structure
    import os
    file_size = os.path.getsize(video_path)
    
    data = {
        "post_info": {
            "title": "Published via Afrigen",
            "privacy_level": "PUBLIC"
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1
        }
    }
    
    try:
        init_resp = requests.post(url, headers=headers, json=data, timeout=30)
        if init_resp.status_code != 200:
            return {"ok": False, "error": f"Failed to init upload: {init_resp.text}"}
            
        upload_url = init_resp.json().get("data", {}).get("upload_url")
        publish_id = init_resp.json().get("data", {}).get("publish_id")
        
        if not upload_url:
            return {"ok": False, "error": "No upload URL from TikTok"}
            
        with open(video_path, "rb") as f:
            headers = {
                "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
                "Content-Type": "video/mp4"
            }
            upload_resp = requests.put(upload_url, headers=headers, data=f)
            
        if upload_resp.status_code in (200, 201):
            return {
                "ok": True,
                "post_id": publish_id,
                "url": f"https://www.tiktok.com/@{creator_id}/video/{publish_id}" # Approximation
            }
        else:
            return {"ok": False, "error": f"Upload failed: {upload_resp.text}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
