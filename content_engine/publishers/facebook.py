from ..models import GeneratedContent

def publish_facebook_post(generated: GeneratedContent, access_token: str = None, page_id: str = None) -> dict:
    import os
    if os.environ.get("DRY_RUN") == "true":
        return {"ok": True, "mock": True, "detail": "Dry run facebook post"}
        
    import sys
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        
    from platforms.facebook import post_to_page, post_photo_to_page
    
    # If there's an image, post_photo_to_page, else post_to_page
    image_url = generated.extra_fields.get("image_url")
    if image_url:
        return post_photo_to_page(image_url, generated.content) # We'll skip adding kwargs to post_photo for now
    else:
        return post_to_page(generated.content, access_token=access_token, page_id=page_id)
