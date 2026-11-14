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


def _get_flyer_font(size: int, bold: bool = False):
    """Retrieve TTF font with fallback to default PIL font."""
    from PIL import ImageFont
    candidates = [
        'arialbd.ttf' if bold else 'arial.ttf',
        'segoeuib.ttf' if bold else 'segoeui.ttf',
        'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',
        'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap_flyer_text(text: str, font, max_width: int, draw) -> list[str]:
    """Wrap text to fit within a given pixel width."""
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(test_line) * 14
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines


def generate_promo_flyer(offer_text: str) -> str | None:
    """Generate a high-converting promotional flyer/poster using 100% free Python PIL."""
    try:
        from PIL import Image, ImageDraw

        W, H = 1080, 1080
        img = Image.new('RGB', (W, H))
        draw = ImageDraw.Draw(img)

        # Gradient obsidian background (#0A0E17 to #121826)
        for y in range(H):
            ratio = y / H
            r = int(10 + (18 - 10) * ratio)
            g = int(14 + (24 - 14) * ratio)
            b = int(23 + (38 - 23) * ratio)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Gold decorative framing
        draw.rectangle([(20, 20), (W - 20, H - 20)], outline=(245, 166, 35), width=3)
        draw.rectangle([(28, 28), (W - 28, H - 28)], outline=(55, 65, 81), width=1)

        # Top Badge Pill
        pill_w, pill_h = 420, 44
        pill_x = (W - pill_w) // 2
        draw.rounded_rectangle([(pill_x, 50), (pill_x + pill_w, 50 + pill_h)], radius=22, fill=(35, 27, 12), outline=(245, 166, 35), width=2)
        font_badge = _get_flyer_font(18, bold=True)
        draw.text((W // 2, 72), '★ SPECIAL CREATOR PROMOTION ★', fill=(245, 166, 35), font=font_badge, anchor='mm')

        # Brand Headline
        font_title = _get_flyer_font(68, bold=True)
        draw.text((W // 2, 145), 'AFRIGEN AI', fill=(245, 166, 35), font=font_title, anchor='mm')

        font_sub = _get_flyer_font(22, bold=False)
        draw.text((W // 2, 200), 'Africa\'s Premier AI Video & Visual Storytelling Engine', fill=(209, 213, 219), font=font_sub, anchor='mm')

        # Central Showcase Card
        card_margin = 70
        card_top = 245
        card_h = 580
        draw.rounded_rectangle([(card_margin, card_top), (W - card_margin, card_top + card_h)], radius=20, fill=(17, 24, 39), outline=(55, 65, 81), width=2)
        # Gold accent line on card
        draw.line([(card_margin + 30, card_top + 130), (W - card_margin - 30, card_top + 130)], fill=(245, 166, 35), width=2)

        # Dynamic Headline
        font_hl = _get_flyer_font(34, bold=True)
        headline = offer_text if offer_text else "Create Cinema-Grade AI Videos from Text Prompts in Minutes!"
        lines = _wrap_flyer_text(headline, font_hl, W - 2 * card_margin - 80, draw)
        y_hl = card_top + 45
        for line in lines[:2]:
            draw.text((W // 2, y_hl), line, fill=(255, 255, 255), font=font_hl, anchor='mm')
            y_hl += 42

        # 4 High-Converting Feature Value Points
        points = [
            "4K Cinema-Grade AI Video Generation from text prompts",
            "Culturally Authentic African Faces, Folklore & Settings",
            "Multi-Tier Plans Starting from ₦10,000 / mo + Free Spark Trial",
            "Direct Generation on Web Dashboard & Telegram Bot (@afrigen_bot)",
        ]
        font_bullet = _get_flyer_font(21, bold=False)
        y_bullet = card_top + 170
        for text in points:
            # Bullet icon circle
            draw.rounded_rectangle([(card_margin + 45, y_bullet - 2), (card_margin + 80, y_bullet + 32)], radius=8, fill=(245, 166, 35))
            draw.text((card_margin + 62, y_bullet + 15), '✓', fill=(11, 15, 25), font=_get_flyer_font(20, bold=True), anchor='mm')
            draw.text((card_margin + 98, y_bullet + 15), text, fill=(243, 244, 246), font=font_bullet, anchor='lm')
            y_bullet += 64

        # Pricing Tier Banner inside card
        draw.rounded_rectangle([(card_margin + 45, card_top + card_h - 75), (W - card_margin - 45, card_top + card_h - 22)], radius=12, fill=(25, 33, 49), outline=(245, 166, 35), width=1)
        font_tier = _get_flyer_font(19, bold=True)
        draw.text((W // 2, card_top + card_h - 48), 'Spark (Free) • Creator (₦10k) • Studio (₦15k) • Director (₦25k)', fill=(245, 166, 35), font=font_tier, anchor='mm')

        # Big Gold CTA Button
        cta_w, cta_h = 760, 84
        cta_x = (W - cta_w) // 2
        cta_y = 860
        draw.rounded_rectangle([(cta_x, cta_y), (cta_x + cta_w, cta_y + cta_h)], radius=16, fill=(245, 166, 35))
        font_cta = _get_flyer_font(30, bold=True)
        draw.text((W // 2, cta_y + cta_h // 2), 'CLAIM YOUR ACCESS → afrigen.com.ng', fill=(11, 15, 25), font=font_cta, anchor='mm')

        # Footer
        font_foot = _get_flyer_font(19, bold=False)
        draw.text((W // 2, 980), 'Empowering 1,000+ African Creators & Agencies • Telegram: @afrigen_bot', fill=(156, 163, 175), font=font_foot, anchor='mm')

        # Save to static uploads
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        campaigns_dir = os.path.join(root_dir, 'static', 'uploads', 'campaigns')
        os.makedirs(campaigns_dir, exist_ok=True)
        filename = f"flyer_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(campaigns_dir, filename)
        img.save(filepath, quality=95)
        logger.info(f"Generated free Python PIL promo flyer: {filepath}")

        # Return web accessible URL
        return f"{SITE_URL}/static/uploads/campaigns/{filename}"
    except Exception as e:
        logger.error(f"Failed to generate Python PIL promo flyer: {e}")
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

