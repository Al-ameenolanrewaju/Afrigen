"""Shared plan / credit / limit logic for video & image generation.

These pure helpers operate on a `User` instance plus the SQLAlchemy session and
encode exactly one set of rules, so the website (`routes/main.py`) and the
Telegram bot (`bot/bot.py`) charge and gate generations identically.

- Free plan: capped at 3 videos and 2 images per calendar month (counters reset
  on the first generation of a new month).
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

# Free-tier monthly allowances.
FREE_MONTHLY_VIDEOS = 3
FREE_MONTHLY_IMAGES = 2


def _new_month(last_reset):
    """True if `last_reset` is missing or in a previous month from today."""
    today = date.today()
    return last_reset is None or (last_reset.year, last_reset.month) != (today.year, today.month)


def video_gate(user, style, extended=False, duration="5"):
    """Check whether `user` may generate a video.

    Returns (ok, error_message, cost). On a free user this may reset the monthly
    counter as a side effect (committed by the caller). `cost` is the credits a
    Pro user will be charged on success; it is irrelevant for free users.
    """
    duration = str(duration or "5")
    if duration not in {"5", "10", "15", "20"}:
        duration = "5"
    if not extended and duration in {"10", "15", "20"}:
        extended = True
    cost = text_to_video_cost(style, extended=extended, duration=duration)

    if user.plan == 'free':
        if _new_month(user.last_video_reset):
            user.monthly_videos_used = 0
            user.last_video_reset = date.today()
            db.session.commit()
        if (user.monthly_videos_used or 0) >= FREE_MONTHLY_VIDEOS:
            return (False,
                    "You've used your 3 free videos this month. Upgrade to Pro for more!",
                    cost)
        return (True, None, cost)

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
        if _new_month(user.last_image_reset):
            user.monthly_images_used = 0
            user.last_image_reset = date.today()
            db.session.commit()
        if (user.monthly_images_used or 0) >= FREE_MONTHLY_IMAGES:
            return (False,
                    "You've used your 2 free images this month. Upgrade to Pro for more!")
        return (True, None)

    if user.plan == 'pro':
        if (user.credits or 0) < IMAGE_COST:
            return (False,
                    "Not enough credits! Please renew your Pro plan at afrigen.com.ng/upgrade")
        return (True, None)

    return (False, "Your account is restricted.")


def charge_video(user, cost):
    """Record a successful video generation (free: bump counter, pro: spend credits)."""
    if user.plan == 'free':
        user.monthly_videos_used = (user.monthly_videos_used or 0) + 1
    elif user.plan == 'pro':
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
