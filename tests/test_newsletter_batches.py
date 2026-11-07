import pytest
from app import app
from models import db, User, Subscriber, EmailOptOut, NewsletterIssue
from services.newsletter import collect_recipients, get_newsletter_batches, send_issue
from unittest.mock import patch

def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()

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

