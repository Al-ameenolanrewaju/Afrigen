import re
import os


PRODUCT_LABELS = {
    "text": "Afrigen Intelligence",
    "video": "Afrigen Video Engine",
    "image": "Afrigen Image Engine",
    "voice": "Afrigen Voice Engine",
    "movie": "Afrigen Movie Engine",
    "media": "Afrigen Media Engine",
}

TEXT_TASK_ROUTING = {
    "Prompt Refinement": "Groq",
    "AI Assistant": "Groq",
    "Quick Chat": "Groq",
    "Blog Writing": "Groq",
    "Newsletter": "Groq",
    "Long-form Writing": "Groq",
    "Campaign": "Groq",
    "Audio Script": "Groq",
    "Default": "Groq",
}

TEXT_PROVIDER_FALLBACKS = ("Groq", "Gemini", "OpenRouter")

VIDEO_MODEL_REGISTRY = {
    "text_to_video": {
        "standard": "fal-ai/kling-video/v1/standard/text-to-video",
        "professional": "fal-ai/kling-video/v1/pro/text-to-video",
        "fast": "fal-ai/fast-animatediff/text-to-video",
        "legacy_fast": "fal-ai/ltx-video",
    },
    "image_to_video": (
        "fal-ai/kling-video/v3/pro/image-to-video",
        "fal-ai/kling-video/v3/standard/image-to-video",
    ),
}

IMAGE_MODEL_REGISTRY = {
    "realistic": "fal-ai/flux/dev",
    "anime": "fal-ai/flux/dev",
    "cinematic": "fal-ai/flux-pro/v1.1",
    "african": "fal-ai/flux/dev",
    "social": "fal-ai/flux/dev",
}

_PROVIDER_LABELS = {
    "groq": "Afrigen Intelligence",
    "gemini": "Afrigen Intelligence",
    "openai": "Afrigen Intelligence",
    "anthropic": "Afrigen Intelligence",
    "claude": "Afrigen Intelligence",
    "openrouter": "Afrigen Intelligence",
    "mistral": "Afrigen Intelligence",
    "deepseek": "Afrigen Intelligence",
    "llama": "Afrigen Intelligence",
    "kling": "Afrigen Video Engine",
    "flux": "Afrigen Image Engine",
    "hugging face": "Afrigen Image Engine",
    "replicate": "Afrigen Media Engine",
    "fal": "Afrigen Media Engine",
    "elevenlabs": "Afrigen Voice Engine",
    "whisper": "Afrigen Voice Engine",
    "stability ai": "Afrigen Image Engine",
}

_PROVIDER_PATTERN = re.compile(
    r"\b(?:(?:google\s+)?gemini(?:\s+[0-9]+(?:\.[0-9]+)*(?:[- ](?:flash|pro|ultra))?)|"
    r"hugging\s+face|stability\s+ai|elevenlabs|"
    r"fal(?:\.ai|-ai|[ ]ai)?|"
    r"groq|kling(?:\s+ai)?(?:\s+pro)?|"
    r"flux(?:\.1)?(?:\s+(?:dev|pro|schnell))?|"
    r"openai(?:\s+gpt-?[0-9a-z.]+)?|gpt-?[0-9][0-9a-z.-]*|"
    r"anthropic(?:\s+claude(?:[- ](?:sonnet|opus|haiku))?(?:[- ]\d+(?:[-.]\d+)*)?)?|"
    r"claude(?:[- ](?:sonnet|opus|haiku))?(?:[- ]\d+(?:[-.]\d+)*)?|"
    r"replicate|deepseek|openrouter|mistral(?:\s+[a-z0-9.-]+)?|"
    r"llama(?:[- ]\d+(?:\.\d+)*)?|whisper(?:[- ]large[- ]v?\d+(?:\.\d+)?)?)\b",
    re.IGNORECASE,
)


def product_label_for_provider(provider_name, default="Afrigen Creative Engine"):
    """Return a customer-safe product label for an internal provider identifier."""
    normalized = (provider_name or "").strip().lower().replace("_", " ")
    for identifier, label in _PROVIDER_LABELS.items():
        if identifier in normalized:
            return label
    return default


def sanitize_generated_text(value):
    """Remove infrastructure branding from AI-generated customer-facing text."""
    if not isinstance(value, str):
        return value

    def replace_provider(match):
        provider = match.group(0).lower()
        if "kling" in provider:
            return PRODUCT_LABELS["video"]
        if "flux" in provider or "hugging" in provider or "stability" in provider:
            return PRODUCT_LABELS["image"]
        if "eleven" in provider or "whisper" in provider:
            return PRODUCT_LABELS["voice"]
        if "fal" in provider or "replicate" in provider:
            return PRODUCT_LABELS["media"]
        return PRODUCT_LABELS["text"]

    sanitized = re.sub(
        r"https?://[^\s)<>]*(?:fal\.media|fal\.ai|replicate\.delivery|huggingface\.co)[^\s)<>]*",
        "[Afrigen media]",
        value,
        flags=re.IGNORECASE,
    )
    return _PROVIDER_PATTERN.sub(replace_provider, sanitized)


def customer_error(product="text"):
    """Return a stable, branded error without exposing upstream diagnostics."""
    messages = {
        "text": "Afrigen Intelligence couldn't complete your request. Please try again.",
        "video": "Afrigen Video Engine is currently unavailable. Please try again shortly.",
        "image": "Afrigen Image Engine couldn't complete your request. Please try again.",
        "voice": "Afrigen Voice Engine couldn't complete your request. Please try again.",
        "movie": "Afrigen Movie Engine couldn't complete this step. Please try again.",
    }
    return messages.get(product, "Afrigen couldn't complete your request. Please try again.")


def redact_secrets(value, additional_secrets=()):
    """Redact credentials from diagnostic strings before they are persisted."""
    if not isinstance(value, str):
        return value

    secrets = {
        secret for secret in additional_secrets
        if isinstance(secret, str) and len(secret) >= 6
    }
    secrets.update(
        secret for key, secret in os.environ.items()
        if key.endswith(("_API_KEY", "_TOKEN", "_SECRET"))
        and isinstance(secret, str) and len(secret) >= 6
    )
    redacted = value
    for secret in sorted(secrets, key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    return re.sub(
        r"(?i)(api[_ -]?key|authorization|access[_ -]?token)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        redacted,
    )
