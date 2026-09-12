from flask import has_app_context

from models import PricingConfig


DEFAULT_PRICING = {
    "cheap_video_cost": 5,
    "kling_video_cost": 10,
    "kling_credits_per_second": 1.5,
    "image_to_video_cost": 15,
}


def get_pricing(key):
    if not has_app_context():
        return DEFAULT_PRICING[key]
    row = PricingConfig.query.filter_by(key=key).first()
    return row.value if row else DEFAULT_PRICING[key]