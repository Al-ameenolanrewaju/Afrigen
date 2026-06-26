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
    system = (
        "You are a social media manager for Afrigen (afrigen.com.ng), an AI video and "
        "image generation platform for African creators. You write short, engaging, "
        "and professional company updates for Facebook. Use emojis naturally."
    )
    user = f"""Write a Facebook announcement for our new blog post.

Blog Title: {blog.title}
Blog URL: {blog_url}
Publish Date: {blog.date}

RULES:
- Do NOT summarize the article. Do NOT analyze the content.
- Keep it short and engaging, like a company/founder update.
- Mention the title and URL.
- Encourage people to follow our Facebook Page: {FACEBOOK_URL}
- End with our website: {WEBSITE_URL}

Return ONLY the Facebook post text."""

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
    """Generates an image prompt, an image via FAL, and a caption, then posts to Facebook."""
    # Topics to rotate
    topics = [
        "Afrigen helps Nigerian creators turn text into stunning AI videos.",
        "Afrigen saves small businesses money by generating high-quality product promo videos without a camera crew.",
        "AI creativity is evolving. Afrigen empowers African artists with cutting-edge tools.",
        "Stop struggling with content creation. Use Afrigen to bring your ideas to life.",
        "Premium AI image generation for African startups and creators.",
        "Turn your imagination into reality with Afrigen's AI tools.",
        "The future of African storytelling is powered by AI and Afrigen."
    ]
    
    # Pick a random topic, but try to find one not recently posted
    recent_posts = FacebookPostHistory.query.filter_by(content_type='brand_awareness')\
                                      .order_by(FacebookPostHistory.timestamp.desc()).limit(10).all()
    recent_texts = [p.post_text for p in recent_posts]
    
    topic = random.choice(topics)
    # Simple deduplication attempt: try to find a topic not in recent texts
    for t in topics:
        if not any(t[:30] in text for text in recent_texts):
            topic = t
            break

    print(f"[facebook_engine] Generating brand awareness assets for topic: '{topic[:50]}...'")

    # 1. Generate Image Prompt
    img_system = (
        "You are an expert AI image prompt engineer for Afrigen, an African AI platform. "
        "You create premium, highly detailed prompts for image generation models."
    )
    img_user = f"""Create a premium image generation prompt for Afrigen based on this topic:
"{topic}"

Requirements:
- Futuristic AI creativity theme
- African creative identity (e.g. diverse creators, modern African cities/studios)
- Professional startup/company style
- High quality, cinematic, realistic lighting
- NO text inside the image.

Return ONLY the image prompt (1-3 sentences)."""
    
    image_prompt = _call(img_system, img_user, max_tokens=300).strip()
    # Strip any potential quotes
    image_prompt = image_prompt.strip('"\'')

    # 2. Generate Caption
    cap_system = (
        "You are a social media manager for Afrigen. You write professional, inspiring, "
        "and engaging brand awareness posts for Facebook."
    )
    cap_user = f"""Write a Facebook post based on this topic:
"{topic}"

Rules:
- Feel like an update from a real technology company.
- Professional but friendly, use emojis naturally.
- Drive engagement (ask a question).
- End with our website: {WEBSITE_URL} and Facebook Page: {FACEBOOK_URL}

Return ONLY the Facebook post text."""
    
    caption = _call(cap_system, cap_user, max_tokens=600).strip()

    print("\n--------------------------------------------------")
    print(f"Post Type: Brand Awareness")
    print(f"Image Prompt:\n{image_prompt}")
    print(f"Caption:\n{caption}")
    print(f"Target Facebook Page ID: {os.environ.get('FACEBOOK_PAGE_ID')}")
    print("--------------------------------------------------\n")

    # 3. Generate Image
    print("[facebook_engine] Generating image via FAL...")
    image_result = generate_image(image_prompt, style="african")
    
    if not image_result.get("success"):
        print(f"[facebook_engine] ❌ Image generation failed: {image_result.get('error')}")
        return {"ok": False, "error": image_result.get("error")}
    
    image_url = image_result["image_url"]
    print(f"[facebook_engine] ✅ Image generated: {image_url}")

    # 4. Post to Facebook
    print("[facebook_engine] Publishing photo to Facebook...")
    result = post_photo_to_page(image_url, caption)
    
    _log_result(result, content_type='brand_awareness', post_text=caption, image_used=image_url)
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
