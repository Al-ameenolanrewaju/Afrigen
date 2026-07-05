import enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

class ContentCategory(enum.Enum):
    BLOG_POST = "BLOG_POST"
    AI_TIP = "AI_TIP"
    PRODUCT_FEATURE = "PRODUCT_FEATURE"
    FOUNDER_THOUGHT = "FOUNDER_THOUGHT"
    COMMUNITY_DISCUSSION = "COMMUNITY_DISCUSSION"
    USER_SHOWCASE = "USER_SHOWCASE"
    AI_NEWS = "AI_NEWS"
    CREATOR_STORY = "CREATOR_STORY"
    BEHIND_THE_SCENES = "BEHIND_THE_SCENES"
    PRODUCT_UPDATE = "PRODUCT_UPDATE"
    EDUCATIONAL_CONTENT = "EDUCATIONAL_CONTENT"
    CASE_STUDY = "CASE_STUDY"

@dataclass
class ContentBrief:
    topic: str
    audience: str
    goal: str
    key_message: str
    key_insight: str
    call_to_action: str
    suggested_tone: str
    supporting_facts: List[str]
    category: ContentCategory
    source_blog: Optional[Dict[str, Any]] = None  # {slug, title, description, body}

@dataclass
class GeneratedContent:
    platform: str
    content: str
    extra_fields: Dict[str, Any]  # Used for things like title, tags, canonicalUrl, image_url, etc.
