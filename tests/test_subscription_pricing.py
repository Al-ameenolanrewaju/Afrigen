import pytest

from app import app
from models import db, PricingConfig
from services.pricing import (
    DEFAULT_SUBSCRIPTION_PRICING,
    get_subscription_payment_details,
    get_subscription_pricing,
)


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_subscription_prices_use_current_defaults():
    with app.app_context():
        assert get_subscription_pricing() == DEFAULT_SUBSCRIPTION_PRICING


def test_subscription_prices_read_saved_admin_values():
    with app.app_context():
        db.session.add(PricingConfig(key="creator_monthly_kobo", value=1_250_000))
        db.session.commit()
        assert get_subscription_pricing()["creator_monthly_kobo"] == 1_250_000
        assert get_subscription_pricing()["studio_monthly_kobo"] == 1_500_000


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (1_000_000, ("creator", 100, False)),
        (10_000_000, ("creator", 1200, True)),
        (1_500_000, ("studio", 300, False)),
        (15_000_000, ("studio", 3600, True)),
        (2_500_000, ("director", 1000, False)),
        (25_000_000, ("director", 12000, True)),
        (11_000_000, ("creator", 1200, True)),
    ],
)
def test_subscription_payment_amount_mapping(amount, expected):
    with app.app_context():
        assert get_subscription_payment_details(amount) == expected


def test_unknown_subscription_amount_is_rejected():
    with app.app_context():
        assert get_subscription_payment_details(999_999) is None


def test_custom_subscription_price_is_used_for_payment_mapping():
    with app.app_context():
        db.session.add(PricingConfig(key="studio_monthly_kobo", value=1_750_000))
        db.session.commit()
        assert get_subscription_payment_details(1_750_000) == ("studio", 300, False)
        assert get_subscription_payment_details(1_500_000) is None
