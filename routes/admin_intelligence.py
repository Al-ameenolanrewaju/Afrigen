"""Parallel executive intelligence dashboard for Afrigen administrators.

This module is intentionally read-only. It reports only data already recorded by
Afrigen and labels payment totals as recorded amounts until reconciliation is
available in the payment schema.
"""
from datetime import datetime, timedelta, timezone
from collections import Counter

from flask import Blueprint, render_template, request
from sqlalchemy import func, case, and_

from models import (
    db, User, Generation, Payment, CreditLedger, WebsiteVisit, ProviderLog,
    ProviderHealth, Workflow, WorkflowRun, SocialPublishingJob, Referral,
)
from monitoring_models import MonitoringIncident, MonitoringSnapshot
from routes.main import admin_required

admin_intelligence = Blueprint(
    "admin_intelligence", __name__, url_prefix="/admin/intelligence"
)

PERIODS = {"7": 7, "30": 30, "90": 90}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _period():
    raw = request.args.get("period", "30")
    days = PERIODS.get(raw, 30)
    end = _utcnow()
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    return days, start, end, previous_start


def _count(query):
    return int(query.scalar() or 0)


def _safe_pct(current, previous):
    if not previous:
        return None
    return round(((current - previous) / previous) * 100, 1)


def _dashboard_data(days, start, end, previous_start):
    # All periods are half-open [start, end) and use naive UTC, matching the
    # application's existing timestamp conventions.
    prev_end = start
    total_users = _count(db.session.query(func.count(User.id)))
    signups = _count(db.session.query(func.count(User.id)).filter(
        User.signup_at >= start, User.signup_at < end
    ))
    previous_signups = _count(db.session.query(func.count(User.id)).filter(
        User.signup_at >= previous_start, User.signup_at < prev_end
    ))
    active_incidents = _count(db.session.query(func.count(MonitoringIncident.id)).filter(
        MonitoringIncident.status.in_(("open", "investigating", "identified", "resolving"))
    ))

    gen_q = db.session.query(
        func.count(Generation.id),
        func.sum(case((Generation.status == "completed", 1), else_=0)),
        func.sum(case((Generation.status == "failed", 1), else_=0)),
        func.sum(case((Generation.status.in_(("pending", "processing")), 1), else_=0)),
    ).filter(Generation.created_at >= start, Generation.created_at < end)
    gen_total, gen_completed, gen_failed, gen_pending = gen_q.one()
    prev_gen = _count(db.session.query(func.count(Generation.id)).filter(
        Generation.created_at >= previous_start, Generation.created_at < prev_end
    ))
    gen_total = int(gen_total or 0)
    gen_completed, gen_failed, gen_pending = int(gen_completed or 0), int(gen_failed or 0), int(gen_pending or 0)
    success_rate = round(gen_completed / gen_total * 100, 1) if gen_total else None

    # Payment.amount is stored in minor units. The Payment model has no status
    # column, so these are explicitly recorded payment rows, not verified revenue.
    payment_count, payment_minor = db.session.query(
        func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0)
    ).filter(Payment.created_at >= start, Payment.created_at < end).one()
    prev_payment_count, prev_payment_minor = db.session.query(
        func.count(Payment.id), func.coalesce(func.sum(Payment.amount), 0)
    ).filter(Payment.created_at >= previous_start, Payment.created_at < prev_end).one()

    visit_count = _count(db.session.query(func.count(WebsiteVisit.id)).filter(
        WebsiteVisit.created_at >= start, WebsiteVisit.created_at < end
    ))
    cost_usd, cost_calls = db.session.query(
        func.coalesce(func.sum(ProviderLog.estimated_cost), 0), func.count(ProviderLog.id)
    ).filter(ProviderLog.timestamp >= start, ProviderLog.timestamp < end).one()
    generation_cost_usd = db.session.query(
        func.coalesce(func.sum(Generation.fal_cost_usd), 0)
    ).filter(
        Generation.created_at >= start, Generation.created_at < end,
        Generation.fal_cost_usd > 0,
    ).scalar() or 0

    workflow_runs = _count(db.session.query(func.count(WorkflowRun.id)).filter(
        WorkflowRun.started_at >= start, WorkflowRun.started_at < end
    ))
    publishing_jobs = _count(db.session.query(func.count(SocialPublishingJob.id)).filter(
        SocialPublishingJob.created_at >= start, SocialPublishingJob.created_at < end
    ))
    referral_signups = _count(db.session.query(func.count(Referral.id)).filter(
        Referral.created_at >= start, Referral.created_at < end
    ))

    daily_labels, daily_signups, daily_generations = [], [], []
    for offset in range(days - 1, -1, -1):
        day_start = (end - timedelta(days=offset + 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        daily_labels.append(day_start.strftime("%b %d"))
        daily_signups.append(_count(db.session.query(func.count(User.id)).filter(
            User.signup_at >= day_start, User.signup_at < day_end
        )))
        daily_generations.append(_count(db.session.query(func.count(Generation.id)).filter(
            Generation.created_at >= day_start, Generation.created_at < day_end
        )))

    countries = db.session.query(
        User.country, func.count(User.id).label("total")
    ).filter(
        User.signup_at >= start, User.signup_at < end,
        User.country.isnot(None), User.country != "",
        func.lower(func.trim(User.country)) != "unknown"
    ).group_by(User.country).order_by(func.count(User.id).desc()).limit(8).all()

    sources = db.session.query(
        User.signup_source, func.count(User.id).label("total")
    ).filter(
        User.signup_at >= start, User.signup_at < end
    ).group_by(User.signup_source).order_by(func.count(User.id).desc()).limit(8).all()

    generation_types = db.session.query(
        Generation.generation_type, func.count(Generation.id)
    ).filter(
        Generation.created_at >= start, Generation.created_at < end
    ).group_by(Generation.generation_type).all()

    incidents = MonitoringIncident.query.filter(
        MonitoringIncident.status.in_(("open", "investigating", "identified", "resolving"))
    ).order_by(
        case((MonitoringIncident.severity == "critical", 0),
             (MonitoringIncident.severity == "warning", 1), else_=2),
        MonitoringIncident.last_seen_at.desc()
    ).limit(6).all()
    snapshots = MonitoringSnapshot.query.order_by(
        MonitoringSnapshot.observed_at.desc()
    ).limit(80).all()
    latest = {}
    for snap in snapshots:
        latest.setdefault(snap.monitor_key, snap)

    provider_health = ProviderHealth.query.order_by(ProviderHealth.updated_at.desc()).limit(8).all()
    recent_generations = Generation.query.order_by(Generation.created_at.desc()).limit(8).all()
    recent_signups = User.query.order_by(User.signup_at.desc()).limit(8).all()

    return {
        "total_users": total_users, "signups": signups,
        "signup_change": _safe_pct(signups, previous_signups),
        "previous_signups": previous_signups,
        "generations": gen_total, "previous_generations": prev_gen,
        "generation_change": _safe_pct(gen_total, prev_gen),
        "completed": gen_completed, "failed": gen_failed, "pending": gen_pending,
        "success_rate": success_rate, "recorded_payment_count": int(payment_count or 0),
        "recorded_payment_ngn": round(float(payment_minor or 0) / 100, 2),
        "previous_recorded_payment_ngn": round(float(prev_payment_minor or 0) / 100, 2),
        "previous_payment_count": int(prev_payment_count or 0),
        "visits": visit_count, "provider_estimated_cost_usd": round(float(cost_usd or 0), 4),
        "provider_cost_calls": int(cost_calls or 0),
        "generation_cost_usd_recorded": round(float(generation_cost_usd or 0), 4),
        "workflow_runs": workflow_runs, "publishing_jobs": publishing_jobs,
        "referral_signups": referral_signups, "active_incidents": active_incidents,
        "labels": daily_labels, "daily_signups": daily_signups,
        "daily_generations": daily_generations,
        "countries": [{"name": row[0], "count": int(row[1])} for row in countries],
        "sources": [{"name": row[0] or "Unknown", "count": int(row[1])} for row in sources],
        "generation_types": [{"name": row[0] or "Unknown", "count": int(row[1])} for row in generation_types],
        "incidents": incidents, "monitor_snapshots": list(latest.values()),
        "provider_health": provider_health, "recent_generations": recent_generations,
        "recent_signups": recent_signups,
    }


@admin_intelligence.route("/", methods=["GET"])
@admin_required
def overview():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template(
        "admin_intelligence/overview.html",
        intelligence=data, period=str(days), period_days=days,
        period_start=start, period_end=end,
    )


@admin_intelligence.route("/users")
@admin_required
def users():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="User Intelligence", active="users", intelligence=data, period=str(days))


@admin_intelligence.route("/finance")
@admin_required
def finance():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="Financial Intelligence", active="finance", intelligence=data, period=str(days))


@admin_intelligence.route("/ai")
@admin_required
def ai():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="AI Platform Intelligence", active="ai", intelligence=data, period=str(days))


@admin_intelligence.route("/operations")
@admin_required
def operations():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="Infrastructure & Operations", active="operations", intelligence=data, period=str(days))


@admin_intelligence.route("/growth")
@admin_required
def growth():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="Marketing & Growth", active="growth", intelligence=data, period=str(days))


@admin_intelligence.route("/security")
@admin_required
def security():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="Security & Administration", active="security", intelligence=data, period=str(days))


@admin_intelligence.route("/automation")
@admin_required
def automation():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="Automation & Customer Experience", active="automation", intelligence=data, period=str(days))


@admin_intelligence.route("/reports")
@admin_required
def reports():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="Reports & Founder Intelligence", active="reports", intelligence=data, period=str(days))


@admin_intelligence.route("/settings")
@admin_required
def settings():
    days, start, end, previous_start = _period()
    data = _dashboard_data(days, start, end, previous_start)
    return render_template("admin_intelligence/department.html",
        department="Administration & Settings", active="settings", intelligence=data, period=str(days))
