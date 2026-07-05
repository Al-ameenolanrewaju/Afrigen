import re
from typing import Tuple, Optional
from .planner import ContentPlanner

def validate_facebook(content: str, blog_url: str = "") -> Tuple[bool, str]:
    # 1. Under platform limit
    if len(content) > 3000:
        return False, "Content exceeds 3000 characters."
    
    # 2. Contains exactly one link (if blog_url is provided)
    if blog_url:
        link_count = content.count("http")
        if link_count != 1:
            return False, f"Expected exactly 1 link, found {link_count}."
            
    # 3. No duplicate hooks
    planner = ContentPlanner()
    first_sentence = content.split('\n')[0].strip()
    if planner.is_topic_recent(first_sentence, limit=15):
        return False, "Opening hook is too similar to a recently used one."
        
    return True, ""

def validate_linkedin(content: str, blog_url: str = "") -> Tuple[bool, str]:
    # Professional tone: check emoji count using actual emoji unicode ranges
    emoji_count = len(re.findall(r'[\U00010000-\U0010ffff]', content))
    if emoji_count > 10:
        return False, f"Too many emojis ({emoji_count}) for a professional tone."
        
    # Check for CTA / links
    if blog_url:
        if blog_url not in content:
            return False, "Missing the required call to action / blog link."
        link_count = content.count("http")
        if link_count != 1:
            return False, f"Expected exactly 1 link, found {link_count}."
        
    return True, ""

def validate_telegram(content: str) -> Tuple[bool, str]:
    word_count = len(content.split())
    if word_count > 250:
        return False, f"Not concise enough. Expected < 250 words, got {word_count}."
    return True, ""

def validate_newsletter(content: str) -> Tuple[bool, str]:
    # Expecting HTML structure and 'SUBJECT:' which is already stripped by the writer
    # Actually, the writer splits the subject. So we validate the final body.
    if "<p>" not in content and not re.search(r'<h[1-6]>', content) and "<ul>" not in content:
        return False, "Missing expected HTML structure tags."
    return True, ""

def validate_devto(content: str) -> Tuple[bool, str]:
    if not content.strip():
        return False, "Dev.to content cannot be empty."
    
    import json
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            return False, "Dev.to response must be a JSON object."
        if "title" not in data or "body" not in data:
            return False, "Dev.to JSON must contain 'title' and 'body' fields."
    except json.JSONDecodeError:
        return False, "Dev.to response is not valid JSON."
        
    return True, ""
