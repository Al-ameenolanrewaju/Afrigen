import re
from datetime import datetime
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from ..models import ContentBrief, GeneratedContent
from ..utils import generate_with_validation
from ..planner import ContentPlanner, get_newsletter_editorial_theme
from ..prompts.newsletter_prompt import NEWSLETTER_SYSTEM, get_newsletter_user_prompt
from ..validators import validate_newsletter

# Ground-truth list of capabilities. Keep this list aligned with the live product.
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


def _clean_html(text: str) -> str:
    """Repair a few common malformed attribute-less tags without rewriting valid markup."""
    for tag in ("p", "h1", "h2", "h3", "h4", "strong", "ul", "ol", "li", "em", "br", "div", "span"):
        text = re.sub(rf'<{tag}\s*["\']\s*>?', f'<{tag}>', text, flags=re.IGNORECASE)
        text = re.sub(rf'</{tag}\s*["\']\s*>?', f'</{tag}>', text, flags=re.IGNORECASE)
    return text.strip()


def _split_subject(text: str, fallback_subject: str):
    subject = fallback_subject
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip().upper().startswith("SUBJECT:"):
        subject = lines[0].split(":", 1)[1].strip() or fallback_subject
        body = "\n".join(lines[1:]).strip()
    return subject, body


def _extract_preheader(body: str) -> str:
    match = re.search(
        r"""<[^>]*class=["'][^"']*newsletter-preheader[^"']*["'][^>]*>(.*?)</[^>]+>""",
        body, flags=re.IGNORECASE | re.DOTALL
    )
    if not match:
        return ""
    return re.sub(r"<[^>]+>", " ", match.group(1)).strip()


class _PlainTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = (data or "").strip()
        if value:
            self.parts.append(value)


def _to_plain_text(markup: str) -> str:
    parser = _PlainTextExtractor()
    parser.feed(markup or "")
    return "\n\n".join(parser.parts)


def _newsletter_validator(content: str) -> tuple[bool, str]:
    text = _clean_html(content)
    _subject, body = _split_subject(text, fallback_subject="The Creator Intelligence Brief")
    return validate_newsletter(body)


def write_newsletter(
    brief: ContentBrief,
    stats: dict = None,
    posts: list = None,
    research_sources: list = None,
) -> GeneratedContent:
    """Generate a daily, five-minute editorial magazine edition."""
    stats = stats or {}
    posts = posts or []
    research_sources = research_sources or []
    # Keep only complete source records with HTTPS article links. The RSS service
    # performs date and feed validation; this is a final boundary before prompting.
    research_sources = [
        source for source in research_sources
        if source.get("title") and source.get("publisher")
        and source.get("published_at") and source.get("url", "").startswith("https://")
    ][:8]
    now = datetime.now(ZoneInfo("Africa/Lagos"))
    today = now.strftime("%B %d, %Y")
    users = int(stats.get("total_users") or 0)
    generations = int(stats.get("total_generations") or 0)

    from constants import SITE_URL

    editorial_theme = get_newsletter_editorial_theme(now)
    posts_block = "\n".join(
        f"- {p.title} | {(p.description or '').strip()} | {SITE_URL}/blog/{p.slug}"
        for p in posts[:5]
        if getattr(p, "title", None) and getattr(p, "slug", None)
    )
    if not posts_block:
        posts_block = "(No published blog articles are available for this edition.)"

    features_block = "\n".join(f"- {feature}" for feature in AFRIGEN_FEATURES)
    user_prompt = get_newsletter_user_prompt(
        brief=brief,
        features_block=features_block,
        posts_block=posts_block,
        users=users,
        generations=generations,
        date_str=today,
        editorial_theme=editorial_theme,
        research_sources=research_sources,
    )

    response = generate_with_validation(
        system=NEWSLETTER_SYSTEM,
        user=user_prompt,
        validator_fn=_newsletter_validator,
        validator_args=(),
        max_tokens=4200,
        max_attempts=3,
    )

    text = _clean_html(response)
    subject, body = _split_subject(
        text,
        fallback_subject=f"The Creator Intelligence Brief — {today}",
    )
    if not body or not body.strip():
        raise ValueError("Newsletter generation returned an empty HTML body.")

    preview_text = _extract_preheader(body)
    plain_text = _to_plain_text(body)

    ContentPlanner().record_newsletter_topic(brief.topic)

    from ..utils import get_logger
    get_logger("NewsletterWriter").info(
        "Generated daily magazine edition: theme=%s words=%s",
        editorial_theme["name"], len(plain_text.split())
    )

    return GeneratedContent(
        platform="newsletter",
        content=body,
        extra_fields={
            "subject": subject,
            "preview_text": preview_text,
            "plain_text": plain_text,
            "editorial_theme": editorial_theme["name"],
            "reading_time_minutes": 5,
            "published_date": today,
        },
    )
