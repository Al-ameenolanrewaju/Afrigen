"""
Generate platform-specific content from a blog post using the Groq API.

Each function takes the blog post (dict with title, description, body, slug)
and returns a dict with {platform, content, [extra_fields]} ready for posting.
"""

import os
import re
import json

# ---------------------------------------------------------------------------
# Cross-platform link constants — stored once, used everywhere.
# Every post on every platform MUST include links to all other platforms.
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    SITE_URL, TELEGRAM_URL, LINKEDIN_URL, TWITTER_URL,
    FACEBOOK_URL, INSTAGRAM_URL, MEDIUM_URL
)

# Shorthand Telegram CTA used across posts.
TELEGRAM_CTA = f"Follow us on Telegram for daily AI prompts → {TELEGRAM_URL}"

# Cross-link footer appended to LinkedIn, Dev.to, and Hashnode posts.
# Only ACTIVE platforms are promoted so we never link to dead pages.
CROSS_LINK_FOOTER = (
    f"\n\nFollow Afrigen:\n"
    f"\U0001f310 Website: {SITE_URL}\n"
    f"\U0001f4e2 Telegram (daily AI prompts): {TELEGRAM_URL}\n"
    f"\U0001f4bc LinkedIn: {LINKEDIN_URL}"
)

MODEL = os.environ.get("BLOG_MODEL", "llama-3.3-70b-versatile")

_client = None


from flask import current_app

def _call(system: str, user: str, max_tokens: int = 2000, json_mode: bool = False) -> str:
    """Single generation call using ProviderManager."""
    from services.provider_manager import provider_manager
    from app import app
    kwargs = {
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
        
    def do_generate():
        return provider_manager.generate_text("Campaign", kwargs["messages"], **kwargs).strip()

    if not current_app:
        with app.app_context():
            return do_generate()
    return do_generate()


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap output in."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    return text


# ---------------------------------------------------------------------------
# Per-platform generators
# ---------------------------------------------------------------------------

def twitter_thread(post: dict) -> dict:
    """Generate a 6-tweet thread with a hook first and blog link last.
    Returns {platform, tweets: [str, ...]} where each string is <= 280 chars."""
    system = (
        "You are a Nigerian social media manager for Afrigen (afrigen.com.ng), an AI "
        "platform that turns text prompts into videos and images for African creators. "
        "You write sharp, engaging Twitter threads in a Nigerian tone — conversational, "
        "relatable, zero corporate-speak. Your audience is Nigerian content creators, "
        "small business owners, and marketers."
    )
    user = f"""Write a 6-tweet thread promoting this Afrigen blog post.

Blog title: {post['title']}
Blog description: {post.get('description', '')}
Blog body (HTML — extract the key points):
{post.get('body', '')[:3000]}

HARD RULES:
- Return EXACTLY 6 tweets, each on its own line, numbered "1/6", "2/6", etc.
- Tweet 1 MUST be a strong hook (question, bold claim, or surprising fact) — not "check out our blog post."
- Tweet 2-5: deliver concrete value from the post — tips, insights, examples.
- Tweet 6: link to the blog post {SITE_URL}/blog/{post['slug']}
- Nigerian conversational tone. Write like you're talking to a friend on Telegram, not a press release.
- Each tweet MUST be <= 280 characters.
- NEVER use hashtags on tweet 6 (the link tweet).

Return ONLY the 6 numbered tweets, nothing else."""

    raw = _call(system, user, max_tokens=1500)
    tweets = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Strip the "N/6 " prefix for storage; we thread them in order.
        cleaned = re.sub(r"^\d+/\d+\s*", "", line).strip()
        if cleaned:
            tweets.append(cleaned[:280])
    # Ensure we have exactly 6
    while len(tweets) < 6:
        tweets.append("")
        
    # Programmatically append CTA to the last tweet
    last_tweet = tweets[5]
    if len(last_tweet) + len(TELEGRAM_CTA) + 2 <= 280:
        tweets[5] = f"{last_tweet}\n\n{TELEGRAM_CTA}".strip()
        
    return {"platform": "twitter", "tweets": tweets[:6]}


def linkedin_post(post: dict) -> dict:
    """Generate a professional LinkedIn post, <= 200 words, with cross-platform
    link footer. Returns {platform, content: str}."""
    system = (
        "You are a professional content marketer for Afrigen (afrigen.com.ng), an AI "
        "video and image generation platform for African creators. You write polished, "
        "insightful LinkedIn posts that position Afrigen as a thought leader in AI for "
        "African content creation."
    )
    user = f"""Write a LinkedIn post promoting this Afrigen blog article.

Title: {post['title']}
Description: {post.get('description', '')}
Key points from the article:
{post.get('body', '')[:3000]}

RULES:
- Maximum 200 words.
- Professional but warm tone — you're writing for founders, marketers, and creators.
- Open with a strong insight or question that hooks professionals.
- Include the blog link: {SITE_URL}/blog/{post['slug']}

Return ONLY the post text, nothing else."""

    text = _strip_fences(_call(system, user, max_tokens=1200))
    final_text = text + CROSS_LINK_FOOTER
    if len(final_text) > 3000:
        allowed = 3000 - len(CROSS_LINK_FOOTER) - 3
        final_text = text[:allowed] + "..." + CROSS_LINK_FOOTER

    return {"platform": "linkedin", "content": final_text}


def facebook_post(post: dict) -> dict:
    """Generate a high-quality Facebook post with a single link to the blog.
    Returns {platform, content: str}."""
    system = """You are NOT a copywriter.
You are the founder of Afrigen.

Every Facebook post should sound like a real thought shared with the community.
Your mission is to make people stop scrolling because they relate to what you're saying—not because you're advertising something.

About Afrigen
Afrigen is building AI tools that help African creators and businesses create professional images and videos.
You genuinely believe AI will help African creators compete globally.
That belief should naturally appear in your writing.

Never "sell."
Share ideas."""

    user = f"""YOUR JOB

Do NOT summarize the article.
Instead, identify ONE interesting insight, challenge, misconception, or opportunity from the article and build the entire post around that.

The writing process
Before writing, silently ask yourself:
"What would make someone stop scrolling?"
"What opinion would start a discussion?"
"What real frustration does this solve?"
"What would a founder actually say?"
Only then begin writing.

Input:
Blog title: {post['title']}
Description: {post.get('description', '')}
Blog body:
{post.get('body', '')[:3000]}
Blog URL: {SITE_URL}/blog/{post['slug']}

Structure
Start with a real observation.
Examples:
"I've noticed something..."
"One thing many businesses underestimate..."
"Most creators don't have a creativity problem."
"We've spoken to many founders recently..."
Avoid sounding scripted.

Then explain the idea naturally.
Write like you're talking to another entrepreneur.

Build curiosity.
Do NOT explain everything.
Leave readers wanting more.

Invite them to read the article.
Use exactly one link:
👉 {SITE_URL}/blog/{post['slug']}

Finish with one question that people genuinely want to answer.
Examples:
What's your experience?
Have you noticed this too?
Would this save you time?
What's holding you back?

Writing style
Short paragraphs.
Natural rhythm.
No long walls of text.
One sentence paragraphs are encouraged.
Use everyday English.
No jargon. No buzzwords. No corporate language.

Words to avoid completely
Never write:
Exciting news
Latest blog
We're excited
Check it out
Game changer
Revolutionary
Cutting-edge
Transform your business
Unlock the power of
Next level
Don't miss this

Emojis
Maximum 3. Only where they naturally fit.

Hashtags
Maximum 2. Only #AfrigenAI and one other relevant hashtag.

Important
The post should never feel like marketing.
It should feel like someone sharing an interesting thought.
Someone should finish reading it before they even realize it's promoting a blog.
If it sounds like an advertisement, rewrite it automatically.

Return ONLY the Facebook post."""

    text = _strip_fences(_call(system, user, max_tokens=1000))
    return {"platform": "facebook", "content": text}


def instagram_caption(post: dict) -> dict:
    """Generate an Instagram caption with emojis, Nigerian creator hashtags, and
    a note to visit link in bio. Returns {platform, content: str}."""
    system = (
        "You are a Nigerian social media creative for Afrigen (afrigen.com.ng), an AI "
        "video and image platform. You write vibrant Instagram captions with emojis, "
        "line breaks, and Nigerian creator energy. Your captions feel like they're from "
        "a real creative, not a brand account."
    )
    user = f"""Write an Instagram caption promoting this Afrigen blog post.

Title: {post['title']}
Description: {post.get('description', '')}
Key points:
{post.get('body', '')[:3000]}

RULES:
- Use emojis naturally throughout (not forced, not excessive).
- Nigerian creator tone — energetic, authentic, encouraging.
- Mention "link in bio" for the full article.
- Include 5-8 Nigerian creator hashtags at the end (e.g., #NigerianCreators #AIContent #ContentCreatorNG #AIForAfrica).
- Blog link (for reference, but tell people link is in bio): {SITE_URL}/blog/{post['slug']}
- End with this CTA on its own line:
{TELEGRAM_CTA}

Return ONLY the caption text, nothing else."""

    text = _call(system, user, max_tokens=1000)
    return {"platform": "instagram", "content": _strip_fences(text)}


def telegram_prompt(post: dict) -> dict:
    """Extract or generate a practical AI video prompt from the blog post.
    This is NOT a blog summary — it's one actionable AI prompt Nigerian creators
    can use today, derived from the blog topic. This is the Telegram channel's
    unique value proposition.

    Returns {platform, content: str} formatted with the channel template."""
    system = (
        "You are an AI prompt engineer for Afrigen (afrigen.com.ng), an AI video and "
        "image generation platform. You create PRACTICAL, copy-paste-ready AI video "
        "prompts that Nigerian and African creators can use immediately. Your prompts "
        "are detailed, specific to African contexts, and produce great results on "
        "AI video models."
    )
    user = f"""Read this Afrigen blog post and extract or create ONE practical AI video/image prompt that a Nigerian creator can copy, paste, and use right now.

Blog title: {post['title']}
Blog body:
{post.get('body', '')[:3000]}

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

📖 Full guide: {SITE_URL}/blog/{post['slug']}

Follow for daily prompts 👇
🐦 Twitter: {TWITTER_URL}
💼 LinkedIn: {LINKEDIN_URL}
📘 Facebook: {FACEBOOK_URL}
📸 Instagram: {INSTAGRAM_URL}
✍️ Medium: {MEDIUM_URL}

Return ONLY the formatted post, nothing else."""

    text = _call(system, user, max_tokens=1200)
    return {"platform": "telegram", "content": _strip_fences(text)}


def medium_article(post: dict) -> dict:
    """Generate a full Medium article cross-post with canonical URL pointing to
    afrigen.com.ng for SEO. Returns {platform, title, content, tags, canonicalUrl}."""
    system = (
        "You are a content editor for Afrigen (afrigen.com.ng), an AI platform for "
        "African creators. You adapt blog posts for Medium publication, maintaining "
        "the original value while formatting for Medium's audience. You write a "
        "compelling author bio that drives readers to Afrigen."
    )
    user = f"""Adapt this Afrigen blog post for Medium publication.

Original title: {post['title']}
Original description: {post.get('description', '')}
Original body (HTML):
{post.get('body', '')[:3000]}

RULES:
- Keep the original title but you may add a subtitle if helpful.
- Rewrite the body in Medium-friendly format using markdown (headings with ##, paragraphs, bullet points).
- Keep the core insights and practical advice intact.
- Nigerian/African creator audience — maintain the original tone.
- At the end, add an author bio section:

---
*About Afrigen: Africa Creates, AI Generates. Afrigen helps Nigerian and African creators turn text prompts into stunning AI videos and images. No camera crew needed — just your idea.*

*Follow Afrigen everywhere:*
*🐦 Twitter: {TWITTER_URL}*
*💼 LinkedIn: {LINKEDIN_URL}*
*📘 Facebook: {FACEBOOK_URL}*
*📸 Instagram: {INSTAGRAM_URL}*
*📢 Telegram (daily AI prompts): {TELEGRAM_URL}*

Return your response as a JSON object with these fields:
- title: the Medium title (string)
- body: the markdown body (string)
- tags: array of 3-5 relevant Medium tags (e.g., ["AI", "Content Creation", "Africa"])

Return ONLY valid JSON, no markdown fences, no commentary."""

    raw = _call(system, user, max_tokens=2500, json_mode=True)
    raw = _strip_fences(raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: wrap the raw text as body
        data = {
            "title": post["title"],
            "body": raw,
            "tags": ["AI", "Content Creation", "Africa", "Technology", "Creativity"],
        }

    return {
        "platform": "medium",
        "title": data.get("title", post["title"]),
        "content": data.get("body", ""),
        "tags": data.get("tags", ["AI", "Content Creation", "Africa"]),
        "canonicalUrl": f"{SITE_URL}/blog/{post['slug']}",
    }


def _article_body(post: dict, platform_name: str) -> dict:
    """Shared generator for long-form markdown cross-posts (Dev.to, Hashnode).

    Returns {title, body (markdown), tags, subtitle}. Used by devto_article and
    hashnode_article so both platforms share one Groq call's worth of structure
    while each publisher maps the fields to its own API.
    """
    system = (
        "You are a content editor for Afrigen (afrigen.com.ng), an AI platform for "
        "African creators that turns text prompts into videos and images. You adapt "
        f"blog posts for {platform_name} publication, keeping the original value while "
        f"formatting cleanly for a developer/creator audience."
    )
    user = f"""Adapt this Afrigen blog post for {platform_name} publication.

Original title: {post['title']}
Original description: {post.get('description', '')}
Original body (HTML):
{post.get('body', '')[:3000]}

RULES:
- Keep the original title (you may also provide a short subtitle).
- Rewrite the body as clean Markdown (## headings, paragraphs, bullet points).
- Keep the core insights and practical advice intact.
- Nigerian/African creator audience — keep the original tone.
- End with this author bio section EXACTLY:

---
*About Afrigen: Africa Creates, AI Generates. Afrigen helps Nigerian and African creators turn text prompts into stunning AI videos and images — no camera crew needed, just your idea.*

*\U0001f310 Website: {SITE_URL}*
*\U0001f4e2 Telegram (daily AI prompts): {TELEGRAM_URL}*
*\U0001f4bc LinkedIn: {LINKEDIN_URL}*

Return your response as a JSON object with these fields:
- title: the article title (string)
- subtitle: a one-line subtitle (string, may be empty)
- body: the markdown body (string)
- tags: array of 3-4 lowercase single-word tags (e.g., ["ai", "africa", "contentcreation"])

Return ONLY valid JSON, no markdown fences, no commentary."""

    raw = _strip_fences(_call(system, user, max_tokens=2500, json_mode=True))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "title": post["title"],
            "subtitle": post.get("description", ""),
            "body": raw,
            "tags": ["ai", "africa", "contentcreation"],
        }
    return {
        "title": data.get("title", post["title"]),
        "subtitle": data.get("subtitle", ""),
        "body": data.get("body", ""),
        "tags": data.get("tags", ["ai", "africa", "contentcreation"]),
    }


def devto_article(post: dict) -> dict:
    """Generate a Dev.to article cross-post with a canonical URL back to Afrigen.
    Returns {platform, title, content, tags, canonicalUrl}."""
    art = _article_body(post, "Dev.to")
    # Dev.to tags: lowercase alphanumeric, max 4.
    tags = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in art["tags"]]
    tags = [t for t in tags if t][:4]
    return {
        "platform": "devto",
        "title": art["title"],
        "content": art["body"],
        "tags": tags or ["ai", "africa"],
        "description": art.get("subtitle", "") or post.get("description", ""),
        "canonicalUrl": f"{SITE_URL}/blog/{post['slug']}",
    }


def hashnode_article(post: dict) -> dict:
    """Generate a Hashnode article cross-post with a canonical URL back to Afrigen.
    Returns {platform, title, subtitle, content, tags, canonicalUrl}."""
    art = _article_body(post, "Hashnode")
    # Hashnode tags use slug + display name; keep them lowercase/alphanumeric.
    tags = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in art["tags"]]
    tags = [t for t in tags if t][:5]
    return {
        "platform": "hashnode",
        "title": art["title"],
        "subtitle": art.get("subtitle", ""),
        "content": art["body"],
        "tags": tags or ["ai", "africa"],
        "canonicalUrl": f"{SITE_URL}/blog/{post['slug']}",
    }


def pinterest_pin(post: dict) -> dict:
    """Generate a Pinterest Pin: a short keyword-rich title + a description with
    a few hashtags, linking back to the Afrigen blog post. The image itself is a
    branded card the publisher renders from the title (Afrigen has no per-post
    image), so this generator only produces the text + destination link.

    Returns {platform, title, description, link, image_title}."""
    system = (
        "You are a Pinterest marketer for Afrigen (afrigen.com.ng), an AI platform "
        "that turns text prompts into videos and images for African creators. You "
        "write keyword-rich, search-friendly Pin titles and descriptions that get "
        "discovered on Pinterest."
    )
    user = f"""Write a Pinterest Pin promoting this Afrigen blog post.

Title: {post['title']}
Description: {post.get('description', '')}
Key points:
{post.get('body', '')[:2500]}

Return a JSON object with these fields:
- title: a punchy, keyword-rich Pin title (MAX 95 characters, no hashtags)
- description: 2-3 sentences of value + a soft CTA to read the full guide, ending
  with 3-5 relevant hashtags (e.g. #AIVideo #ContentCreation #AfricanCreators).
  MAX 480 characters.

Return ONLY valid JSON, no markdown fences, no commentary."""

    raw = _strip_fences(_call(system, user, max_tokens=700, json_mode=True))
    try:
        data = json.loads(raw)
        title = (data.get("title") or post["title"])[:95]
        description = (data.get("description") or post.get("description", ""))[:480]
    except json.JSONDecodeError:
        title = post["title"][:95]
        description = (post.get("description", "") or raw)[:480]

    return {
        "platform": "pinterest",
        "title": title,
        "description": description,
        "link": f"{SITE_URL}/blog/{post['slug']}",
        "image_title": post["title"],
    }


# ---------------------------------------------------------------------------
# Bulk generation using Content Engine
# ---------------------------------------------------------------------------

ACTIVE_PLATFORMS = ["telegram", "linkedin", "devto", "pinterest"]

# We keep pinterest_pin as it is since it doesn't have a new writer yet (per instructions, we focused on Facebook, LinkedIn, Telegram, Newsletter, Dev.to).
# I'll keep the old generators accessible.

_GENERATORS = {
    "telegram": telegram_prompt,
    "linkedin": linkedin_post,
    "devto": devto_article,
    "hashnode": hashnode_article,
    "pinterest": pinterest_pin,
    # --- disabled (not in ACTIVE_PLATFORMS) ---
    "twitter": twitter_thread,
    "facebook": facebook_post,
    "instagram": instagram_caption,
    "medium": medium_article,
}

def generate_all(post: dict) -> list[dict]:
    """Generate content for every ACTIVE platform. Returns list of result dicts.
    Uses the new Content Engine for supported platforms."""
    import sys
    import os
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
        
    from content_engine import (
        ContentPlanner, generate_content_brief, ContentCategory,
        write_linkedin_post, write_telegram_post, write_devto_article
    )
    
    # 1. Generate Master Brief
    # Since it's from a blog post, the category is BLOG_POST
    try:
        source_context = f"Title: {post['title']}\nDescription: {post.get('description', '')}\nBody:\n{post.get('body', '')[:3000]}"
        brief = generate_content_brief(ContentCategory.BLOG_POST, source_context, source_blog=post)
    except Exception as e:
        print(f"[generate] ⚠️ Master Brief generation failed: {e}. Falling back to legacy generators.")
        brief = None
    
    results = []
    for name in ACTIVE_PLATFORMS:
        if name == "linkedin" and brief:
            try:
                gen = write_linkedin_post(brief)
                results.append({"platform": name, "content": gen.content})
                print(f"[generate] ✅ {name} content ready (Content Engine)")
                continue
            except Exception as e:
                print(f"[generate] ❌ {name} (Content Engine) FAILED: {e}")
                results.append({"platform": name, "error": str(e)})
                continue
                
        if name == "telegram" and brief:
            try:
                gen = write_telegram_post(brief)
                results.append({"platform": name, "content": gen.content})
                print(f"[generate] ✅ {name} content ready (Content Engine)")
                continue
            except Exception as e:
                print(f"[generate] ❌ {name} (Content Engine) FAILED: {e}")
                results.append({"platform": name, "error": str(e)})
                continue
                
        if name == "devto" and brief:
            try:
                gen = write_devto_article(brief)
                res = {"platform": name, "content": gen.content}
                res.update(gen.extra_fields)
                results.append(res)
                print(f"[generate] ✅ {name} content ready (Content Engine)")
                continue
            except Exception as e:
                print(f"[generate] ❌ {name} (Content Engine) FAILED: {e}")
                results.append({"platform": name, "error": str(e)})
                continue

        # Fallback to legacy generators
        fn = _GENERATORS.get(name)
        if not fn:
            print(f"[generate] ⚠️ {name} has no generator — skipping")
            continue
        try:
            results.append(fn(post))
            print(f"[generate] ✅ {name} content ready (Legacy)")
        except Exception as e:
            print(f"[generate] ❌ {name} (Legacy) FAILED: {e}")
            results.append({"platform": name, "error": str(e)})
            
    return results
