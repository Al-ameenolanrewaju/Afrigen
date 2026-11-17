"""Daily editorial magazine generation and newsletter delivery lifecycle."""
import os
import re
import json
import logging
from datetime import datetime, date, timezone

from models import db, User, Subscriber, Generation, NewsletterIssue, EmailOptOut
from services.email import send_newsletter, BASE_URL

logger = logging.getLogger(__name__)


# Same model the rest of the app uses (Groq). Override with NEWSLETTER_MODEL if desired.
NEWSLETTER_MODEL = (
    os.environ.get("NEWSLETTER_MODEL")
    or os.environ.get("GROQ_MODEL")
    or "openai/gpt-oss-20b"
)

# Ground-truth list of things Afrigen can actually do, fed to the model so the
# newsletter only ever promotes REAL features (never hallucinated ones). Keep this
# in sync with the product — the model picks ONE to spotlight each week.
AFRIGEN_FEATURES = [
    "Public share pages: every video/image you generate gets its own clean shareable link with a 'create your own, free' button — great for Reels and bios.",
    "Text-to-video from a simple prompt, with a built-in AI prompt refiner that expands your idea into a detailed shot.",
    "Five video styles: Cinematic, Anime, Realistic, African, and Social.",
    "AI image generation from text.",
    "Image-to-video (Pro): turn a still photo into a moving clip.",
    "AI voiceover baked into your video (Pro).",
    "Longer 10-second clips on supported styles (Pro).",
    "On-screen text/captions burned straight onto the finished clip.",
    "Aspect ratios for every platform: 9:16 vertical for TikTok/Reels/Status, 16:9, and 1:1.",
    "Telegram bot for refining prompts on the go.",
    "Referral program: earn free credits when friends you invite sign up.",
]


# ---------- AI generation (Groq, grounded in our own product + blog) ----------

def generate_weekly_digest(stats=None, include_research=False):
    """Write this week's Afrigen newsletter using Content Engine.

    Grounded in our REAL features and REAL published blog posts (with their exact
    URLs) so nothing is invented. Returns (subject, body_html). Raises on
    API/config errors so callers can surface the problem instead of silently
    sending an empty email.
    """
    from services.blog import get_all_posts
    import sys
    import os
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
        
    from content_engine import ContentPlanner, generate_content_brief, write_newsletter

    # 1. Select the stable daily magazine theme using Nigeria-local time.
    planner = ContentPlanner()
    editorial_theme = planner.select_newsletter_theme()
    category = editorial_theme["category"]

    stats = stats or {}
    posts = get_all_posts()[:5]

    # 2. Research recent AI developments before writing the edition.
    # Feed failures are isolated; the writer safely falls back to evergreen content
    # when no sufficiently recent, parseable source material is available.
    from services.newsletter_research import collect_newsletter_research
    research_sources = collect_newsletter_research()
    logger.info("Newsletter research collected %s verified feed items", len(research_sources))

    # 3. Build the master brief around the day's editorial angle.
    latest_post = posts[0] if posts else None
    source_context = (
        f"Daily newsletter editorial: {editorial_theme['name']}. "
        f"Direction: {editorial_theme['angle']} "
        f"Focus on useful AI knowledge, practical creator education, and African creativity. "
        f"Latest published article: {latest_post.title if latest_post else 'No current article supplied; use an evergreen subject.'}"
    )
    brief = generate_content_brief(category, source_context)

    # 4. Generate newsletter using only the curated research records above.
    generated = write_newsletter(
        brief=brief,
        stats=stats,
        posts=posts,
        research_sources=research_sources,
    )
    
    result = (
        generated.extra_fields.get("subject", "The Creator Intelligence Brief"),
        generated.content,
    )
    return (*result, research_sources) if include_research else result


def _strip_code_fences(text):
    """llama often wraps its output in ```html ... ``` fences — remove them so the
    SUBJECT line and HTML body come through clean."""
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines).strip()


# Tags that take no attributes in our newsletter HTML. The model occasionally
# fumbles their opening tag — e.g. it writes `<p"Hello` or `<p">Hello` instead of
# `<p>Hello` — which then renders as broken text in the email. Normalise those.
_ATTRLESS_TAGS = ("p", "h1", "h2", "h3", "h4", "strong", "ul", "li", "em", "br", "div", "span")


def _clean_html(text):
    """Repair the common malformed-opening-tag glitch (`<p"`, `<h3 '>`, …) for
    attribute-less tags, turning them back into clean `<p>`/`<h3>` tags. Leaves
    well-formed tags and attribute-bearing tags like <a href="…"> untouched."""
    for tag in _ATTRLESS_TAGS:
        # A stray quote sitting where the closing `>` belongs, with optional
        # whitespace and an optional trailing `>`.
        text = re.sub(rf'<{tag}\s*["\']\s*>?', f'<{tag}>', text, flags=re.IGNORECASE)
        # Same for the closing tag, e.g. `</p"` -> `</p>`.
        text = re.sub(rf'</{tag}\s*["\']\s*>?', f'</{tag}>', text, flags=re.IGNORECASE)
    return text


def _split_subject(text, fallback_subject):
    """Pull the 'SUBJECT: ...' first line out of the model output."""
    subject = fallback_subject
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip().upper().startswith("SUBJECT:"):
        subject = lines[0].split(":", 1)[1].strip() or fallback_subject
        body = "\n".join(lines[1:]).strip()
    return subject, body


# ---------- Recipients ----------

def collect_recipients(limit=None, offset=0):
    """Return deduplicated, explicitly opted-in users and newsletter subscribers.

    Global opt-outs are always excluded. Registered accounts must have marketing
    emails enabled; waitlist subscribers must have their newsletter flag enabled.
    """
    opted_out = {
        (email or "").strip().lower()
        for (email,) in db.session.query(EmailOptOut.email).all()
    }

    seen = set()
    recipients = []

    # Registered accounts are eligible only when the user opted into marketing.
    user_query = db.session.query(User.email, User.username).filter(
        User.marketing_emails.is_(True)
    )
    for email, name in user_query.all():
        key = (email or "").strip().lower()
        if key and key not in seen and key not in opted_out:
            seen.add(key)
            recipients.append((email, name))

    # Waitlist records are included only when their newsletter preference is enabled.
    subscriber_query = db.session.query(Subscriber.email, Subscriber.name).filter(
        Subscriber.newsletter.is_(True)
    )
    for email, name in subscriber_query.all():
        key = (email or "").strip().lower()
        if key and key not in seen and key not in opted_out:
            seen.add(key)
            recipients.append((email, name))

    if offset:
        recipients = recipients[offset:]
    if limit and limit > 0:
        recipients = recipients[:limit]
    return recipients

def get_newsletter_batches(batch_size=80):
    """Split the total deduplicated newsletter audience into batches (default 80 for Resend free tier)."""
    all_recipients = collect_recipients()
    total = len(all_recipients)
    if batch_size <= 0:
        batch_size = 80
    batches = []
    for idx, start in enumerate(range(0, total, batch_size), 1):
        end = min(start + batch_size, total)
        batches.append({
            "batch_number": idx,
            "start": start,
            "end": end,
            "count": end - start,
            "offset": start,
            "limit": batch_size,
            "label": f"Batch {idx}: Users {start + 1} to {end} ({end - start} subscribers)"
        })
    return batches, total


def upsert_subscriber_from_user(user):
    """Keep the newsletter subscriber table in sync with a registered user."""
    if user is None:
        return None

    email = (getattr(user, 'email', '') or '').strip().lower()
    if not email:
        return None

    subscriber = Subscriber.query.filter_by(email=email).first()
    if subscriber is None:
        subscriber = Subscriber(
            name=(getattr(user, 'username', '') or email.split('@', 1)[0]).strip() or email,
            email=email,
            newsletter=bool(getattr(user, 'marketing_emails', False)),
        )
        db.session.add(subscriber)
    else:
        subscriber.name = (getattr(user, 'username', '') or subscriber.name or email.split('@', 1)[0]).strip() or email
        subscriber.email = email
        subscriber.newsletter = bool(getattr(user, 'marketing_emails', False))

    if subscriber.created_at is None:
        subscriber.created_at = datetime.now(timezone.utc)
    subscriber.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return subscriber


def sync_user_email_preferences(user, form_data=None):
    """Persist user notification settings and keep the subscriber row aligned."""
    if user is None:
        return None

    if form_data is not None:
        user.email_notifications = bool(form_data.get('email_notifications') in ('on', 'true', '1', True))
        user.marketing_emails = bool(form_data.get('marketing_emails') in ('on', 'true', '1', True))
        user.product_updates = bool(form_data.get('product_updates') in ('on', 'true', '1', True))

    if user.marketing_emails:
        return upsert_subscriber_from_user(user)

    subscriber = Subscriber.query.filter_by(email=(user.email or '').strip().lower()).first()
    if subscriber:
        subscriber.newsletter = False
        subscriber.updated_at = datetime.now(timezone.utc)
        db.session.commit()
    return subscriber


def sync_all_users_to_subscribers():
    """Backfill all registered users into the subscriber table so the newsletter audience is complete."""
    users = User.query.all()
    created = 0
    for user in users:
        email = (user.email or '').strip().lower()
        if not email:
            continue
        if Subscriber.query.filter_by(email=email).first():
            continue
        upsert_subscriber_from_user(user)
        created += 1
    return created


def audience_size():
    return len(collect_recipients())


def get_newsletter_audience_count():
    """Return the real deduplicated newsletter audience, including opted-in users and waitlist subscribers."""
    return len(collect_recipients())


# ---------- Draft lifecycle ----------

# Statuses that count as "the current, not-yet-sent draft".
PENDING_STATUSES = ("draft", "approved")


def get_current_draft():
    """The most recent not-yet-sent issue (draft or approved), or None."""
    return (
        NewsletterIssue.query
        .filter(NewsletterIssue.status.in_(PENDING_STATUSES))
        .order_by(NewsletterIssue.created_at.desc())
        .first()
    )


def create_draft(subject, body, auto_generated=True, research_sources=None):
    issue = NewsletterIssue(
        subject=subject or "",
        body=body or "",
        status="draft",
        auto_generated=auto_generated,
        research_sources_json=json.dumps(research_sources or [], ensure_ascii=False),
    )
    db.session.add(issue)
    db.session.commit()
    return issue


def save_draft(issue, subject, body):
    issue.subject = subject or ""
    issue.body = body or ""
    issue.status = "draft"  # editing un-approves: you always approve the final text
    db.session.commit()
    return issue


def approve_draft(issue, subject=None, body=None):
    """Save any pending edits, then mark the draft approved for Monday's auto-send."""
    if subject is not None:
        issue.subject = subject
    if body is not None:
        issue.body = body
    issue.status = "approved"
    db.session.commit()
    return issue


def send_issue(issue, limit=None, offset=0):
    """Send an issue to a slice of recipients and return delivery totals and failures."""
    recipients = collect_recipients(limit=limit, offset=offset)
    issue.send_attempted_at = datetime.now(timezone.utc)
    db.session.commit()
    result = send_newsletter(
        recipients,
        issue.subject,
        issue.body,
        base_url=BASE_URL,
        is_html=True,
        return_details=True,
    )
    issue.attempted_count = result["attempted"]
    issue.failed_count = result["failed"]
    issue.delivery_failures = json.dumps(result["failures"])
    if result["sent"] and not result.get("test_recipient"):
        issue.status = "sent"
        issue.recipients_count = result["sent"]
        issue.sent_at = datetime.now(timezone.utc)
        result["sent_at"] = issue.sent_at.isoformat()
    db.session.commit()
    return result


# ---------- Admin notifications ----------

def _admin_emails():
    raw = os.environ.get("ADMIN_EMAILS", "oadedamola07@gmail.com")
    return [e.strip() for e in raw.split(",") if e.strip()]


def _notify_admins(heading, message):
    from services.email import send_admin_notice
    review_url = f"{BASE_URL}/admin/newsletter"
    for email in _admin_emails():
        send_admin_notice(email, heading, message, button_url=review_url,
                           button_text="Review newsletter")


# ---------- Scheduled jobs ----------

def run_weekly_generation():
    """Build this week's draft and ask the admin to review/approve it.
    Called by the Saturday scheduler / cron endpoint."""
    stats = {
        "total_users": User.query.count(),
        "total_generations": Generation.query.count(),
    }
    subject, body, research_sources = generate_weekly_digest(stats, include_research=True)
    issue = create_draft(subject, body, auto_generated=True, research_sources=research_sources)
    print(f"Weekly newsletter draft generated (issue {issue.id}).")
    _notify_admins(
        "📰 This week's Afrigen newsletter is ready to review",
        "A draft has been generated for review. Use Send now when it is ready.",
    )
    return issue


def run_weekly_send():
    """Send the current weekly draft automatically on Monday.

    Only an explicitly approved issue may be sent automatically.
    """
    issue = get_current_draft()

    if issue is None:
        try:
            issue = run_weekly_generation()
        except Exception as exc:
            _notify_admins(
                "Weekly newsletter could not be generated",
                f"The automatic send was skipped because generation failed: {exc}",
            )
            print(f"Weekly newsletter skipped: generation failed: {exc}")
            return 0

    if issue.status != "approved":
        print(f"Weekly newsletter skipped: issue {issue.id} is not approved.")
        return 0

    if not issue.body:
        _notify_admins(
            "Weekly newsletter NOT sent — empty draft",
            "Monday's automatic newsletter had no body content and was not sent.",
        )
        print("Weekly newsletter skipped: empty draft.")
        return 0

    result = send_issue(issue)
    print(f"Weekly newsletter sent to {result['sent']} recipients "
          f"({result['failed']} failed, issue {issue.id}).")
    return result["sent"]


# ---------- Daily Newsletter Campaign Batch Runner ----------

def run_daily_newsletter_batch(app_ctx=None):
    """Find the first 'sending' campaign and dispatch a batch of emails."""
    from models import NewsletterCampaign
    campaign = NewsletterCampaign.query.filter_by(status='sending').first()
    if not campaign:
        return
    recipients = collect_recipients(limit=campaign.batch_size, offset=campaign.batch_offset)
    if recipients:
        send_newsletter(recipients, campaign.subject, campaign.html_body, is_html=True)
    campaign.batch_offset += campaign.batch_size
    if campaign.batch_offset >= campaign.total_audience:
        campaign.status = 'complete'
        campaign.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    print(f"Newsletter campaign {campaign.id}: batch sent ({len(recipients)} recipients), offset now {campaign.batch_offset}")


def run_daily_newsletter_cycle():
    """Generate one immutable daily edition and deliver it in ordered batches of 80.

    The audience is snapshotted once per edition. Failed recipients remain pending
    and are retried before the next audience slice; a new edition is not generated
    until every snapshot recipient has either received it or opted out.
    """
    from models import NewsletterIssue

    # Ensure the table is available on deployments that rely on create_all for
    # additive tables. This is idempotent and does not alter existing rows.
    db.create_all()

    issue = (
        NewsletterIssue.query.filter_by(status="sending")
        .order_by(NewsletterIssue.created_at.asc())
        .first()
    )

    if issue is None:
        # The editorial workflow is deliberately approval-gated. Generate a
        # reviewable draft first; no recipient is contacted until an admin approves.
        issue = get_current_draft()
        if issue is None:
            recipients = collect_recipients()
            if not recipients:
                print("Daily newsletter skipped: no eligible subscribers.")
                return {"generated": False, "sent": 0, "pending": 0}
            subject, body, research_sources = generate_weekly_digest({
                "total_users": User.query.count(),
                "total_generations": Generation.query.count(),
            })
            if not subject or not body or not body.strip():
                raise ValueError("Daily newsletter generation returned an empty subject or body.")
            issue = create_draft(
                subject, body, auto_generated=True, research_sources=research_sources
            )
            print(f"Daily newsletter edition {issue.id} is ready for editorial approval.")
            _notify_admins(
                "Daily newsletter is ready for review",
                f"Edition #{issue.id} has been generated with its source list. Approve it in the newsletter editor before delivery.",
            )
            return {"generated": True, "issue_id": issue.id, "awaiting_approval": True, "sent": 0, "pending": 0}

        if issue.status != "approved":
            print(f"Daily newsletter issue {issue.id} is awaiting editorial approval.")
            return {"generated": False, "issue_id": issue.id, "awaiting_approval": True, "sent": 0, "pending": 0}

        recipients = collect_recipients()
        if not recipients:
            print("Daily newsletter skipped: no eligible subscribers.")
            return {"generated": False, "sent": 0, "pending": 0}
        snapshot = [
            {"email": (email or "").strip().lower(), "name": name or "",
             "position": position, "batch_number": position // 80,
             "status": "pending", "attempts": 0}
            for position, (email, name) in enumerate(recipients)
        ]
        issue.status = "sending"
        issue.recipients_count = 0
        issue.attempted_count = 0
        issue.failed_count = 0
        issue.delivery_failures = json.dumps({"version": 1, "audience": snapshot})
        db.session.commit()
        print(f"Approved newsletter edition {issue.id} queued for {len(snapshot)} recipients.")

    try:
        state = json.loads(issue.delivery_failures or "{}")
    except (TypeError, ValueError):
        state = {}
    audience = state.get("audience") if isinstance(state, dict) else None
    if not isinstance(audience, list):
        raise ValueError(f"Daily newsletter issue {issue.id} has no valid audience snapshot.")

    # Re-check current eligibility and global opt-outs before every send.
    currently_eligible = {
        email.lower() for email, _name in collect_recipients()
    }
    pending = []
    for item in audience:
        email = (item.get("email") or "").strip().lower()
        if item.get("status") != "pending":
            continue
        if email not in currently_eligible:
            item["status"] = "suppressed"
            continue
        pending.append(item)

    # Keep the original 1–80, 81–160, ... cohorts stable. A failed address
    # holds its cohort for retry instead of shifting later subscribers forward.
    next_batch_number = min(
        (int(item.get("batch_number", int(item.get("position", 0)) // 80)) for item in pending),
        default=None,
    )
    batch = [
        item for item in pending
        if int(item.get("batch_number", int(item.get("position", 0)) // 80)) == next_batch_number
    ][:80]
    if not batch:
        remaining = [x for x in audience if x.get("status") == "pending"]
        if not remaining:
            sent_count = sum(1 for x in audience if x.get("status") == "sent")
            issue.status = "sent"
            issue.recipients_count = sent_count
            issue.failed_count = 0
            issue.sent_at = datetime.now(timezone.utc)
            issue.delivery_failures = json.dumps({"version": 1, "audience": audience})
            db.session.commit()
            print(f"Daily newsletter edition {issue.id} completed ({sent_count} delivered).")
            return {"generated": False, "sent": 0, "pending": 0, "complete": True}
        issue.delivery_failures = json.dumps({"version": 1, "audience": audience})
        db.session.commit()
        return {"generated": False, "sent": 0, "pending": len(remaining)}

    send_list = [(x["email"], x.get("name") or "") for x in batch]
    issue.send_attempted_at = datetime.now(timezone.utc)
    for item in batch:
        item["attempts"] = int(item.get("attempts", 0)) + 1
    db.session.commit()

    result = send_newsletter(
        send_list, issue.subject, issue.body,
        base_url=BASE_URL, is_html=True, return_details=True,
    )
    failed_emails = {
        (failure.get("email") or "").strip().lower()
        for failure in result.get("failures", [])
    }
    if not result.get("test_recipient"):
        if result.get("sent", 0) == len(batch) - len(failed_emails):
            for item in batch:
                if item["email"] not in failed_emails:
                    item["status"] = "sent"
        else:
            # Provider response was ambiguous: do not mark anyone delivered.
            logger.error("Daily newsletter issue %s returned an incomplete provider result; batch will retry.", issue.id)

    issue.attempted_count = (issue.attempted_count or 0) + result.get("attempted", 0)
    issue.recipients_count = sum(1 for x in audience if x.get("status") == "sent")
    issue.failed_count = sum(1 for x in audience if x.get("status") == "pending")
    issue.delivery_failures = json.dumps({"version": 1, "audience": audience})
    db.session.commit()

    pending_count = sum(1 for x in audience if x.get("status") == "pending")
    if pending_count == 0:
        issue.status = "sent"
        issue.sent_at = datetime.now(timezone.utc)
        issue.failed_count = 0
        issue.recipients_count = sum(1 for x in audience if x.get("status") == "sent")
        db.session.commit()
    logger.info(
        "Daily newsletter issue %s: attempted=%s accepted=%s failed=%s pending=%s",
        issue.id, result.get("attempted", 0), result.get("sent", 0),
        result.get("failed", 0), pending_count,
    )
    return {
        "issue_id": issue.id,
        "attempted": result.get("attempted", 0),
        "sent": result.get("sent", 0),
        "failed": result.get("failed", 0),
        "pending": pending_count,
    }
