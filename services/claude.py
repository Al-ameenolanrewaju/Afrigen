import os
import re
from services.provider_manager import provider_manager

STYLE_PROMPTS = {
    "cinematic": """You are an expert cinematic video prompt engineer. 
    Transform the idea into a detailed cinematic prompt with:
    - 4K quality, golden hour lighting
    - Professional camera angles
    - African cultural elements where relevant
    - Mood and atmosphere
    - Technical quality indicators
    Keep under 200 words. Return ONLY the prompt.""",

    "anime": """You are an expert anime video prompt engineer.
    Transform the idea into a detailed anime style prompt with:
    - Japanese anime aesthetic
    - Vibrant colors and dynamic movement
    - Anime art style details
    - African characters with anime styling
    Keep under 200 words. Return ONLY the prompt.""",

    "realistic": """You are an expert realistic video prompt engineer.
    Transform the idea into a hyper-realistic prompt with:
    - Photorealistic details
    - Natural lighting and shadows
    - Real world African settings
    - Ultra high definition quality
    Keep under 200 words. Return ONLY the prompt.""",

    "african": """You are an expert African content video prompt engineer.
    Transform the idea into a rich African aesthetic prompt with:
    - Traditional African clothing and accessories
    - African landscapes and settings
    - Rich cultural elements (Yoruba, Igbo, Hausa etc.)
    - Vibrant African colors and patterns
    Keep under 200 words. Return ONLY the prompt.""",

    "social": """You are an expert social media video prompt engineer.
    Transform the idea into a social media optimized prompt with:
    - Eye-catching visuals
    - Fast paced and dynamic
    - Perfect for TikTok/Instagram/Facebook
    - African content creators style
    Keep under 200 words. Return ONLY the prompt."""
}

VIDEO_FIDELITY_RULES = """

    FIDELITY RULES (do not break these):
    - Keep the user's core subject, action, and intent. Enhance with detail;
      never replace or drop what they actually asked for.
    - If they name specific things (people, places, objects, brands, counts),
      preserve them exactly.
    - If any words should appear on screen (text, captions, signs, titles),
      copy them VERBATIM in double quotes and describe them as large, BOLD,
      high-contrast and legible. Never paraphrase or invent on-screen words.
    - Do not add unrelated subjects or change the scene the user described."""


def _refinement_is_usable(original_prompt, refined_prompt):
    original_words = {
        word.lower() for word in re.findall(r"[a-zA-Z0-9]+", original_prompt or "")
        if len(word) > 3
    }
    refined_words = {
        word.lower() for word in re.findall(r"[a-zA-Z0-9]+", refined_prompt or "")
    }
    return (
        len((refined_prompt or "").strip()) >= 20
        and (not original_words or original_words & refined_words)
    )


def extract_on_screen_text(user_prompt):
    """Pull out any words the user wants displayed on the video.

    Video models render text poorly, so on-screen words are burned on afterwards
    as a clean overlay (see services.video.add_text_overlay). This asks the LLM
    to return ONLY those words, verbatim, or an empty string when the user wants
    no on-screen text. Returns "" on any failure so the caller just skips the
    overlay.
    """
    system_message = (
        "You extract on-screen text from a video idea. If the user wants any "
        "words, a title, caption, sign, or label to literally appear on the "
        "screen, return ONLY those exact words, verbatim, with nothing else: no "
        "quotes, no explanation, no labels. If the user does NOT ask for any "
        "words on screen, return exactly an empty response. Keep it short (a few "
        "words); never invent text the user did not ask for."
    )
    try:
        response = provider_manager.generate_text(
            task_type="Prompt Refinement",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=40,
        )
        text = (response or "").strip()
        # Strip wrapping quotes the model sometimes adds, and guard against it
        # narrating "none"/"no text" instead of returning empty.
        text = text.strip().strip('"').strip("'").strip()
        if text.lower() in ("", "none", "no text", "n/a", "empty"):
            return ""
        return text
    except Exception as e:
        print("EXTRACT TEXT ERROR:", str(e))
        return ""


def get_model_prompt_rules(model_name="fal-ai/ltx-2.3-quality/clean-plate", duration="5"):
    """Return model-specific instructions for prompt generation.

    Different FAL backends have different failure modes: the free LTX model is
    best with simple, stable compositions, while Kling handles more cinematic and
    longer-duration continuity. We tune the prompt rather than trying to force a
    single generic prompt across all models.
    """
    model_name = (model_name or "fal-ai/ltx-2.3-quality/clean-plate").lower()
    duration = str(duration or "5")

    if "kling" in model_name:
        duration_hint = {
            "5": "Keep the scene clear and cinematic with a smooth beginning and end.",
            "10": "Maintain cinematic continuity and a believable subject arc across the full shot.",
            "15": "Keep the camera steady and the subject consistent to preserve flow over a longer duration.",
            "20": "Use a simple, coherent, slowly evolving scene to preserve visual continuity across a long clip.",
        }.get(duration, "Keep the shot stable and coherent across time.")
        return (
            "You are refining a prompt for the premium Kling model. "
            "Use cinematic continuity, smooth camera motion, and a believable subject arc. "
            "Keep one main subject and one clear action. Avoid crowded compositions, scene jumps, duplicate objects, and unstable motion. "
            f"{duration_hint} "
            "Preserve the user's exact subject, location, and intent."
        )

    if "animatediff" in model_name:
        duration_hint = {
            "5": "Keep the motion compact and readable.",
            "10": "Use a short, controlled motion loop with clear subject focus.",
            "15": "Keep the action simple and steady to avoid jitter.",
            "20": "Favor a stable, compact motion path over complex choreography.",
        }.get(duration, "Keep the motion compact and readable.")
        return (
            "You are refining a prompt for the AnimateDiff model. "
            "Use a compact, readable motion pattern with strong subject focus. "
            "Keep the scene simple, structured, and visually stable. Avoid jitter, clutter, rapid scene changes, and conflicting actions. "
            f"{duration_hint} "
            "Preserve the user's exact subject and environment."
        )

    # Free LTX model: the safest default is to avoid heavy motion, crowding, and
    # scene complexity, which are common causes of poor continuity and lapses.
    duration_hint = {
        "5": "Keep the action simple, stable, and complete in one clear motion.",
        "10": "Keep one clear subject and one clean action with minimal motion complexity.",
        "15": "Use a calm, stable composition with one main subject and one main action.",
        "20": "Use minimal motion and a clean, coherent scene so the clip stays believable over a longer duration.",
    }.get(duration, "Keep the scene simple, stable, and easy to track.")
    return (
        "You are refining a prompt for the free LTX model. "
        "Use one main subject, one clear action, and one clean background. "
        "Avoid sudden camera movement, scene jumps, clashing motion, duplicated objects, warped faces, and overly complex compositions. "
        f"{duration_hint} "
        "Preserve the user's exact subject, place, and intent."
    )


def refine_prompt(user_prompt, style="cinematic", model_name="fal-ai/ltx-2.3-quality/clean-plate", duration="5"):
    system_message = (
        STYLE_PROMPTS.get(style, STYLE_PROMPTS["cinematic"]) + "\n\n" +
        get_model_prompt_rules(model_name=model_name, duration=duration) + "\n\n" +
        VIDEO_FIDELITY_RULES
    )

    user_message = (
        "Rewrite the following idea as one complete, detailed video-generation "
        "prompt. It must be at least 40 words and include the subject, action, "
        "setting, lighting, camera direction, and mood. Never return a list of "
        "keywords or a fragment. Preserve the user's subject and intent:\n\n"
        + (user_prompt or "")
    )
    response = provider_manager.generate_text(
        task_type="Prompt Refinement",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        max_tokens=500
    )

    if not _refinement_is_usable(user_prompt, response):
        response = provider_manager.generate_text(
            task_type="Prompt Refinement",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": (
                    "Your previous answer was incomplete. Return ONLY one "
                    "complete video prompt of at least 40 words. Include the "
                    "original subject and action exactly; add setting, lighting, "
                    "camera movement, and mood. Original idea:\n\n" + (user_prompt or "")
                )}
            ],
            max_tokens=500
        )

    return response


def refine_image_prompt(user_prompt, style="realistic"):
    """Refine prompt for image generation"""

    # Shared rules appended to every style. The critical one is TEXT
    # PRESERVATION: image models garble text, and the refiner must never
    # paraphrase or drop words the user wants printed (flyers, billboards,
    # posters, signs, logos).
    TEXT_RULES = """

    CRITICAL RULES FOR ANY TEXT, WORDS, OR LETTERING IN THE IMAGE
    (flyers, billboards, posters, signs, banners, logos, labels):
    - Copy the user's exact words VERBATIM. Never paraphrase, translate,
      shorten, or invent new wording. Keep their spelling and punctuation.
    - Wrap every piece of on-image text in double quotes in your prompt,
      e.g. the text reads "GRAND OPENING - 50% OFF".
    - Explicitly describe that text as: large, BOLD, high-contrast, sharp,
      perfectly legible, correctly spelled, centered and well-spaced.
    - If the user gives several lines, keep them as separate lines and state
      which is the headline (biggest, boldest) vs. smaller supporting text.
    - Do NOT add extra words, slogans, or captions the user did not write."""

    IMAGE_STYLE_PROMPTS = {
        "realistic": """You are an expert image prompt engineer.
        Transform the idea into a detailed realistic image prompt with:
        - Photorealistic details
        - Lighting description
        - Camera settings (lens, aperture)
        - African cultural elements where relevant
        - Ultra high definition quality
        Keep under 150 words. Return ONLY the prompt.""" + TEXT_RULES,

        "artistic": """You are an expert artistic image prompt engineer.
        Transform the idea into a detailed artistic prompt with:
        - Art style (oil painting, watercolor, digital art)
        - Color palette
        - African artistic elements
        - Mood and atmosphere
        Keep under 150 words. Return ONLY the prompt.""" + TEXT_RULES,

        "cinematic": """You are an expert cinematic image prompt engineer.
        Transform the idea into a cinematic still image prompt with:
        - Movie still quality
        - Dramatic lighting
        - African cinematic aesthetic
        - Professional photography details
        Keep under 150 words. Return ONLY the prompt.""" + TEXT_RULES,

        "african": """You are an expert African art prompt engineer.
        Transform the idea into a rich African aesthetic image prompt with:
        - Traditional African patterns and clothing
        - African landscapes and settings
        - Cultural elements (Yoruba, Igbo, Hausa etc.)
        - Vibrant African colors
        Keep under 150 words. Return ONLY the prompt.""" + TEXT_RULES,

        "anime": """You are an expert anime image prompt engineer.
        Transform the idea into a detailed anime style prompt with:
        - Japanese anime aesthetic
        - Vibrant colors
        - African characters in anime style
        - Dynamic composition
        Keep under 150 words. Return ONLY the prompt.""" + TEXT_RULES
    }

    system_message = IMAGE_STYLE_PROMPTS.get(style, IMAGE_STYLE_PROMPTS["realistic"])

    user_message = (
        "Rewrite the following idea as one complete, detailed image-generation "
        "prompt. It must be at least 40 words and include the subject, setting, "
        "composition, lighting, colors, and mood. Never return keywords or a "
        "fragment. Preserve the user's subject and intent:\n\n" + (user_prompt or "")
    )
    response = provider_manager.generate_text(
        task_type="Prompt Refinement",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        max_tokens=500
    )

    if not _refinement_is_usable(user_prompt, response):
        response = provider_manager.generate_text(
            task_type="Prompt Refinement",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": (
                    "Your previous answer was incomplete. Return ONLY one "
                    "complete image prompt of at least 40 words. Include the "
                    "original subject exactly; add setting, composition, lighting, "
                    "colors, and mood. Original idea:\n\n" + (user_prompt or "")
                )}
            ],
            max_tokens=500
        )

    return response