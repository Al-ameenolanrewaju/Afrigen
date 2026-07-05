"""
DEPRECATED: This module is deprecated. Use `content_engine.cli` instead.

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
    """Generates and posts a short announcement for a new blog article using Content Engine."""
    from content_engine import generate_content_brief, ContentCategory, write_facebook_post, publish_facebook_post
    
    print("[facebook_engine] Generating blog announcement via Content Engine...")
    
    source_context = f"Title: {blog.title}\nDescription: {blog.description}\nBody:\n{blog.body[:3000]}"
    
    try:
        # Create brief
        post_dict = {"slug": blog.slug, "title": blog.title, "description": blog.description, "body": blog.body}
        brief = generate_content_brief(ContentCategory.BLOG_POST, source_context, source_blog=post_dict)
        
        # Generate post
        generated_post = write_facebook_post(brief)
        caption = generated_post.content
        
        print("\n--------------------------------------------------")
        print(f"Post Type: Blog Update")
        print(f"Caption:\n{caption}")
        print(f"Target Facebook Page ID: {os.environ.get('FACEBOOK_PAGE_ID')}")
        print("--------------------------------------------------\n")

        print("[facebook_engine] Publishing to Facebook...")
        result = publish_facebook_post(generated_post)
        
        _log_result(result, content_type='blog_update', post_text=caption, blog_url=blog_url)
        return result
    except Exception as e:
        print(f"[facebook_engine] ❌ Failed in Content Engine: {e}")
        return {"ok": False, "error": str(e)}


def _generate_brand_awareness_post():
    """Generates a premium Afrigen brand awareness post with AI image and publishes to Facebook using Content Engine."""
    from content_engine import ContentPlanner, generate_content_brief, write_facebook_post, publish_facebook_post

    planner = ContentPlanner()
    category = planner.select_category()

    # The topics here can just act as a seed/source material
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

    # Select a topic avoiding recent ones using Planner history
    topic = random.choice(topics)
    for t in topics:
        if not planner.is_topic_recent(t):
            topic = t
            break
            
    planner.record_topic(topic)

    print(f"[facebook_engine] Generating Afrigen brand post for category: {category.value}, topic: '{topic[:60]}...'")

    try:
        # Create Master Brief
        brief = generate_content_brief(category, source_context=topic)
        
        # 1. Generate Image Prompt directly here (could also be part of Content Engine, but keeping it simple)
        img_system = "You are an expert AI image prompt engineer creating visuals for Afrigen, an African AI creativity startup. Your job is to create premium startup-quality image prompts."
        img_user = f"Create a cinematic image generation prompt based on:\n\n\"{brief.topic}\"\n\nRequirements:\n- Premium technology startup aesthetic\n- African creators using advanced AI technology\n- Modern African workspace, studio, or city environment\n- Diverse realistic African people\n- Futuristic but believable\n- Professional brand photography style\n- High quality cinematic lighting\n- Suitable for a company social media page\n- No text inside image\n- No logos\n- No watermark\n\nReturn ONLY the image prompt."
        
        from scripts.generate_content import _call
        image_prompt = _call(img_system, img_user, max_tokens=300).strip().strip("\"'")

        # 2. Generate Caption using Content Engine Facebook Writer
        generated_post = write_facebook_post(brief)
        caption = generated_post.content

        print("\n--------------------------------------------------")
        print("Post Type: Brand Awareness")
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
        generated_post.extra_fields["image_url"] = image_url
        print(f"[facebook_engine] ✅ Image generated: {image_url}")

        # 4. Publish via Content Engine Publisher
        print("[facebook_engine] Publishing photo to Facebook...")
        result = publish_facebook_post(generated_post)

        _log_result(result, content_type="brand_awareness", post_text=caption, image_used=image_url)
        return result
    except Exception as e:
        print(f"[facebook_engine] ❌ Failed in Content Engine: {e}")
        return {"ok": False, "error": str(e)}


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
