from flask import has_app_context

from models import PricingConfig


DEFAULT_PRICING = {
    "cheap_video_cost": 5,
    "kling_video_cost": 10,
    "kling_credits_per_second": 1.5,
    "image_to_video_cost": 15,
}


def get_pricing(key):
    if key not in DEFAULT_PRICING:
        raise KeyError(key)
    if not has_app_context():
        return DEFAULT_PRICING[key]
    row = PricingConfig.query.filter_by(key=key).first()
    return row.value if row else DEFAULT_PRICING[key]

# Subscription prices are stored in kobo (NGN minor units) so Paystack,
# public pricing pages, and verification all use one source of truth.
DEFAULT_SUBSCRIPTION_PRICING = {
    "creator_monthly_kobo": 1_000_000,
    "creator_annual_kobo": 10_000_000,
    "studio_monthly_kobo": 1_500_000,
    "studio_annual_kobo": 15_000_000,
    "director_monthly_kobo": 2_500_000,
    "director_annual_kobo": 25_000_000,
}


def get_subscription_pricing():
    """Return current subscription prices in kobo, falling back to launch prices."""
    if not has_app_context():
        return dict(DEFAULT_SUBSCRIPTION_PRICING)
    values = dict(DEFAULT_SUBSCRIPTION_PRICING)
    for key in values:
        row = PricingConfig.query.filter_by(key=key).first()
        if row is not None:
            values[key] = int(round(row.value))
    return values


def get_subscription_payment_details(amount):
    """Resolve a verified Paystack amount to its tier, credit grant and term."""
    prices = get_subscription_pricing()
    details = {
        prices["creator_monthly_kobo"]: ("creator", 100, False),
        prices["creator_annual_kobo"]: ("creator", 1200, True),
        prices["studio_monthly_kobo"]: ("studio", 300, False),
        prices["studio_annual_kobo"]: ("studio", 3600, True),
        prices["director_monthly_kobo"]: ("director", 1000, False),
        prices["director_annual_kobo"]: ("director", 12000, True),
    }
    # Keep accepting the old Creator annual checkout amount only when it
    # does not collide with a different currently configured plan price.
    if 11_000_000 not in details:
        details[11_000_000] = ("creator", 1200, True)
    return details.get(amount)
