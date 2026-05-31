from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import secrets
from datetime import datetime, date

def generate_referral_code():
    return secrets.token_urlsafe(16)

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    plan = db.Column(db.String(20), default="free")

    # Daily credits
    credits = db.Column(db.Integer, default=10)
    daily_credits_used = db.Column(db.Integer, default=0)
    last_credit_reset = db.Column(db.Date, nullable=True)
    monthly_videos_used = db.Column(db.Integer, default=0)
    last_video_reset = db.Column(db.Date, nullable=True)

    monthly_images_used = db.Column(db.Integer, default=0)
    last_image_reset = db.Column(db.Date, nullable=True)

    is_banned = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    country = db.Column(db.String(100), nullable=True)
    signup_source = db.Column(db.String(100), nullable=True, default='direct')

    def __repr__(self):
        return f"<User {self.username}>"


class Generation(db.Model):
    __tablename__ = "generations"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    original_prompt = db.Column(db.Text, nullable=False)
    refined_prompt = db.Column(db.Text, nullable=False)

    video_url = db.Column(db.String(500), nullable=True)
    audio_url = db.Column(db.String(500), nullable=True)
    image_url = db.Column(db.String(500), nullable=True)

    generation_type = db.Column(db.String(20), default="text")
    status = db.Column(db.String(20), default="pending")


    ad_watched = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    fal_request_id = db.Column(db.String(200), nullable=True)

    # ONLY relationship definition
    user = db.relationship("User", backref="generations")

    def __repr__(self):
        return f"<Generation {self.id}>"


class TelegramUser(db.Model):
    __tablename__ = "telegram_users"

    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(50), unique=True, nullable=False)

    username = db.Column(db.String(80), nullable=True)
    first_name = db.Column(db.String(80), nullable=True)

    prompts_refined = db.Column(db.Integer, default=0)

    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TelegramUser {self.username}>"


class SavedPrompt(db.Model):
    __tablename__ = "saved_prompts"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    original_prompt = db.Column(db.Text, nullable=False)
    refined_prompt = db.Column(db.Text, nullable=True)

    prompt_type = db.Column(db.String(20), default="video")
    style = db.Column(db.String(20), default="cinematic")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="saved_prompts")


class Referral(db.Model):
    __tablename__ = "referrals"

    id = db.Column(db.Integer, primary_key=True)

    referrer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    referred_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    referral_code = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    is_used = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)