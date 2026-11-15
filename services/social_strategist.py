"""AI Marketing Strategist and Platform Copywriter for Afrigen.

Plans content calendars, enforces marketing pillar ratios, writes platform-specific
copy for Facebook and LinkedIn, and guards originality against duplication.
"""

import os
import json
import hashlib
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from models import db, SocialPost, SocialCampaign, AIContentHistory, SocialAutomationSettings
import services.claude as claude_service
from services.provider_manager import provider_manager

logger = logging.getLogger(__name__)

SITE_URL = os.environ.get("BASE_URL", "https://www.afrigen.com.ng").rstrip("/")

DEFAULT_PILLARS = {
    "education": 25,
    "demo": 20,
    "industry_insights": 15,
    "product_updates": 15,
    "community": 10,
    "case_study": 10,
    "promotion": 5,
}

PILLAR_DESCRIPTIONS = {
    "education": "AI education, tutorials, and practical prompting tips for African creators.",
    "demo": "Showcase of AI-generated video, photo, and voiceover capabilities.",
    "industry_insights": "The rise of African creative technology, Nollywood AI, and digital storytelling.",
    "product_updates": "Genuine features: Movie Studio, Kling video, photorealism, and Telegram bot.",
    "community": "Creator questions, polls, and interactive discussions to drive high engagement.",
    "case_study": "Stories of how African brands and entrepreneurs save time and scale content with Afrigen.",
    "promotion": "Direct subscription offers: Creator plan (₦10k/mo) and free trial allowances.",
}


# ==============================================================================
# STRATEGY & TOPIC GENERATION
# ==============================================================================

def select_next_pillar(user_id: int, settings: Optional[SocialAutomationSettings] = None) -> str:
    """Select the next content pillar balancing the configured percentage targets."""
    ratios = DEFAULT_PILLARS.copy()
    if settings and settings.pillar_ratios_json:
        try:
            custom_ratios = json.loads(settings.pillar_ratios_json)
            if isinstance(custom_ratios, dict) and sum(custom_ratios.values()) > 0:
                ratios = custom_ratios
        except Exception:
            pass

    # Query last 10 posts to avoid immediate repetition of the same pillar
    recent_posts = (
        SocialPost.query.filter_by(user_id=user_id)
        .order_by(SocialPost.created_at.desc())
        .limit(10)
        .all()
    )
    recent_pillars = [p.content_pillar for p in recent_posts if p.content_pillar]

    # Weighted random selection with penalty for recent pillars
    weighted_pool = []
    for pillar, weight in ratios.items():
        penalty = recent_pillars.count(pillar) * 4
        effective_weight = max(1, weight - penalty)
        weighted_pool.extend([pillar] * effective_weight)

    return random.choice(weighted_pool) if weighted_pool else "education"


def plan_post_concept(pillar: str, platform: str) -> Dict[str, Any]:
    """Generate a high-level creative concept for a post given its pillar and platform."""
    concepts = {
        "education": [
            ("Mastering Camera Movement in AI Video", "How to write prompts for pan, tilt, and drone zooms in Kling AI.", "video"),
            ("3 Secrets to Photorealistic African Skin Tones", "Prompt engineering guide for 35mm portraiture without cartoon artifacts.", "image"),
            ("From Script to Screen: 5-Minute Production Workflow", "How creators turn ideas into finished video ads using Afrigen.", "flyer"),
        ],
        "demo": [
            ("Lagos 2050: Cyberpunk African Metropolis", "Cinematic showcase of futuristic African architecture and culture.", "video"),
            ("Traditional Royalty Meets Modern High Fashion", "Photorealistic portrait series highlighting authentic traditional fabrics.", "image"),
            ("Audio-Visual Storytelling: Nigerian Voiceovers", "Demo of native Nigerian English neural narration synced to cinematic clips.", "video"),
        ],
        "industry_insights": [
            ("Why African Creators Are Leading the Generative AI Revolution", "Thought leadership on localized models and authentic representation.", "text"),
            ("The Cost of Video Production vs Generative AI", "Data breakdown: Why modern marketing agencies are adopting AI suites.", "image"),
            ("Nollywood's New Era: AI in Pre-visualization", "How indie filmmakers use AI scene storyboarding to secure funding.", "flyer"),
        ],
        "product_updates": [
            ("Introducing Afrigen Movie Studio", "Direct scenes, shots, character consistency, and full films in one workspace.", "video"),
            ("Create AI Videos on Telegram with @afrigen_bot", "Generate photos and videos straight from your mobile chat.", "flyer"),
            ("High-Fidelity Prompt Lab & Free Image Allowances", "Refine prompts automatically and claim your monthly Spark allowances.", "image"),
        ],
        "community": [
            ("Question for African Creators: What's Your Biggest Bottleneck?", "Engaging discussion on scriptwriting, video editing, or voiceovers.", "text"),
            ("Show Us Your Best AI Prompts", "Creator spotlight callout for community prompts and techniques.", "text"),
            ("Which Visual Style Wins: Cinematic Realism vs Afro-Futurism?", "Interactive community poll comparing visual approaches.", "image"),
        ],
        "case_study": [
            ("How a Lagos E-commerce Brand Scaled Social Ads 5x", "Case study on producing 20 video ads weekly on a creator budget.", "flyer"),
            ("Building Visual Campaigns in Minutes Instead of Days", "Workflow breakdown of an agency producing client storyboards with Afrigen.", "image"),
        ],
        "promotion": [
            ("Scale Your Creativity: Creator Plan at ₦10,000/Month", "Commercial rights, Kling AI video generation, and unlimited prompt refining.", "flyer"),
            ("Start Creating with Afrigen AI Today — Free Spark Plan", "Claim monthly free image & video allowances. No credit card required.", "flyer"),
        ],
    }

    options = concepts.get(pillar, concepts["education"])
    title, summary, fmt = random.choice(options)
    return {
        "title": title,
        "summary": summary,
        "format": fmt,
        "pillar": pillar,
    }


# ==============================================================================
# PLATFORM-SPECIFIC COPYWRITING ENGINE
# ==============================================================================

def generate_platform_copy(
    title: str,
    summary: str,
    pillar: str,
    platform: str,
    content_format: str = "image",
    user_id: Optional[int] = None,
) -> Dict[str, str]:
    """Generate high-converting, platform-specific copy for Facebook or LinkedIn."""
    system_prompt = (
        "You are the Lead Marketing Strategist for Afrigen AI (https://afrigen.com.ng).\n"
        "Brand Tagline: 'Africa Creates, AI Generates.'\n"
        "Positioning: Africa's premier AI creative production platform (AI Video, Photo, Voiceover, Movie Studio).\n"
        "Rules:\n"
        "- Never fabricate fake customer names, fake metrics, or fake testimonials.\n"
        "- Maintain a premium, inspiring, authentic tone (Black, Gold, Orange aesthetic).\n"
        "- Do not use excessive emojis or robotic clichés like 'In today's fast-paced digital world'.\n"
        "- Write naturally, with a strong hook, actionable insight, and relevant CTA."
    )

    if platform == "facebook":
        platform_instructions = (
            "FACEBOOK STRATEGY:\n"
            "- Tone: Conversational, engaging, creator-friendly, inspiring.\n"
            "- Format: Engaging opening line/hook, storytelling paragraph, practical takeaway, question to stimulate comments, clear CTA.\n"
            "- Length: 120–220 words.\n"
            "- Include 3–4 relevant hashtags at the bottom.\n"
            "- CTA should guide users to try it at afrigen.com.ng"
        )
    else:  # linkedin
        platform_instructions = (
            "LINKEDIN STRATEGY:\n"
            "- Tone: Professional thought leadership, founder perspective / building in public, business ROI, strategic clarity.\n"
            "- Format: Bold single-line hook, concise paragraphs with white space, strategic insight for businesses & agencies, professional CTA.\n"
            "- Length: 150–250 words.\n"
            "- Include 3 relevant hashtags.\n"
            "- CTA should invite professional discussion and direct to afrigen.com.ng"
        )

    user_prompt = f"""Write a ready-to-publish social media post for {platform.upper()}.

TOPIC: {title}
SUMMARY: {summary}
CONTENT PILLAR: {pillar}
FORMAT: {content_format}

{platform_instructions}

Return JSON with exactly these keys:
{{
    "caption": "The complete post text ready to publish (without hashtags or CTA)",
    "call_to_action": "Clear short CTA text (e.g. 'Create your first video at afrigen.com.ng')",
    "hashtags": "#AfrigenAI #AfricaCreates #AIVideo",
    "creative_prompt": "Detailed visual generation prompt for creating the matching {content_format}"
}}
"""

    caption = ""
    cta = "Start creating at afrigen.com.ng"
    hashtags = "#AfrigenAI #AfricaCreates #AIVideo"
    creative_prompt = f"Afrigen commercial showcase for {title}. Cinematic lighting, authentic African aesthetic."

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response_text = provider_manager.generate(messages, max_tokens=1000)
        if response_text:
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            data = json.loads(cleaned.strip())
            caption = data.get("caption", "").strip()
            cta = data.get("call_to_action", cta).strip()
            hashtags = data.get("hashtags", hashtags).strip()
            creative_prompt = data.get("creative_prompt", creative_prompt).strip()
    except Exception as exc:
        logger.warning("LLM copywriting failed: %s; using high-quality fallback template.", exc)

    if not caption:
        if platform == "facebook":
            caption = (
                f"✨ {title}\n\n"
                f"{summary}\n\n"
                f"African creators are reshaping modern digital storytelling. Whether you're producing "
                f"cinematic ads, photorealistic visuals, or custom voiceovers, Afrigen AI brings your ideas to life.\n\n"
                f"What's the biggest project you're working on this week? Drop your thoughts below!"
            )
        else:
            caption = (
                f"{title}.\n\n"
                f"The creative technology landscape across Africa is evolving at unprecedented speed.\n\n"
                f"{summary}\n\n"
                f"At Afrigen, our mission is simple: provide world-class AI video, image, and voice production tools "
                f"tailored specifically for African businesses, marketing teams, and indie filmmakers.\n\n"
                f"Efficiency doesn't mean compromising on cultural authenticity. It means empowering creators to scale."
            )

    return {
        "caption": caption,
        "call_to_action": cta,
        "hashtags": hashtags,
        "creative_prompt": creative_prompt,
    }


# ==============================================================================
# ORIGINALITY & DUPLICATE DETECTION
# ==============================================================================

def check_content_originality(caption: str, user_id: int) -> Dict[str, Any]:
    """Check if caption or hook closely matches previously published content."""
    normalized = " ".join(caption.lower().split()[:25])
    caption_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # Look for exact hash match in past 60 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    existing = AIContentHistory.query.filter(
        AIContentHistory.user_id == user_id,
        AIContentHistory.caption_hash == caption_hash,
        AIContentHistory.created_at >= cutoff
    ).first()

    if existing:
        return {
            "is_original": False,
            "reason": f"Caption hook duplicates previous post #{existing.post_id} from {existing.created_at.strftime('%b %d')}.",
            "hash": caption_hash,
        }

    return {"is_original": True, "hash": caption_hash}


def record_content_history(user_id: int, post_id: int, platform: str, caption: str, topic: str):
    """Store publication history entry for future duplicate prevention."""
    normalized = " ".join(caption.lower().split()[:25])
    caption_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    first_sentence = caption.split(".")[0][:250] if "." in caption else caption[:250]

    entry = AIContentHistory(
        user_id=user_id,
        post_id=post_id,
        platform=platform,
        caption_hash=caption_hash,
        hook_text=first_sentence,
        topic=topic[:150],
    )
    db.session.add(entry)
    db.session.commit()
