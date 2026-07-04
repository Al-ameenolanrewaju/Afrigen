"""
Daily Facebook Automation Engine.
Checks for new blog posts and creates an announcement.
If no new post, generates a brand awareness post with AI images.
"""

import os
import random
from datetime import datetime, timedelta
import sys

# Import necessary modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, BlogPost, FacebookPostHistory
from scripts.platforms.facebook import post_to_page, post_photo_to_page
from scripts.generate_content import _call, SITE_URL
from services.video import generate_image
from constants import WEBSITE_URL, FACEBOOK_URL

def run_daily_facebook_engine():
    """
    Main function to run the daily Facebook automation.
    It decides between a blog update post and a brand awareness post.
    """
    print("\n[facebook_engine] 🚀 Starting daily Facebook engine...")

    # Find all published blog posts, ordered by newest first
    published_blogs = BlogPost.query.filter_by(status='published').order_by(BlogPost.published_at.desc()).all()
    
    selected_blog = None
    blog_url = None

    for blog in published_blogs:
        b_url = f"{WEBSITE_URL}/blog/{blog.slug}"
        print(f"[facebook_engine] Latest blog found: {blog.title}")
        
        # Duplicate protection check
        is_posted = FacebookPostHistory.query.filter_by(blog_url=b_url).first() is not None
        print(f"[facebook_engine] Already posted: {is_posted}")
        
        if not is_posted:
            selected_blog = blog
            blog_url = b_url
            break

    if selected_blog:
        print("[facebook_engine] Decision: Blog Update")
        return _generate_blog_update_post(selected_blog, blog_url)
    else:
        print("[facebook_engine] Decision: Brand Awareness")
        return _generate_brand_awareness_post()


def _generate_blog_update_post(blog: BlogPost, blog_url: str):
    """Generates and posts a short announcement for a new blog article."""
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
Blog title: {blog.title}
Blog URL: {blog_url}

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
👉 {blog_url}

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

    print("[facebook_engine] Generating blog announcement caption...")
    caption = _call(system, user, max_tokens=600).strip()
    
    print("\n--------------------------------------------------")
    print(f"Post Type: Blog Update")
    print(f"Caption:\n{caption}")
    print(f"Target Facebook Page ID: {os.environ.get('FACEBOOK_PAGE_ID')}")
    print("--------------------------------------------------\n")

    print("[facebook_engine] Publishing to Facebook...")
    result = post_to_page(caption)
    
    _log_result(result, content_type='blog_update', post_text=caption, blog_url=blog_url)
    return result


def _generate_brand_awareness_post():
    """Generates a premium Afrigen brand awareness post with AI image and publishes to Facebook."""

    topics = [
        "Afrigen is building AI tools that help African creators turn ideas into professional visual content.",
        "African storytelling is entering a new era where creators can produce more with fewer resources.",
        "Small businesses need better ways to create marketing content. AI is changing how brands tell their stories.",
        "Every great video starts with an idea. Afrigen helps creators transform those ideas into visuals.",
        "The future of content creation will combine human creativity with artificial intelligence.",
        "We are exploring how AI can help African creators, startups, and businesses compete globally.",
        "Creators should spend more time creating and less time fighting complicated production workflows.",
        "AI is not replacing creativity. It is giving more people the tools to express their creativity."
    ]

    # Avoid repeating recent topics
    recent_posts = (
        FacebookPostHistory.query
        .filter_by(content_type='brand_awareness')
        .order_by(FacebookPostHistory.timestamp.desc())
        .limit(10)
        .all()
    )

    recent_texts = [p.post_text for p in recent_posts]

    topic = random.choice(topics)

    for t in topics:
        if not any(t[:40] in text for text in recent_texts):
            topic = t
            break

    print(
        f"[facebook_engine] Generating Afrigen brand post for topic: '{topic[:60]}...'"
    )


    # =========================
    # IMAGE PROMPT GENERATION
    # =========================

    img_system = """
You are an expert AI image prompt engineer creating visuals for Afrigen,
an African AI creativity startup.

Your job is to create premium startup-quality image prompts.
"""

    img_user = f"""
Create a cinematic image generation prompt based on:

"{topic}"

Requirements:
- Premium technology startup aesthetic
- African creators using advanced AI technology
- Modern African workspace, studio, or city environment
- Diverse realistic African people
- Futuristic but believable
- Professional brand photography style
- High quality cinematic lighting
- Suitable for a company social media page
- No text inside image
- No logos
- No watermark

Return ONLY the image prompt.
"""

    image_prompt = _call(
        img_system,
        img_user,
        max_tokens=300
    ).strip()

    image_prompt = image_prompt.strip("\"'")


    # =========================
    # CAPTION GENERATION
    # =========================

    cap_system = """
You are the official social media voice of Afrigen,
an African AI creativity company.

Write posts like a professional technology startup.

Tone:
- Visionary
- Human
- Professional
- Confident
- Community focused

Avoid:
- "Exciting news!"
- Generic marketing language
- Hard selling
- Sounding like AI generated text
- Too many emojis

The post should feel like it was written by the Afrigen team or founder.
"""

    cap_user = f"""
Create a Facebook post about:

"{topic}"

Requirements:
- Start with a strong opening idea.
- Explain why this matters.
- Mention Afrigen naturally.
- Encourage discussion with a question.
- Build trust with the audience.
- Keep it between 100-200 words.
- Use maximum 3 emojis.
- End with:

{WEBSITE_URL}

Return ONLY the Facebook post text.
"""

    caption = _call(
        cap_system,
        cap_user,
        max_tokens=600
    ).strip()


    print("\n--------------------------------------------------")
    print("Post Type: Brand Awareness")
    print(f"Image Prompt:\n{image_prompt}")
    print(f"Caption:\n{caption}")
    print(
        f"Target Facebook Page ID: {os.environ.get('FACEBOOK_PAGE_ID')}"
    )
    print("--------------------------------------------------\n")


    # =========================
    # IMAGE GENERATION
    # =========================

    print("[facebook_engine] Generating image via FAL...")

    image_result = generate_image(
        image_prompt,
        style="african"
    )

    if not image_result.get("success"):
        print(
            f"[facebook_engine] ❌ Image generation failed: {image_result.get('error')}"
        )

        return {
            "ok": False,
            "error": image_result.get("error")
        }


    image_url = image_result["image_url"]

    print(
        f"[facebook_engine] ✅ Image generated: {image_url}"
    )


    # =========================
    # FACEBOOK POST
    # =========================

    print("[facebook_engine] Publishing photo to Facebook...")

    result = post_photo_to_page(
        image_url,
        caption
    )


    _log_result(
        result,
        content_type="brand_awareness",
        post_text=caption,
        image_used=image_url
    )

    return result


def _log_result(result, content_type, post_text, blog_url=None, image_used=None):
    """Log the API response and save to history if successful."""
    print("\n[facebook_engine] API Response:")
    print(result)

    if result.get("ok"):
        print(f"[facebook_engine] ✅ Success! Post ID: {result.get('post_id')}")
        history = FacebookPostHistory(
            content_type=content_type,
            blog_url=blog_url,
            post_text=post_text,
            facebook_post_id=result.get("post_id"),
            image_used=image_used
        )
        db.session.add(history)
        db.session.commit()
    else:
        print(f"[facebook_engine] ❌ Failed: {result.get('error')}")
