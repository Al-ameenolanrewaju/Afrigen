import re
from datetime import date
from ..models import ContentBrief, GeneratedContent
from ..utils import generate_with_validation
from ..prompts.newsletter_prompt import NEWSLETTER_SYSTEM, get_newsletter_user_prompt
from ..validators import validate_newsletter

# Ground-truth list of things Afrigen can actually do
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

def _newsletter_validator(content: str) -> tuple[bool, str]:
    text = _clean_html(content)
    subject, body = _split_subject(text, fallback_subject="Afrigen Weekly")
    return validate_newsletter(body)

def write_newsletter(brief: ContentBrief, stats: dict = None, posts: list = None) -> GeneratedContent:
    stats = stats or {}
    today = date.today().strftime("%B %d, %Y")
    users = stats.get("total_users", 0)
    generations = stats.get("total_generations", 0)
    posts = posts or []
    
    from constants import SITE_URL
    
    if posts:
        posts_block = "\n".join(
            f"- {p.title} | {(p.description or '').strip()} | {SITE_URL}/blog/{p.slug}"
            for p in posts
        )
    else:
        posts_block = "(no blog posts published yet — skip the 'From the blog' section)"

    features_block = "\n".join(f"- {f}" for f in AFRIGEN_FEATURES)
    
    user_prompt = get_newsletter_user_prompt(
        brief=brief,
        features_block=features_block,
        posts_block=posts_block,
        users=users,
        generations=generations,
        date_str=today
    )
    
    response = generate_with_validation(
        system=NEWSLETTER_SYSTEM,
        user=user_prompt,
        validator_fn=_newsletter_validator,
        validator_args=(),
        max_tokens=3000,
        max_attempts=2
    )
    
    text = _clean_html(response)
    subject, body = _split_subject(text, fallback_subject=f"Afrigen Weekly — {today}")
    
    from ..utils import get_logger
    logger = get_logger("NewsletterWriter")
    logger.info("Newsletter content generated successfully.")
    
    return GeneratedContent(
        platform="newsletter",
        content=body,
        extra_fields={"subject": subject}
    )

_ATTRLESS_TAGS = ("p", "h1", "h2", "h3", "h4", "strong", "ul", "li", "em", "br", "div", "span")

def _clean_html(text: str) -> str:
    # Only repair malformed opening tags (e.g. `<p"`, `<div '>`, etc.)
    # and leave perfectly valid tags with style/class/href attributes alone.
    for tag in _ATTRLESS_TAGS:
        text = re.sub(rf'<{tag}\s*["\']\s*>?', f'<{tag}>', text, flags=re.IGNORECASE)
        text = re.sub(rf'</{tag}\s*["\']\s*>?', f'</{tag}>', text, flags=re.IGNORECASE)
    return text

def _split_subject(text: str, fallback_subject: str):
    subject = fallback_subject
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip().upper().startswith("SUBJECT:"):
        subject = lines[0].split(":", 1)[1].strip() or fallback_subject
        body = "\n".join(lines[1:]).strip()
    return subject, body
