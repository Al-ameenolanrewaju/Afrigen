import requests
import json
import jwt
from datetime import datetime, timezone
from typing import Dict, Any

def get_ghost_jwt(api_key: str) -> str:
    """Generate a JWT token for Ghost Admin API authentication."""
    id_hex, secret_hex = api_key.split(':')
    
    iat = int(datetime.now(timezone.utc).timestamp())
    header = {
        'alg': 'HS256',
        'typ': 'JWT',
        'kid': id_hex
    }
    payload = {
        'iat': iat,
        'exp': iat + 5 * 60, # 5 minutes expiry
        'aud': '/admin/'
    }
    
    return jwt.encode(payload, bytes.fromhex(secret_hex), algorithm='HS256', headers=header)

def publish_to_ghost(
    title: str, 
    content: str, 
    site_url: str, 
    admin_api_key: str
) -> Dict[str, Any]:
    """
    Publish a post to Ghost using the Admin API.
    """
    try:
        token = get_ghost_jwt(admin_api_key)
    except Exception as e:
        return {"ok": False, "error": f"Invalid Admin API Key format: {e}"}
        
    endpoint = f"{site_url.rstrip('/')}/ghost/api/admin/posts/?source=html"
    
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "posts": [{
            "title": title,
            "html": content,
            "status": "published"
        }]
    }
    
    try:
        resp = requests.post(endpoint, headers=headers, json=data, timeout=30)
            
        if resp.status_code in (200, 201):
            result = resp.json()
            post = result.get("posts", [{}])[0]
            return {
                "ok": True,
                "post_id": post.get("id"),
                "url": post.get("url")
            }
        else:
            return {
                "ok": False,
                "error": f"HTTP {resp.status_code}: {resp.text}"
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}
