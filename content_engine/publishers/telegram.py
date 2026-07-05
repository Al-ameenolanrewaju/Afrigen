from ..models import GeneratedContent

def publish_telegram_post(generated: GeneratedContent) -> dict:
    import os
    if os.environ.get("DRY_RUN") == "true":
        return {"ok": True, "mock": True, "detail": "Dry run telegram post"}
        
    import sys
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        
    from platforms.telegram import post_to_channel
    return post_to_channel(generated.content)
