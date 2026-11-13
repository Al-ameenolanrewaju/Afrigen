import pytest
from datetime import datetime, timezone
from app import app
from models import db, User, Notification, NewsletterCampaign
from services.credits import is_paid_plan, get_tier, image_to_video_gate, video_gate, image_gate


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_tier_resolution_and_paid_helpers():
    assert not is_paid_plan("free")
    assert not is_paid_plan("spark")
    assert is_paid_plan("creator")
    assert is_paid_plan("pro")
    assert is_paid_plan("studio")
    assert is_paid_plan("director")

    assert get_tier("spark") == 0
    assert get_tier("free") == 0
    assert get_tier("creator") == 1
    assert get_tier("pro") == 1
    assert get_tier("studio") == 2
    assert get_tier("director") == 3


def test_image_to_video_tier_enforcement():
    with app.app_context():
        free_user = User(username="free1", email="f1@ex.com", plan="free", credits=50)
        creator_user = User(username="cr1", email="c1@ex.com", plan="creator", credits=50)
        studio_user = User(username="st1", email="s1@ex.com", plan="studio", credits=50)
        director_user = User(username="dir1", email="d1@ex.com", plan="director", credits=50)

        # Free & Creator cannot use image-to-video
        ok, err = image_to_video_gate(free_user)
        assert not ok
        assert "Studio or Director" in err

        ok, err = image_to_video_gate(creator_user)
        assert not ok
        assert "Studio or Director" in err

        # Studio & Director can use image-to-video if credits available
        ok, err = image_to_video_gate(studio_user)
        assert ok
        assert err is None

        ok, err = image_to_video_gate(director_user)
        assert ok
        assert err is None


def test_in_app_notification_creation():
    with app.app_context():
        user = User(username="notif_user", email="nu@ex.com", password="pw", plan="spark", credits=5)
        db.session.add(user)
        db.session.commit()

        notif = Notification(
            user_id=user.id,
            title="Promo Alert",
            message="Get 50% off Studio plan today!",
            link="/upgrade",
            type="promo"
        )
        db.session.add(notif)
        db.session.commit()

        unread = Notification.query.filter_by(user_id=user.id, is_read=False).all()
        assert len(unread) == 1
        assert unread[0].title == "Promo Alert"


def test_newsletter_campaign_model():
    with app.app_context():
        camp = NewsletterCampaign(
            subject="Special African Creator Offer",
            html_body="<p>Upgrade to Studio tier for cinematic 10s video!</p>",
            status="draft",
            batch_size=80,
            batch_offset=0,
            total_audience=240
        )
        db.session.add(camp)
        db.session.commit()

        saved = NewsletterCampaign.query.first()
        assert saved is not None
        assert saved.batch_size == 80
        assert saved.status == "draft"


def test_monthly_quota_reset():
    with app.app_context():
        spark_user = User(
            username="sparky",
            email="sp@ex.com",
            password="pw",
            plan="spark",
            credits=0,
            monthly_images_used=2,
            free_video_allowance=0
        )
        db.session.add(spark_user)
        db.session.commit()

        # Simulate reset job
        spark_users = User.query.filter(User.plan.in_(['free', 'spark'])).all()
        for u in spark_users:
            u.monthly_images_used = 0
            u.free_video_allowance = 1
            u.monthly_free_images_left = 2
            u.monthly_free_videos_left = 1
            u.last_quota_reset_at = datetime.now(timezone.utc)
        db.session.commit()

        reloaded = db.session.get(User, spark_user.id)
        assert reloaded.monthly_images_used == 0
        assert reloaded.free_video_allowance == 1
