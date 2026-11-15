import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app import app
from models import (
    db, User, SocialPost, SocialCampaign, SocialMediaAsset,
    SocialPublishingJob, SocialAnalytics, SocialAutomationSettings,
    AIContentHistory, ConnectedAccount
)
from services.social_strategist import (
    select_next_pillar, plan_post_concept, generate_platform_copy,
    check_content_originality, record_content_history
)
from services.social_creative_hf import (
    generate_social_image, generate_social_video, validate_media_asset
)
from services.social_qa import run_social_quality_audit
from services.social_publisher import (
    claim_next_publishing_job, process_single_publishing_job,
    run_social_publishing_cycle, WORKER_ID
)
from services.social_analytics import (
    analyze_marketing_performance, adapt_future_strategy
)
from services.social_engine import (
    get_or_create_settings, generate_autonomous_post, generate_daily_social_schedule
)


@pytest.fixture(autouse=True)
def setup_test_db():
    with app.app_context():
        db.create_all()
        yield
        db.session.rollback()


def _create_test_user(email="social_tester@afrigen.com"):
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            username=f"tester_{email.split('@')[0]}",
            email=email,
            password="testpassword",
            plan="creator",
            credits=100
        )
        db.session.add(user)
        db.session.commit()
    return user


# ==============================================================================
# 1. STRATEGY & PLATFORM COPYWRITING TESTS
# ==============================================================================

def test_select_next_pillar_balances_targets():
    with app.app_context():
        user = _create_test_user("pillar_test@afrigen.com")
        settings = get_or_create_settings(user.id)
        pillar = select_next_pillar(user.id, settings)
        assert pillar in ["education", "demo", "industry_insights", "product_updates", "community", "case_study", "promotion"]


def test_platform_specific_copywriting_facebook_vs_linkedin():
    with app.app_context():
        user = _create_test_user("copy_test@afrigen.com")
        
        # Facebook copy
        fb_copy = generate_platform_copy(
            title="AI Video Creation for Nollywood",
            summary="How indie creators shoot 4K scenes without physical cameras.",
            pillar="education",
            platform="facebook",
            user_id=user.id
        )
        assert fb_copy["caption"]
        assert "Afrigen" in fb_copy["caption"] or "afrigen" in fb_copy["caption"].lower() or "AI" in fb_copy["caption"]
        assert fb_copy["call_to_action"]

        # LinkedIn copy
        li_copy = generate_platform_copy(
            title="The Economics of Generative AI for African Agencies",
            summary="Lowering client production budgets by 60% with instant digital assets.",
            pillar="industry_insights",
            platform="linkedin",
            user_id=user.id
        )
        assert li_copy["caption"]
        assert "Afrigen" in li_copy["caption"] or "African" in li_copy["caption"]


def test_content_originality_and_duplicate_prevention():
    with app.app_context():
        user = _create_test_user("orig_test@afrigen.com")
        caption = "Unlock high-definition African AI video generation with our new Movie Studio suite."
        
        # First check should be original
        res1 = check_content_originality(caption, user.id)
        assert res1["is_original"] is True
        
        # Record history
        record_content_history(user.id, post_id=101, platform="facebook", caption=caption, topic="Movie Studio")
        
        # Second check should detect duplicate
        res2 = check_content_originality(caption, user.id)
        assert res2["is_original"] is False
        assert "duplicates previous post" in res2["reason"]


# ==============================================================================
# 2. HUGGING FACE & CREATIVE GENERATION TESTS
# ==============================================================================

def test_generate_social_image_with_pil_fallback():
    with app.app_context():
        # Test PIL flyer generation fallback
        res = generate_social_image(
            prompt="Afrigen Creator Plan Special: ₦10,000/month",
            aspect_ratio="1:1",
            fallback_to_flyer=True
        )
        assert res["ok"] is True
        assert res["media_url"]
        assert res["media_type"] in ("image", "flyer")


def test_validate_media_asset_helper():
    assert validate_media_asset("", "image") is False
    assert validate_media_asset("ftp://invalid", "image") is False
    assert validate_media_asset("https://example.com/mock.jpg", "image") in (True, False)


# ==============================================================================
# 3. AUTONOMOUS QUALITY ASSURANCE TESTS
# ==============================================================================

def test_social_qa_accepts_compliant_post():
    caption = (
        "Empower your African creative agency with Afrigen AI. "
        "Produce cinema-grade visuals, photorealistic portraits, and voiceovers. "
        "Try our free Spark plan today at afrigen.com.ng!"
    )
    res = run_social_quality_audit(
        caption=caption,
        platform="facebook",
        content_format="text",
        call_to_action="Start creating at afrigen.com.ng"
    )
    assert res["passed"] is True
    assert res["score"] >= 75


def test_social_qa_rejects_forbidden_claims():
    bad_caption = "Get 99% off lifetime unlimited free credits right now and guaranteed viral success!"
    res = run_social_quality_audit(
        caption=bad_caption,
        platform="facebook",
        content_format="text"
    )
    assert res["passed"] is False
    assert res["score"] < 70
    assert any("non-compliant" in f for f in res["flags"])


# ==============================================================================
# 4. PUBLISHING ENGINE & WORKER LEASE LOCKING TESTS
# ==============================================================================

def test_claim_next_publishing_job_leases_atomically():
    with app.app_context():
        user = _create_test_user("lease_test@afrigen.com")
        settings = get_or_create_settings(user.id)
        settings.emergency_paused = False
        db.session.commit()

        # Create scheduled post and job
        post = SocialPost(
            user_id=user.id,
            platform="facebook",
            title="Scheduled Post Test",
            caption="Autonomous post caption ready for publication on Afrigen AI.",
            status="scheduled",
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            idempotency_key="lease_test_key_001"
        )
        db.session.add(post)
        db.session.flush()

        job = SocialPublishingJob(
            user_id=user.id,
            post_id=post.id,
            platform="facebook",
            status="pending",
            scheduled_time=datetime.now(timezone.utc) - timedelta(minutes=1),
            idempotency_key="lease_test_key_001"
        )
        db.session.add(job)
        db.session.commit()

        # Worker 1 claims job
        claimed = claim_next_publishing_job(worker_id="worker_alpha")
        assert claimed is not None
        assert claimed.id == job.id
        assert claimed.locked_by == "worker_alpha"
        assert claimed.status == "running"

        # Worker 2 attempting to claim should get None (already locked)
        claimed_2 = claim_next_publishing_job(worker_id="worker_beta")
        assert claimed_2 is None


def test_process_single_publishing_job_success():
    with app.app_context():
        user = _create_test_user("pub_success@afrigen.com")

        post = SocialPost(
            user_id=user.id,
            platform="facebook",
            title="Live Publishing Test",
            caption="Testing automated publishing through Afrigen AI.",
            status="scheduled",
            scheduled_at=datetime.now(timezone.utc),
            idempotency_key="pub_success_key_002"
        )
        db.session.add(post)
        db.session.flush()

        job = SocialPublishingJob(
            user_id=user.id,
            post_id=post.id,
            platform="facebook",
            status="pending",
            scheduled_time=datetime.now(timezone.utc),
            idempotency_key="pub_success_key_002"
        )
        db.session.add(job)
        db.session.commit()

        # Mock FacebookAdapter.publish
        with patch("services.connected_accounts.adapters.facebook.FacebookAdapter.publish") as mock_pub:
            mock_pub.return_value = {
                "ok": True,
                "post_id": "fb_mock_post_12345",
                "post_url": "https://www.facebook.com/posts/12345"
            }
            res = process_single_publishing_job(job)
            assert res["ok"] is True
            assert post.status == "published"
            assert post.remote_post_id == "fb_mock_post_12345"
            assert job.status == "completed"


# ==============================================================================
# 5. ANALYTICS & AI PERFORMANCE INTELLIGENCE TESTS
# ==============================================================================

def test_analyze_marketing_performance_and_self_tuning():
    with app.app_context():
        user = _create_test_user("analytics_tester@afrigen.com")
        settings = get_or_create_settings(user.id)

        # Create 2 published posts with different pillars
        p1 = SocialPost(
            user_id=user.id,
            platform="facebook",
            title="Tutorial Post",
            content_pillar="education",
            content_format="video",
            caption="Educational tutorial for creators.",
            status="published",
            remote_post_id="post_edu_1",
            published_at=datetime.now(timezone.utc)
        )
        p2 = SocialPost(
            user_id=user.id,
            platform="linkedin",
            title="Promo Post",
            content_pillar="promotion",
            content_format="flyer",
            caption="Promo post offer.",
            status="published",
            remote_post_id="post_promo_2",
            published_at=datetime.now(timezone.utc)
        )
        db.session.add_all([p1, p2])
        db.session.flush()

        a1 = SocialAnalytics(user_id=user.id, post_id=p1.id, platform="facebook", engagement_rate=8.5, impressions=200)
        a2 = SocialAnalytics(user_id=user.id, post_id=p2.id, platform="linkedin", engagement_rate=1.5, impressions=100)
        db.session.add_all([a1, a2])
        db.session.commit()

        analysis = analyze_marketing_performance(user.id)
        assert analysis["has_data"] is True
        assert analysis["total_published"] >= 2
        assert analysis["top_pillar"] == "education"

        # Test self-tuning loop
        adapt_future_strategy(user.id)
        updated_ratios = json.loads(settings.pillar_ratios_json)
        assert updated_ratios["education"] >= 25


# ==============================================================================
# 6. DASHBOARD & ENDPOINT INTEGRATION TESTS
# ==============================================================================

def test_social_automation_dashboard_view():
    client = app.test_client()
    with app.app_context():
        user = _create_test_user("dash_tester@afrigen.com")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        res = client.get("/social-automation")
        assert res.status_code == 200
        assert b"Social Media Automation Engine" in res.data
        assert b"Today's Queue" in res.data
        assert b"AI Content Studio" in res.data


def test_social_automation_toggle_pause_endpoint():
    client = app.test_client()
    with app.app_context():
        user = _create_test_user("pause_tester@afrigen.com")
        settings = get_or_create_settings(user.id)
        settings.emergency_paused = False
        db.session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        res = client.post("/social-automation/pause", json={})
        assert res.status_code == 200
        assert res.get_json()["emergency_paused"] is True
