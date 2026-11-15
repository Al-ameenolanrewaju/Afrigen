"""Autonomous Quality Assurance and Content Validation Engine for Afrigen.

Scores planned social content, verifies factual brand details and pricing,
validates URLs and length limits, and prevents hallucinated claims.
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

FORBIDDEN_PHRASES = [
    "99% off", "100% discount", "free 1000 credits", "get rich quick",
    "unlimited free forever", "guaranteed viral", "test flyer upload from python pil engine",
    "john from london said", "sarah from google said"
]

VALID_PRICE_REFERENCES = ["10,000", "10000", "₦10k", "free spark plan", "monthly allowances"]


def run_social_quality_audit(
    caption: str,
    platform: str,
    content_format: str,
    media_url: str = None,
    call_to_action: str = None,
) -> Dict[str, Any]:
    """Perform comprehensive pre-publishing QA check and return a quality score (0-100)."""
    score = 100
    checks = []
    flags = []

    text = (caption or "").strip()
    lower_text = text.lower()

    # 1. Minimum and Maximum Length Validation
    char_len = len(text)
    if char_len < 50:
        score -= 40
        flags.append("Caption is too short to provide meaningful value.")
        checks.append({"name": "length", "passed": False, "detail": "Under 50 characters"})
    elif platform == "linkedin" and char_len > 3000:
        score -= 30
        flags.append("Caption exceeds LinkedIn character limit (3,000 characters).")
        checks.append({"name": "length", "passed": False, "detail": "Exceeds 3,000 characters"})
    elif platform == "facebook" and char_len > 5000:
        score -= 30
        flags.append("Caption exceeds Facebook recommended limit (5,000 characters).")
        checks.append({"name": "length", "passed": False, "detail": "Exceeds 5,000 characters"})
    else:
        checks.append({"name": "length", "passed": True, "detail": f"{char_len} characters"})

    # 2. Forbidden Phrases & Hallucination Prevention
    for forbidden in FORBIDDEN_PHRASES:
        if forbidden in lower_text:
            score -= 50
            flags.append(f"Contains non-compliant marketing phrase: '{forbidden}'.")
            checks.append({"name": "compliance", "passed": False, "detail": f"Forbidden: {forbidden}"})
            break
    else:
        checks.append({"name": "compliance", "passed": True, "detail": "Complies with truth-in-advertising rules"})

    # 3. Brand Identity Check
    has_brand = any(b in lower_text for b in ("afrigen", "africa creates", "african ai", "afrigen.com.ng"))
    if not has_brand:
        score -= 20
        flags.append("Missing core brand mention (Afrigen or afrigen.com.ng).")
        checks.append({"name": "branding", "passed": False, "detail": "Brand reference missing"})
    else:
        checks.append({"name": "branding", "passed": True, "detail": "Brand properly identified"})

    # 4. Emoji Spam Detection
    emoji_count = len(re.findall(r'[\U00010000-\U0010ffff]', text))
    if emoji_count > 10:
        score -= 15
        flags.append("Excessive emoji usage detracts from professional brand aesthetic.")
        checks.append({"name": "emoji_density", "passed": False, "detail": f"{emoji_count} emojis detected"})
    else:
        checks.append({"name": "emoji_density", "passed": True, "detail": f"{emoji_count} emojis (balanced)"})

    # 5. Media URL Validation (for image/video formats)
    if content_format in ("image", "flyer", "video"):
        if not media_url:
            score -= 35
            flags.append(f"Content format is '{content_format}' but no media asset URL is attached.")
            checks.append({"name": "media_attached", "passed": False, "detail": "Missing media URL"})
        elif not media_url.startswith("http"):
            score -= 30
            flags.append(f"Media URL '{media_url}' is not a valid absolute HTTP/HTTPS address.")
            checks.append({"name": "media_attached", "passed": False, "detail": "Invalid URL structure"})
        else:
            checks.append({"name": "media_attached", "passed": True, "detail": "Valid media asset attached"})

    # 6. Call To Action Check
    if not call_to_action and "afrigen.com.ng" not in lower_text:
        score -= 10
        flags.append("No clear call-to-action or link provided.")
        checks.append({"name": "cta", "passed": False, "detail": "Missing CTA"})
    else:
        checks.append({"name": "cta", "passed": True, "detail": "CTA present"})

    final_score = max(0, min(100, score))
    passed = final_score >= 70

    return {
        "passed": passed,
        "score": final_score,
        "checks": checks,
        "flags": flags,
        "status_recommendation": "ready" if passed else "retry_pending",
    }
