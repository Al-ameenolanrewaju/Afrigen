"""Autonomous Quality Assurance and Content Validation Engine for Afrigen.

Scores planned social content, verifies factual brand details and pricing,
validates media accessibility and platform compatibility, and strictly prevents
hallucinated claims, fake testimonials, invented statistics, and internal development leaks.
"""

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

FORBIDDEN_PHRASES = [
    "99% off", "100% discount", "free 1000 credits", "get rich quick",
    "unlimited free forever", "guaranteed viral", "guaranteed sales",
    "instant monetization", "make money while you sleep",
    "test flyer upload from python pil engine", "from python pil engine",
    "john from london said", "sarah from google said", "sarah said", "john said",
    "llm fallback", "[refreshed edition]", "todo:", "debug:",
]

# Patterns for detecting fake testimonials or fabricated user reviews
FAKE_TESTIMONIAL_PATTERNS = [
    r'\b(?:said|says)\s+[A-Z][a-z]+\s+(?:from|at|in)\s+[A-Z][a-z]+',
    r'\b[A-Z][a-z]+\s+(?:from|at|in)\s+(?:london|google|new york|paris|lagos)\s+(?:said|testifies|shares)',
    r'\bclient testimonial:\s*"',
    r'\bverified customer review:\s*"',
    r'"(?:i was skeptical at first|this changed my life|i made \$\d+)',
]

# Patterns for detecting invented statistics or unrealistic ROI claims
INVENTED_STAT_PATTERNS = [
    r'\bproven to (?:boost|increase|scale|grow) (?:by )?\d{2,}%',
    r'\b(?:99\.9%|98\.7%|99%)\s+(?:of creators|of users|satisfaction|accuracy)',
    r'\b\d{3,}% (?:increase|growth|boost|roi|jump)\b',
    r'\bmake \$\d+[\d,]* (?:a day|per day|in your sleep|passive income)\b',
]

VALID_PRICE_REFERENCES = ["10,000", "10000", "₦10k", "free spark plan", "monthly allowances"]


def run_social_quality_audit(
    caption: str,
    platform: str,
    content_format: str,
    media_url: Optional[str] = None,
    call_to_action: Optional[str] = None,
) -> Dict[str, Any]:
    """Perform comprehensive pre-publishing QA check and return a quality score (0-100)."""
    score = 100
    checks = []
    flags = []

    text = (caption or "").strip()
    lower_text = text.lower()
    platform = (platform or "facebook").lower().strip()

    # 1. Minimum and Maximum Length Validation
    char_len = len(text)
    if char_len < 50:
        score -= 40
        flags.append("Caption is too short to provide meaningful value.")
        checks.append({"name": "length", "passed": False, "detail": f"Under 50 characters ({char_len})"})
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

    # 2. Forbidden Marketing Phrases & False Claims
    for forbidden in FORBIDDEN_PHRASES:
        if forbidden in lower_text:
            score -= 50
            flags.append(f"Contains non-compliant marketing phrase: '{forbidden}'.")
            checks.append({"name": "compliance", "passed": False, "detail": f"Forbidden: {forbidden}"})
            break
    else:
        checks.append({"name": "compliance", "passed": True, "detail": "Complies with truth-in-advertising rules"})

    # 3. Fake Testimonial Detection
    for pattern in FAKE_TESTIMONIAL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            score -= 45
            flags.append(f"Contains fabricated testimonial or unverified customer quote: '{match.group(0)}'.")
            checks.append({"name": "truth_in_advertising", "passed": False, "detail": f"Fabricated quote: {match.group(0)}"})
            break
    else:
        checks.append({"name": "truth_in_advertising", "passed": True, "detail": "No fabricated testimonials"})

    # 4. Invented Statistics & Unrealistic ROI Claims
    for pattern in INVENTED_STAT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            score -= 40
            flags.append(f"Contains invented statistic or unrealistic performance claim: '{match.group(0)}'.")
            checks.append({"name": "factual_claims", "passed": False, "detail": f"Invented statistic: {match.group(0)}"})
            break
    else:
        checks.append({"name": "factual_claims", "passed": True, "detail": "No invented statistics"})

    # 5. Internal Development Artifacts Leakage
    dev_leak_patterns = [r'\[refreshed edition\]', r'\{\{.*?\}\}', r'todo:', r'debug:']
    for pat in dev_leak_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            score -= 35
            flags.append(f"Contains internal development marker or template artifact: '{match.group(0)}'.")
            checks.append({"name": "no_internal_leaks", "passed": False, "detail": f"Internal marker: {match.group(0)}"})
            break
    else:
        checks.append({"name": "no_internal_leaks", "passed": True, "detail": "Clean copy without internal artifacts"})

    # 6. Brand Consistency Check
    has_brand = any(b in lower_text for b in ("afrigen", "africa creates", "african ai", "afrigen.com.ng"))
    if not has_brand:
        score -= 20
        flags.append("Missing core brand mention (Afrigen or afrigen.com.ng).")
        checks.append({"name": "branding", "passed": False, "detail": "Brand reference missing"})
    else:
        checks.append({"name": "branding", "passed": True, "detail": "Brand properly identified"})

    # 7. Emoji Spam Detection
    emoji_count = len(re.findall(r'[\U00010000-\U0010ffff]', text))
    if emoji_count > 6:
        score -= 20
        flags.append("Excessive emoji usage detracts from professional brand aesthetic.")
        checks.append({"name": "emoji_density", "passed": False, "detail": f"{emoji_count} emojis detected (max recommended is 3)"})
    else:
        checks.append({"name": "emoji_density", "passed": True, "detail": f"{emoji_count} emojis (tasteful)"})

    # 8. Media URL Validation (for image/flyer/video formats)
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

    # 9. Call To Action Check
    if not call_to_action and "afrigen.com.ng" not in lower_text:
        score -= 10
        flags.append("No clear call-to-action or link provided.")
        checks.append({"name": "cta", "passed": False, "detail": "Missing CTA"})
    else:
        checks.append({"name": "cta", "passed": True, "detail": "CTA present"})

    # 10. Unverified Pricing Check
    price_mentions = re.findall(r'[₦$€£]\s*\d+[\d,]*|\b\d+[\d,]*\s*(?:naira|usd|dollars)\b', lower_text)
    if price_mentions:
        for p in price_mentions:
            clean_p = p.replace(" ", "").replace(",", "")
            if not any(valid in clean_p for valid in ("10000", "10k", "0")):
                score -= 35
                flags.append(f"Contains unverified pricing claim: '{p}'. Only official pricing (₦10,000/mo or Free Spark Plan) is permitted.")
                checks.append({"name": "pricing_verification", "passed": False, "detail": f"Unverified price: {p}"})
                break
        else:
            checks.append({"name": "pricing_verification", "passed": True, "detail": "Pricing aligns with official catalog"})
    else:
        checks.append({"name": "pricing_verification", "passed": True, "detail": "No unverified price claims"})

    final_score = max(0, min(100, score))
    passed = final_score >= 70

    return {
        "passed": passed,
        "score": final_score,
        "checks": checks,
        "flags": flags,
        "status_recommendation": "ready" if passed else "retry_pending",
    }


def attempt_qa_auto_correction(
    caption: str,
    platform: str,
    flags: List[str],
    call_to_action: Optional[str] = None,
) -> Dict[str, Any]:
    """Attempt autonomous correction of minor QA defects to bring score above passing threshold."""
    corrected = (caption or "").strip()

    # 1. Strip internal development markers if present
    corrected = re.sub(r'\[refreshed edition\]', '', corrected, flags=re.IGNORECASE).strip()

    # 2. Add missing brand identity if flagged
    if any("Missing core brand mention" in f for f in flags):
        if platform == "linkedin":
            corrected = f"{corrected}\n\nBuilt with Afrigen AI (https://afrigen.com.ng) — empowering African creative professionals."
        else:
            corrected = f"{corrected}\n\nExperience creative freedom with Afrigen AI at afrigen.com.ng."

    # 3. Add missing call to action if flagged
    if any("No clear call-to-action" in f for f in flags):
        cta_text = call_to_action or "Start creating today at afrigen.com.ng"
        if cta_text not in corrected and "afrigen.com.ng" not in corrected:
            corrected = f"{corrected}\n\n👉 {cta_text}"

    # 4. Trim excessive emojis if flagged (keep at most 3)
    if any("Excessive emoji usage" in f for f in flags):
        emojis = re.findall(r'[\U00010000-\U0010ffff]', corrected)
        if len(emojis) > 3:
            for em in emojis[3:]:
                corrected = corrected.replace(em, "", 1)

    return {
        "corrected_caption": corrected.strip(),
        "modified": corrected.strip() != (caption or "").strip(),
    }
