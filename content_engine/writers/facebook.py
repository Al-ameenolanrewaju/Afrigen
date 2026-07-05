from ..models import ContentBrief, GeneratedContent
from ..utils import generate_with_validation
from ..prompts.facebook_prompt import FACEBOOK_SYSTEM, get_facebook_user_prompt
from ..validators import validate_facebook

def write_facebook_post(brief: ContentBrief) -> GeneratedContent:
    blog_url = ""
    if brief.source_blog:
        from constants import SITE_URL
        blog_url = f"{SITE_URL}/blog/{brief.source_blog['slug']}"

    user_prompt = get_facebook_user_prompt(brief, blog_url)
    
    content = generate_with_validation(
        system=FACEBOOK_SYSTEM,
        user=user_prompt,
        validator_fn=validate_facebook,
        validator_args=(blog_url,),
        max_tokens=600,
        max_attempts=2
    )
    
    from ..utils import get_logger
    logger = get_logger("FacebookWriter")
    logger.info("Facebook content generated successfully.")
    
    return GeneratedContent(
        platform="facebook",
        content=content,
        extra_fields={}
    )
