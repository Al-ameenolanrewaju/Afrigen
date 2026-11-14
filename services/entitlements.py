"""Centralized Entitlements and Feature Access Service for Afrigen 2.0.

Encodes exact feature gates based on plan tiers:
- Spark / Free (Tier 0): 2 images/month, 1 free video token, basic tools.
- Creator / Pro (Tier 1): Full Kling video, unlimited image generation with credits, campaigns.
- Studio (Tier 2): All Tier 1 features + Image-to-Video generation, 300 credits/mo, advanced marketing.
- Director (Tier 3): All Tier 2 features + Movie Studio, Kling Pro cinematic scenes, 1000 credits/mo, full rendering pipeline.
- Admin: Full bypass access to all capabilities.
"""
from services.credits import get_tier, is_paid_plan

# Dedicated Movie Studio tier threshold: Director plan is Tier 3
MOVIE_STUDIO_MIN_TIER = 3
IMAGE_TO_VIDEO_MIN_TIER = 2

ADMIN_EMAILS = {"oadedamola07@gmail.com"}


def is_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'email', '') in ADMIN_EMAILS


def can_access_movie_studio(user) -> bool:
    """Check if the user is authorized for the full AI Movie Studio production environment."""
    if not user or not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    return get_tier(getattr(user, 'plan', 'free')) >= MOVIE_STUDIO_MIN_TIER


def can_access_image_to_video(user) -> bool:
    """Check if the user can generate videos from an existing image."""
    if not user or not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    return get_tier(getattr(user, 'plan', 'free')) >= IMAGE_TO_VIDEO_MIN_TIER


def get_user_entitlements(user) -> dict:
    """Return a dictionary of all active capabilities for frontend and API gates."""
    plan = getattr(user, 'plan', 'free') if user and user.is_authenticated else 'free'
    tier = get_tier(plan)
    admin = is_admin(user)

    return {
        "tier": tier,
        "plan": plan.upper(),
        "is_admin": admin,
        "is_paid": is_paid_plan(plan) or admin,
        "movie_studio": can_access_movie_studio(user),
        "image_to_video": can_access_image_to_video(user),
        "advanced_rendering": tier >= 3 or admin,
        "voiceover_synthesis": is_paid_plan(plan) or admin,
        "commercial_license": is_paid_plan(plan) or admin,
        "priority_queue": tier >= 2 or admin,
        "max_movie_projects": 25 if tier >= 3 or admin else 0,
        "max_video_duration": "10s" if is_paid_plan(plan) or admin else "5s",
    }

