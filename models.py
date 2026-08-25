from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import secrets
from datetime import datetime, date, timezone

import enum

class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"

class AssetType(str, enum.Enum):
    STRATEGY = "strategy"
    BLOG = "blog"
    NEWSLETTER = "newsletter"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    X = "x"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    LANDING_PAGE = "landing_page"

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

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    country = db.Column(db.String(100), nullable=True)
    signup_source = db.Column(db.String(100), nullable=True, default='direct')
    
    # Profile & Settings
    profile_picture = db.Column(db.String(500), nullable=True)
    email_notifications = db.Column(db.Boolean, default=True)
    marketing_emails = db.Column(db.Boolean, default=False)
    product_updates = db.Column(db.Boolean, default=True)
    default_ai_provider = db.Column(db.String(50), nullable=True, default='gemini')

    def __repr__(self):
        return f"<User {self.username}>"

class Brand(db.Model):
    __tablename__ = "brands"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    name = db.Column(db.String(255), nullable=False)
    logo_url = db.Column(db.String(500), nullable=True)
    cover_image_url = db.Column(db.String(500), nullable=True)
    
    primary_color = db.Column(db.String(50), nullable=True)
    secondary_color = db.Column(db.String(50), nullable=True)
    accent_color = db.Column(db.String(50), nullable=True)
    typography = db.Column(db.String(100), nullable=True)
    
    voice = db.Column(db.String(100), nullable=True)
    tone = db.Column(db.String(100), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    target_audience = db.Column(db.String(255), nullable=True)
    languages = db.Column(db.String(255), nullable=True)
    
    website = db.Column(db.String(255), nullable=True)
    social_links = db.Column(db.Text, nullable=True) # JSON string
    
    mission = db.Column(db.Text, nullable=True)
    vision = db.Column(db.Text, nullable=True)
    
    keywords = db.Column(db.String(500), nullable=True)
    negative_keywords = db.Column(db.String(500), nullable=True)
    
    preferred_art_style = db.Column(db.String(100), nullable=True)
    preferred_video_style = db.Column(db.String(100), nullable=True)
    voice_preference = db.Column(db.String(100), nullable=True)
    default_ai_models = db.Column(db.Text, nullable=True) # JSON string
    
    custom_instructions = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("brands", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<Brand {self.name}>"

class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    name = db.Column(db.String(255), nullable=False, default="Untitled Project")
    description = db.Column(db.Text, nullable=True)
    cover_image_url = db.Column(db.String(500), nullable=True)
    tags = db.Column(db.String(500), nullable=True)  # Comma separated tags
    
    is_favorite = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("projects", cascade="all, delete-orphan"))

    @property
    def generation_count(self):
        return len(self.generations)

    def __repr__(self):
        return f"<Project {self.name}>"


class Generation(db.Model):
    __tablename__ = "generations"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )
    
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=True
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

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    fal_request_id = db.Column(db.String(200), nullable=True)

    fal_request_id = db.Column(db.String(200), nullable=True)

    user = db.relationship("User", backref=db.backref("generations", cascade="all, delete-orphan"))
    project = db.relationship("Project", backref=db.backref("generations", cascade="all, delete-orphan"))

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

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("payments", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<Payment {self.reference}>"


class TelegramUser(db.Model):
    __tablename__ = "telegram_users"

    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(50), unique=True, nullable=False)

    username = db.Column(db.String(80), nullable=True)
    first_name = db.Column(db.String(80), nullable=True)
    chat_id = db.Column(db.String(80), nullable=True)
    chat_title = db.Column(db.String(255), nullable=True)

    prompts_refined = db.Column(db.Integer, default=0)

    # Linked website account. Generation through the bot draws from this user's
    # plan / credits / monthly limits, so the website and Telegram share one
    # source of truth for billing.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user = db.relationship("User", backref=db.backref("telegram_accounts", cascade="all, delete-orphan"))

    joined_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

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

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("saved_prompts", cascade="all, delete-orphan"))


class Subscriber(db.Model):
    """Pre-launch waitlist / newsletter signup (from the /launch page)."""
    __tablename__ = "subscribers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    newsletter = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

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
    attempted_count = db.Column(db.Integer, nullable=True)
    failed_count = db.Column(db.Integer, nullable=True)
    delivery_failures = db.Column(db.Text, nullable=True)
    send_attempted_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    sent_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<NewsletterIssue {self.id} {self.status}>"

class UserContent(db.Model):
    """Unified user-owned content library for generated assets.

    This replaces the old admin-only blog draft path for customer-generated
    content. Every item belongs to a logged-in user and can be published through
    the existing publishing engine later.
    """
    __tablename__ = "user_contents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    content_type = db.Column(db.String(50), nullable=False, default="text")
    title = db.Column(db.String(300), nullable=True)
    body = db.Column(db.Text, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    file_url = db.Column(db.String(500), nullable=True)
    thumbnail_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(30), default="draft")
    source = db.Column(db.String(50), default="manual")
    provider_used = db.Column(db.String(100), nullable=True)
    content_metadata = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    published_at = db.Column(db.DateTime, nullable=True)
    published_to = db.Column(db.String(100), nullable=True)

    user = db.relationship("User", backref=db.backref("contents", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<UserContent {self.id} {self.content_type}>"


class ConnectedAccount(db.Model):
    __tablename__ = "connected_accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    account_name = db.Column(db.String(100), nullable=True)
    account_identifier = db.Column(db.String(255), nullable=True)
    encrypted_access_token = db.Column(db.Text, nullable=True)
    encrypted_refresh_token = db.Column(db.Text, nullable=True)
    token_expiry = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="connected")
    connected_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_sync = db.Column(db.DateTime, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref=db.backref('connected_accounts', lazy=True, cascade="all, delete-orphan"))


class ServiceCredential(db.Model):
    """Stores system credentials (e.g. AI API keys, SMTP passwords) centrally, 
    separating them from external publishing ConnectedAccounts."""
    __tablename__ = "service_credentials"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_type = db.Column(db.String(50), nullable=False) # e.g. 'ai', 'email'
    provider = db.Column(db.String(50), nullable=False) # e.g. 'openai', 'smtp', 'resend'
    
    account_name = db.Column(db.String(100), nullable=True) # Optional friendly name
    encrypted_key = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.Text, nullable=True) # e.g. host, port, username for SMTP
    
    status = db.Column(db.String(20), default="active")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('service_credentials', lazy=True, cascade="all, delete-orphan"))


class PublishingPreference(db.Model):
    __tablename__ = "publishing_preferences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    content_type = db.Column(db.String(50), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    auto_publish = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('publishing_preferences', lazy=True, cascade="all, delete-orphan"))


class PublishingLog(db.Model):
    __tablename__ = "publishing_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey('user_contents.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    published_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    request_id = db.Column(db.String(100), nullable=True)
    response_id = db.Column(db.String(255), nullable=True)
    published_url = db.Column(db.Text, nullable=True)
    execution_time_ms = db.Column(db.Integer, nullable=True)
    error_details = db.Column(db.Text, nullable=True) # Stored as JSON string

    user = db.relationship('User', backref=db.backref('publishing_logs', lazy=True, cascade="all, delete-orphan"))
    content = db.relationship('UserContent', backref=db.backref('publishing_logs', lazy=True, cascade="all, delete-orphan"))

class PublishingRetryQueue(db.Model):
    __tablename__ = "publishing_retry_queue"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey('user_contents.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="pending") # pending, processing, failed, success
    retry_count = db.Column(db.Integer, default=0)
    next_attempt = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref=db.backref('publishing_retry_queue', lazy=True, cascade="all, delete-orphan"))
    content = db.relationship('UserContent', backref=db.backref('publishing_retry_queue', lazy=True, cascade="all, delete-orphan"))

class ProviderHealth(db.Model):
    __tablename__ = "provider_health"
    
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="healthy") # healthy, degraded, down
    success_count = db.Column(db.Integer, default=0)
    failure_count = db.Column(db.Integer, default=0)
    avg_latency_ms = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text, nullable=True)
    last_error_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def provider_name(self):
        return self.provider

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

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
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
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

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

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

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
    blog_post = db.relationship("BlogPost", backref=db.backref("distribution_runs", cascade="all, delete-orphan"))

    status = db.Column(db.String(20), default="running")  # running | completed | failed
    started_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
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

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f"<DistributionResult {self.platform} ok={self.ok}>"


class FacebookPostHistory(db.Model):
    """Tracks what has been posted to Facebook to prevent duplicate content."""
    __tablename__ = "facebook_post_history"

    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(50), nullable=False) # 'blog_update' or 'brand_awareness'
    blog_url = db.Column(db.String(500), nullable=True)
    post_text = db.Column(db.Text, nullable=False)
    facebook_post_id = db.Column(db.String(200), nullable=False)
    image_used = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f"<FacebookPostHistory {self.id} {self.content_type}>"





class ProviderLog(db.Model):
    __tablename__ = "provider_logs"

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False)
    provider_used = db.Column(db.String(50), nullable=False)
    fallback_triggered = db.Column(db.Boolean, default=False)
    latency = db.Column(db.Float, default=0.0)
    estimated_tokens = db.Column(db.Integer, default=0)
    estimated_cost = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="success") # success, error
    error_message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ProviderLog {self.task_type} via {self.provider_used}>"


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    
    title = db.Column(db.String(255), nullable=True)
    goal = db.Column(db.Text, nullable=False)
    business_goal = db.Column(db.Text, nullable=True)
    target_audience = db.Column(db.String(255), nullable=True)
    tone = db.Column(db.String(100), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), default="planning") # planning, generating, completed, failed
    progress = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("campaigns", cascade="all, delete-orphan"))
    project = db.relationship("Project", backref=db.backref("campaigns", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<Campaign {self.id} for Goal: {self.goal[:20]}>"

class CampaignTask(db.Model):
    __tablename__ = "campaign_tasks"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False)
    
    name = db.Column(db.String(255), nullable=False)
    task_type = db.Column(db.String(50), nullable=False)
    provider = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default="pending")
    priority = db.Column(db.Integer, default=0)
    progress = db.Column(db.Integer, default=0)
    
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    campaign = db.relationship("Campaign", backref=db.backref("campaign_tasks", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<CampaignTask {self.name} (Status: {self.status})>"


class Workflow(db.Model):
    __tablename__ = "workflows"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, unique=True)
    
    status = db.Column(db.String(50), default="pending") # pending, running, completed, failed
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    campaign = db.relationship("Campaign", backref=db.backref("workflow", uselist=False, cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<Workflow {self.id} for Campaign {self.campaign_id}>"


class WorkflowTask(db.Model):
    __tablename__ = "workflow_tasks"

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey("workflows.id"), nullable=False)
    
    task_type = db.Column(db.String(50), nullable=False) # e.g. campaign_strategy, blog_article, facebook_post
    status = db.Column(db.String(50), default="pending") # pending, in_progress, completed, failed
    
    # Store dependencies as a JSON list of internal task string IDs (e.g., ["strategy", "blog"])
    # We will map these string IDs to the actual DB rows upon insertion.
    dependencies = db.Column(db.Text, nullable=True) # JSON array of internal IDs
    internal_id = db.Column(db.String(50), nullable=True) # E.g., "task_1", used for resolving dependencies
    
    result_data = db.Column(db.Text, nullable=True) # JSON payload containing the output
    error_msg = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    workflow = db.relationship("Workflow", backref=db.backref("tasks", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<WorkflowTask {self.task_type} (Status: {self.status})>"


class CampaignAsset(db.Model):
    __tablename__ = "campaign_assets"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False)
    task_id = db.Column(db.Integer, nullable=True) # Removed FK to allow workflow_tasks OR campaign_tasks IDs
    
    asset_type = db.Column(db.String(50), nullable=False) # image, video, blog_text, social_post
    title = db.Column(db.String(255), nullable=True)
    content = db.Column(db.Text, nullable=False) # URL to media or raw text content
    file_url = db.Column(db.String(500), nullable=True)
    thumbnail_url = db.Column(db.String(500), nullable=True)
    meta_data = db.Column("metadata", db.Text, nullable=True)
    provider_used = db.Column(db.String(100), nullable=True)
    generation_time = db.Column(db.Float, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    campaign = db.relationship("Campaign", backref=db.backref("assets", cascade="all, delete-orphan"))
    task = db.relationship("CampaignTask", primaryjoin="CampaignAsset.task_id == CampaignTask.id", foreign_keys=[task_id], backref=db.backref("generated_asset", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<CampaignAsset {self.asset_type}>"


class CampaignAnalytics(db.Model):
    __tablename__ = "campaign_analytics"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=False, unique=True)
    
    metrics = db.Column(db.Text, nullable=True) # JSON storing likes, shares, clicks, etc.
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    campaign = db.relationship("Campaign", backref=db.backref("analytics", uselist=False, cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<CampaignAnalytics for Campaign {self.campaign_id}>"