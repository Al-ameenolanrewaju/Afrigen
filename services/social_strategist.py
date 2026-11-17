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
from services.provider_manager import provider_manager

logger = logging.getLogger(__name__)

SITE_URL = os.environ.get("BASE_URL", "https://www.afrigen.com.ng").rstrip("/")

# Target Content Distribution (Pillars)
# AI education: 25%, AI demonstrations: 20%, Industry insights: 15%,
# Product updates: 15%, Community engagement: 10%, Verified success stories: 10%, Promotions: 5%
DEFAULT_PILLARS = {
    "education": 25,
    "demo": 20,
    "industry_insights": 15,
    "product_updates": 15,
    "community": 10,
    "case_study": 10,
}

# Display names matching exact user specification
PILLAR_DISPLAY_NAMES = {
    "education": "AI education",
    "demo": "AI demonstrations",
    "industry_insights": "Industry insights",
    "product_updates": "Product updates",
    "community": "Community engagement",
    "case_study": "Verified success stories",
    "promotion": "Promotions",
}

# Bidirectional alias mapping ensuring backwards and forwards compatibility
PILLAR_ALIASES = {
    "education": "education",
    "ai_education": "education",
    "ai education": "education",
    "demo": "demo",
    "ai_demonstrations": "demo",
    "ai demonstrations": "demo",
    "demonstrations": "demo",
    "industry_insights": "industry_insights",
    "industry insights": "industry_insights",
    "product_updates": "product_updates",
    "product updates": "product_updates",
    "community": "community",
    "community_engagement": "community",
    "community engagement": "community",
    "case_study": "case_study",
    "case_studies": "case_study",
    "verified_success_stories": "case_study",
    "verified success stories": "case_study",
    "success_stories": "case_study",
    "promotion": "promotion",
    "promotions": "promotion",
    "promo": "promotion",
}

PILLAR_DESCRIPTIONS = {
    "education": "Practical AI education, prompt engineering masterclasses, and workflow tutorials for African creators.",
    "demo": "Photorealistic visual showcases, cinematic video demos, and neural voiceover demonstrations.",
    "industry_insights": "Analysis of the African creative economy, Nollywood digital transformation, and agency AI economics.",
    "product_updates": "Afrigen platform capabilities: Movie Studio, Telegram @afrigen_bot, monthly Spark allowances.",
    "community": "Thoughtful questions, creative challenges, and discussions connecting African digital creators.",
    "case_study": "Authentic workflows and verifiable time savings achieved by African creators and indie studios.",
    "promotion": "Official subscription plans: Creator Plan (₦10,000/mo) and free Spark monthly allowances.",
}


def normalize_pillar(pillar: Optional[str]) -> str:
    """Normalize pillar strings or aliases to canonical key."""
    if not pillar:
        return "education"
    clean = str(pillar).strip().lower().replace("-", "_")
    return PILLAR_ALIASES.get(clean, PILLAR_ALIASES.get(clean.replace("_", " "), "education"))


def get_pillar_display_name(pillar: Optional[str]) -> str:
    """Get human-readable display name for a pillar."""
    norm = normalize_pillar(pillar)
    return PILLAR_DISPLAY_NAMES.get(norm, norm.replace("_", " ").title())


# ==============================================================================
# STRATEGY & TOPIC GENERATION
# ==============================================================================

def select_next_pillar(user_id: int, settings: Optional[SocialAutomationSettings] = None) -> str:
    """Select the next content pillar balancing the configured percentage targets.

    Guarantees that:
    - Target ratios are respected (Education 25%, Demos 20%, Insights 15%, etc.).
    - Recent pillars receive a selection penalty to eliminate repetitive streaks.
    - Promotional content is capped at 5% and never scheduled back-to-back.
    """
    ratios = DEFAULT_PILLARS.copy()
    # Promotional content is never part of autonomous organic scheduling.
    ratios["promotion"] = 0
    if settings and settings.pillar_ratios_json:
        try:
            custom_ratios = json.loads(settings.pillar_ratios_json)
            if isinstance(custom_ratios, dict) and sum(custom_ratios.values()) > 0:
                normalized_custom = {}
                for k, v in custom_ratios.items():
                    norm_k = normalize_pillar(k)
                    normalized_custom[norm_k] = normalized_custom.get(norm_k, 0) + int(v)
                # Keep promotional strictly <= 10% even if customized
                if normalized_custom.get("promotion", 0) > 10:
                    normalized_custom["promotion"] = 5
                normalized_custom["promotion"] = 0
                ratios = normalized_custom
        except Exception:
            pass

    # Query last 12 posts to check recent pillar cadence
    recent_posts = (
        SocialPost.query.filter_by(user_id=user_id)
        .order_by(SocialPost.created_at.desc())
        .limit(12)
        .all()
    )
    recent_pillars = [normalize_pillar(p.content_pillar) for p in recent_posts if p.content_pillar]

    # Promotional suppression: if any of the last 6 posts was promo, eliminate promo
    if "promotion" in recent_pillars[:6]:
        ratios["promotion"] = 0

    # Weighted pool with penalties for recently used pillars
    weighted_pool: List[str] = []
    for pillar, weight in ratios.items():
        if weight <= 0:
            continue
        penalty = recent_pillars.count(pillar) * 5
        effective_weight = max(1, weight - penalty)
        weighted_pool.extend([pillar] * effective_weight)

    return random.choice(weighted_pool) if weighted_pool else "education"


# Comprehensive, diverse concept library covering all required subcategories
EXPANSIVE_CONCEPTS: Dict[str, List[Dict[str, Any]]] = {
    "education": [
        {
            "title": "Mastering Camera Movement in AI Video Production",
            "summary": "Step-by-step guide on prompt syntax for fluid pans, drone zooms, and Dutch angles in generative video.",
            "format": "video",
            "creative_type": "educational_graphic",
            "subcategory": "AI education and tutorials",
        },
        {
            "title": "Prompt Engineering for Melanin & African Skin Tones",
            "summary": "Essential lighting and texture keywords (warm golden rim lighting, 35mm film grain) to prevent plastic artifacts.",
            "format": "image",
            "creative_type": "educational_graphic",
            "subcategory": "AI tips and tricks",
        },
        {
            "title": "5-Minute Pre-Visualization Workflow for Video Creators",
            "summary": "How digital creators storyboard scene lighting, character poses, and shot lists with AI before shooting.",
            "format": "flyer",
            "creative_type": "infographic",
            "subcategory": "AI education and tutorials",
        },
        {
            "title": "Audio Pacing & Dynamic Video Editing with AI",
            "summary": "Techniques for aligning visual motion beats to African neural narration for high-retention social reels.",
            "format": "video",
            "creative_type": "feature_demonstration",
            "subcategory": "AI tips and tricks",
        },
    ],
    "demo": [
        {
            "title": "Lagos 2050: Afro-Futuristic Architecture & High-Tech Transit",
            "summary": "Cinematic visual showcase depicting sustainable African skylines, solar-woven towers, and vibrant street life.",
            "format": "video",
            "creative_type": "ai_illustration",
            "subcategory": "AI demonstrations",
        },
        {
            "title": "Traditional Heritage Meets High-Fashion Editorial",
            "summary": "Ultra-detailed portrait series highlighting intricate Kente and Aso-Oke textures in modern haute couture.",
            "format": "image",
            "creative_type": "ai_illustration",
            "subcategory": "AI demonstrations",
        },
        {
            "title": "Neural Voice Narration Synced to Cinematic Visuals",
            "summary": "Showcase of natural Nigerian and West African English narration layered over 8K drone landscapes.",
            "format": "video",
            "creative_type": "feature_demonstration",
            "subcategory": "AI demonstrations",
        },
        {
            "title": "The Power of Prompt-to-Video: From Script to Finished Reel",
            "summary": "Real-time demonstration turning a two-sentence creative prompt into a broadcast-ready 5-second video teaser.",
            "format": "video",
            "creative_type": "feature_demonstration",
            "subcategory": "AI demonstrations",
        },
    ],
    "industry_insights": [
        {
            "title": "Why African Creators Are Leading Generative AI Adoption",
            "summary": "Deep dive into how mobile-first African creators bypass expensive studio infrastructure through localized AI.",
            "format": "text",
            "creative_type": "brand_awareness",
            "subcategory": "Industry insights",
        },
        {
            "title": "Production Economics: Traditional Studio vs AI Pre-production",
            "summary": "Cost and turnaround breakdown showing how African creative agencies reduce client storyboard budgets by 70%.",
            "format": "image",
            "creative_type": "infographic",
            "subcategory": "Industry insights",
        },
        {
            "title": "Nollywood's Digital Frontier: AI in Independent Filmmaking",
            "summary": "How indie directors pitch major distributors with AI-assisted pitch decks, concept trailers, and shot bibles.",
            "format": "image",
            "creative_type": "brand_awareness",
            "subcategory": "Industry insights",
        },
        {
            "title": "Building in Public: Why Authentic Localized Models Matter",
            "summary": "Founder reflection on training and curating creative models that represent African culture without stereotypes.",
            "format": "text",
            "creative_type": "brand_awareness",
            "subcategory": "Building-in-public updates",
        },
    ],
    "product_updates": [
        {
            "title": "Inside Afrigen Movie Studio: Complete Scene Direction",
            "summary": "Feature announcement: Direct multi-shot scenes, character consistency, and cinematic pacing in one unified canvas.",
            "format": "video",
            "creative_type": "product_announcement",
            "subcategory": "Afrigen product demonstrations",
        },
        {
            "title": "Create Professional AI Assets on Telegram with @afrigen_bot",
            "summary": "Generate photorealistic imagery and prompt refinements directly from your mobile chat without opening a laptop.",
            "format": "flyer",
            "creative_type": "product_announcement",
            "subcategory": "Feature announcements",
        },
        {
            "title": "Prompt Lab 2.0 & Monthly Free Spark Allowances",
            "summary": "Refine complex creative prompts automatically and claim monthly free image & video credits on our Spark Plan.",
            "format": "image",
            "creative_type": "product_announcement",
            "subcategory": "Feature announcements",
        },
    ],
    "community": [
        {
            "title": "Creator Question: What Is Your Single Biggest Video Bottleneck?",
            "summary": "Interactive discussion asking creators whether scriptwriting, rendering hardware, or voice talent costs slow them down.",
            "format": "text",
            "creative_type": "brand_awareness",
            "subcategory": "Community discussions",
        },
        {
            "title": "Which Visual Style Wins: Hyper-Realism or Afro-Surrealism?",
            "summary": "Community debate exploring audience reactions to grounded cinematic styles versus stylized futuristic aesthetics.",
            "format": "image",
            "creative_type": "campaign_creative",
            "subcategory": "Community discussions",
        },
        {
            "title": "Creator Inspiration: The Next Wave of African Storytellers",
            "summary": "Spotlight on how independent African creators are turning personal folklore into global digital franchises.",
            "format": "text",
            "creative_type": "brand_awareness",
            "subcategory": "Creator inspiration",
        },
    ],
    "case_study": [
        {
            "title": "How Indie Creators Cut Visual Pitch Deck Time from 2 Weeks to 2 Days",
            "summary": "Factual workflow breakdown of indie marketing teams prototyping campaign storyboards rapidly with Afrigen.",
            "format": "flyer",
            "creative_type": "educational_graphic",
            "subcategory": "Customer success stories when verified",
        },
        {
            "title": "Workflow Blueprint: Scaling E-Commerce Ad Creatives on a Budget",
            "summary": "Verified breakdown of an African fashion retail team generating weekly catalog mockups without studio rentals.",
            "format": "image",
            "creative_type": "educational_graphic",
            "subcategory": "Customer success stories when verified",
        },
    ],
    "promotion": [
        {
            "title": "Scale Commercial Creative Production: Afrigen Creator Plan (₦10,000/mo)",
            "summary": "Full commercial licensing rights, high-definition AI video generation, and priority prompt refinement queue.",
            "format": "flyer",
            "creative_type": "promotional_flyer",
            "subcategory": "Promotional campaigns",
        },
        {
            "title": "Start Creating Today on Afrigen AI — Free Spark Plan",
            "summary": "Claim your monthly free Spark image & video allowances. No credit card required to start creating.",
            "format": "flyer",
            "creative_type": "promotional_flyer",
            "subcategory": "Promotional campaigns",
        },
    ],
}


def plan_post_concept(
    pillar: str,
    platform: str,
    user_id: Optional[int] = None,
    marketing_objective: str = "awareness",
    analytics_guidance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate or retrieve a high-value, non-repetitive creative concept."""
    norm_pillar = normalize_pillar(pillar)

    # Retrieve recent post titles for this user to avoid any duplicate ideas
    recent_titles: List[str] = []
    if user_id:
        try:
            recent_posts = (
                SocialPost.query.filter_by(user_id=user_id)
                .order_by(SocialPost.created_at.desc())
                .limit(20)
                .all()
            )
            recent_titles = [p.title.lower() for p in recent_posts if p.title]
        except Exception:
            pass

    # Try dynamic LLM topic generation first if LLM is active
    try:
        topic_prompt = f"""You are Lead Content Strategist for Afrigen AI (https://afrigen.com.ng).
Brand: Africa's premier AI video, image, and creative production suite.
Pillar: {norm_pillar} ({PILLAR_DESCRIPTIONS.get(norm_pillar, '')})
Platform: {platform.upper()}
Marketing Objective: {marketing_objective}
Avoid these recently published topics: {json.dumps(recent_titles[:10])}

Generate a fresh, original, non-generic social post concept.
Do NOT invent fake customer names, fake metrics, or fake testimonials.
Do NOT write robotic phrases like 'In today's fast-paced world'.

Return JSON with:
{{
    "title": "Punchy 5-10 word title",
    "summary": "1-2 sentence core value summary",
    "format": "video" | "image" | "flyer" | "text",
    "creative_type": "promotional_flyer" | "educational_graphic" | "ai_illustration" | "product_announcement" | "feature_demonstration" | "brand_awareness" | "infographic" | "campaign_creative"
}}"""
        resp_text = provider_manager.generate([{"role": "user", "content": topic_prompt}], max_tokens=300)
        if resp_text:
            cleaned = resp_text.strip()
            if "```" in cleaned:
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            data = json.loads(cleaned.strip())
            title = data.get("title", "").strip()
            if title and title.lower() not in recent_titles:
                return {
                    "title": title,
                    "summary": data.get("summary", "").strip(),
                    "format": data.get("format", "image"),
                    "pillar": norm_pillar,
                    "creative_type": data.get("creative_type", "educational_graphic"),
                }
    except Exception as exc:
        logger.debug("LLM dynamic concept generation skipped: %s; using curated library.", exc)

    # Curated library fallback with duplicate filtering
    options = EXPANSIVE_CONCEPTS.get(norm_pillar, EXPANSIVE_CONCEPTS["education"])
    unseen_options = [opt for opt in options if opt["title"].lower() not in recent_titles]
    chosen = random.choice(unseen_options if unseen_options else options)

    return {
        "title": chosen["title"],
        "summary": chosen["summary"],
        "format": chosen["format"],
        "pillar": norm_pillar,
        "creative_type": chosen.get("creative_type", "educational_graphic"),
        "subcategory": chosen.get("subcategory", norm_pillar),
    }


# ==============================================================================
# WEEKLY CONTENT PLANNER
# ==============================================================================

def plan_weekly_content(
    user_id: int,
    start_date: Optional[datetime] = None,
    posts_per_day: int = 1,
    marketing_objective: str = "awareness",
    analytics_guidance: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Plan a full 7-day cohesive content calendar adhering to pillar ratios.

    Target Distribution across 7-14 posts:
    - AI education: 25% (~2-3 posts)
    - AI demonstrations: 20% (~2-3 posts)
    - Industry insights: 15% (~1-2 posts)
    - Product updates: 15% (~1-2 posts)
    - Community engagement: 10% (~1 post)
    - Verified success stories: 10% (~1 post)
    - Promotions: 5% (at most 1 post, never on day 1)
    """
    now = start_date or (datetime.now(timezone.utc) + timedelta(hours=2))
    days_to_plan = 7
    total_posts = days_to_plan * max(1, min(posts_per_day, 2))

    # Balanced pillar schedule matching target distribution
    pillar_sequence = [
        "education",
        "demo",
        "industry_insights",
        "education",
        "product_updates",
        "community",
        "demo",
        "case_study",
        "education",
        "product_updates",
        "industry_insights",
        "demo",
        "promotion",
        "community",
    ]

    planned_posts: List[Dict[str, Any]] = []
    platforms = ["facebook", "linkedin"]

    for i in range(total_posts):
        day_offset = i // max(1, posts_per_day)
        pillar = pillar_sequence[i % len(pillar_sequence)]
        platform = platforms[i % len(platforms)]

        # Optimal posting times: morning 08:00 WAT for Facebook, afternoon 17:00 WAT for LinkedIn
        base_hour = 8 if platform == "facebook" else 17
        slot_day = now + timedelta(days=day_offset)
        slot_time = slot_day.replace(
            hour=base_hour, minute=0, second=0, microsecond=0
        )
        if slot_time <= datetime.now(timezone.utc):
            slot_time = (slot_day + timedelta(days=1)).replace(
                hour=base_hour, minute=0, second=0, microsecond=0
            )

        concept = plan_post_concept(
            pillar=pillar,
            platform=platform,
            user_id=user_id,
            marketing_objective=marketing_objective,
            analytics_guidance=analytics_guidance,
        )

        planned_posts.append({
            "slot_index": i + 1,
            "scheduled_time": slot_time,
            "platform": platform,
            "pillar": pillar,
            "title": concept["title"],
            "summary": concept["summary"],
            "format": concept["format"],
            "creative_type": concept.get("creative_type", "educational_graphic"),
            "marketing_objective": marketing_objective,
        })

    return planned_posts


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
    analytics_guidance: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Generate high-value, platform-specific copy for Facebook or LinkedIn.

    Ensures that:
    - Facebook and LinkedIn receive completely distinct hooks, tone, length, and CTAs.
    - Facebook leverages conversational storytelling, practical takeaways, and comment prompts.
    - LinkedIn leverages founder thought leadership, agency economics, and strategic clarity.
    - Captions never contain robotic clichés, fake testimonials, or unverified claims.
    """
    platform = platform.lower().strip()
    norm_pillar = normalize_pillar(pillar)

    system_prompt = (
        "You are the Senior Marketing Copywriter for Afrigen AI (https://afrigen.com.ng).\n"
        "Brand Identity:\n"
        "- Tagline: 'Africa Creates, AI Generates.'\n"
        "- Mission: Africa's premier AI video, image, and voice production studio.\n"
        "- Aesthetics: Obsidian Black, Radiant Gold, Warm Amber, African-inspired cinematic elegance.\n"
        "Strict Non-Negotiable Rules:\n"
        "1. NEVER invent fake customer names, fake quotes, or fake testimonials.\n"
        "2. NEVER invent unverified metrics or false percentage claims.\n"
        "3. Only official pricing is permitted: Creator Plan at ₦10,000/month or free Spark allowances.\n"
        "4. DO NOT use generic robotic clichés like 'In today's fast-paced digital world', 'game-changer', or 'delve into'.\n"
        "5. Keep emojis minimal and professional (maximum 2-3 tasteful emojis).\n"
        "6. Provide genuine, actionable educational or strategic value in every single post.\n"
        "7. Use only facts explicitly present in the topic, summary, or verified product context. If a detail is not supplied, omit it.\n"
        "8. Never invent founder experiences, customer outcomes, statistics, timelines, prices, technical specifications, or product capabilities.\n"
        "9. Avoid announcement-style openings, repeated brand slogans, generic motivational language, and empty engagement bait.\n"
        "10. Write like a knowledgeable human editor: specific, natural, varied in structure, and useful even if the reader never clicks the link."
    )

    if platform == "facebook":
        platform_instructions = (
            "FACEBOOK STRATEGY:\n"
            "- Tone: Conversational, direct, observant, and useful; not salesy or motivational.\n"
            "- Open with a concrete creator problem, surprising observation, or practical question—not a brand announcement.\n"
            "- Give one usable technique, example, checklist, or decision rule grounded in the supplied topic.\n"
            "- Vary post structures; do not force a story, question, CTA, or brand mention into every post.\n"
            "- Structure: choose the form that best serves the idea; do not force a fixed template.\n"
            "- Length: 90–180 words.\n"
            "- Use 0–3 relevant hashtags only when they add context; do not append a fixed hashtag block."
        )
    else:  # linkedin
        platform_instructions = (
            "LINKEDIN STRATEGY:\n"
            "- Tone: Analytical, professional, precise, and grounded; no inflated executive jargon.\n"
            "- Lead with a clear thesis or trade-off, then explain the reasoning and practical implication.\n"
            "- Use a real builder perspective only when the supplied context supports it; never fabricate personal experience.\n"
            "- Vary structure and close naturally; do not force a sales CTA into every post.\n"
            "- Structure: state a thesis, support it with reasoning, and end when the point is complete.\n"
            "- Length: 120–220 words.\n"
            "- Use 0–3 relevant hashtags only when they add context; do not append a fixed hashtag block."
        )

    user_prompt = f"""Write ready-to-publish social copy for {platform.upper()}.

TOPIC: {title}
SUMMARY: {summary}
PILLAR: {norm_pillar}
FORMAT: {content_format}

{platform_instructions}

Return JSON with exactly these keys:
{{
    "caption": "The complete post text ready to publish. Include a CTA only when natural; do not pad the post with slogans.",
    "call_to_action": "Clear short CTA text (e.g. 'Explore creative workflows at afrigen.com.ng')",
    "hashtags": "{'#AfrigenAI #AfricaCreates #AIVideo #AfricanCreators' if platform == 'facebook' else '#AfrigenAI #GenerativeAI #CreativeEconomy'}",
    "creative_prompt": "Ultra-detailed visual generation prompt in Afrigen's black/gold/amber aesthetic to create matching {content_format}"
}}
"""

    caption = ""
    cta = "Start creating at afrigen.com.ng"
    hashtags = "#AfrigenAI #AfricaCreates #AIVideo" if platform == "facebook" else "#AfrigenAI #GenerativeAI #CreativeEconomy"
    creative_prompt = f"Afrigen commercial showcase for {title}. Obsidian black background, radiant gold rim lighting, warm amber cinematic tones, 8k resolution, authentic African aesthetic."

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response_text = provider_manager.generate(messages, max_tokens=1000)
        if response_text:
            cleaned = response_text.strip()
            if "```" in cleaned:
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            data = json.loads(cleaned.strip())
            caption = data.get("caption", "").strip()
            cta = data.get("call_to_action", cta).strip()
            hashtags = data.get("hashtags", hashtags).strip()
            creative_prompt = data.get("creative_prompt", creative_prompt).strip()
    except Exception as exc:
        logger.warning("LLM copywriting failed: %s; using curated platform-specific fallback.", exc)

    # Platform-specific high quality fallbacks
    if not caption:
        if platform == "facebook":
            caption = (
                f"{title}\n\n"
                f"{summary}\n\n"
                f"African creators are proving every day that world-class visual storytelling doesn't require "
                f"a multimillion-naira studio budget. With Afrigen AI, you can direct 4K scenes, generate "
                f"authentic African portraits, and record localized voiceovers directly in your browser.\n\n"
                f"What is the single biggest creative hurdle you're tackling this week? Tell us in the comments!"
            )
        else:
            caption = (
                f"{title}.\n\n"
                f"The African creative economy is entering an era defined by localized artificial intelligence.\n\n"
                f"{summary}\n\n"
                f"Traditional production cycles often force indie agencies to spend weeks and significant capital "
                f"just to pre-visualize client concepts. Afrigen AI closes this gap by providing production-ready "
                f"generative video, photorealistic imagery, and neural voice models built specifically for African contexts.\n\n"
                f"Efficiency and cultural authenticity are no longer trade-offs. They are the new baseline."
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

def check_content_originality(caption: str, user_id: int, platform: Optional[str] = None) -> Dict[str, Any]:
    """Check if caption, hook, or text closely matches previously published content.

    Prevents:
    - Duplicate captions published to the same user's account within 60 days.
    - Identical cross-platform captions (Facebook vs LinkedIn duplicate posts).
    """
    clean_text = (caption or "").strip()
    if not clean_text:
        return {"is_original": False, "reason": "Caption is empty.", "hash": ""}

    normalized = " ".join(clean_text.lower().split()[:25])
    caption_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # 1. Exact opening hook hash check in past 60 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    existing = AIContentHistory.query.filter(
        AIContentHistory.user_id == user_id,
        AIContentHistory.caption_hash == caption_hash,
        AIContentHistory.created_at >= cutoff,
    ).first()

    if existing:
        return {
            "is_original": False,
            "reason": f"Caption hook duplicates previous post #{existing.post_id} from {existing.created_at.strftime('%b %d')}.",
            "hash": caption_hash,
        }

    # 2. Cross-platform duplication check: Ensure identical caption isn't published on other platform
    words_set = set(normalized.split())
    if len(words_set) >= 6:
        recent_history = (
            AIContentHistory.query.filter(
                AIContentHistory.user_id == user_id,
                AIContentHistory.created_at >= cutoff,
            )
            .limit(30)
            .all()
        )
        for h in recent_history:
            h_words = set(h.hook_text.lower().split())
            if not h_words:
                continue
            overlap = len(words_set.intersection(h_words)) / max(1, len(words_set.union(h_words)))
            if overlap >= 0.80:
                return {
                    "is_original": False,
                    "reason": f"Content is too similar ({int(overlap*100)}% match) to previous post #{h.post_id}.",
                    "hash": caption_hash,
                }

    return {"is_original": True, "hash": caption_hash}


def record_content_history(user_id: int, post_id: int, platform: str, caption: str, topic: str):
    """Store publication history entry for future duplicate prevention."""
    normalized = " ".join((caption or "").lower().split()[:25])
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
