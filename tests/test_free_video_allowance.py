import pytest
from app import app
from models import db, User, CreditLedger
from services.credits import video_gate, charge_video, refund_video

def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()

def test_free_user_video_gate_without_allowance():
    with app.app_context():
        user = User(
            username="free_user_1",
            email="free1@example.com",
            password="hash",
            plan="free",
            credits=0,
            free_video_allowance=0
        )
        db.session.add(user)
        db.session.commit()

        ok, error, cost = video_gate(user, "cinematic")
        assert not ok
        assert "Video generation is a Pro feature" in error

def test_free_user_video_gate_with_allowance():
    with app.app_context():
        user = User(
            username="free_user_2",
            email="free2@example.com",
            password="hash",
            plan="free",
            credits=0,
            free_video_allowance=1
        )
        db.session.add(user)
        db.session.commit()

        ok, error, cost = video_gate(user, "cinematic")
        assert ok
        assert error is None
        assert cost == 0

def test_charge_and_refund_free_video_allowance():
    with app.app_context():
        user = User(
            username="free_user_3",
            email="free3@example.com",
            password="hash",
            plan="free",
            credits=0,
            free_video_allowance=2
        )
        db.session.add(user)
        db.session.commit()

        # Charge one video
        charge_video(user, cost=0)
        db.session.commit()

        assert user.free_video_allowance == 1
        ledger = CreditLedger.query.filter_by(user_id=user.id).order_by(CreditLedger.id.desc()).first()
        assert ledger is not None
        assert "Free video allowance used" in ledger.reason

        # Refund one video
        refund_video(user, cost=0, reason="Video failed refund")
        db.session.commit()

        assert user.free_video_allowance == 2
