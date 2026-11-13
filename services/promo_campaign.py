"""Promotional Campaign Engine for Afrigen.

Generates AI flyers and distributes high-converting promotional campaigns
across all connected social platforms (Telegram, LinkedIn, Facebook, Instagram, Dev.to).
"""

import os
import sys
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SITE_URL = os.environ.get("BASE_URL", "https://www.afrigen.com.ng")


def generate_promo_flyer(offer_text: str) -> str | None:
    """Generate an eye-catching promotional flyer/poster using Fal/HuggingFace."""
    from services.video import generate_image

    prompt = (
        f"African vibrant commercial advertising poster, modern sleek 3D graphic design flyer, "
        f"Afrigen AI creative technology, high energy African creators in Lagos studio producing cinema videos, "
        f"bold typography style elements, glowing golden orange accents, professional cinematic lighting, 8k render. "
        f"Theme: {offer_text}"
    )

    try:
        image_url = generate_image(
            prompt=prompt,
            style="cinematic",
            aspect_ratio="1:1",
            allow_fal=True
        )
        return image_url
    except Exception as e:
        logger.error(f"Failed to generate promo flyer: {e}")
        return None


def generate_promo_post(offer_text: str, platform: str, flyer_url: str = None) -> str:
    """Generate promotional copy for a specific platform using ProviderManager/Groq."""
    try:
        from services.provider_manager import provider_manager
    except ImportError:
        provider_manager = None

    platform_guidance = {
        "telegram": (
            "Casual, exciting Nigerian tone with emojis. Write 2-3 short punchy paragraphs. "
            "Highlight the promo offer, explain why African creators need this, and end with "
            f"a strong call to action linking to {SITE_URL}/upgrade"
        ),
        "facebook": (
            "Engaging, conversational tone with storytelling hook. 2-3 short paragraphs, bullet points "
            f"highlighting features/benefits of Afrigen AI, and clear CTA link {SITE_URL}/upgrade"
        ),
        "instagram": (
            "Catchy punchy caption with high-energy emojis. Mention the flyer visual, short value props, "
            "direct followers to link in bio (afrigen.com.ng), and add 8-10 relevant hashtags."
        ),
        "linkedin": (
            "Polished, professional thought-leadership tone for African creators, agencies, and marketers. "
            "Focus on ROI, speed, cultural representation in AI video, and end with link."
        ),
        "devto": (
            "Engaging technical creator angle. Explain how Afrigen's AI video generation engine is empowering "
            "African storytelling at scale. Markdown formatted with headings."
        ),
    }

    style_guide = platform_guidance.get(platform, "Exciting promotional copy for African creators.")

    system_prompt = (
        "You are the Lead Growth Marketer for Afrigen (afrigen.com.ng), Africa's premier AI video "
        "and image generation platform. You write magnetic, conversion-focused promotional copy that turns "
        "creators into active subscribers. Never sound like a generic corporate bot."
    )

    user_prompt = f"""Write a high-converting promotional post for {platform.upper()}.

PROMOTION / OFFER:
{offer_text}

STYLE & PLATFORM RULES:
{style_guide}

Afrigen highlights:
- Generates high-definition AI videos & images from simple text prompts
- Built specifically for African cultural styles, folklore, commercials, and stories
- Tier plans start from ₦10,000/mo (Creator, Studio, Director) with 2 free images & 1 video monthly for Spark free users

Output ONLY the final promotional text ready to publish."""

    if provider_manager:
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            text = provider_manager.generate(messages, max_tokens=1000)
            if text:
                return text.strip()
        except Exception as e:
            logger.warning(f"ProviderManager failed for {platform} promo copy: {e}")

    # Fallback copy
    return (
        f"🚀 Special Announcement from Afrigen AI!\n\n"
        f"{offer_text}\n\n"
        f"Create high-definition AI videos and visuals crafted for African creators. "
        f"Claim your access now at {SITE_URL}/upgrade 🌍✨"
    )


def run_promo_campaign(offer_text: str, platforms: list = None) -> dict:
    """Run a multi-platform promotional campaign with an auto-generated flyer."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scripts_dir = os.path.join(root_dir, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    target_platforms = platforms or ["telegram", "linkedin", "facebook", "instagram", "devto"]
    results = {
        "offer": offer_text,
        "flyer_url": None,
        "platforms": {},
    }

    # Step 1: Generate visual flyer
    try:
        flyer_url = generate_promo_flyer(offer_text)
        results["flyer_url"] = flyer_url
    except Exception as e:
        logger.error(f"Flyer generation error: {e}")
        flyer_url = None

    # Step 2: Post to each platform
    for platform in target_platforms:
        platform = platform.lower().strip()
        copy = generate_promo_post(offer_text, platform, flyer_url=flyer_url)

        try:
            if platform == "telegram":
                from platforms.telegram import post_to_channel
                text_to_send = f"{copy}\n\n🖼️ [Poster Flyer]({flyer_url})" if flyer_url else copy
                res = post_to_channel(text_to_send)
                results["platforms"]["telegram"] = res

            elif platform == "linkedin":
                from platforms.linkedin import post_article
                res = post_article(copy)
                results["platforms"]["linkedin"] = res

            elif platform == "facebook":
                from platforms.facebook import post_to_page
                res = post_to_page(text=copy, link=flyer_url or f"{SITE_URL}/upgrade")
                results["platforms"]["facebook"] = res

            elif platform == "devto":
                from platforms.devto import publish_article
                res = publish_article(
                    title=f"Afrigen AI: {offer_text[:80]}",
                    content=copy,
                    tags=["ai", "video", "contentcreation", "africa"],
                    canonical_url=f"{SITE_URL}/upgrade",
                    description=offer_text[:150]
                )
                results["platforms"]["devto"] = res

            elif platform == "instagram":
                # Instagram Graph API requires published photo container
                results["platforms"]["instagram"] = {
                    "ok": True,
                    "caption": copy,
                    "flyer_url": flyer_url,
                    "note": "Ready for Instagram publishing via Meta Business Suite / Scheduler"
                }

            else:
                results["platforms"][platform] = {
                    "ok": False,
                    "error": f"Unsupported platform: {platform}"
                }

        except Exception as e:
            logger.error(f"Failed to publish promo to {platform}: {e}")
            results["platforms"][platform] = {"ok": False, "error": str(e)}

    return results

