from unittest.mock import patch
from app import app
from models import db, User, Subscriber, EmailOptOut
from services.newsletter import (
    upsert_subscriber_from_user,
    sync_user_email_preferences,
    sync_all_users_to_subscribers,
    get_newsletter_audience_count,
)


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_upsert_subscriber_from_user_adds_signup_record():
    with app.app_context():
        user = User(
            username='alice',
            email='alice@example.com',
            password='hash',
            credits=5,
            marketing_emails=True,
        )
        db.session.add(user)
        db.session.commit()

        upsert_subscriber_from_user(user)

        subscriber = Subscriber.query.filter_by(email='alice@example.com').first()
        assert subscriber is not None
        assert subscriber.name == 'alice'
        assert subscriber.newsletter is True
        assert subscriber.created_at is not None
        assert user.signup_at is not None


def test_sync_user_email_preferences_persists_marketing_opt_in():
    with app.app_context():
        user = User(
            username='bob',
            email='bob@example.com',
            password='hash',
            credits=5,
            marketing_emails=False,
        )
        db.session.add(user)
        db.session.commit()

        sync_user_email_preferences(user, {'marketing_emails': 'on'})

        db.session.refresh(user)
        assert user.marketing_emails is True
        subscriber = Subscriber.query.filter_by(email='bob@example.com').first()
        assert subscriber is not None
        assert subscriber.newsletter is True


def test_sync_all_users_to_subscribers_backfills_missing_users():
    with app.app_context():
        user = User(
            username='charlie',
            email='charlie@example.com',
            password='hash',
            credits=5,
            marketing_emails=False,
        )
        db.session.add(user)
        db.session.commit()

        created = sync_all_users_to_subscribers()

        assert created == 1
        subscriber = Subscriber.query.filter_by(email='charlie@example.com').first()
        assert subscriber is not None
        assert subscriber.newsletter is False


def test_get_newsletter_audience_count_counts_registered_users_and_waitlist_without_duplicates():
    with app.app_context():
        user = User(
            username='dana',
            email='dana@example.com',
            password='hash',
            credits=5,
            marketing_emails=False,
        )
        db.session.add(user)
        db.session.add(Subscriber(name='Waitlist Person', email='waitlist@example.com', newsletter=True))
        db.session.add(Subscriber(name='Duplicate User', email='dana@example.com', newsletter=True))
        db.session.commit()

        count = get_newsletter_audience_count()

        assert count == 2



def test_existing_waitlist_subscriber_can_explicitly_reenable_newsletter():
    with app.app_context():
        subscriber = Subscriber(
            name='Returning Reader',
            email='reader@example.com',
            newsletter=False,
        )
        db.session.add(subscriber)
        db.session.add(EmailOptOut(email='reader@example.com'))
        db.session.commit()

        client = app.test_client()
        with patch('services.email.send_launch_confirmation'):
            response = client.post('/launch/subscribe', json={
                'name': 'Returning Reader',
                'email': 'reader@example.com',
                'newsletter': True,
            })

        assert response.status_code == 200
        assert response.get_json()['already'] is True
        db.session.refresh(subscriber)
        assert subscriber.newsletter is True
        assert EmailOptOut.query.filter_by(email='reader@example.com').first() is None


def test_app_keeps_user_sessions_persistent():
    assert app.config.get('SESSION_PERMANENT') is True
    assert app.config.get('PERMANENT_SESSION_LIFETIME').days >= 7
    assert app.config.get('REMEMBER_COOKIE_DURATION').days >= 7
