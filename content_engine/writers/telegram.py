from ..models import ContentBrief, GeneratedContent
from ..utils import generate_with_validation
from ..prompts.telegram_prompt import TELEGRAM_SYSTEM, get_telegram_user_prompt
from ..validators import validate_telegram

def write_telegram_post(brief: ContentBrief) -> GeneratedContent:
    blog_url = ""
    if brief.source_blog:
        from constants import SITE_URL
        blog_url = f"{SITE_URL}/blog/{brief.source_blog['slug']}"

    user_prompt = get_telegram_user_prompt(brief, blog_url)
    
    content = generate_with_validation(
        system=TELEGRAM_SYSTEM,
        user=user_prompt,
        validator_fn=validate_telegram,
        validator_args=(),
        max_tokens=1200,
        max_attempts=2
    )
    
    from ..utils import get_logger
    logger = get_logger("TelegramWriter")
    logger.info("Telegram content generated successfully.")
    
    return GeneratedContent(
        platform="telegram",
        content=content,
        extra_fields={}
    )
