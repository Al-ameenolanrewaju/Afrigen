from ..models import ContentBrief

NEWSLETTER_SYSTEM = """You are the editor of Afrigen's weekly email newsletter. Afrigen is an African AI platform for generating videos and images from text prompts (tagline 'Africa Creates, AI Generates'). You write warm, concise, skimmable newsletters for Nigerian and African content creators and small businesses. The newsletter is about Afrigen itself — our features, our guides, and practical tips — NOT a summary of outside tech news."""

def get_newsletter_user_prompt(brief: ContentBrief, features_block: str, posts_block: str, users: int, generations: int, date_str: str) -> str:
    from constants import SITE_URL
    return f"""Today is {date_str}. Write this week's Afrigen newsletter.

Use this Content Brief as the core theme/tip for the newsletter:
Topic: {brief.topic}
Goal: {brief.goal}
Key Insight: {brief.key_insight}
Call To Action: {brief.call_to_action}

WHAT AFRIGEN CAN DO (only ever mention features from this list — never invent any):
{features_block}

OUR PUBLISHED BLOG GUIDES:
{posts_block}

OUR COMMUNITY RIGHT NOW: {users} creators, {generations} generations.

Write the newsletter with these sections, in this order:
1. A short, warm one-line opener.
2. "Feature spotlight" — pick ONE feature from the list and explain in 2-3 sentences how a creator would actually use it.
3. "From the blog" — pick 2 or 3 of the guides above and write one short line for each, linking the title with an <a> tag to its exact URL.
4. "Quick tip" — Use the Content Brief provided above to write one genuinely useful, specific tip for an African creator. One short paragraph.
5. "Afrigen this week" — mention our {users} creators and {generations} generations, and invite readers to create something now with a link to {SITE_URL}/dashboard.

HARD RULES:
- Do NOT mention any feature that is not in the list above.
- Do NOT invent blog links, slugs, statistics, partnerships, or outside news.
- Keep it warm, concrete, and skimmable.
- The FIRST line must be exactly:  SUBJECT: <a punchy subject line under 70 chars>
- After that line, output the email BODY as simple inline HTML using only <h3>, <p>, <strong>, <a> tags (no <html>, <head>, <body>, or <style> tags)."""
