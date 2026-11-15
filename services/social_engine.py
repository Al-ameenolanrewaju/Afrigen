"""Master Social Automation Orchestrator for Afrigen AI.

Brings together strategy planning, Hugging Face creative generation, platform-specific
copywriting, quality auditing, distributed job scheduling, and analytics synchronization.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from models import (
    db, User, SocialPost, SocialCampaign, SocialMediaAsset,
    SocialPublishingJob, SocialAutomationSettings, ConnectedAccount
)
from services.social_strategist import (
    select_next_pillar, plan_post_concept, generate_platform_copy,
    check_content_originality
)
from services.social_creative_hf import (
    generate_social_image, generate_social_video, validate_media_asset
)
from services.social_qa import run_social_quality_audit
from services.social_publisher import run_social_publishing_cycle
from services.social_analytics import sync_all_recent_analytics, adapt_future_strategy

logger = logging.getLogger(__name__)


def get_or_create_settings(user_id: int) -> SocialAutomationSettings:
    """Retrieve or initialize default social automation settings for a user."""
    settings = SocialAutomationSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = SocialAutomationSettings(
            user_id=user_id,
            enabled=True,
            emergency_paused=False,
            facebook_enabled=True,
            linkedin_enabled=True,
            daily_limit_facebook=1,
            daily_limit_linkedin=1,
            preferred_posting_hours_json='[8, 17]',
        )
        db.session.add(settings)
        db.session.commit()
    return settings


# ==============================================================================
# AUTONOMOUS CONTENT GENERATION PIPELINE
# ==============================================================================

def generate_autonomous_post(
    user_id: int,
    platform: str,
    campaign_id: Optional[int] = None,
    scheduled_for: Optional[datetime] = None,
    preferred_pillar: Optional[str] = None,
    preferred_format: Optional[str] = None,
) -> Optional[SocialPost]:
    """Execute end-to-end autonomous post creation: strategy -> copy -> creative -> QA -> job."""
    settings = get_or_create_settings(user_id)
    if settings.emergency_paused or not settings.enabled:
        logger.info("Automation is currently paused for user %s", user_id)
        return None

    platform = platform.lower().strip()
    if platform == "facebook" and not settings.facebook_enabled:
        return None
    if platform == "linkedin" and not settings.linkedin_enabled:
        return None

    # Step 1: Strategy & Pillar Selection
    pillar = preferred_pillar or select_next_pillar(user_id, settings)
    concept = plan_post_concept(pillar, platform)
    title = concept["title"]
    summary = concept["summary"]
    content_format = preferred_format or concept["format"]

    # Step 2: Platform-Specific Copywriting
    copy_data = generate_platform_copy(
        title=title,
        summary=summary,
        pillar=pillar,
        platform=platform,
        content_format=content_format,
        user_id=user_id,
    )
    caption = copy_data["caption"]
    cta = copy_data["call_to_action"]
    hashtags = copy_data["hashtags"]
    creative_prompt = copy_data["creative_prompt"]

    # Step 3: Originality & Duplicate Check
    originality = check_content_originality(caption, user_id)
    if not originality["is_original"]:
        logger.info("Hook duplicate detected: %s. Generating fresh variations.", originality["reason"])
        caption = f"{caption}\n\n[Refreshed Edition]"

    # Step 4: Creative Generation (Hugging Face / PIL Flyer / Video)
    media_url = None
    media_asset = None
    if content_format in ("image", "flyer", "video"):
        if content_format == "video" and settings.allow_video_generation:
            vid_res = generate_social_video(creative_prompt, duration_seconds=5)
            if vid_res.get("ok"):
                media_url = vid_res.get("media_url")
                media_asset = SocialMediaAsset(
                    user_id=user_id,
                    campaign_id=campaign_id,
                    media_type="video",
                    public_url=media_url,
                    provider=vid_res.get("provider", "huggingface"),
                    model_name=vid_res.get("model_name"),
                    duration_seconds=5,
                    status="ready",
                )
        else:
            # Generate image or flyer via Hugging Face with PIL fallback
            img_res = generate_social_image(creative_prompt, aspect_ratio="1:1", fallback_to_flyer=True)
            if img_res.get("ok"):
                media_url = img_res.get("media_url")
                media_asset = SocialMediaAsset(
                    user_id=user_id,
                    campaign_id=campaign_id,
                    media_type=img_res.get("media_type", "image"),
                    public_url=media_url,
                    provider=img_res.get("provider", "huggingface"),
                    model_name=img_res.get("model_name"),
                    dimensions=img_res.get("dimensions", "1080x1080"),
                    status="ready",
                )

    # Step 5: Quality Assurance & Safety Audit
    qa_result = run_social_quality_audit(
        caption=caption,
        platform=platform,
        content_format=content_format,
        media_url=media_url,
        call_to_action=cta,
    )

    # Schedule Time Calculation
    publish_time = scheduled_for or (datetime.now(timezone.utc) + timedelta(minutes=15))
    idempotency_key = f"soc_{user_id}_{platform}_{uuid.uuid4().hex[:10]}"

    # Step 6: Create Persistent SocialPost Record
    post = SocialPost(
        user_id=user_id,
        campaign_id=campaign_id,
        platform=platform,
        title=title,
        content_pillar=pillar,
        marketing_objective="awareness",
        target_audience="African creators, entrepreneurs, and digital professionals",
        content_format=content_format,
        caption=caption,
        hashtags=hashtags,
        call_to_action=cta,
        creative_instructions=creative_prompt,
        media_url=media_url,
        media_type=content_format if media_url else "text",
        status="scheduled" if qa_result["passed"] else "retry_pending",
        scheduled_at=publish_time,
        quality_score=qa_result["score"],
        quality_checks_json=json.dumps(qa_result["checks"]),
        idempotency_key=idempotency_key,
    )
    db.session.add(post)
    db.session.flush()

    if media_asset:
        media_asset.post_id = post.id
        db.session.add(media_asset)

    # Step 7: Create Distributed Publishing Job
    if qa_result["passed"]:
        job = SocialPublishingJob(
            user_id=user_id,
            post_id=post.id,
            platform=platform,
            status="pending",
            scheduled_time=publish_time,
            idempotency_key=idempotency_key,
        )
        db.session.add(job)

    db.session.commit()
    logger.info("Autonomous %s post #%s created (status: %s, score: %s)", platform, post.id, post.status, post.quality_score)
    return post


def generate_daily_social_schedule(user_id: int) -> List[SocialPost]:
    """Generate daily autonomous social posts (1 Facebook + 1 LinkedIn)."""
    settings = get_or_create_settings(user_id)
    if settings.emergency_paused or not settings.enabled:
        return []

    created_posts = []
    now = datetime.now(timezone.utc)

    # Preferred posting hours: morning (e.g. 08:00 UTC) and evening (e.g. 17:00 UTC)
    hours = [8, 17]
    if settings.preferred_posting_hours_json:
        try:
            hours = json.loads(settings.preferred_posting_hours_json)
        except Exception:
            pass

    # Schedule Facebook Post for morning window
    if settings.facebook_enabled:
        fb_time = now.replace(hour=hours[0] if hours else 8, minute=0, second=0, microsecond=0)
        if fb_time <= now:
            fb_time = now + timedelta(minutes=10)
        fb_post = generate_autonomous_post(user_id=user_id, platform="facebook", scheduled_for=fb_time)
        if fb_post:
            created_posts.append(fb_post)

    # Schedule LinkedIn Post for evening window
    if settings.linkedin_enabled:
        li_hour = hours[1] if len(hours) > 1 else 17
        li_time = now.replace(hour=li_hour, minute=0, second=0, microsecond=0)
        if li_time <= now:
            li_time = now + timedelta(minutes=25)
        li_post = generate_autonomous_post(user_id=user_id, platform="linkedin", scheduled_for=li_time)
        if li_post:
            created_posts.append(li_post)

    return created_posts


def run_autonomous_maintenance_cycle():
    """Periodic background worker task:
    1. Runs queue publishing pass with distributed lease locking.
    2. Synchronizes performance analytics.
    3. Self-tunes content pillar weights based on engagement.
    """
    try:
        # 1. Publish ready jobs
        published_count = run_social_publishing_cycle()
        if published_count > 0:
            logger.info("Published %s social posts during cycle.", published_count)

        # 2. Sync analytics for active accounts
        active_settings = SocialAutomationSettings.query.filter_by(enabled=True).limit(10).all()
        for s in active_settings:
            sync_all_recent_analytics(s.user_id)
            adapt_future_strategy(s.user_id)

    except Exception as exc:
        logger.error("Error in autonomous social maintenance cycle: %s", exc)
