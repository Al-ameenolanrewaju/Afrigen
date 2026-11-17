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

        with patch("services.newsletter.generate_weekly_digest", return_value=("Daily edition", "<p>Useful content</p>", [{"title": "Source", "publisher": "Publisher", "url": "https://example.com/story"}])) as generator:
            with patch("services.newsletter.send_newsletter", side_effect=[
                {"attempted": 80, "sent": 80, "failed": 0, "failures": [], "test_recipient": None},
                {"attempted": 5, "sent": 5, "failed": 0, "failures": [], "test_recipient": None},
            ]) as sender:
                from services.newsletter import run_daily_newsletter_cycle
                generated = run_daily_newsletter_cycle()
                assert generator.call_args.kwargs["include_research"] is True
                issue = NewsletterIssue.query.one()
                assert generated["awaiting_approval"] is True
                assert sender.call_count == 0
                issue.status = "approved"
                db.session.commit()
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



def test_daily_newsletter_retries_failed_recipient_before_next_fixed_cohort():
    with app.app_context():
        db.session.add_all([
            Subscriber(name=f"Reader {i}", email=f"cohort{i}@mail.net", newsletter=True)
            for i in range(82)
        ])
        db.session.commit()

        with patch("services.newsletter.generate_weekly_digest", return_value=("Daily edition", "<p>Useful content</p>", [{"title": "Source", "publisher": "Publisher", "url": "https://example.com/story"}])):
            with patch("services.newsletter.send_newsletter", side_effect=[
                {"attempted": 80, "sent": 79, "failed": 1,
                 "failures": [{"email": "cohort0@mail.net", "error": "temporary"}], "test_recipient": None},
                {"attempted": 1, "sent": 1, "failed": 0, "failures": [], "test_recipient": None},
                {"attempted": 2, "sent": 2, "failed": 0, "failures": [], "test_recipient": None},
            ]) as sender:
                from services.newsletter import run_daily_newsletter_cycle
                generated = run_daily_newsletter_cycle()
                issue = NewsletterIssue.query.one()
                assert generated["awaiting_approval"] is True
                assert sender.call_count == 0
                issue.status = "approved"
                db.session.commit()
                first = run_daily_newsletter_cycle()
                retry = run_daily_newsletter_cycle()
                final = run_daily_newsletter_cycle()

        assert first["pending"] == 3
        assert retry["sent"] == 1
        assert retry["pending"] == 2
        assert final["sent"] == 2
        assert sender.call_args_list[1].args[0] == [("cohort0@mail.net", "Reader 0")]
        assert sender.call_args_list[2].args[0] == [
            ("cohort80@mail.net", "Reader 80"),
            ("cohort81@mail.net", "Reader 81"),
        ]
        assert NewsletterIssue.query.one().status == "sent"


def test_legacy_zero_count_newsletter_metrics_are_rejected_before_approval():
    from routes.main import _contains_stale_newsletter_metrics

    assert _contains_stale_newsletter_metrics(
        "<h2>Afrigen Update</h2><p>We are currently at 0 creators and 0 generations.</p>"
    )
    assert _contains_stale_newsletter_metrics(
        "<p>Currently at 0 creator and 0 generation.</p>"
    )
    assert not _contains_stale_newsletter_metrics(
        "<p>Learn a practical way to improve your next video.</p>"
    )
    assert not _contains_stale_newsletter_metrics(
        "<p>Our community continues to build.</p>"
    )
