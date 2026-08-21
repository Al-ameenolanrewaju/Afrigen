from ..models import GeneratedContent

def publish_linkedin_post(generated: GeneratedContent, access_token: str = None, person_id: str = None) -> dict:
    import os
    if os.environ.get("DRY_RUN") == "true":
        return {"ok": True, "mock": True, "detail": "Dry run linkedin post"}
        
    import sys
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        
    from platforms.linkedin import post_article
    return post_article(generated.content, access_token=access_token, person_id=person_id)
