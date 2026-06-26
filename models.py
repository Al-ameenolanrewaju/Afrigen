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

    # One-time code shown on the dashboard so a user can link their Telegram
    # account to this website account (sent to the bot as `/link <code>`).
    # Cleared once the link is established.
    telegram_link_code = db.Column(db.String(20), nullable=True)

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

    # Whether the user requested an AI voiceover (Pro). The voiceover is
    # generated in the fal webhook once the video actually succeeds, so we
    # remember the choice here at request time.
    wants_voiceover = db.Column(db.Boolean, default=False)


    ad_watched = db.Column(db.Boolean, default=False)

    # Credits charged for this generation. Premium (Kling) videos cost more than
    # the cheaper AnimateDiff path, so we record the price at request time and
    # deduct exactly that amount once the video succeeds.
    credit_cost = db.Column(db.Integer, nullable=False, default=5, server_default="5")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    fal_request_id = db.Column(db.String(200), nullable=True)

    # ONLY relationship definition
    user = db.relationship("User", backref="generations")

    def __repr__(self):
        return f"<Generation {self.id}>"


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Paystack transaction reference. Unique so a given payment can only ever
    # grant credits once (prevents reference-replay credit refills).
    reference = db.Column(db.String(200), unique=True, nullable=False)
    amount = db.Column(db.Integer, nullable=True)
    plan = db.Column(db.String(20), default="monthly")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="payments")

    def __repr__(self):
        return f"<Payment {self.reference}>"


class TelegramUser(db.Model):
    __tablename__ = "telegram_users"

    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(50), unique=True, nullable=False)

    username = db.Column(db.String(80), nullable=True)
    first_name = db.Column(db.String(80), nullable=True)

    prompts_refined = db.Column(db.Integer, default=0)

    # Linked website account. Generation through the bot draws from this user's
    # plan / credits / monthly limits, so the website and Telegram share one
    # source of truth for billing.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user = db.relationship("User", backref="telegram_accounts")

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


class Subscriber(db.Model):
    """Pre-launch waitlist / newsletter signup (from the /launch page)."""
    __tablename__ = "subscribers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    newsletter = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Subscriber {self.email}>"


class NewsletterIssue(db.Model):
    """A weekly newsletter. The most recent row with status='draft' is the
    'current draft' the admin can edit before it ships."""
    __tablename__ = "newsletter_issues"

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(300), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")  # HTML body, editable
    status = db.Column(db.String(20), default="draft")      # draft | sent
    auto_generated = db.Column(db.Boolean, default=True)
    recipients_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<NewsletterIssue {self.id} {self.status}>"


class BlogPost(db.Model):
    """A blog article shown at /blog. Auto-generated posts land as status='draft'
    and stay completely invisible to the public until an admin approves them at
    /admin/blog (which sets status='published' + published_at). Mirrors the
    NewsletterIssue draft→approve lifecycle."""
    __tablename__ = "blog_posts"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.String(320), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")   # trusted HTML, rendered with | safe
    tag = db.Column(db.String(60), default="")
    read_time = db.Column(db.String(40), default="")

    status = db.Column(db.String(20), default="draft")       # draft | published
    auto_generated = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published_at = db.Column(db.DateTime, nullable=True)

    @property
    def date(self):
        """Human display date used by the templates (matches the old dict field)."""
        d = self.published_at or self.created_at
        return d.strftime("%B %d, %Y") if d else ""

    def __repr__(self):
        return f"<BlogPost {self.slug} {self.status}>"


class EmailOptOut(db.Model):
    """Emails that have unsubscribed from the newsletter."""
    __tablename__ = "email_opt_outs"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<EmailOptOut {self.email}>"


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

    def __repr__(self):
        return f"<Referral {self.referral_code}>"


class DistributionRun(db.Model):
    """One distribution attempt for a blog post — triggered from the admin panel.
    Tracks overall status and per-platform results so the admin can see what
    succeeded, what failed, and retry individual platforms."""
    __tablename__ = "distribution_runs"

    id = db.Column(db.Integer, primary_key=True)
    blog_post_id = db.Column(
        db.Integer, db.ForeignKey("blog_posts.id"), nullable=False
    )
    blog_post = db.relationship("BlogPost", backref="distribution_runs")

    status = db.Column(db.String(20), default="running")  # running | completed | failed
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    # Summary counts (denormalized for fast display)
    total_platforms = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    fail_count = db.Column(db.Integer, default=0)

    results = db.relationship(
        "DistributionResult", back_populates="run",
        cascade="all, delete-orphan", order_by="DistributionResult.platform"
    )

    def __repr__(self):
        return f"<DistributionRun {self.id} post={self.blog_post_id} {self.status}>"


class DistributionResult(db.Model):
    """Per-platform result within a distribution run."""
    __tablename__ = "distribution_results"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(
        db.Integer, db.ForeignKey("distribution_runs.id"), nullable=False
    )
    run = db.relationship("DistributionRun", back_populates="results")

    platform = db.Column(db.String(30), nullable=False)  # twitter, linkedin, etc.
    ok = db.Column(db.Boolean, default=False)
    error = db.Column(db.Text, nullable=True)
    post_url = db.Column(db.String(500), nullable=True)   # live link to the posted content
    extra = db.Column(db.Text, nullable=True)              # JSON blob for platform-specific data

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DistributionResult {self.platform} ok={self.ok}>"