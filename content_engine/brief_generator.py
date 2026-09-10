import json
import re
from .models import ContentBrief, ContentCategory
from .utils import generate_with_llm, strip_fences
from .prompts.master_prompt import MASTER_BRIEF_SYSTEM, get_master_brief_user_prompt
from typing import Optional, Dict, Any

def generate_content_brief(category: ContentCategory, source_context: str, source_blog: Optional[Dict[str, Any]] = None) -> ContentBrief:
    """
    Generates a ContentBrief based on the provided category and source material.
    """
    user_prompt = get_master_brief_user_prompt(category.value, source_context)
    
    try:
        response = generate_with_llm(
            system=MASTER_BRIEF_SYSTEM,
            user=user_prompt,
            max_tokens=1500,
            json_mode=True
        )
        response = strip_fences(response)
        data = json.loads(response)
        required_fields = ("topic", "key_message", "key_insight")
        if not all(str(data.get(field, "")).strip() for field in required_fields):
            raise ValueError("AI returned an incomplete content brief")
    except Exception as e:
        from .utils import get_logger
        logger = get_logger("BriefGenerator")
        logger.error(f"Error generating brief: {e}")
        
        fallback_topic = "Afrigen empowers African creators"
        fallback_message = "AI gives African creators practical tools to turn ideas into professional content."
        fallback_insight = "Creators can spend less time on production and more time developing useful ideas."
        if source_blog and "title" in source_blog:
            fallback_topic = source_blog["title"]
            fallback_message = source_blog.get("description") or fallback_message
            body = source_blog.get("body", "")
            if body:
                fallback_insight = re.sub(r"<[^>]+>", " ", body).strip()[:300]
            
        data = {
            "topic": fallback_topic,
            "audience": "African Creators",
            "goal": "Awareness",
            "key_message": fallback_message,
            "key_insight": fallback_insight,
            "call_to_action": "Visit Afrigen",
            "suggested_tone": "Professional",
            "supporting_facts": []
        }

    from .utils import get_logger
    logger = get_logger("BriefGenerator")
    logger.info(f"Brief Generated for topic: '{data.get('topic', '')[:50]}...'")

    return ContentBrief(
        topic=data.get("topic", ""),
        audience=data.get("audience", ""),
        goal=data.get("goal", ""),
        key_message=data.get("key_message", ""),
        key_insight=data.get("key_insight", ""),
        call_to_action=data.get("call_to_action", ""),
        suggested_tone=data.get("suggested_tone", ""),
        supporting_facts=data.get("supporting_facts", []),
        category=category,
        source_blog=source_blog
    )
