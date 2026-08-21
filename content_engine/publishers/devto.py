from ..models import GeneratedContent

def publish_devto_article(generated: GeneratedContent, api_key: str = None) -> dict:
    import os
    if os.environ.get("DRY_RUN") == "true":
        return {"ok": True, "mock": True, "detail": "Dry run devto article"}
        
    import sys
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        
    from platforms.devto import publish_article
    return publish_article(
        title=generated.extra_fields.get("title", ""),
        content=generated.content,
        tags=generated.extra_fields.get("tags", []),
        canonical_url=generated.extra_fields.get("canonicalUrl", ""),
        description=generated.extra_fields.get("description", ""),
        api_key=api_key
    )
