from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import app
from models import db, User, DramaSeries, DramaEpisode, DramaProductionJob, DramaUsageLedger
from services.drama_studio import create_series, create_episode, monthly_usage_summary, finalize_episode_quota, requeue_failed_episode
from services import drama_worker


def _director():
    token = uuid4().hex[:10]
    user = User(
        username=f"worker_{token}",
        email=f"worker_{token}@example.test",
        password="test-hash",
        plan="director",
        credits=100,
    )
    db.session.add(user)
    db.session.commit()
    return user


def setup_function():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()


def test_worker_retries_then_completes_episode(monkeypatch):
    with app.app_context():
        user = _director()
        _, _, series = create_series(user, "Worker Test")
        _, _, episode, job = create_episode(user, series.id)

        def fail_once(_job):
            raise RuntimeError("temporary provider outage")

        monkeypatch.setattr(drama_worker, "_run_episode_pipeline", fail_once)
        assert drama_worker.process_drama_production_job(job.id) is False
        db.session.refresh(job)
        assert job.status == "failed"
        assert job.attempt_count == 1
        assert monthly_usage_summary(user.id)["reserved"] == 1

        monkeypatch.setattr(drama_worker, "_run_episode_pipeline", lambda _job: None)
        assert drama_worker.process_drama_production_job(job.id) is True
        db.session.refresh(job)
        assert job.status == "completed"
        assert monthly_usage_summary(user.id)["completed"] == 1
        assert monthly_usage_summary(user.id)["reserved"] == 0


def test_exhausted_worker_retries_release_episode_allowance(monkeypatch):
    with app.app_context():
        user = _director()
        _, _, series = create_series(user, "Exhausted Worker")
        _, _, episode, job = create_episode(user, series.id)

        monkeypatch.setattr(
            drama_worker, "_run_episode_pipeline",
            lambda _job: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
        )
        for _ in range(drama_worker.MAX_PRODUCTION_ATTEMPTS):
            drama_worker.process_drama_production_job(job.id)
            db.session.expire_all()
            job = db.session.get(DramaProductionJob, job.id)
            if job.attempt_count < drama_worker.MAX_PRODUCTION_ATTEMPTS:
                job.status = "queued"
                db.session.commit()

        db.session.refresh(job)
        assert job.status == "failed"
        assert job.attempt_count == drama_worker.MAX_PRODUCTION_ATTEMPTS
        assert monthly_usage_summary(user.id)["reserved"] == 0
        assert monthly_usage_summary(user.id)["remaining"] == 30


def test_stale_worker_claim_is_requeued():
    with app.app_context():
        user = _director()
        _, _, series = create_series(user, "Stale Worker")
        _, _, episode, job = create_episode(user, series.id)
        job.status = "processing"
        job.attempt_count = 1
        job.started_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        db.session.commit()

        assert drama_worker.recover_stale_drama_jobs() == 1
        db.session.refresh(job)
        assert job.status == "queued"


def test_admin_cost_report_marks_provider_cost_as_estimate():
    with app.app_context():
        user = _director()
        _, _, series = create_series(user, "Cost Report")
        _, _, episode, _ = create_episode(user, series.id)
        db.session.add(DramaUsageLedger(
            user_id=user.id,
            episode_id=episode.id,
            usage_type="shot_provider_cost_estimate",
            status="estimated",
            provider_cost_usd=0.225,
            idempotency_key=f"test-estimate-{uuid4().hex}",
        ))
        db.session.commit()

        report = drama_worker.admin_drama_cost_report()
        assert report["estimated_provider_cost_usd"] >= 0.225
        assert "not provider invoices" in report["cost_basis"]



def test_manual_retry_re_reserves_allowance_after_exhausted_failure():
    with app.app_context():
        user = _director()
        _, _, series = create_series(user, "Manual Retry")
        _, _, episode, job = create_episode(user, series.id)
        assert finalize_episode_quota(episode.id, success=False)
        assert monthly_usage_summary(user.id)["remaining"] == 30

        ok, message = requeue_failed_episode(user, episode.id)
        assert ok, message
        db.session.refresh(job)
        db.session.refresh(episode)
        assert job.status == "queued"
        assert job.attempt_count == 0
        assert episode.quota_status == "reserved"
        assert monthly_usage_summary(user.id)["reserved"] == 1
        assert monthly_usage_summary(user.id)["remaining"] == 29
