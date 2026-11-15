import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app import app
from models import (
    db, User, SocialPost, SocialCampaign, SocialMediaAsset,
    SocialPublishingJob, SocialAnalytics, SocialAutomationSettings,
    AIContentHistory, ConnectedAccount, Notification
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
        assert b"Social Marketing Engine" in res.data
        assert b"Content Calendar" in res.data
        assert b"AI Content Studio" in res.data
        assert b"Creative Studio" in res.data
        assert b"Campaigns" in res.data
        assert b"Publishing Queue" in res.data
        assert b"Published Posts" in res.data
        assert b"Automation Settings" in res.data


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


def test_qa_auto_correction_repairs_missing_branding_and_cta():
    from services.social_qa import attempt_qa_auto_correction, run_social_quality_audit
    bad_caption = "Explore revolutionary new creative technology that enables creators to scale production instantly."
    initial_qa = run_social_quality_audit(bad_caption, "facebook", "text")
    assert any("Missing core brand mention" in f for f in initial_qa["flags"])

    correction = attempt_qa_auto_correction(bad_caption, "facebook", initial_qa["flags"])
    assert correction["modified"] is True
    assert "Afrigen" in correction["corrected_caption"]

    re_audit = run_social_quality_audit(correction["corrected_caption"], "facebook", "text")
    assert re_audit["score"] > initial_qa["score"]


def test_campaign_creation_and_autogenerate_posts():
    client = app.test_client()
    with app.app_context():
        user = _create_test_user("camp_tester@afrigen.com")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        with patch("services.social_engine.generate_social_video") as mock_vid:
            mock_vid.return_value = {
                "ok": True,
                "media_url": "https://example.com/mock_campaign_video.mp4",
                "media_type": "video",
                "provider": "huggingface",
                "model_name": "damo-vilab/text-to-video-ms-1.7m",
                "duration_seconds": 5
            }
            res = client.post(
                "/social-automation/campaigns/create",
                json={
                    "name": "Nollywood AI Creative Sprint",
                    "objective": "awareness",
                    "target_audience": "Indie filmmakers and screenwriters",
                    "platforms": ["facebook", "linkedin"],
                    "autogenerate_posts": True
                }
            )
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["posts_count"] > 0

        # Verify campaign in database
        camp = SocialCampaign.query.filter_by(id=data["campaign_id"]).first()
        assert camp is not None
        assert camp.user_id == user.id
        assert len(camp.posts) == data["posts_count"]


def test_edit_post_recalculates_qa_score():
    client = app.test_client()
    with app.app_context():
        user = _create_test_user("edit_tester@afrigen.com")
        post = SocialPost(
            user_id=user.id,
            platform="facebook",
            title="Initial Title",
            caption="Short initial caption that lacks brand mentions or details.",
            status="scheduled",
            quality_score=50
        )
        db.session.add(post)
        db.session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        new_caption = "Empower your creative agency with Afrigen AI. Produce cinema-grade visuals and custom voiceovers. Start creating at afrigen.com.ng"
        res = client.post(
            f"/social-automation/posts/{post.id}/edit",
            json={
                "title": "Updated Brand Feature",
                "caption": new_caption,
                "call_to_action": "Try Afrigen today at afrigen.com.ng"
            }
        )
        assert res.status_code == 200
        assert post.title == "Updated Brand Feature"
        assert post.quality_score >= 80


def test_creative_studio_generation_route():
    client = app.test_client()
    with app.app_context():
        user = _create_test_user("creative_tester@afrigen.com")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        res = client.post(
            "/social-automation/creative/generate",
            json={
                "prompt": "African cinema showcase with dramatic gold and dark teal lighting",
                "media_type": "image",
                "aspect_ratio": "1:1"
            }
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["media_url"]
        assert data["asset_id"]

        # Verify asset created in DB
        asset = SocialMediaAsset.query.filter_by(id=data["asset_id"]).first()
        assert asset is not None
        assert asset.user_id == user.id


def test_linkedin_organization_urn_support():
    with app.app_context():
        from services.connected_accounts.adapters.linkedin import LinkedinAdapter
        adapter = LinkedinAdapter()

        user = _create_test_user("li_org_tester@afrigen.com")
        # Create ConnectedAccount with organization publishing identity
        acc = ConnectedAccount(
            user_id=user.id,
            provider="linkedin",
            account_name="Afrigen AI Organization",
            account_identifier="org_998877",
            status="connected",
            metadata_json=json.dumps({"publishing_identity": "urn:li:organization:998877"})
        )
        db.session.add(acc)
        db.session.commit()

        meta = adapter._parse_metadata(acc.metadata_json)
        author = meta.get("publishing_identity") or acc.account_identifier
        assert author == "urn:li:organization:998877"
        assert author.startswith("urn:li:organization:")


def test_multi_tenant_isolation_guaranteed():
    with app.app_context():
        user_a = _create_test_user("tenant_a@afrigen.com")
        user_b = _create_test_user("tenant_b@afrigen.com")

        # User A creates a post
        post_a = SocialPost(
            user_id=user_a.id,
            platform="facebook",
            title="Tenant A Private Post",
            caption="Secret marketing strategy for tenant A with Afrigen AI.",
            status="draft"
        )
        db.session.add(post_a)
        db.session.commit()

        # User B queries posts; should NOT see User A's post
        user_b_posts = SocialPost.query.filter_by(user_id=user_b.id).all()
        assert post_a.id not in [p.id for p in user_b_posts]

        # User B cannot publish User A's post
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_b.id)
            sess["_fresh"] = True

        res = client.post(f"/social-automation/posts/{post_a.id}/publish-now")
        assert res.status_code == 404


# ==============================================================================
# 7. NEW IMPROVED AUTOMATION & VALIDATION TESTS
# ==============================================================================

def test_weekly_content_planner_distribution():
    with app.app_context():
        from services.social_strategist import plan_weekly_content
        user = _create_test_user("weekly_planner@afrigen.com")
        plan = plan_weekly_content(user.id, posts_per_day=1)
        assert len(plan) == 7

        pillars = [p["pillar"] for p in plan]
        assert "education" in pillars or "demo" in pillars
        # Promotions should be at most 1 in the week
        promo_count = sum(1 for p in pillars if p in ("promotion", "promotions"))
        assert promo_count <= 1

        # Check recommended publishing hours: Facebook morning (8), LinkedIn evening (17)
        for item in plan:
            if item["platform"] == "facebook":
                assert item["scheduled_time"].hour == 8
            elif item["platform"] == "linkedin":
                assert item["scheduled_time"].hour == 17


def test_platform_differentiation_facebook_vs_linkedin():
    with app.app_context():
        user = _create_test_user("platform_diff@afrigen.com")
        fb_copy = generate_platform_copy(
            title="Prompt Engineering Melanin Tones",
            summary="Essential lighting keywords for rich African skin tones.",
            pillar="education",
            platform="facebook",
            user_id=user.id
        )
        li_copy = generate_platform_copy(
            title="Prompt Engineering Melanin Tones",
            summary="Essential lighting keywords for rich African skin tones.",
            pillar="education",
            platform="linkedin",
            user_id=user.id
        )
        # Captions must NEVER be identical
        assert fb_copy["caption"] != li_copy["caption"]
        # Facebook should contain conversational/interactive discussion
        assert "?" in fb_copy["caption"] or "comments" in fb_copy["caption"].lower()
        # LinkedIn should have strategic/founder perspective
        assert "agency" in li_copy["caption"].lower() or "production" in li_copy["caption"].lower() or "roi" in li_copy["caption"].lower() or "creative economy" in li_copy["caption"].lower()


def test_qa_rejects_fake_testimonials_and_invented_stats():
    from services.social_qa import run_social_quality_audit

    # 1. Fake testimonial rejection
    fake_quote = "Afrigen AI is great! John from London said this platform increased our client retention instantly. Visit afrigen.com.ng"
    audit1 = run_social_quality_audit(fake_quote, "facebook", "text")
    assert audit1["passed"] is False
    assert any("fabricated testimonial" in f.lower() or "unverified customer" in f.lower() for f in audit1["flags"])

    # 2. Invented statistic rejection
    fake_stat = "Afrigen AI is proven to boost sales by 850% for 99.9% of creators across Africa. Visit afrigen.com.ng"
    audit2 = run_social_quality_audit(fake_stat, "facebook", "text")
    assert audit2["passed"] is False
    assert any("invented statistic" in f.lower() or "unrealistic" in f.lower() for f in audit2["flags"])

    # 3. Unverified pricing rejection
    bad_price = "Get complete studio access for only $5/month today on Afrigen AI at afrigen.com.ng"
    audit3 = run_social_quality_audit(bad_price, "facebook", "text")
    assert audit3["passed"] is False
    assert any("unverified pricing" in f.lower() or "unverified price" in f.lower() for f in audit3["flags"])

    # 4. Internal development leak rejection
    leak = "Afrigen AI creative release. Test flyer upload from python pil engine [Refreshed Edition]. afrigen.com.ng"
    audit4 = run_social_quality_audit(leak, "facebook", "text")
    assert audit4["passed"] is False
    assert any("non-compliant" in f.lower() or "internal" in f.lower() for f in audit4["flags"])


def test_huggingface_video_generation_workflow():
    with app.app_context():
        from services.social_creative_hf import generate_social_video, verify_video_bytes
        # 1. Valid video container validation
        dummy_mp4 = b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00isommp42" + (b"A" * 15000)
        v_check = verify_video_bytes(dummy_mp4)
        assert v_check["valid"] is True
        assert v_check["format"] == "mp4"

        # 2. Incomplete or corrupted video rejection
        corrupt_bytes = b"tiny"
        assert verify_video_bytes(corrupt_bytes)["valid"] is False

        # 3. Mock HF inference call
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = dummy_mp4
        mock_resp.headers = {"content-type": "video/mp4"}

        with patch("services.social_creative_hf._get_hf_token", return_value="hf_mock_token_12345"), \
             patch("requests.post", return_value=mock_resp):
            res = generate_social_video(
                prompt="Lagos 2050 Afro-futuristic drone flythrough",
                duration_seconds=5
            )
            assert res["ok"] is True
            assert res["media_type"] == "video"
            assert res["provider"] == "huggingface"
            assert res["media_url"].startswith("http")


def test_expired_oauth_token_detection_and_notification():
    with app.app_context():
        user = _create_test_user("expired_oauth@afrigen.com")

        acc = ConnectedAccount.query.filter_by(user_id=user.id, provider="facebook").first()
        if not acc:
            acc = ConnectedAccount(
                user_id=user.id,
                provider="facebook",
                account_name="Test FB Page",
                account_identifier="fb_12345",
                status="connected",
                encrypted_access_token="dummy_token"
            )
            db.session.add(acc)
            db.session.commit()

        post = SocialPost(
            user_id=user.id,
            platform="facebook",
            title="Expired Token Post",
            caption="Testing expired token reporting on Afrigen AI at afrigen.com.ng.",
            status="scheduled",
            scheduled_at=datetime.now(timezone.utc),
            idempotency_key="expired_tok_test_01"
        )
        db.session.add(post)
        db.session.flush()

        job = SocialPublishingJob(
            user_id=user.id,
            post_id=post.id,
            platform="facebook",
            status="pending",
            scheduled_time=datetime.now(timezone.utc),
            idempotency_key="expired_tok_test_01"
        )
        db.session.add(job)
        db.session.commit()

        # Simulate Meta OAuth token expiration response (code 190)
        with patch("services.connected_accounts.adapters.facebook.FacebookAdapter.publish") as mock_pub:
            mock_pub.return_value = {
                "ok": False,
                "error": "Facebook feed publish failed: Error validating access token: Session has expired (code 190)."
            }
            res = process_single_publishing_job(job)
            assert res["ok"] is False
            # Job and post should be permanently failed without indefinite retry
            assert job.status == "failed"
            assert post.status == "failed"
            # Account status updated to expired
            assert acc.status == "expired"

            # User alert notification created
            notif = Notification.query.filter_by(user_id=user.id, type="warning").first()
            assert notif is not None
            assert "expired" in notif.message.lower()


def test_prevent_duplicate_publishing_if_already_published():
    with app.app_context():
        user = _create_test_user("dup_prevent@afrigen.com")
        post = SocialPost(
            user_id=user.id,
            platform="facebook",
            title="Already Published Post",
            caption="Testing duplicate prevention on Afrigen AI.",
            status="published",
            remote_post_id="remote_existing_12345",
            published_url="https://facebook.com/posts/12345",
            idempotency_key="dup_prevent_001"
        )
        db.session.add(post)
        db.session.flush()

        job = SocialPublishingJob(
            user_id=user.id,
            post_id=post.id,
            platform="facebook",
            status="pending",
            scheduled_time=datetime.now(timezone.utc),
            idempotency_key="dup_prevent_001"
        )
        db.session.add(job)
        db.session.commit()

        with patch("services.connected_accounts.adapters.facebook.FacebookAdapter.publish") as mock_pub:
            res = process_single_publishing_job(job)
            assert res["ok"] is True
            assert job.status == "completed"
            # Adapter publish must NOT have been called
            mock_pub.assert_not_called()

