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

from models import db
from services.video import text_to_video_cost

# Flat credit price of an image generation for Pro users (mirrors routes/main.py).
IMAGE_COST = 2

# Free-tier total (lifetime) allowances.
FREE_TOTAL_IMAGES = 2


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


def charge_video(user, cost):
    """Record a successful video generation for a Pro user."""
    if user.plan == 'pro':
        user.credits = (user.credits or 0) - cost
        if user.credits < 0:
            user.credits = 0


def charge_image(user):
    """Record a successful image generation (free: bump counter, pro: spend credits)."""
    if user.plan == 'free':
        user.monthly_images_used = (user.monthly_images_used or 0) + 1
    elif user.plan == 'pro':
        user.credits = (user.credits or 0) - IMAGE_COST
        if user.credits < 0:
            user.credits = 0
