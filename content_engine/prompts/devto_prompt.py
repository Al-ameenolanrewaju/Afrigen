from ..models import ContentBrief

DEVTO_SYSTEM = """You are a content editor for Afrigen (afrigen.com.ng), an AI platform for African creators that turns text prompts into videos and images. You adapt content for Dev.to publication, keeping the original value while formatting cleanly for a developer/creator audience.
Your writing should be technical, developer-friendly, and long-form.
"""

def get_devto_user_prompt(brief: ContentBrief) -> str:
    from constants import SITE_URL, TELEGRAM_URL, LINKEDIN_URL
    return f"""Write a Dev.to article based on this Content Brief.

Topic: {brief.topic}
Audience: {brief.audience} (Developers and Technical Creators)
Goal: {brief.goal}
Key Message: {brief.key_message}
Key Insight: {brief.key_insight}
Call To Action: {brief.call_to_action}

RULES:
- Create a compelling title.
- Create a one-line subtitle.
- Write the body as clean Markdown (## headings, paragraphs, bullet points, maybe some technical pseudocode or workflow examples if relevant).
- Keep the core insights and practical advice intact.
- Nigerian/African creator audience — keep the original tone.
- End with this author bio section EXACTLY:

---
*About Afrigen: Africa Creates, AI Generates. Afrigen helps Nigerian and African creators turn text prompts into stunning AI videos and images — no camera crew needed, just your idea.*

*🌐 Website: {SITE_URL}*
*📢 Telegram (daily AI prompts): {TELEGRAM_URL}*
*💼 LinkedIn: {LINKEDIN_URL}*

Return your response as a JSON object with these fields:
- title: the article title (string)
- subtitle: a one-line subtitle (string, may be empty)
- body: the markdown body (string)
- tags: array of 3-4 lowercase single-word tags (e.g., ["ai", "africa", "contentcreation"])

Return ONLY valid JSON, no markdown fences, no commentary."""
