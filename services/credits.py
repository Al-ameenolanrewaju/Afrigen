"""Shared plan / credit / limit logic for video & image generation.

These pure helpers operate on a `User` instance plus the SQLAlchemy session and
encode exactly one set of rules, so the website (`routes/main.py`) and the
Telegram bot (`services/telegram_bot.py`) charge and gate generations identically.

- Spark/free plan: monthly free quota (2 images, 1 free video allowance); no credits.
- Creator/Pro plan (tier 1): pays credits per generation.
- Studio plan (tier 2): pays credits; image-to-video unlocked.
- Director plan (tier 3): pays credits; image-to-video unlocked.
- Any other plan is blocked.

Callers are responsible for committing the session after a charge.
"""
from datetime import date

from models import db, User, CreditLedger
from services.video import text_to_video_cost

# Flat credit price of an image generation for paid users (mirrors routes/main.py).
IMAGE_COST = 2
IMAGE_TO_VIDEO_COST = 10

# Free-tier total monthly allowances.
FREE_TOTAL_IMAGES = 2
FREE_MONTHLY_VIDEOS = 1

# Monthly credit grants per plan tier
PLAN_CREDIT_GRANTS = {'creator': 100, 'pro': 100, 'studio': 300, 'director': 1000}

# Plan tier ordering (spark/free = 0, creator/pro = 1, studio = 2, director = 3)
PLAN_TIER_ORDER = {'spark': 0, 'free': 0, 'creator': 1, 'pro': 1, 'studio': 2, 'director': 3}


def is_paid_plan(plan: str) -> bool:
    """Return True if the plan is any paid tier (creator, pro, studio, director)."""
    return plan in ('pro', 'creator', 'studio', 'director')


def get_tier(plan: str) -> int:
    """Return the numeric tier level for a plan."""
    return PLAN_TIER_ORDER.get(plan, 0)


def deduct_credits_atomic(user_id, amount, reason="Credit deduction"):
    """
    Atomically deduct credits from a user using a SQL-level decrement
    with a conditional check (credits >= amount) to prevent race conditions.
    Returns (success, error_message).
    """
    if amount <= 0:
        return True, None

    result = db.session.query(User).filter(
        User.id == user_id,
        User.credits >= amount
    ).update(
        {User.credits: User.credits - amount},
        synchronize_session='fetch'
    )
    if result > 0:
        db.session.add(CreditLedger(user_id=user_id, delta=-amount, reason=reason))
        return True, None
    return False, "Not enough credits."


def video_gate(user, style, extended=False, duration="5"):
    """Check whether `user` may generate a video.

    Returns (ok, error_message, cost). `cost` is the credits a
    paid user will be charged on success; it is irrelevant for free/spark users.
    """
    duration = str(duration or "5")
    if duration not in {"5", "10", "15", "20"}:
        duration = "5"
    if not extended and duration in {"10", "15", "20"}:
        extended = True
    cost = text_to_video_cost(style, extended=extended, duration=duration)

    plan = getattr(user, 'plan', 'free') or 'free'

    # Spark / free tier — check free video allowance
    if not is_paid_plan(plan):
        if (getattr(user, 'free_video_allowance', 0) or 0) > 0:
            return (True, None, 0)
        return (False, "Video generation is a Pro feature. Upgrade to create videos!", cost)

    # Paid tiers — check credits
    if (user.credits or 0) < cost:
        return (False,
                "Not enough credits! Please renew your plan at afrigen.com.ng/upgrade",
                cost)
    return (True, None, cost)


def image_gate(user):
    """Check whether `user` may generate an image. Returns (ok, error_message)."""
    plan = getattr(user, 'plan', 'free') or 'free'

    # Spark / free tier
    if not is_paid_plan(plan):
        if (user.monthly_images_used or 0) >= FREE_TOTAL_IMAGES:
            return (False,
                    "You've used your 2 free images. Upgrade to Pro for more!")
        return (True, None)

    # Paid tiers — check credits or fallback_credits
    if (user.credits or 0) >= IMAGE_COST:
        return (True, None)
    if (getattr(user, 'fallback_credits', 0) or 0) >= IMAGE_COST:
        return (True, None)
    return (False,
            "Not enough credits! Please renew your plan at afrigen.com.ng/upgrade")


def record_credit_change(user, delta, reason):
    db.session.add(CreditLedger(user_id=user.id, delta=delta, reason=reason))


def charge_video(user, cost, reason="Video generation"):
    """Record a successful video generation for a paid user or free user with free video allowance."""
    plan = getattr(user, 'plan', 'free') or 'free'

    if not is_paid_plan(plan):
        if (getattr(user, 'free_video_allowance', 0) or 0) > 0:
            user.free_video_allowance = max(0, user.free_video_allowance - 1)
            record_credit_change(user, 0, f"Free video allowance used (Remaining: {user.free_video_allowance})")
        return

    ok, err = deduct_credits_atomic(user.id, cost, reason)
    if not ok:
        # Fallback if uncommitted changes or in-memory user
        user.credits = max(0, (user.credits or 0) - cost)
        record_credit_change(user, -cost, reason)


def image_to_video_gate(user):
    """Check whether a Studio/Director user may generate a video from an image."""
    plan = getattr(user, 'plan', 'free') or 'free'
    tier = get_tier(plan)
    if tier < 2:
        return False, "Image to Video requires Studio or Director plan!"
    if (user.credits or 0) < IMAGE_TO_VIDEO_COST:
        return False, f"You need at least {IMAGE_TO_VIDEO_COST} credits for image-to-video!"
    return True, None


def charge_image_to_video(user, reason="Image-to-video generation"):
    """Deduct image-to-video credits without allowing a negative balance."""
    plan = getattr(user, 'plan', 'free') or 'free'
    if is_paid_plan(plan):
        ok, err = deduct_credits_atomic(user.id, IMAGE_TO_VIDEO_COST, reason)
        if not ok:
            user.credits = max(0, (user.credits or 0) - IMAGE_TO_VIDEO_COST)
            record_credit_change(user, -IMAGE_TO_VIDEO_COST, reason)


def refund_video(user, cost, reason="Video generation refund"):
    """Refund a failed video generation exactly once."""
    plan = getattr(user, 'plan', 'free') or 'free'
    if not is_paid_plan(plan):
        user.free_video_allowance = (getattr(user, 'free_video_allowance', 0) or 0) + 1
        record_credit_change(user, 0, reason)
    else:
        user.credits = (user.credits or 0) + cost
        record_credit_change(user, cost, reason)


def charge_image(user, reason="Image generation"):
    """Record a successful image generation (free: bump counter, paid: spend credits)."""
    plan = getattr(user, 'plan', 'free') or 'free'
    if not is_paid_plan(plan):
        user.monthly_images_used = (user.monthly_images_used or 0) + 1
    else:
        ok, err = deduct_credits_atomic(user.id, IMAGE_COST, reason)
        if not ok:
            user.credits = max(0, (user.credits or 0) - IMAGE_COST)
            record_credit_change(user, -IMAGE_COST, reason)
