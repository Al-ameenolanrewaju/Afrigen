"""Autonomous Social Publishing Engine with Distributed Worker Lease Locking.

Coordinates scheduled publishing to Facebook Pages and LinkedIn with database-backed
leases, idempotency guarantees, exponential backoff retries, and duplicate prevention.
"""

import os
import uuid
import json
import socket
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from models import (
    db, SocialPost, SocialPublishingJob, ConnectedAccount,
    SocialAutomationSettings, Notification
)
from services.social_strategist import record_content_history

logger = logging.getLogger(__name__)

WORKER_ID = f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex[:6]}"
LEASE_DURATION_SECONDS = 300  # 5-minute lease lock


def get_worker_identity() -> str:
    return WORKER_ID


# ==============================================================================
# WORKER LEASE LOCKING & JOB DISPATCH
# ==============================================================================

def claim_next_publishing_job(worker_id: str = None) -> Optional[SocialPublishingJob]:
    """Atomically acquire lease lock on the next pending social publishing job.

    Ensures that across multiple Render instances or workers, only ONE instance
    publishes a specific post.
    """
    wid = worker_id or WORKER_ID
    now = datetime.now(timezone.utc)
    lease_expires = now + timedelta(seconds=LEASE_DURATION_SECONDS)

    # 1. Look for unassigned or expired lease jobs that are ready to publish
    candidate = (
        SocialPublishingJob.query.filter(
            SocialPublishingJob.status.in_(["pending", "retrying"]),
            SocialPublishingJob.scheduled_time <= now,
            db.or_(
                SocialPublishingJob.locked_at.is_(None),
                SocialPublishingJob.lease_expires_at < now,
            ),
        )
        .order_by(SocialPublishingJob.scheduled_time.asc())
        .with_for_update(skip_locked=True)
        .first()
    )

    if not candidate:
        return None

    # Check emergency pause on user's automation settings
    settings = SocialAutomationSettings.query.filter_by(user_id=candidate.user_id).first()
    if settings and settings.emergency_paused:
        logger.info("Publishing paused by user emergency pause setting for user %s", candidate.user_id)
        return None

    # Claim lease lock
    candidate.locked_by = wid
    candidate.locked_at = now
    candidate.lease_expires_at = lease_expires
    candidate.status = "running"
    db.session.commit()
    logger.info("Worker '%s' claimed job #%s for post #%s (%s)", wid, candidate.id, candidate.post_id, candidate.platform)
    return candidate


def process_single_publishing_job(job: SocialPublishingJob) -> Dict[str, Any]:
    """Execute publication of a single claimed job with idempotency and retry handling."""
    post = job.post
    if not post:
        job.status = "failed"
        job.error_details = "Post record not found."
        db.session.commit()
        return {"ok": False, "error": job.error_details}

    # Ensure post status reflects active publishing
    post.status = "publishing"
    post.attempt_count = (post.attempt_count or 0) + 1
    post.last_attempt_at = datetime.now(timezone.utc)
    db.session.commit()

    platform = (job.platform or "").lower().strip()
    result = None

    try:
        from services.connected_accounts.provider_registry import get_adapter
        adapter = get_adapter(platform)
        if not adapter:
            raise ValueError(f"No publishing adapter available for platform: {platform}")

        # Publish via adapter (FacebookAdapter or LinkedinAdapter)
        result = adapter.publish(user_id=job.user_id, content=post)

    except Exception as exc:
        logger.exception("Publishing exception for post #%s on %s: %s", post.id, platform, exc)
        result = {"ok": False, "error": str(exc)}

    # Evaluate Result
    now = datetime.now(timezone.utc)
    if result and result.get("ok"):
        remote_id = result.get("post_id") or result.get("id")
        post_url = result.get("post_url") or result.get("url")

        # Success transition
        job.status = "completed"
        job.response_data_json = json.dumps(result)
        job.error_details = None

        post.status = "published"
        post.remote_post_id = str(remote_id) if remote_id else None
        post.published_url = post_url
        post.published_at = now
        post.error_details = None
        db.session.commit()

        # Record in originality history
        try:
            record_content_history(
                user_id=post.user_id,
                post_id=post.id,
                platform=platform,
                caption=post.caption,
                topic=post.title or post.content_pillar or "Marketing",
            )
        except Exception as hist_err:
            logger.warning("Could not record content history: %s", hist_err)

        # Notify user of successful autonomous publishing
        try:
            db.session.add(Notification(
                user_id=post.user_id,
                title=f"Published to {platform.capitalize()}",
                message=f"'{post.title or 'Post'}' was published successfully to your {platform.capitalize()} channel.",
                notification_type="social_publishing",
                category="marketing",
                link_url=post_url or "/social-automation",
            ))
            db.session.commit()
        except Exception:
            pass

        logger.info("Successfully published post #%s to %s (remote_id: %s)", post.id, platform, remote_id)
        return {"ok": True, "post_id": remote_id, "post_url": post_url}

    else:
        err_msg = (result.get("error") if result else None) or "Unknown publishing error."
        job.attempt_count = (job.attempt_count or 0) + 1
        job.error_details = err_msg
        post.error_details = err_msg

        if job.attempt_count < job.max_attempts:
            # Exponential backoff (attempt 1: +3m, attempt 2: +15m)
            backoff_minutes = 3 if job.attempt_count == 1 else 15
            job.status = "retrying"
            job.next_retry_at = now + timedelta(minutes=backoff_minutes)
            job.scheduled_time = job.next_retry_at
            job.locked_at = None
            job.locked_by = None
            job.lease_expires_at = None
            post.status = "retry_pending"
            logger.warning("Job #%s failed (attempt %s/%s). Retrying at %s: %s",
                           job.id, job.attempt_count, job.max_attempts, job.next_retry_at, err_msg)
        else:
            job.status = "failed"
            post.status = "failed"
            # Alert user on permanent publishing failure
            try:
                db.session.add(Notification(
                    user_id=post.user_id,
                    title=f"Publishing Failed: {platform.capitalize()}",
                    message=f"Post '{post.title or 'Post'}' could not be published after {job.max_attempts} attempts: {err_msg[:120]}",
                    notification_type="social_publishing",
                    category="marketing",
                    link_url="/social-automation",
                ))
            except Exception:
                pass
            logger.error("Job #%s permanently failed after %s attempts: %s", job.id, job.max_attempts, err_msg)

        db.session.commit()
        return {"ok": False, "error": err_msg}


def run_social_publishing_cycle() -> int:
    """Run one pass of the publishing queue, claiming and executing ready jobs.

    Returns the count of jobs processed.
    """
    processed = 0
    # Process up to 5 jobs per scheduler invocation
    for _ in range(5):
        try:
            job = claim_next_publishing_job()
            if not job:
                break
            process_single_publishing_job(job)
            processed += 1
        except Exception as exc:
            logger.error("Error in publishing queue cycle: %s", exc)
            break
    return processed
