from ..models import ContentBrief, GeneratedContent
from ..utils import generate_with_validation
from ..prompts.linkedin_prompt import LINKEDIN_SYSTEM, get_linkedin_user_prompt
from ..validators import validate_linkedin

def write_linkedin_post(brief: ContentBrief) -> GeneratedContent:
    blog_url = ""
    if brief.source_blog:
        from constants import SITE_URL
        blog_url = f"{SITE_URL}/blog/{brief.source_blog['slug']}"

    user_prompt = get_linkedin_user_prompt(brief, blog_url)
    
    content = generate_with_validation(
        system=LINKEDIN_SYSTEM,
        user=user_prompt,
        validator_fn=validate_linkedin,
        validator_args=(blog_url,),
        max_tokens=1200,
        max_attempts=2
    )
    
    from constants import SITE_URL, TELEGRAM_URL, LINKEDIN_URL
    cross_link_footer = (
        f"\n\nFollow Afrigen:\n"
        f"🌐 Website: {SITE_URL}\n"
        f"📢 Telegram (daily AI prompts): {TELEGRAM_URL}\n"
        f"💼 LinkedIn: {LINKEDIN_URL}"
    )
    
    final_text = content + cross_link_footer
    if len(final_text) > 3000:
        allowed = 3000 - len(cross_link_footer) - 3
        final_text = content[:allowed] + "..." + cross_link_footer
        
    from ..utils import get_logger
    logger = get_logger("LinkedInWriter")
    logger.info("LinkedIn content generated successfully.")
    
    return GeneratedContent(
        platform="linkedin",
        content=final_text,
        extra_fields={}
    )
