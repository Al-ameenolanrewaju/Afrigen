import json
import re
from ..models import ContentBrief, GeneratedContent
from ..utils import generate_with_validation
from ..prompts.devto_prompt import DEVTO_SYSTEM, get_devto_user_prompt

def write_devto_article(brief: ContentBrief) -> GeneratedContent:
    user_prompt = get_devto_user_prompt(brief)
    
    from ..validators import validate_devto
    
    raw = generate_with_validation(
        system=DEVTO_SYSTEM,
        user=user_prompt,
        validator_fn=validate_devto,
        validator_args=(),
        max_tokens=2500,
        max_attempts=2,
        json_mode=True
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Should not happen as validation ensures valid JSON, but fallback safely just in case
        from ..utils import get_logger
        logger = get_logger("DevToWriter")
        logger.error("Unexpected JSON failure in devto writer despite validation.")
        data = {
            "title": brief.topic,
            "subtitle": brief.key_insight,
            "body": brief.key_message,
            "tags": ["ai", "africa", "contentcreation"],
        }
        
    title = data.get("title", brief.topic)
    tags = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in data.get("tags", ["ai", "africa"])]
    tags = [t for t in tags if t][:4]
    
    canonical_url = ""
    if brief.source_blog:
        from constants import SITE_URL
        canonical_url = f"{SITE_URL}/blog/{brief.source_blog['slug']}"
    
    from ..utils import get_logger
    logger = get_logger("DevToWriter")
    logger.info("DevTo article generated successfully.")
    
    return GeneratedContent(
        platform="devto",
        content=data.get("body", ""),
        extra_fields={
            "title": title,
            "tags": tags or ["ai", "africa"],
            "description": data.get("subtitle", ""),
            "canonicalUrl": canonical_url
        }
    )
