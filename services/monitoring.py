import os
import shutil
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import case, func, or_, text

from models import (
    CreditLedger,
    Generation,
    Payment,
    PaystackWebhookLog,
    ProviderHealth,
    ProviderLog,
    PublishingRetryQueue,
    SocialPublishingJob,
    User,
    db,
)
from monitoring_models import (
    MonitoringDailyReport,
    MonitoringIncident,
    MonitoringIncidentEvent,
    MonitoringSnapshot,
    ensure_monitoring_tables,
)


INCIDENT_STATUSES = {"open", "investigating", "identified", "resolving", "resolved", "closed"}
ACTIVE_INCIDENT_STATUSES = {"open", "investigating", "identified", "resolving"}
SNAPSHOT_RETENTION_DAYS = 90


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _positive_int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _positive_float(name, default):
    try:
        value = float(os.environ.get(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _database_check(_now):
    db.session.execute(text("SELECT 1"))
    return {
        "monitor_key": "database",
        "status": "healthy",
        "summary": "Database query succeeded.",
        "metrics": {"query_ok": True},
    }


def _generation_check(now):
    failure_window = now - timedelta(minutes=30)
    stuck_after = now - timedelta(minutes=_positive_int("MONITORING_STUCK_GENERATION_MINUTES", 15))

    stuck = Generation.query.filter(
        Generation.status == "processing",
        Generation.created_at <= stuck_after,
    ).count()
    failed = Generation.query.filter(
        Generation.status == "failed",
        Generation.created_at >= failure_window,
    ).count()
    recent_total = Generation.query.filter(Generation.created_at >= failure_window).count()
    output_window = now - timedelta(hours=24)
    completed_missing_image = Generation.query.filter(
        Generation.status == "completed",
        Generation.generation_type.in_(("image", "photo")),
        Generation.created_at >= output_window,
        or_(Generation.image_url.is_(None), Generation.image_url == ""),
    ).count()
    completed_missing_video = Generation.query.filter(
        Generation.status == "completed",
        Generation.generation_type == "video",
        Generation.created_at >= output_window,
        or_(Generation.video_url.is_(None), Generation.video_url == ""),
    ).count()
    completed_missing_audio = Generation.query.filter(
        Generation.status == "completed",
        Generation.generation_type.in_(("voice", "audio", "voiceover")),
        Generation.created_at >= output_window,
        or_(Generation.audio_url.is_(None), Generation.audio_url == ""),
    ).count()
    missing_outputs = completed_missing_image + completed_missing_video + completed_missing_audio
    failure_rate = failed / recent_total if recent_total else 0.0
    failure_threshold = _positive_float("MONITORING_GENERATION_FAILURE_RATE_WARNING", 0.25)
    status = "critical" if stuck else (
        "warning" if missing_outputs or (recent_total >= 10 and failure_rate >= failure_threshold) else "healthy"
    )
    if stuck:
        summary = "{} generation(s) have remained processing beyond the configured threshold.".format(stuck)
    elif missing_outputs:
        summary = "{} completed generation(s) have no recorded output URL.".format(missing_outputs)
    else:
        summary = "{} of {} generations failed in the last 30 minutes.".format(failed, recent_total)
    return {
        "monitor_key": "generation_lifecycle",
        "status": status,
        "summary": summary,
        "metrics": {
            "stuck_processing": stuck,
            "failed_30m": failed,
            "total_30m": recent_total,
            "failure_rate_30m": round(failure_rate, 4),
            "completed_missing_image": completed_missing_image,
            "completed_missing_video": completed_missing_video,
            "completed_missing_audio": completed_missing_audio,
        },
    }


def _generation_abandonment_check(now):
    age_minutes = _positive_int("MONITORING_PENDING_GENERATION_MINUTES", 10)
    threshold = now - timedelta(minutes=age_minutes)
    stale_pending = Generation.query.filter(
        Generation.status == "pending",
        Generation.created_at <= threshold,
    ).count()
    critical_count = _positive_int("MONITORING_PENDING_GENERATION_CRITICAL_COUNT", 10)
    status = "critical" if stale_pending >= critical_count else (
        "warning" if stale_pending else "healthy"
    )
    return {
        "monitor_key": "generation_abandonment",
        "status": status,
        "summary": "{} generation(s) have remained pending for at least {} minutes.".format(
            stale_pending, age_minutes
        ),
        "metrics": {
            "stale_pending": stale_pending,
            "age_threshold_minutes": age_minutes,
            "critical_count_threshold": critical_count,
        },
    }


def _provider_check(now):
    health_rows = ProviderHealth.query.order_by(ProviderHealth.updated_at.desc()).all()
    since = now - timedelta(minutes=30)
    provider_log_limit = 5000
    recent_logs = (
        ProviderLog.query.filter(ProviderLog.timestamp >= since)
        .order_by(ProviderLog.timestamp.desc())
        .limit(provider_log_limit)
        .all()
    )
    failures = sum(1 for row in recent_logs if (row.status or "").lower() not in {"success", "succeeded", "completed"})
    total = len(recent_logs)
    failure_threshold = _positive_float("MONITORING_PROVIDER_FAILURE_RATE_WARNING", 0.5)
    unhealthy = [row for row in health_rows if (row.status or "").lower() in {"offline", "down", "unhealthy"}]
    degraded = [row for row in health_rows if (row.status or "").lower() in {"degraded", "warning"}]
    if unhealthy:
        status = "critical"
    elif degraded or (total >= 10 and failures / total >= failure_threshold):
        status = "warning"
    else:
        status = "healthy"
    return {
        "monitor_key": "provider_health",
        "status": status,
        "summary": "{} unavailable and {} degraded provider health record(s); {} of {} recent requests failed.".format(
            len(unhealthy), len(degraded), failures, total
        ),
        "metrics": {
            "unavailable_count": len(unhealthy),
            "degraded_count": len(degraded),
            "requests_30m": total,
            "failed_requests_30m": failures,
            "failure_rate_30m": round(failures / total, 4) if total else 0.0,
            "failure_rate_warning_threshold": failure_threshold,
            "inspection_limit": provider_log_limit,
        },
    }


def _webhook_check(now):
    since = now - timedelta(hours=1)
    rows = PaystackWebhookLog.query.filter(
        PaystackWebhookLog.created_at >= since
    ).order_by(PaystackWebhookLog.created_at.desc()).limit(1000).all()
    invalid_signatures = sum(1 for row in rows if not row.signature_verified)
    failed_outcomes = sum(
        1 for row in rows
        if any(token in (row.outcome or "").lower() for token in ("error", "fail", "exception"))
    )
    invalid_signature_threshold = _positive_int("MONITORING_WEBHOOK_INVALID_SIGNATURE_CRITICAL", 1)
    failure_threshold = _positive_int("MONITORING_WEBHOOK_FAILURE_WARNING", 1)
    status = "critical" if invalid_signatures >= invalid_signature_threshold else (
        "warning" if failed_outcomes >= failure_threshold else "healthy"
    )
    return {
        "monitor_key": "payment_webhooks",
        "status": status,
        "summary": "{} invalid signature(s) and {} failed outcome(s) in the last hour.".format(
            invalid_signatures, failed_outcomes
        ),
        "metrics": {
            "events_inspected": len(rows),
            "invalid_signatures_1h": invalid_signatures,
            "failed_outcomes_1h": failed_outcomes,
            "invalid_signature_critical_threshold": invalid_signature_threshold,
            "failed_outcome_warning_threshold": failure_threshold,
            "inspection_limit": 1000,
        },
    }


def _queue_check(_now):
    retry_count = PublishingRetryQueue.query.filter(
        PublishingRetryQueue.status.in_(("pending", "processing", "failed"))
    ).count()
    social_count = SocialPublishingJob.query.filter(
        SocialPublishingJob.status.in_(("pending", "running", "retrying"))
    ).count()
    total = retry_count + social_count
    threshold = _positive_int("MONITORING_QUEUE_BACKLOG_WARNING", 20)
    status = "critical" if total >= threshold * 2 else ("warning" if total >= threshold else "healthy")
    return {
        "monitor_key": "publishing_queues",
        "status": status,
        "summary": "{} publishing task(s) are pending, running, retrying, or failed.".format(total),
        "metrics": {
            "connected_account_tasks": retry_count,
            "social_publishing_jobs": social_count,
            "total_backlog": total,
            "warning_threshold": threshold,
        },
    }


def _database_capacity_check(_now):
    pool = db.engine.pool
    try:
        capacity = pool.size()
        checked_out = pool.checkedout()
    except (AttributeError, NotImplementedError):
        return {
            "monitor_key": "database_capacity",
            "status": "unknown",
            "summary": "Database connection-pool capacity is not exposed by this database driver.",
            "metrics": {"available": False},
        }
    if not capacity:
        return {
            "monitor_key": "database_capacity",
            "status": "unknown",
            "summary": "Database connection-pool capacity is not configured.",
            "metrics": {"available": False},
        }
    utilization = checked_out / capacity
    warning_threshold = _positive_float("MONITORING_DB_POOL_WARNING", 0.75)
    critical_threshold = max(
        warning_threshold,
        _positive_float("MONITORING_DB_POOL_CRITICAL", 0.9),
    )
    status = "critical" if utilization >= critical_threshold else (
        "warning" if utilization >= warning_threshold else "healthy"
    )
    return {
        "monitor_key": "database_capacity",
        "status": status,
        "summary": "Database connection pool is {:.0f}% utilized.".format(utilization * 100),
        "metrics": {
            "checked_out": checked_out,
            "configured_capacity": capacity,
            "utilization": round(utilization, 4),
            "warning_threshold": warning_threshold,
            "critical_threshold": critical_threshold,
            "available": True,
        },
    }


def _financial_activity_check(now):
    current_start = now - timedelta(days=30)
    previous_start = now - timedelta(days=60)
    current = db.session.query(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), 0),
    ).filter(Payment.created_at >= current_start).first()
    previous = db.session.query(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), 0),
    ).filter(
        Payment.created_at >= previous_start,
        Payment.created_at < current_start,
    ).first()
    current_count, current_amount = current
    previous_count, previous_amount = previous
    return {
        "monitor_key": "confirmed_revenue",
        "status": "healthy",
        "summary": "Recorded {} payment(s) in the last 30 days; figures exclude projections.".format(current_count),
        "metrics": {
            "confirmed_revenue_ngn_30d": round(float(current_amount or 0) / 100, 2),
            "payment_records_30d": current_count,
            "confirmed_revenue_ngn_previous_30d": round(float(previous_amount or 0) / 100, 2),
            "payment_records_previous_30d": previous_count,
        },
    }


def _ai_cost_check(now):
    since = now - timedelta(days=30)
    generation_cost, costed_generations = db.session.query(
        func.coalesce(func.sum(Generation.fal_cost_usd), 0),
        func.count(Generation.id),
    ).filter(
        Generation.created_at >= since,
        Generation.fal_cost_usd > 0,
    ).first()
    provider_cost, provider_costed_calls = db.session.query(
        func.coalesce(func.sum(ProviderLog.estimated_cost), 0),
        func.count(ProviderLog.id),
    ).filter(
        ProviderLog.timestamp >= since,
        ProviderLog.estimated_cost.isnot(None),
    ).first()
    return {
        "monitor_key": "ai_recorded_costs",
        "status": "healthy",
        "summary": "Recorded generation costs and provider estimates are reported separately.",
        "metrics": {
            "generation_cost_usd_recorded_30d": round(float(generation_cost or 0), 4),
            "costed_generations_30d": costed_generations,
            "provider_estimated_cost_recorded_30d": round(float(provider_cost or 0), 4),
            "provider_costed_calls_30d": provider_costed_calls,
        },
    }


def _credit_consumption_check(now):
    threshold = _positive_int("MONITORING_CREDIT_BURN_WARNING", 500)
    debits = func.sum(
        case((CreditLedger.delta < 0, -CreditLedger.delta), else_=0)
    )
    rows = (
        db.session.query(CreditLedger.user_id, debits.label("credits_spent"))
        .filter(CreditLedger.created_at >= now - timedelta(hours=24))
        .group_by(CreditLedger.user_id)
        .having(debits >= threshold)
        .order_by(debits.desc())
        .limit(26)
        .all()
    )
    affected = [
        {"user_id": row.user_id, "credits_spent_24h": int(row.credits_spent)}
        for row in rows[:25]
    ]
    count_text = "at least {} account(s)".format(len(rows)) if len(rows) > 25 else "{} account(s)".format(len(rows))
    return {
        "monitor_key": "credit_consumption",
        "status": "warning" if affected else "healthy",
        "summary": "{} crossed the configured 24-hour credit consumption review threshold.".format(count_text),
        "metrics": {
            "review_threshold_credits_24h": threshold,
            "affected_accounts": affected,
            "affected_accounts_returned": len(affected),
            "affected_accounts_truncated": len(rows) > 25,
        },
    }


def _read_linux_memory():
    values = {}
    with open("/proc/meminfo", "r", encoding="ascii") as memory_file:
        for line in memory_file:
            name, value = line.split(":", 1)
            if name in {"MemTotal", "MemAvailable"}:
                values[name] = int(value.strip().split()[0]) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        return None
    return values["MemTotal"], values["MemAvailable"]


def _host_capacity_check(now):
    disk_path = os.environ.get("MONITORING_DISK_PATH") or os.getcwd()
    disk = shutil.disk_usage(disk_path)
    disk_used_percent = (disk.used / disk.total * 100) if disk.total else 0
    memory = None
    try:
        memory = _read_linux_memory()
    except (OSError, ValueError):
        pass

    memory_used_percent = None
    memory_total = None
    memory_available = None
    if memory:
        memory_total, memory_available = memory
        memory_used_percent = (memory_total - memory_available) / memory_total * 100

    warning_threshold = min(100, _positive_float("MONITORING_RESOURCE_WARNING_PERCENT", 85))
    critical_threshold = max(
        warning_threshold,
        min(100, _positive_float("MONITORING_RESOURCE_CRITICAL_PERCENT", 95)),
    )
    pressure = [disk_used_percent]
    if memory_used_percent is not None:
        pressure.append(memory_used_percent)
    highest_pressure = max(pressure)
    status = "critical" if highest_pressure >= critical_threshold else (
        "warning" if highest_pressure >= warning_threshold else "healthy"
    )

    disk_history = (
        MonitoringSnapshot.query.filter(
            MonitoringSnapshot.monitor_key == "host_capacity",
            MonitoringSnapshot.observed_at >= now - timedelta(hours=24),
        )
        .order_by(MonitoringSnapshot.observed_at.asc())
        .limit(288)
        .all()
    )
    projected_days = None
    if len(disk_history) >= 12:
        first = disk_history[0]
        last = disk_history[-1]
        elapsed = (last.observed_at - first.observed_at).total_seconds()
        first_free = (first.metrics or {}).get("disk_free_bytes")
        last_free = (last.metrics or {}).get("disk_free_bytes")
        if elapsed >= 6 * 60 * 60 and first_free is not None and last_free is not None and first_free > last_free:
            bytes_per_second = (first_free - last_free) / elapsed
            threshold_free = disk.total * max(0, 1 - warning_threshold / 100)
            if bytes_per_second > 0 and last_free > threshold_free:
                projected_days = round((last_free - threshold_free) / bytes_per_second / 86400, 1)

    metrics = {
        "disk_used_percent": round(disk_used_percent, 2),
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "memory_available": memory is not None,
        "memory_used_percent": round(memory_used_percent, 2) if memory_used_percent is not None else None,
        "memory_available_bytes": memory_available,
        "memory_total_bytes": memory_total,
        "normalized_load_1m": None,
        "projected_days_until_disk_warning": projected_days,
        "projection_is_estimate": projected_days is not None,
    }
    if hasattr(os, "getloadavg"):
        try:
            metrics["normalized_load_1m"] = round(os.getloadavg()[0] / max(1, os.cpu_count() or 1), 3)
        except OSError:
            pass

    return {
        "monitor_key": "host_capacity",
        "status": status,
        "summary": "Host disk is {:.1f}% used{}.".format(
            disk_used_percent,
            " and memory is {:.1f}% used".format(memory_used_percent) if memory_used_percent is not None else "",
        ),
        "metrics": metrics,
    }


CHECKS = (
    _database_check,
    _generation_check,
    _generation_abandonment_check,
    _provider_check,
    _webhook_check,
    _queue_check,
    _database_capacity_check,
    _financial_activity_check,
    _ai_cost_check,
    _credit_consumption_check,
    _host_capacity_check,
)
CHECK_KEYS = {
    _database_check: "database",
    _generation_check: "generation_lifecycle",
    _generation_abandonment_check: "generation_abandonment",
    _provider_check: "provider_health",
    _webhook_check: "payment_webhooks",
    _queue_check: "publishing_queues",
    _database_capacity_check: "database_capacity",
    _financial_activity_check: "confirmed_revenue",
    _ai_cost_check: "ai_recorded_costs",
    _credit_consumption_check: "credit_consumption",
    _host_capacity_check: "host_capacity",
}
CHECK_RECOMMENDATIONS = {
    "database": "No action required.",
    "generation_lifecycle": "Inspect stuck jobs and completion callbacks; verify refunds before manual retries.",
    "generation_abandonment": "Inspect the generation queue and worker health; retry only after checking whether a job already ran.",
    "provider_health": "Review persisted provider health and recent request outcomes.",
    "payment_webhooks": "Review webhook verification and recorded outcomes without exposing request bodies.",
    "publishing_queues": "Inspect retryable jobs and queue workers; avoid replaying non-idempotent publishes.",
    "database_capacity": "Review connection-pool sizing and worker concurrency.",
    "confirmed_revenue": "Compare verified payment records with the payment provider ledger before financial decisions.",
    "ai_recorded_costs": "Reconcile recorded generation costs and provider estimates with invoices; do not treat estimates as invoices.",
    "credit_consumption": "Review the affected account IDs and ledger entries; this is a review signal only and does not suspend accounts.",
    "host_capacity": "Inspect host disk and memory capacity; projected time-to-threshold is a trend estimate, not a guarantee.",
}


def _record_incident_event(incident, event_type, now, *, actor_user_id=None, note=None, details=None):
    db.session.add(
        MonitoringIncidentEvent(
            incident_id=incident.id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            note=(note or "")[:1000] or None,
            details=details or {},
            created_at=now,
        )
    )
_SCHEMA_WARNING_EMITTED = False


def _snapshot_run_key(monitor_key, now):
    bucket = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    return "{}:{}".format(monitor_key, bucket.strftime("%Y%m%d%H%M"))


def _record_snapshot(result, now):
    run_key = _snapshot_run_key(result["monitor_key"], now)
    snapshot = MonitoringSnapshot.query.filter_by(run_key=run_key).one_or_none()
    if snapshot is None:
        snapshot = MonitoringSnapshot(
            run_key=run_key,
            monitor_key=result["monitor_key"],
            status=result["status"],
            summary=result["summary"][:255],
            metrics=result["metrics"],
            observed_at=now,
        )
        db.session.add(snapshot)
    else:
        snapshot.status = result["status"]
        snapshot.summary = result["summary"][:255]
        snapshot.metrics = result["metrics"]
        snapshot.observed_at = now
    return snapshot


def _record_incident(result, now):
    monitor_key = result["monitor_key"]
    if result["status"] == "healthy":
        incident = MonitoringIncident.query.filter_by(
            fingerprint=monitor_key
        ).one_or_none()
        if incident and incident.status in ACTIVE_INCIDENT_STATUSES:
            incident.status = "resolved"
            incident.resolved_at = now
            incident.last_seen_at = now
            incident.updated_at = now
            _record_incident_event(
                incident,
                "resolved",
                now,
                details={"monitor": monitor_key},
            )
        return
    if result["status"] == "unknown":
        return

    incident = MonitoringIncident.query.filter_by(fingerprint=monitor_key).one_or_none()
    if incident is None:
        incident = MonitoringIncident(
            fingerprint=monitor_key,
            source=monitor_key,
            title=result["summary"][:180],
            severity=result["status"],
            status="open",
            evidence=result["metrics"],
            recommendation=result["recommendation"],
            first_seen_at=now,
            last_seen_at=now,
            occurrences=1,
        )
        db.session.add(incident)
        db.session.flush()
        _record_incident_event(
            incident,
            "detected",
            now,
            details={"severity": incident.severity, "evidence": incident.evidence},
        )
        return

    incident.title = result["summary"][:180]
    previous_severity = incident.severity
    if incident.status in {"resolved", "closed"}:
        incident.status = "open"
        incident.first_seen_at = now
        incident.resolved_at = None
        incident.acknowledged_at = None
        _record_incident_event(
            incident,
            "reopened",
            now,
            details={"severity": result["status"], "evidence": result["metrics"]},
        )
    elif previous_severity != result["status"]:
        _record_incident_event(
            incident,
            "severity_changed",
            now,
            details={"previous": previous_severity, "current": result["status"]},
        )
    incident.severity = result["status"]
    incident.last_seen_at = now
    incident.occurrences += 1
    incident.evidence = result["metrics"]
    incident.recommendation = result["recommendation"]
    incident.updated_at = now


def run_monitoring_cycle(now=None):
    """Collect and persist bounded operational snapshots and deduplicated incidents."""
    global _SCHEMA_WARNING_EMITTED
    now = now or _utcnow()
    try:
        ensure_monitoring_tables(db.engine)
        inspector = db.inspect(db.engine)
        required_tables = {
            "monitoring_snapshots",
            "monitoring_incidents",
            "monitoring_incident_events",
            "monitoring_daily_reports",
        }
        if not required_tables.issubset(set(inspector.get_table_names())):
            ensure_monitoring_tables(db.engine)
    except Exception as exc:
        if not _SCHEMA_WARNING_EMITTED:
            current_app.logger.error("Could not inspect monitoring schema (%s)", type(exc).__name__)
            _SCHEMA_WARNING_EMITTED = True
        return []
    _SCHEMA_WARNING_EMITTED = False
    results = []
    for check in CHECKS:
        monitor_key = CHECK_KEYS[check]
        try:
            result = check(now)
        except Exception as exc:
            db.session.rollback()
            error_type = type(exc).__name__
            current_app.logger.error("Monitoring check %s failed (%s)", monitor_key, error_type)
            result = {
                "monitor_key": monitor_key,
                "status": "unknown",
                "summary": "Monitoring check could not complete ({}).".format(error_type),
                "metrics": {"check_completed": False},
            }
        result["recommendation"] = CHECK_RECOMMENDATIONS[result["monitor_key"]]
        try:
            _record_snapshot(result, now)
            _record_incident(result, now)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(
                "Could not persist monitoring check %s (%s)", result["monitor_key"], type(exc).__name__
            )
        results.append(result)

    try:
        cutoff = now - timedelta(days=SNAPSHOT_RETENTION_DAYS)
        MonitoringSnapshot.query.filter(MonitoringSnapshot.observed_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("Could not prune monitoring history (%s)", type(exc).__name__)
    return results


def latest_monitoring_snapshots(limit=24):
    latest = db.session.query(
        MonitoringSnapshot.monitor_key,
        func.max(MonitoringSnapshot.observed_at).label("latest_at"),
    ).group_by(MonitoringSnapshot.monitor_key).subquery()
    return (
        MonitoringSnapshot.query.join(
            latest,
            (MonitoringSnapshot.monitor_key == latest.c.monitor_key)
            & (MonitoringSnapshot.observed_at == latest.c.latest_at),
        )
        .order_by(MonitoringSnapshot.monitor_key.asc())
        .limit(limit)
        .all()
    )


def open_monitoring_incidents(limit=50):
    return (
        MonitoringIncident.query.filter(
            MonitoringIncident.status.in_(("open", "investigating", "identified", "resolving"))
        )
        .order_by(
            case(
                (MonitoringIncident.severity == "critical", 0),
                (MonitoringIncident.severity == "warning", 1),
                else_=2,
            ),
            MonitoringIncident.last_seen_at.desc(),
        )
        .limit(limit)
        .all()
    )


def update_monitoring_incident(
    incident,
    *,
    status,
    assigned_to=None,
    note=None,
    actor_user_id=None,
    now=None,
):
    if status not in INCIDENT_STATUSES:
        raise ValueError("Invalid incident status.")
    now = now or _utcnow()
    previous_status = incident.status
    previous_assignee = incident.assigned_to
    previous_note = incident.administrator_note
    was_acknowledged = incident.acknowledged_at is not None
    incident.status = status
    incident.assigned_to = (assigned_to or "").strip()[:255] or None
    incident.administrator_note = (note or "").strip()[:4000] or None
    incident.acknowledged_at = incident.acknowledged_at or now
    incident.resolved_at = now if status in {"resolved", "closed"} else None
    incident.updated_at = now
    if previous_status != status:
        _record_incident_event(
            incident,
            "status_changed",
            now,
            actor_user_id=actor_user_id,
            details={"previous": previous_status, "current": status},
        )
    if not was_acknowledged:
        _record_incident_event(
            incident,
            "acknowledged",
            now,
            actor_user_id=actor_user_id,
        )
    if previous_assignee != incident.assigned_to:
        _record_incident_event(
            incident,
            "assignment_changed",
            now,
            actor_user_id=actor_user_id,
            details={"assigned": bool(incident.assigned_to)},
        )
    if previous_note != incident.administrator_note:
        _record_incident_event(
            incident,
            "note_updated",
            now,
            actor_user_id=actor_user_id,
            note=(
                "Administrator note updated."
                if incident.administrator_note
                else "Administrator note cleared."
            ),
        )
    db.session.commit()
    return incident


def generate_daily_intelligence_report(now=None):
    """Persist a factual UTC-day summary; predictions are deliberately excluded."""
    now = now or _utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    signups = User.query.filter(
        User.signup_at >= start,
        User.signup_at < end,
    ).count()
    generations = dict(
        db.session.query(Generation.status, func.count(Generation.id))
        .filter(Generation.created_at >= start, Generation.created_at < end)
        .group_by(Generation.status)
        .all()
    )
    payment_count, payment_amount = db.session.query(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), 0),
    ).filter(Payment.created_at >= start, Payment.created_at < end).first()
    generation_cost_usd = db.session.query(
        func.coalesce(func.sum(Generation.fal_cost_usd), 0)
    ).filter(
        Generation.created_at >= start,
        Generation.created_at < end,
        Generation.fal_cost_usd > 0,
    ).scalar()
    provider_estimate = db.session.query(
        func.coalesce(func.sum(ProviderLog.estimated_cost), 0)
    ).filter(
        ProviderLog.timestamp >= start,
        ProviderLog.timestamp < end,
        ProviderLog.estimated_cost.isnot(None),
    ).scalar()
    active_incidents = open_monitoring_incidents(limit=25)
    active_incident_count = MonitoringIncident.query.filter(
        MonitoringIncident.status.in_(ACTIVE_INCIDENT_STATUSES)
    ).count()
    critical_incident_count = MonitoringIncident.query.filter(
        MonitoringIncident.status.in_(ACTIVE_INCIDENT_STATUSES),
        MonitoringIncident.severity == "critical",
    ).count()
    facts = {
        "period_start_utc": start.isoformat() + "Z",
        "period_end_utc": end.isoformat() + "Z",
        "user_signups": {
            "classification": "fact",
            "value": signups,
            "source": "users.signup_at",
        },
        "generation_activity": {
            "classification": "fact",
            "source": "generations.status",
            "by_status": generations,
            "completed": int(generations.get("completed", 0)),
            "failed": int(generations.get("failed", 0)),
        },
        "payment_activity": {
            "classification": "fact",
            "source": "payments",
            "payment_records": payment_count,
            "recorded_revenue_ngn": round(float(payment_amount or 0) / 100, 2),
        },
        "generation_cost": {
            "classification": "fact",
            "source": "generations.fal_cost_usd",
            "recorded_usd": round(float(generation_cost_usd or 0), 4),
        },
        "provider_cost": {
            "classification": "estimate",
            "source": "provider_logs.estimated_cost",
            "recorded_estimate": round(float(provider_estimate or 0), 4),
        },
        "active_incidents": {
            "classification": "fact",
            "count": active_incident_count,
            "critical": critical_incident_count,
            "recommendations_truncated": active_incident_count > len(active_incidents),
        },
    }
    recommendations = [
        {
            "priority": incident.severity,
            "source": incident.source,
            "action": incident.recommendation,
        }
        for incident in active_incidents
    ]

    report_date = start.date()
    report = MonitoringDailyReport.query.filter_by(report_date=report_date).one_or_none()
    if report is None:
        report = MonitoringDailyReport(report_date=report_date)
        db.session.add(report)
    report.facts = facts
    report.recommendations = recommendations
    report.generated_at = now
    db.session.commit()
    return report


