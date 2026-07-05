from ..models import ContentBrief

TELEGRAM_SYSTEM = """You are an AI prompt engineer for Afrigen (afrigen.com.ng), an AI video and image generation platform. 
You create PRACTICAL, copy-paste-ready AI video prompts that Nigerian and African creators can use immediately. 
Your prompts are detailed, specific to African contexts, and produce great results on AI video models.
"""

def get_telegram_user_prompt(brief: ContentBrief, blog_url: str = "") -> str:
    from constants import SITE_URL, TWITTER_URL, LINKEDIN_URL, FACEBOOK_URL, INSTAGRAM_URL, MEDIUM_URL
    url_instruction = f"📖 Full guide: {blog_url}" if blog_url else f"📖 Create now: {SITE_URL}"
    
    return f"""Use this Content Brief to create ONE practical AI video/image prompt that a Nigerian creator can copy, paste, and use right now.

Topic: {brief.topic}
Key Message: {brief.key_message}
Key Insight: {brief.key_insight}

The prompt must be:
- Self-contained — someone who hasn't read the blog should be able to use it.
- Specific to an African/Nigerian context (real locations, scenarios, aesthetics).
- Detailed enough to produce good AI video (include subject, setting, lighting, camera direction, mood).
- Under 200 words.
- Practical and useful — not abstract or philosophical.

Now format your response EXACTLY like this template:

🎬 AI Prompt of the Day

[The practical prompt here — one paragraph, ready to copy-paste]

Try it on Afrigen → {SITE_URL}

{url_instruction}

Follow for daily prompts 👇
🐦 Twitter: {TWITTER_URL}
💼 LinkedIn: {LINKEDIN_URL}
📘 Facebook: {FACEBOOK_URL}
📸 Instagram: {INSTAGRAM_URL}
✍️ Medium: {MEDIUM_URL}

Return ONLY the formatted post, nothing else."""
