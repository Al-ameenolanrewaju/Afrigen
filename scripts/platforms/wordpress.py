import requests
import json
from typing import Dict, Any, Optional

def publish_to_wordpress(
    title: str, 
    content: str, 
    site_url: str, 
    auth_type: str, 
    access_token: Optional[str] = None, 
    username: Optional[str] = None, 
    app_password: Optional[str] = None
) -> Dict[str, Any]:
    """
    Publish a post to WordPress REST API.
    Supports either 'oauth' (Bearer token) or 'app_password' (Basic Auth).
    """
    endpoint = f"{site_url.rstrip('/')}/wp-json/wp/v2/posts"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    auth = None
    if auth_type == "oauth" and access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    elif auth_type == "app_password" and username and app_password:
        auth = (username, app_password)
    else:
        return {"ok": False, "error": "Invalid auth configuration for WordPress"}
        
    data = {
        "title": title,
        "content": content,
        "status": "publish"
    }
    
    try:
        if auth:
            resp = requests.post(endpoint, headers=headers, json=data, auth=auth, timeout=30)
        else:
            resp = requests.post(endpoint, headers=headers, json=data, timeout=30)
            
        if resp.status_code in (200, 201):
            result = resp.json()
            return {
                "ok": True,
                "post_id": result.get("id"),
                "url": result.get("link")
            }
        else:
            return {
                "ok": False,
                "error": f"HTTP {resp.status_code}: {resp.text}"
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}
