import logging
import pytest
from app import app
from models import db, User, Subscriber, EmailOptOut, NewsletterIssue
from services.newsletter import collect_recipients, get_newsletter_batches, send_issue
from services.email import send_newsletter
from unittest.mock import patch

def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()

def test_routine_scheduler_and_http_logs_are_suppressed():
    assert logging.getLogger("apscheduler.executors.default").level == logging.WARNING
    assert logging.getLogger("werkzeug").level == logging.WARNING

def test_collect_recipients_slicing():
    with app.app_context():
        # Create 100 test users
        users = [
            User(username=f"user_{i}", email=f"user_{i}@example.com", password="pw", credits=5)
            for i in range(100)
        ]
        db.session.add_all(users)
        db.session.commit()

        # Batch 1: first 80
        batch_1 = collect_recipients(limit=80, offset=0)
        assert len(batch_1) == 80
        assert batch_1[0][0] == "user_0@example.com"
        assert batch_1[-1][0] == "user_79@example.com"

        # Batch 2: remaining 20
        batch_2 = collect_recipients(limit=80, offset=80)
        assert len(batch_2) == 20
        assert batch_2[0][0] == "user_80@example.com"
        assert batch_2[-1][0] == "user_99@example.com"

def test_get_newsletter_batches():
    with app.app_context():
        # Create 185 test users
        users = [
            User(username=f"u_{i}", email=f"u_{i}@example.com", password="pw", credits=5)
            for i in range(185)
        ]
        db.session.add_all(users)
        db.session.commit()

        batches, total = get_newsletter_batches(batch_size=80)
        assert total == 185
        assert len(batches) == 3

        # Batch 1: 0 - 80
        assert batches[0]["offset"] == 0
        assert batches[0]["count"] == 80

        # Batch 2: 80 - 160
        assert batches[1]["offset"] == 80
        assert batches[1]["count"] == 80

        # Batch 3: 160 - 185
        assert batches[2]["offset"] == 160
        assert batches[2]["count"] == 25

def test_send_newsletter_uses_configured_test_recipient():
    with app.app_context(), patch.dict("os.environ", {"NEWSLETTER_TEST_RECIPIENT": "test@resend.dev"}):
        with patch("services.email.resend.Batch.send", return_value={"data": [{}, {}]}) as send_batch:
            result = send_newsletter(
                [("one@example.com", "One"), ("two@example.com", "Two")],
                "Test subject",
                "Test body",
                return_details=True,
            )

    payloads = send_batch.call_args.args[0]
    assert [payload["to"] for payload in payloads] == ["test@resend.dev", "test@resend.dev"]
    assert result["sent"] == 2
    assert result["test_recipient"] == "test@resend.dev"

def test_send_newsletter_skips_reserved_example_domains():
    with app.app_context(), patch.dict("os.environ", {"NEWSLETTER_TEST_RECIPIENT": ""}):
        with patch("services.email.resend.Batch.send", return_value={"data": [{}, {}]}) as send_batch:
            result = send_newsletter(
                [("one@gmail.com", "One"), ("placeholder@example.com", "Placeholder"), ("two@gmail.com", "Two")],
                "Test subject",
                "Test body",
                return_details=True,
            )

    payloads = send_batch.call_args.args[0]
    assert [payload["to"] for payload in payloads] == ["one@gmail.com", "two@gmail.com"]
    assert result["attempted"] == 3
    assert result["sent"] == 2
    assert result["failed"] == 1
    assert result["failures"][0]["email"] == "placeholder@example.com"

def test_send_newsletter_isolates_provider_rejected_recipient(caplog):
    def send_batch(payloads):
        if any(payload["to"] == "blocked@qa-mail.net" for payload in payloads):
            raise Exception("Invalid `to` field. Please use our testing email address.")
        return {"data": [{} for _ in payloads]}

    with app.app_context(), patch.dict("os.environ", {"NEWSLETTER_TEST_RECIPIENT": ""}):
        with patch("services.email.resend.Batch.send", side_effect=send_batch):
            result = send_newsletter(
                [
                    ("one@gmail.com", "One"),
                    ("blocked@qa-mail.net", "Blocked"),
                    ("two@gmail.com", "Two"),
                ],
                "Test subject",
                "Test body",
                return_details=True,
            )

    assert result["sent"] == 2
    assert result["failed"] == 1
    assert result["failures"][0]["email"] == "blocked@qa-mail.net"
    assert "attempted=3 sent=2 failed=1" in caplog.text
    assert "Invalid `to` field" in caplog.text
    assert "blocked@qa-mail.net" not in caplog.text

