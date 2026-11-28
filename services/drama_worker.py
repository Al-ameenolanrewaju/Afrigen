"""Durable worker for end-to-end AI Drama Studio episode production.

The worker reuses the existing Movie Studio screenplay, storyboard, dialogue,
shot-generation and master-render services. It records every stage in the
DramaProductionJob row so interrupted work can be retried safely.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from models import (
    db, DramaEpisode, DramaProductionJob, DramaUsageLedger,
    MovieRenderJob, MovieScene, MovieShot,
)

logger = logging.getLogger(__name__)
MAX_PRODUCTION_ATTEMPTS = 3
STALE_JOB_MINUTES = 45
RENDER_WAIT_SECONDS = 600


def _now():
    return datetime.now(timezone.utc)


def _set_step(job, step, progress, status="processing"):
    job.current_step = step
    job.progress = max(0, min(100, int(progress)))
    job.status = status
    job.updated_at = _now()
    db.session.commit()


def _record_estimated_shot_cost(episode, shot):
    """Record a provider-cost estimate once; it is not an invoice/actual charge."""
    key = f"drama-episode:{episode.id}:shot:{shot.id}:provider-estimate"
    if DramaUsageLedger.query.filter_by(idempotency_key=key).first():
        return
    try:
        from services.video import estimate_fal_video_cost
        estimated = float(estimate_fal_video_cost("kling image-to-video", shot.duration or "5"))
    except Exception:
        estimated = 0.0
    db.session.add(DramaUsageLedger(
        user_id=episode.user_id,
        episode_id=episode.id,
        usage_type="shot_provider_cost_estimate",
        status="estimated",
        provider_cost_usd=estimated,
        idempotency_key=key,
    ))
    db.session.commit()


def _run_episode_pipeline(job):
    from services.movie_studio import (
        generate_screenplay_treatment,
        create_scene_shots_and_storyboards,
        generate_scene_pidgin_dialogue,
        generate_shot_video_clip,
        start_movie_render_job,
    )

    episode = db.session.get(DramaEpisode, job.episode_id)
    if not episode or not episode.movie_project:
        raise RuntimeError("Episode or linked Movie Studio project was not found.")
    project = episode.movie_project

    _set_step(job, "screenplay", 5)
    if not MovieScene.query.filter_by(project_id=project.id).count():
        ok, message = generate_screenplay_treatment(project, preserve_existing_cast=True)
        if not ok:
            raise RuntimeError(message or "Screenplay generation failed.")

    scenes = (MovieScene.query.filter_by(project_id=project.id)
              .order_by(MovieScene.order.asc(), MovieScene.scene_number.asc()).all())
    if not scenes:
        raise RuntimeError("The screenplay did not create any scenes.")

    _set_step(job, "storyboard", 20)
    for scene in scenes:
        if not scene.shots:
            ok, message = create_scene_shots_and_storyboards(scene.id)
            if not ok:
                raise RuntimeError(message or f"Storyboard generation failed for scene {scene.scene_number}.")

    scenes = (MovieScene.query.filter_by(project_id=project.id)
              .order_by(MovieScene.order.asc(), MovieScene.scene_number.asc()).all())
    _set_step(job, "dialogue", 35)
    for scene in scenes:
        if scene.screenplay_text and scene.screenplay_text.strip() and scene.shots:
            ok, message, _tracks = generate_scene_pidgin_dialogue(scene.id)
            if not ok and "No valid dialogue lines" not in str(message):
                raise RuntimeError(message or f"Dialogue generation failed for scene {scene.scene_number}.")

    shots = (MovieShot.query.filter_by(project_id=project.id)
             .order_by(MovieShot.scene_id.asc(), MovieShot.order.asc()).all())
    if not shots:
        raise RuntimeError("No storyboard shots were created.")

    _set_step(job, "shot_generation", 45)
    total = len(shots)
    for index, shot in enumerate(shots, 1):
        if shot.status != "completed" or not shot.video_url:
            ok, result = generate_shot_video_clip(shot.id)
            if not ok:
                raise RuntimeError(f"Shot {shot.id} failed: {result}")
        _record_estimated_shot_cost(episode, shot)
        _set_step(job, "shot_generation", 45 + int(index / total * 35))

    _set_step(job, "master_render", 82)
    latest_render = (MovieRenderJob.query.filter_by(project_id=project.id)
                     .order_by(MovieRenderJob.created_at.desc()).first())
    if latest_render and latest_render.status == "completed" and latest_render.output_video_url:
        render_id = latest_render.id
    elif latest_render and latest_render.status == "processing":
        render_id = latest_render.id
    else:
        ok, render_id = start_movie_render_job(project.id, episode.user_id)
        if not ok:
            raise RuntimeError(render_id or "Master render could not be queued.")

    deadline = time.monotonic() + RENDER_WAIT_SECONDS
    while time.monotonic() < deadline:
        db.session.expire_all()
        render = db.session.get(MovieRenderJob, render_id)
        if not render:
            raise RuntimeError("Master render job disappeared.")
        if render.status == "completed" and render.output_video_url:
            _set_step(job, "completed", 100, status="completed")
            return
        if render.status == "failed":
            raise RuntimeError(render.error_message or "Master render failed.")
        time.sleep(5)
    raise RuntimeError("Master render is still processing; the production job will be retried.")


def process_drama_production_job(job_id):
    """Claim and process one queued/retryable episode job."""
    job = (DramaProductionJob.query.filter_by(id=job_id)
           .with_for_update().first())
    if not job or job.status in {"completed", "processing", "rendering"}:
        return False
    if job.attempt_count >= MAX_PRODUCTION_ATTEMPTS:
        return False

    job.status = "processing"
    job.attempt_count += 1
    job.started_at = _now()
    job.error_message = None
    job.updated_at = _now()
    db.session.commit()

    try:
        _run_episode_pipeline(job)
        job = db.session.get(DramaProductionJob, job_id)
        job.status = "completed"
        job.current_step = "completed"
        job.progress = 100
        job.completed_at = _now()
        job.updated_at = _now()
        db.session.commit()
        from services.drama_studio import finalize_episode_quota
        finalize_episode_quota(job.episode_id, success=True)
        return True
    except Exception as exc:
        db.session.rollback()
        job = db.session.get(DramaProductionJob, job_id)
        if not job:
            return False
        job.status = "failed"
        job.current_step = "failed"
        job.error_message = str(exc)[:2000]
        job.updated_at = _now()
        if job.attempt_count >= MAX_PRODUCTION_ATTEMPTS:
            from services.drama_studio import finalize_episode_quota
            db.session.commit()
            finalize_episode_quota(job.episode_id, success=False)
        else:
            db.session.commit()
        logger.exception("Drama production job %s failed on attempt %s", job_id, job.attempt_count)
        return False


def recover_stale_drama_jobs():
    """Return abandoned worker claims to the retry queue or release exhausted slots."""
    cutoff = _now() - timedelta(minutes=STALE_JOB_MINUTES)
    stale = DramaProductionJob.query.filter(
        DramaProductionJob.status.in_(["processing", "rendering"]),
        DramaProductionJob.started_at < cutoff,
    ).all()
    recovered = 0
    for job in stale:
        if job.attempt_count < MAX_PRODUCTION_ATTEMPTS:
            job.status = "queued"
            job.error_message = "Recovered after a worker timeout; queued for retry."
            job.current_step = job.current_step or "screenplay"
        else:
            job.status = "failed"
            job.current_step = "failed"
            job.error_message = "Production stopped after repeated worker timeouts."
        job.updated_at = _now()
        recovered += 1
    db.session.commit()

    exhausted = DramaProductionJob.query.filter_by(status="failed").filter(
        DramaProductionJob.attempt_count >= MAX_PRODUCTION_ATTEMPTS
    ).all()
    from services.drama_studio import finalize_episode_quota
    for job in exhausted:
        episode = db.session.get(DramaEpisode, job.episode_id)
        if episode and episode.quota_status == "reserved":
            finalize_episode_quota(episode.id, success=False)
    return recovered


def process_drama_production_queue(limit=1):
    """Recover timed-out jobs, then process a small batch of queued/retryable jobs."""
    recover_stale_drama_jobs()
    jobs = (DramaProductionJob.query.filter(
        DramaProductionJob.status.in_(["queued", "failed"]),
        DramaProductionJob.attempt_count < MAX_PRODUCTION_ATTEMPTS,
    ).order_by(DramaProductionJob.created_at.asc()).limit(max(1, int(limit))).all())
    results = []
    for job in jobs:
        results.append(process_drama_production_job(job.id))
    return results


def admin_drama_cost_report():
    """Aggregate estimated provider spend and credited usage for admin reporting."""
    from sqlalchemy import func
    rows = (db.session.query(
        DramaUsageLedger.usage_type,
        func.count(DramaUsageLedger.id),
        func.coalesce(func.sum(DramaUsageLedger.provider_cost_usd), 0.0),
        func.coalesce(func.sum(DramaUsageLedger.credits_charged), 0),
    ).group_by(DramaUsageLedger.usage_type).all())
    totals = {
        "estimated_provider_cost_usd": round(sum(float(row[2] or 0) for row in rows), 4),
        "credits_charged": int(sum(int(row[3] or 0) for row in rows)),
        "ledger_entries": int(sum(int(row[1] or 0) for row in rows)),
        "cost_basis": "Estimated provider costs only; not provider invoices or actual settled spend.",
        "by_usage_type": [
            {"usage_type": row[0], "entries": int(row[1]),
             "estimated_provider_cost_usd": round(float(row[2] or 0), 4),
             "credits_charged": int(row[3] or 0)}
            for row in rows
        ],
    }
    return totals
