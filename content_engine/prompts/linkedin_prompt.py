from ..models import ContentBrief

LINKEDIN_SYSTEM = """You are a professional content marketer for Afrigen (afrigen.com.ng), an AI video and image generation platform for African creators.
You write polished, insightful LinkedIn posts that position Afrigen as a thought leader in AI for African content creation.
"""

def get_linkedin_user_prompt(brief: ContentBrief, blog_url: str = "") -> str:
    from constants import SITE_URL, TELEGRAM_URL, LINKEDIN_URL
    cross_link_footer = (
        f"\\n\\nFollow Afrigen:\\n"
        f"🌐 Website: {SITE_URL}\\n"
        f"📢 Telegram (daily AI prompts): {TELEGRAM_URL}\\n"
        f"💼 LinkedIn: {LINKEDIN_URL}"
    )

    url_instruction = f"Include the blog link: {blog_url}" if blog_url else ""
    
    return f"""Write a LinkedIn post based on this Content Brief.

Topic: {brief.topic}
Audience: {brief.audience}
Goal: {brief.goal}
Key Message: {brief.key_message}
Key Insight: {brief.key_insight}
Call To Action: {brief.call_to_action}

RULES:
- Maximum 200 words.
- Professional but warm tone — you're writing for founders, marketers, and creators.
- Open with a strong insight or question that hooks professionals.
- {url_instruction}

Return ONLY the post text, nothing else. We will append standard cross-platform links automatically."""
