"""Shared plan / credit / limit logic for video & image generation.

These pure helpers operate on a `User` instance plus the SQLAlchemy session and
encode exactly one set of rules, so the website (`routes/main.py`) and the
Telegram bot (`bot/bot.py`) charge and gate generations identically.

- Free plan: video generation is unavailable; image generation is capped at 2 images (lifetime limit).
- Pro plan: pays credits per generation (video cost depends on the model, image
  is a flat 2 credits).
- Any other plan (e.g. "banned") is blocked.

Callers are responsible for committing the session after a charge.
"""
from datetime import date

from models import db, User, CreditLedger
from services.video import text_to_video_cost

# Flat credit price of an image generation for Pro users (mirrors routes/main.py).
IMAGE_COST = 2
IMAGE_TO_VIDEO_COST = 10

# Free-tier total (lifetime) allowances.
FREE_TOTAL_IMAGES = 2


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
    Pro user will be charged on success; it is irrelevant for free users.
    """
    duration = str(duration or "5")
    if duration not in {"5", "10", "15", "20"}:
        duration = "5"
    if not extended and duration in {"10", "15", "20"}:
        extended = True
    cost = text_to_video_cost(style, extended=extended, duration=duration)

    if user.plan == 'free':
        if (getattr(user, 'free_video_allowance', 0) or 0) > 0:
            return (True, None, 0)
        return (False, "Video generation is a Pro feature. Upgrade to create videos!", cost)

    if user.plan == 'pro':
        if (user.credits or 0) < cost:
            return (False,
                    "Not enough credits! Please renew your Pro plan at afrigen.com.ng/upgrade",
                    cost)
        return (True, None, cost)

    return (False, "Your account is restricted.", cost)


def image_gate(user):
    """Check whether `user` may generate an image. Returns (ok, error_message)."""
    if user.plan == 'free':
        if (user.monthly_images_used or 0) >= FREE_TOTAL_IMAGES:
            return (False,
                    "You've used your 2 free images. Upgrade to Pro for more!")
        return (True, None)

    if user.plan == 'pro':
        if (user.credits or 0) < IMAGE_COST:
            return (False,
                    "Not enough credits! Please renew your Pro plan at afrigen.com.ng/upgrade")
        return (True, None)

    return (False, "Your account is restricted.")


def record_credit_change(user, delta, reason):
    db.session.add(CreditLedger(user_id=user.id, delta=delta, reason=reason))


def charge_video(user, cost, reason="Video generation"):
    """Record a successful video generation for a Pro user or free user with free video allowance."""
    if user.plan == 'free' and (getattr(user, 'free_video_allowance', 0) or 0) > 0:
        user.free_video_allowance = max(0, user.free_video_allowance - 1)
        record_credit_change(user, 0, f"Free video allowance used (Remaining: {user.free_video_allowance})")
        return

    if user.plan == 'pro':
        ok, err = deduct_credits_atomic(user.id, cost, reason)
        if not ok:
            # Fallback if uncommitted changes or in-memory user
            user.credits = max(0, (user.credits or 0) - cost)
            record_credit_change(user, -cost, reason)


def image_to_video_gate(user):
    """Check whether a Pro user may generate a video from an image."""
    if user.plan != 'pro':
        return False, "Image to Video is a Pro feature!"
    if (user.credits or 0) < IMAGE_TO_VIDEO_COST:
        return False, f"You need at least {IMAGE_TO_VIDEO_COST} credits for image-to-video!"
    return True, None


def charge_image_to_video(user, reason="Image-to-video generation"):
    """Deduct image-to-video credits without allowing a negative balance."""
    if user.plan == 'pro':
        ok, err = deduct_credits_atomic(user.id, IMAGE_TO_VIDEO_COST, reason)
        if not ok:
            user.credits = max(0, (user.credits or 0) - IMAGE_TO_VIDEO_COST)
            record_credit_change(user, -IMAGE_TO_VIDEO_COST, reason)


def refund_video(user, cost, reason="Video generation refund"):
    """Refund a failed video generation exactly once."""
    if user.plan == 'free':
        user.free_video_allowance = (getattr(user, 'free_video_allowance', 0) or 0) + 1
        record_credit_change(user, 0, reason)
    elif user.plan == 'pro':
        user.credits = (user.credits or 0) + cost
        record_credit_change(user, cost, reason)


def charge_image(user, reason="Image generation"):
    """Record a successful image generation (free: bump counter, pro: spend credits)."""
    if user.plan == 'free':
        user.monthly_images_used = (user.monthly_images_used or 0) + 1
    elif user.plan == 'pro':
        ok, err = deduct_credits_atomic(user.id, IMAGE_COST, reason)
        if not ok:
            user.credits = max(0, (user.credits or 0) - IMAGE_COST)
            record_credit_change(user, -IMAGE_COST, reason)
