import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "fallback-secret-key"
    DEBUG = os.environ.get("DEBUG", "False") == "True"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Claude API
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

    # ElevenLabs
    ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

    # Telegram
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    # Bot @username (no @), used to build the "send /link to @bot" instructions.
    TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME")

    # Paystack
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY")

    # Video APIs
    KLING_API_KEY = os.environ.get("KLING_API_KEY")
    FAL_API_KEY = os.environ.get("FAL_KEY")

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Pre-launch waitlist page. Set LAUNCH_ACTIVE=false after launch to retire /launch.
    LAUNCH_ACTIVE = os.environ.get("LAUNCH_ACTIVE", "True").lower() in ("true", "1", "yes")

    # Secret for protecting the HTTP cron endpoints (weekly newsletter triggers).
    CRON_SECRET = os.environ.get("CRON_SECRET")

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

