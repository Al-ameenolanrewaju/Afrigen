import os
import sys
import random
from typing import Dict, Any, List

from .planner import ContentPlanner
from .models import ContentCategory, ContentBrief, GeneratedContent
from .brief_generator import generate_content_brief
from .writers.facebook import write_facebook_post
from .writers.linkedin import write_linkedin_post
from .writers.telegram import write_telegram_post
from .writers.devto import write_devto_article
from .writers.newsletter import write_newsletter
from .publishers.facebook import publish_facebook_post
from .publishers.linkedin import publish_linkedin_post
from .publishers.telegram import publish_telegram_post
from .publishers.devto import publish_devto_article
from .publishers.newsletter import publish_newsletter_draft
from .utils import get_logger

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

logger = get_logger("ContentPipeline")

# Only active platforms for the unified Content Engine
ACTIVE_PLATFORMS = ["linkedin", "telegram", "devto", "newsletter"]

class ContentPipeline:
    def __init__(self, dry_run=False, preview=False):
        self.dry_run = dry_run
        self.preview = preview
        if self.dry_run:
            os.environ["DRY_RUN"] = "true"

    def run_automatic(self):
        """
        Intended for Render Cron (runs once per day).
        Executes full pipeline, checks idempotency, publishes automatically.
        """
        logger.info("Running AUTOMATIC mode (Daily Cron)")
        blog_post = self._get_latest_published_blog()
        
        if blog_post:
            b_url = f"https://afrigen.com.ng/blog/{blog_post.slug}"
            if not self._check_idempotency(b_url):
                logger.info("Decision: Blog Update")
                return self._run_blog_update(blog_post, b_url)
        
        logger.info("Decision: Brand Awareness")
        return self._run_brand_awareness()

    def run_manual_publish_today(self):
        """Manually execute the daily automatic run."""
        logger.info("Running MANUAL mode: publish_today")
        return self.run_automatic()

    def run_manual_publish_blog(self, blog_url: str):
        """Force publish a specific blog URL, bypassing idempotency checks."""
        logger.info(f"Running MANUAL mode: publish_blog for {blog_url}")
        blog_post = self._resolve_blog_from_url(blog_url)
        if not blog_post:
            logger.error("Could not resolve blog post")
            return None
        return self._run_blog_update(blog_post, blog_url)

    def run_manual_preview(self, blog_url=None):
        """Generate content and print to console without publishing."""
        logger.info("Running MANUAL mode: preview")
        self.preview = True
        
        # We need an app context for DB access if resolving latest blog
        # But if blog_url is provided, we can bypass the DB.
        if blog_url:
            return self.run_manual_publish_blog(blog_url)
        else:
            return self._run_brand_awareness()

    def run_manual_dry_run(self, blog_url=None):
        """Execute the pipeline but mock external API calls."""
        logger.info("Running MANUAL mode: dry_run")
        self.dry_run = True
        os.environ["DRY_RUN"] = "true"
        if blog_url:
            return self.run_manual_publish_blog(blog_url)
        else:
            return self.run_automatic()

    def _get_latest_published_blog(self):
        try:
            from models import BlogPost
            return BlogPost.query.filter_by(status='published').order_by(BlogPost.published_at.desc()).first()
        except Exception as e:
            logger.error(f"DB Error fetching blog (you may need an app context): {e}")
            return None

    def _check_idempotency(self, blog_url: str) -> bool:
        # Check if we have already posted a blog update for this URL
        try:
            from models import FacebookPostHistory
            # We look for ANY record with this blog_url to avoid repeating the blog update
            return FacebookPostHistory.query.filter_by(blog_url=blog_url).first() is not None
        except Exception as e:
            logger.error(f"DB Error checking idempotency: {e}")
            return False

    def _resolve_blog_from_url(self, blog_url: str):
        from scripts.distribute import resolve_blog_post
        
        post_dict = resolve_blog_post(blog_url)
        if not post_dict:
            # Optional mock for testing preview
            if self.preview:
                logger.warning(f"Could not resolve {blog_url}, using mock data for preview.")
                return {
                    "slug": "mock-post",
                    "title": "A Mock Post for Preview",
                    "description": "This is a mock description for previewing the engine.",
                    "body": "<p>This is a mock body. It talks about AI video generation in Africa.</p>",
                    "url": blog_url
                }
            return None
        return post_dict

    def _run_blog_update(self, blog_post, blog_url: str):
        if not isinstance(blog_post, dict):
            # It's an ORM object
            source_context = f"Title: {blog_post.title}\nDescription: {blog_post.description}\nBody:\n{blog_post.body[:3000]}"
            post_dict = {"slug": blog_post.slug, "title": blog_post.title, "description": blog_post.description, "body": blog_post.body}
        else:
            # It's a dict from resolve_blog_post
            source_context = f"Title: {blog_post['title']}\nDescription: {blog_post.get('description', '')}\nBody:\n{blog_post.get('body', '')[:3000]}"
            post_dict = blog_post

        brief = generate_content_brief(ContentCategory.BLOG_POST, source_context, source_blog=post_dict)
        return self._execute_generation_and_publish(brief, "blog_update", blog_url)

    def _run_brand_awareness(self):
        planner = ContentPlanner()
        category = planner.select_category()

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

        topic = random.choice(topics)
        for t in topics:
            if not planner.is_topic_recent(t):
                topic = t
                break
                
        planner.record_topic(topic)
        brief = generate_content_brief(category, source_context=topic)
        return self._execute_generation_and_publish(brief, "brand_awareness")

    def _execute_generation_and_publish(self, brief: ContentBrief, content_type: str, blog_url: str = None):
        results = {}
        
        # 1. Generate Image for brand awareness (or if requested)
        image_url = None
        if content_type == "brand_awareness" and not self.preview:
            try:
                from scripts.generate_content import _call
                img_system = "You are an expert AI image prompt engineer creating visuals for Afrigen."
                img_user = f"Create a cinematic image generation prompt based on:\n\n\"{brief.topic}\"\n\nReturn ONLY the image prompt."
                image_prompt = _call(img_system, img_user, max_tokens=300).strip().strip("\"'")
                
                from services.video import generate_image
                image_result = generate_image(image_prompt, style="african")
                if image_result.get("success"):
                    image_url = image_result["image_url"]
                    logger.info(f"✅ Image generated: {image_url}")
                else:
                    logger.warning("Image generation failed API side. Falling back to text-only.")
            except Exception as e:
                logger.warning(f"Image generation threw an exception: {e}. Falling back to text-only.")

        # 2. Setup Writers and Publishers
        writers = {
            "facebook": write_facebook_post,
            "linkedin": write_linkedin_post,
            "telegram": write_telegram_post,
            "devto": write_devto_article,
            "newsletter": write_newsletter
        }
        
        publishers = {
            "facebook": publish_facebook_post,
            "linkedin": publish_linkedin_post,
            "telegram": publish_telegram_post,
            "devto": publish_devto_article,
            "newsletter": publish_newsletter_draft
        }

        if self.preview:
            print(f"\n{'='*60}")
            print(f"[preview] PREVIEW MODE ACTIVATED")
            print(f"{'='*60}")

        # 3. Process Each Platform
        for platform in ACTIVE_PLATFORMS:
            if platform not in writers: continue
            
            logger.info(f"Generating content for {platform}...")
            try:
                gen_content = writers[platform](brief)
                if image_url:
                    gen_content.extra_fields["image_url"] = image_url
                
                if self.preview:
                    print(f"\n--- {platform.upper()} ---")
                    print(f"✅ Generated Content:")
                    print(gen_content.content)
                    if gen_content.extra_fields:
                        print("Extra Fields:")
                        for k, v in gen_content.extra_fields.items():
                            print(f"  {k}: {v}")
                else:
                    logger.info(f"Publishing to {platform}...")
                    pub_result = publishers[platform](gen_content)
                    results[platform] = pub_result
                    
                    if pub_result.get("ok"):
                        logger.info(f"✅ {platform} published successfully.")
                        self._log_history(content_type, platform, blog_url, gen_content.content, image_url, pub_result)
                    else:
                        logger.error(f"❌ {platform} publish failed: {pub_result.get('error')}")
            except Exception as e:
                logger.error(f"❌ {platform} failed: {e}")
                results[platform] = {"ok": False, "error": str(e)}
                
        if self.preview:
            print(f"\n{'='*60}")
            print(f"[preview] PREVIEW COMPLETE. NO PUBLISHING OCCURRED.")
            print(f"{'='*60}")
            
        return results

    def _log_history(self, content_type, platform, blog_url, text, image_url, pub_result):
        # We reuse FacebookPostHistory table to avoid DB migrations but store data for all platforms.
        # This keeps the publishing pipeline single and reusable.
        try:
            from models import db, FacebookPostHistory
            post_id = pub_result.get("post_id") or pub_result.get("issue_id") or "N/A"
            history = FacebookPostHistory(
                content_type=f"{content_type}_{platform}",
                blog_url=blog_url,
                post_text=text,
                facebook_post_id=str(post_id),
                image_used=image_url
            )
            db.session.add(history)
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to log history for {platform}: {e}")
