"""Weekly auto-generated newsletter.

Generates a draft with Groq (llama) using fresh headlines pulled from Google News
RSS, lets the admin edit it, and sends it to everyone (registered users + waitlist),
minus anyone who has unsubscribed.
"""
import os
from datetime import datetime, date
from xml.etree import ElementTree

import requests

from models import db, User, Subscriber, Generation, NewsletterIssue, EmailOptOut
from services.email import send_newsletter, BASE_URL


# Same model the rest of the app uses (Groq). Override with NEWSLETTER_MODEL if desired.
NEWSLETTER_MODEL = os.environ.get("NEWSLETTER_MODEL", "llama-3.3-70b-versatile")

# Topics we pull fresh weekly headlines for. Kept tight and audience-specific so
# the feed surfaces news our readers (African AI creators + small businesses using
# video/image tools) actually care about, instead of generic US tech/legal noise.
# The first two track the tools themselves; the last two keep it local & relevant.
NEWS_QUERIES = [
    "AI video generator",
    "AI image generator",
    "Nigeria creators AI tools",
    "African startups AI funding",
]


# ---------- Live web headlines (free, no API key) ----------

def _fetch_web_headlines(max_per_query=4, timeout=8):
    """Pull this week's real headlines from Google News RSS. Returns a list of
    '- Headline (Source)' strings; degrades gracefully to [] on any failure.

    The feed is localized to Nigeria (gl=NG) so results skew toward African
    creators/business rather than US-centric coverage — global tool launches
    still surface, but the local angle our readers care about comes through."""
    headlines = []
    for query in NEWS_QUERIES:
        q = requests.utils.quote(f"{query} when:7d")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-NG&gl=NG&ceid=NG:en"
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            for item in root.findall("./channel/item")[:max_per_query]:
                title = (item.findtext("title") or "").strip()
                src_el = item.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                if title:
                    headlines.append(f"- {title}" + (f" ({source})" if source else ""))
        except Exception as e:
            print(f"News fetch failed for '{query}': {e}")

    # De-dupe, preserve order.
    seen, deduped = set(), []
    for h in headlines:
        if h not in seen:
            seen.add(h)
            deduped.append(h)
    return deduped


# ---------- AI generation (Groq + fresh headlines) ----------

def generate_weekly_digest(stats=None):
    """Write this week's newsletter with Groq, grounded in fresh web headlines.

    Returns (subject, body_html). Raises on API/config errors so callers can
    surface the problem instead of silently sending an empty email.
    """
    from services.claude import client as groq_client  # reuse the initialised Groq client

    stats = stats or {}
    today = date.today().strftime("%B %d, %Y")
    users = stats.get("total_users", 0)
    generations = stats.get("total_generations", 0)

    headlines = _fetch_web_headlines()
    headlines_block = "\n".join(headlines) if headlines else "(no fresh headlines found this week)"

    system_message = (
        "You are the editor of Afrigen's weekly email newsletter. Afrigen is an African "
        "AI platform for generating videos and images from text prompts (tagline "
        "'Africa Creates, AI Generates'). Write warm, concise, skimmable newsletters."
    )
    user_message = f"""Today is {today}. Write this week's Afrigen newsletter, grounded in the REAL headlines below.

THIS WEEK'S HEADLINES (pulled from the web):
{headlines_block}

Instructions:
- Choose the 3-5 items most relevant to African AI creators and write a short, friendly blurb for each (a bold headline + one short paragraph). Do NOT invent facts beyond these headlines.
- End with an "Afrigen this week" section noting our community: {users} creators and {generations} generations so far, and invite readers to go create something.
- The FIRST line must be exactly:  SUBJECT: <a punchy subject line under 70 chars>
- After that line, output the email BODY as simple inline HTML using only <h3>, <p>, <strong>, <a> tags (no <html>, <head>, <body>, or <style> tags).
- Keep it warm, concise, and skimmable."""

    response = groq_client.chat.completions.create(
        model=NEWSLETTER_MODEL,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1500,
    )
    text = _strip_code_fences((response.choices[0].message.content or "").strip())
    return _split_subject(text, fallback_subject=f"Afrigen Weekly — {today}")


def _strip_code_fences(text):
    """llama often wraps its output in ```html ... ``` fences — remove them so the
    SUBJECT line and HTML body come through clean."""
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines).strip()


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
    """Send an issue to all recipients and mark it sent. Returns the count."""
    recipients = collect_recipients()
    sent = send_newsletter(
        recipients,
        issue.subject,
        issue.body,
        base_url=BASE_URL,
        is_html=True,
    )
    issue.status = "sent"
    issue.recipients_count = sent
    issue.sent_at = datetime.utcnow()
    db.session.commit()
    return sent


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
        "A draft has been auto-generated. Review and edit it, then click "
        "<strong>Approve</strong> so it goes out Monday at 9am. "
        "If it isn't approved, it won't be sent.",
    )
    return issue


def run_weekly_send():
    """Send the current draft — ONLY if it has been approved. Otherwise skip and
    remind the admin. Called by the Monday scheduler / cron endpoint."""
    issue = get_current_draft()

    if issue is None or issue.status != "approved":
        _notify_admins(
            "⏸️ Weekly newsletter NOT sent — needs your approval",
            "Monday's newsletter was skipped because there is no approved draft. "
            "Open the dashboard to review and approve this week's issue.",
        )
        print("Weekly newsletter skipped: no approved draft.")
        return 0

    sent = send_issue(issue)
    print(f"Weekly newsletter sent to {sent} recipients (issue {issue.id}).")
    return sent
