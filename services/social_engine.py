"""Master Social Automation Orchestrator for Afrigen AI.

Brings together content planning, Hugging Face creative generation, platform-specific
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
    check_content_originality, plan_weekly_content, normalize_pillar
)
from services.social_creative_hf import (
    generate_social_image, generate_social_video, validate_media_asset
)
from services.social_qa import run_social_quality_audit, attempt_qa_auto_correction
from services.social_publisher import run_social_publishing_cycle
from services.social_analytics import (
    sync_all_recent_analytics, adapt_future_strategy, get_performance_guidance
)

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
            preferred_posting_hours_json='[6, 6]',
        )
        db.session.add(settings)
        db.session.commit()
    elif settings.preferred_posting_hours_json in (None, '', '[8, 17]', '[6, 17]'):
        # Migrate known legacy defaults to 07:00 WAT for both platforms.
        # Preserve any other explicitly customized posting hours.
        settings.preferred_posting_hours_json = '[6, 6]'
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
    marketing_objective: str = "awareness",
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

    # Step 1: Strategy, Pillar Selection & Performance Intelligence
    guidance = get_performance_guidance(user_id)
    raw_pillar = preferred_pillar or select_next_pillar(user_id, settings)
    pillar = normalize_pillar(raw_pillar)

    concept = plan_post_concept(
        pillar=pillar,
        platform=platform,
        user_id=user_id,
        marketing_objective=marketing_objective,
        analytics_guidance=guidance,
    )
    title = concept["title"]
    summary = concept["summary"]
    content_format = preferred_format or concept["format"]
    creative_type = concept.get("creative_type", "educational_graphic")

    # Step 2: Platform-Specific Copywriting
    copy_data = generate_platform_copy(
        title=title,
        summary=summary,
        pillar=pillar,
        platform=platform,
        content_format=content_format,
        user_id=user_id,
        analytics_guidance=guidance,
    )
    caption = copy_data["caption"]
    cta = copy_data["call_to_action"]
    hashtags = copy_data["hashtags"]
    creative_prompt = copy_data["creative_prompt"]

    # Step 3: Originality & Duplicate Check
    originality = check_content_originality(caption, user_id, platform=platform)
    if not originality["is_original"]:
        logger.info("Hook duplicate detected: %s. Generating fresh variations.", originality["reason"])
        # Re-generate copy with explicit fresh angle
        fresh_copy = generate_platform_copy(
            title=f"New Perspective: {title}",
            summary=summary,
            pillar=pillar,
            platform=platform,
            content_format=content_format,
            user_id=user_id,
        )
        caption = fresh_copy["caption"]
        cta = fresh_copy["call_to_action"]
        hashtags = fresh_copy["hashtags"]

    # Step 4: Creative Generation via Hugging Face
    media_url = None
    media_asset = None
    image_model = settings.hf_image_model or "black-forest-labs/FLUX.1-schnell"
    video_model = settings.hf_video_model or "damo-vilab/text-to-video-ms-1.7m"

    if content_format in ("image", "flyer", "video"):
        if content_format == "video" and settings.allow_video_generation:
            vid_res = generate_social_video(
                prompt=creative_prompt,
                duration_seconds=5,
                model_override=video_model,
            )
            if vid_res.get("ok"):
                media_url = vid_res.get("media_url")
                media_asset = SocialMediaAsset(
                    user_id=user_id,
                    campaign_id=campaign_id,
                    media_type="video",
                    public_url=media_url,
                    provider=vid_res.get("provider", "huggingface"),
                    model_name=vid_res.get("model_name", video_model),
                    duration_seconds=5,
                    status="ready",
                )
            else:
                logger.warning("Hugging Face video generation failed: %s. Falling back to branded graphic.", vid_res.get("error"))
                # When video fails, switch format to high-definition graphic so post isn't blocked
                content_format = "image"

        if content_format in ("image", "flyer"):
            img_res = generate_social_image(
                prompt=creative_prompt,
                aspect_ratio="1:1",
                model_override=image_model,
                creative_type=creative_type,
                fallback_to_flyer=True,
            )
            if img_res.get("ok"):
                media_url = img_res.get("media_url")
                media_asset = SocialMediaAsset(
                    user_id=user_id,
                    campaign_id=campaign_id,
                    media_type=img_res.get("media_type", "image"),
                    public_url=media_url,
                    provider=img_res.get("provider", "huggingface"),
                    model_name=img_res.get("model_name", image_model),
                    dimensions=img_res.get("dimensions", "1080x1080"),
                    status="ready",
                )

    # Step 5: Quality Assurance & Safety Audit with Auto-Correction and Regeneration
    qa_result = run_social_quality_audit(
        caption=caption,
        platform=platform,
        content_format=content_format,
        media_url=media_url,
        call_to_action=cta,
    )

    # Attempt automatic correction if initial QA was borderline
    if not qa_result["passed"]:
        correction = attempt_qa_auto_correction(caption, platform, qa_result["flags"], call_to_action=cta)
        if correction.get("modified"):
            caption = correction["corrected_caption"]
            qa_result = run_social_quality_audit(
                caption=caption,
                platform=platform,
                content_format=content_format,
                media_url=media_url,
                call_to_action=cta,
            )

    # If still failing due to content issues (e.g. non-compliant phrase or fake claims), regenerate
    if not qa_result["passed"] and any("non-compliant" in f or "fabricated" in f or "invented" in f for f in qa_result["flags"]):
        logger.warning("QA failed with critical flags: %s. Triggering safe copy regeneration.", qa_result["flags"])
        safe_copy = generate_platform_copy(
            title=title,
            summary=summary,
            pillar=pillar,
            platform=platform,
            content_format=content_format,
            user_id=user_id,
        )
        caption = safe_copy["caption"]
        qa_result = run_social_quality_audit(
            caption=caption,
            platform=platform,
            content_format=content_format,
            media_url=media_url,
            call_to_action=safe_copy["call_to_action"],
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
        marketing_objective=marketing_objective,
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

    # Step 7: Create Distributed Publishing Job (only when QA passes)
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

    # Posting times are stored in UTC: 07:00 WAT = 06:00 UTC.
    # The first slot is Facebook and the second is LinkedIn.
    hours = [6, 6]
    if settings.preferred_posting_hours_json:
        try:
            hours = json.loads(settings.preferred_posting_hours_json)
        except Exception:
            pass

    # Both platforms use their configured daily slots (07:00 WAT by default).
    # If the planner runs after a slot, schedule that platform for the next day.
    if settings.facebook_enabled:
        fb_hour = hours[0] if hours else 6
        fb_time = now.replace(hour=fb_hour, minute=0, second=0, microsecond=0)
        if fb_time <= now:
            fb_time += timedelta(days=1)
        fb_post = generate_autonomous_post(user_id=user_id, platform="facebook", scheduled_for=fb_time)
        if fb_post:
            created_posts.append(fb_post)

    if settings.linkedin_enabled:
        li_hour = hours[1] if len(hours) > 1 else (hours[0] if hours else 6)
        li_time = now.replace(hour=li_hour, minute=0, second=0, microsecond=0)
        if li_time <= now:
            li_time += timedelta(days=1)
        li_post = generate_autonomous_post(user_id=user_id, platform="linkedin", scheduled_for=li_time)
        if li_post:
            created_posts.append(li_post)

    return created_posts


def generate_weekly_social_schedule(user_id: int, start_date: Optional[datetime] = None) -> List[SocialPost]:
    """Generate a cohesive 7-day scheduled content calendar balancing all 7 content pillars."""
    settings = get_or_create_settings(user_id)
    if settings.emergency_paused or not settings.enabled:
        return []

    guidance = get_performance_guidance(user_id)
    planned = plan_weekly_content(
        user_id=user_id,
        start_date=start_date,
        posts_per_day=1,
        marketing_objective="awareness",
        analytics_guidance=guidance,
    )

    created_posts = []
    for item in planned:
        post = generate_autonomous_post(
            user_id=user_id,
            platform=item["platform"],
            scheduled_for=item["scheduled_time"],
            preferred_pillar=item["pillar"],
            preferred_format=item["format"],
            marketing_objective=item.get("marketing_objective", "awareness"),
        )
        if post:
            created_posts.append(post)

    return created_posts


def generate_campaign_posts(campaign_id: int, user_id: int, posts_count: int = 4) -> List[SocialPost]:
    """Generate cohesive multi-platform scheduled posts for a marketing campaign."""
    campaign = SocialCampaign.query.filter_by(id=campaign_id, user_id=user_id).first()
    if not campaign:
        return []

    settings = get_or_create_settings(user_id)
    platforms = ["facebook", "linkedin"]
    if campaign.platforms_json:
        try:
            platforms = json.loads(campaign.platforms_json)
        except Exception:
            pass

    start_date = campaign.start_date or (datetime.now(timezone.utc) + timedelta(hours=1))
    end_date = campaign.end_date or (start_date + timedelta(days=7))
    total_span_seconds = max(3600, int((end_date - start_date).total_seconds()))
    step_seconds = max(3600, total_span_seconds // max(1, posts_count))

    created_posts = []
    objective = campaign.objective or "awareness"
    target_audience = campaign.target_audience or "African creators and businesses"

    for i in range(posts_count):
        platform = platforms[i % len(platforms)]
        post_time = start_date + timedelta(seconds=i * step_seconds)
        pillar = select_next_pillar(user_id, settings)
        fmt = "video" if (i % 2 == 0 and settings.allow_video_generation) else ("flyer" if i % 2 == 1 else "image")

        post = generate_autonomous_post(
            user_id=user_id,
            platform=platform,
            campaign_id=campaign.id,
            scheduled_for=post_time,
            preferred_pillar=pillar,
            preferred_format=fmt,
            marketing_objective=objective,
        )
        if post:
            post.marketing_objective = objective
            post.target_audience = target_audience
            db.session.commit()
            created_posts.append(post)

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
