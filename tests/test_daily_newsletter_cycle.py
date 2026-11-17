import pytest
from unittest.mock import patch

from app import app
from models import db, User, Subscriber, EmailOptOut, NewsletterIssue
from services.newsletter import collect_recipients


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_collect_recipients_includes_independent_subscribers_deduplicates_and_honors_opt_out():
    with app.app_context():
        user = User(username="registered", email="same@example.net", password="pw", credits=5, marketing_emails=True)
        db.session.add(user)
        db.session.add_all([
            Subscriber(name="Duplicate", email="SAME@example.net", newsletter=True),
            Subscriber(name="Independent", email="independent@example.net", newsletter=True),
            Subscriber(name="Opted out", email="blocked@example.net", newsletter=True),
            EmailOptOut(email="blocked@example.net"),
        ])
        db.session.commit()

        recipients = collect_recipients()
        normalized = [email.lower() for email, _name in recipients]
        assert normalized.count("same@example.net") == 1
        assert "independent@example.net" in normalized
        assert "blocked@example.net" not in normalized


def test_daily_newsletter_cycle_snapshots_and_sends_batches_without_skipping():
    with app.app_context():
        db.session.add_all([
            Subscriber(name=f"Reader {i}", email=f"reader{i}@mail.net", newsletter=True)
            for i in range(85)
        ])
        db.session.commit()

        with patch("services.newsletter.generate_weekly_digest", return_value=("Daily edition", "<p>Useful content</p>")):
            with patch("services.newsletter.send_newsletter", side_effect=[
                {"attempted": 80, "sent": 80, "failed": 0, "failures": [], "test_recipient": None},
                {"attempted": 5, "sent": 5, "failed": 0, "failures": [], "test_recipient": None},
            ]) as sender:
                from services.newsletter import run_daily_newsletter_cycle
                first = run_daily_newsletter_cycle()
                second = run_daily_newsletter_cycle()

        assert first["sent"] == 80
        assert first["pending"] == 5
        assert second["sent"] == 5
        assert second["pending"] == 0
        assert sender.call_count == 2
        issue = NewsletterIssue.query.one()
        assert issue.status == "sent"
        assert issue.recipients_count == 85
