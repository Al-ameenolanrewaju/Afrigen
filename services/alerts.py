import os
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models import AlertState, db


def notify_admin_alert(subject, message):
    recipients = [value.strip() for value in os.environ.get("ADMIN_EMAILS", "").split(",") if value.strip()]
    if not recipients:
        return False
    from services.email import send_admin_notice
    sent = False
    for recipient in recipients:
        sent = bool(send_admin_notice(recipient, subject, message)) or sent
    return sent


def claim_alert(alert_type):
    db.session.execute(
        pg_insert(AlertState).values(
            alert_type=alert_type,
            active=False,
        ).on_conflict_do_nothing(index_elements=[AlertState.alert_type])
    )
    result = db.session.execute(
        update(AlertState)
        .where(
            AlertState.alert_type == alert_type,
            AlertState.active.is_(False),
        )
        .values(
            active=True,
            last_alerted_at=datetime.now(timezone.utc),
        )
        .returning(AlertState.alert_type)
    )
    db.session.commit()
    return result.scalar_one_or_none() is not None


def clear_alert(alert_type):
    state = db.session.get(AlertState, alert_type)
    if state and state.active:
        state.active = False
        db.session.commit()


def alert_once(alert_type, subject, message):
    try:
        if not claim_alert(alert_type):
            return False
        notify_admin_alert(subject, message)
        return True
    except Exception as exc:
        db.session.rollback()
        print(f"Admin alert error: {exc}")
        return False