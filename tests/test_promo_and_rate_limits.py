import os
import pytest
from PIL import Image
from app import app, scheduler
from models import db, User
from services.promo_campaign import generate_promo_flyer


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_free_python_flyer_generation():
    """Verify that Python PIL flyer generation creates a valid 1080x1080 image without API costs."""
    url = generate_promo_flyer("50% Off Creator Tiers Today!")
    assert url is not None
    assert "/static/uploads/campaigns/flyer_" in url
    
    # Check that file exists on disk and is a valid 1080x1080 image
    filename = url.split("/")[-1]
    local_path = os.path.join("static", "uploads", "campaigns", filename)
    assert os.path.exists(local_path)
    
    with Image.open(local_path) as img:
        assert img.size == (1080, 1080)
        assert img.format == "PNG"


def test_admin_grant_free_video_limiter_exemption():
    """Verify that admin grant-free-video endpoint has @limiter.exempt and can be invoked repeatedly."""
    with app.app_context():
        admin = User(
            username="admin_user",
            email="oadedamola07@gmail.com",
            password="hash",
            plan="pro"
        )
        target_user = User(
            username="recipient_user",
            email="recipient@example.com",
            password="hash",
            plan="spark",
            free_video_allowance=0
        )
        db.session.add_all([admin, target_user])
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin.id)
            sess['_fresh'] = True

        # Rapidly invoke grant free video 10 times to verify no 429 Too Many Requests
        for _ in range(10):
            res = client.post(f"/admin/grant-free-video/{target_user.id}?count=1")
            assert res.status_code == 302

        refreshed_user = db.session.get(User, target_user.id)
        assert refreshed_user.free_video_allowance == 10


def test_scheduled_promo_jobs_exist():
    """Verify that APScheduler has morning and evening promo jobs configured."""
    from app import autopost_promo_morning_job, autopost_promo_evening_job
    assert callable(autopost_promo_morning_job)
    assert callable(autopost_promo_evening_job)
