"""Weekly auto-generated newsletter.

Generates a draft with Groq (llama) that is ABOUT AFRIGEN — a feature spotlight,
links to our real published blog guides, a practical creator tip, and our latest
community stats. It is NOT a roundup of external AI news. The admin can edit it,
then it's sent to everyone (registered users + waitlist), minus unsubscribes.
"""
import os
import re
import json
from datetime import datetime, date, timezone

from models import db, User, Subscriber, Generation, NewsletterIssue, EmailOptOut
from services.email import send_newsletter, BASE_URL


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

def generate_weekly_digest(stats=None):
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

    # 1. Use Planner to pick a newsletter topic/category
    planner = ContentPlanner()
    category = planner.select_category()

    stats = stats or {}
    posts = get_all_posts()[:5]
    
    # 2. Generate Master Brief
    # We can use the latest blog post as context, or a general theme
    source_context = f"Newsletter Edition. Focus on Afrigen updates, AI tools, and African creativity. Latest post: {posts[0].title if posts else 'General AI Update'}"
    brief = generate_content_brief(category, source_context)

    # 3. Generate newsletter via Content Engine
    generated = write_newsletter(brief=brief, stats=stats, posts=posts)
    
    return generated.extra_fields.get("subject", "Afrigen Weekly"), generated.content


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

def collect_recipients():
    """Every email we can reach — registered users + waitlist — de-duped
    (case-insensitive), excluding anyone who unsubscribed."""
    opted_out = {e.lower() for (e,) in db.session.query(EmailOptOut.email).all()}

    seen = set()
    recipients = []
    # Registered accounts first (so their username is used as the name on dupes).
    for email, name in db.session.query(User.email, User.username).all():
        key = (email or "").lower()
        if key and key not in seen and key not in opted_out:
            seen.add(key)
            recipients.append((email, name))
    for email, name in db.session.query(Subscriber.email, Subscriber.name).all():
        key = (email or "").lower()
        if key and key not in seen and key not in opted_out:
            seen.add(key)
            recipients.append((email, name))
    return recipients


def audience_size():
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


def create_draft(subject, body, auto_generated=True):
    issue = NewsletterIssue(
        subject=subject or "",
        body=body or "",
        status="draft",
        auto_generated=auto_generated,
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


def send_issue(issue):
    """Send an issue and return delivery totals and failures."""
    recipients = collect_recipients()
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
    if result["sent"]:
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
    subject, body = generate_weekly_digest(stats)
    issue = create_draft(subject, body, auto_generated=True)
    print(f"Weekly newsletter draft generated (issue {issue.id}).")
    _notify_admins(
        "📰 This week's Afrigen newsletter is ready to review",
        "A draft has been generated for review. Use Send now when it is ready.",
    )
    return issue


def run_weekly_send():
    """Send the current weekly draft automatically on Monday.

    Approval remains available for preview and editing, but it is not required
    for the scheduled delivery to happen.
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
