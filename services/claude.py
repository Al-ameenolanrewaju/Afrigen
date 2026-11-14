import os
import re
from services.provider_manager import provider_manager
from services.ai_products import VIDEO_MODEL_REGISTRY

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
    Keep under 200 words. Return ONLY the prompt.""",

    "movie": """You are an elite Hollywood-level cinematic scene prompt engineer for Afrigen's Movie Scene Studio.
    Transform the idea into a premium feature-film quality scene prompt:
    - Anamorphic lens, 2.39:1 aspect ratio cinematic framing, shallow depth of field
    - Dramatic Nollywood/Hollywood lighting — practical light sources, volumetric God rays
    - Rich African setting, production design, authentic costumes and props
    - Detailed camera movement (slow crane push-in, tracking shot, etc.)
    - Film-grade color grading description (teal-orange Hollywood grade, warm Nollywood palette)
    - Single cohesive scene with clear dramatic tension and emotional arc
    - Ultra high quality: "shot on ARRI Alexa 65, 4K, film grain, masterwork cinematography"
    Keep under 220 words. OUTPUT FORMAT: Single paragraph only. Return ONLY the prompt."""
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


def is_clarification_response(text):
    """Identify an AI reply asking the user for context instead of refining a prompt."""
    normalized = (text or "").lower().replace("\u2018", "'").replace("\u2019", "'")
    return any(
        phrase in normalized
        for phrase in (
            "i'm sorry",
            "i am sorry",
            "could you please",
            "can you please",
            "would you please",
            "please provide more details",
            "please provide more detail",
            "need more details",
            "need more detail",
            "can you describe",
        )
    )


def _refinement_is_usable(original_prompt, refined_prompt):
    refined_prompt = (refined_prompt or "").strip()
    if (
        "Rewrite the following idea" in refined_prompt
        or "Return ONLY" in refined_prompt
        or is_clarification_response(refined_prompt)
    ):
        return False
    original_words = {
        word.lower() for word in re.findall(r"[a-zA-Z0-9]+", original_prompt or "")
        if len(word) > 3
    }
    refined_words = {
        word.lower() for word in re.findall(r"[a-zA-Z0-9]+", refined_prompt or "")
    }
    return (
        len(refined_prompt) >= 40
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


def get_model_prompt_rules(model_name=None, duration="5"):
    model_name = model_name or VIDEO_MODEL_REGISTRY["text_to_video"]["standard"]
    """Return model-specific instructions for prompt generation.

    Optimized for Kling AI to generate high-fidelity, physically consistent, cinematic video.
    """
    model_name = (model_name or "fal-ai/kling-video/v1/standard/text-to-video").lower()
    duration = str(duration or "5")

    if "kling" in model_name:
        is_pro = "pro" in model_name
        duration_hint = {
            "5": "Keep the scene clear and cinematic with a smooth beginning and end.",
            "10": "Maintain cinematic continuity and a believable subject arc across the full shot.",
            "15": "Keep the camera steady and the subject consistent to preserve flow over a longer duration.",
            "20": "Use a simple, coherent, slowly evolving scene to preserve visual continuity across a long clip.",
        }.get(duration, "Keep the shot stable and coherent across time.")
        quality_note = "premium Kling Pro" if is_pro else "premium Kling"
        return (
            f"You are refining a prompt for the {quality_note} model. "
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


def refine_prompt(
    user_prompt,
    style="cinematic",
    model_name=None,
    duration="5",
    user=None,
):
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
    try:
        response = provider_manager.generate_text(
            task_type="Prompt Refinement",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            user=user,
            max_tokens=2048
        )
    except Exception as exc:
        print("VIDEO PROMPT REFINEMENT ERROR:", str(exc))
        response = ""

    if not _refinement_is_usable(user_prompt, response):
        try:
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
                user=user,
                max_tokens=2048
            )
        except Exception as exc:
            print("VIDEO PROMPT RETRY ERROR:", str(exc))
            response = ""

    if not _refinement_is_usable(user_prompt, response):
        response = (
            f"{(user_prompt or '').strip()}. Create a detailed {style} video with one "
            "clear main subject and action, a coherent setting, purposeful camera "
            "movement, natural lighting, rich visual detail, and a consistent mood."
        )

    return _clean_refined_prompt(response)


def _clean_refined_prompt(text: str) -> str:
    """Extract raw prompt from conversational LLM output if needed."""
    if not text:
        return ""
    cleaned = text.strip()
    import re
    # If the model output has "Prompt:" or "> **Prompt:**"
    match = re.search(r'(?:> \*\*Prompt:\*\*|\*\*Prompt:\*\*|Prompt:)\s*([^\n\r]+(?:\n[^\n\r#]+)*)', cleaned, re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        if len(extracted) > 30:
            cleaned = extracted
    elif "option 1" in cleaned.lower():
        lines = cleaned.splitlines()
        opt1_lines = []
        capture = False
        for line in lines:
            if "option 1" in line.lower():
                capture = True
                continue
            if capture:
                if line.startswith("#") or "option 2" in line.lower():
                    break
                if line.strip():
                    opt1_lines.append(line.strip().lstrip('>').strip())
        if opt1_lines:
            cleaned = " ".join(opt1_lines)

    # Strip surrounding quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def refine_image_prompt(user_prompt, style="realistic", user=None):
    """Refine prompt for image generation with authentic African representation and exact text preservation."""

    TEXT_RULES = """

    CRITICAL RULES FOR ANY TEXT, WORDS, OR LETTERING IN THE IMAGE:
    - Copy the user's exact words VERBATIM in quotes, e.g. text reads "Afrigen Ai is cooking, stay tune".
    - Never omit, paraphrase, or change the capitalization/spelling.
    - Explicitly state that the text is written in large, BOLD, high-contrast, perfectly legible lettering on the sign/poster.
    - If a poster/placard is requested, describe the subject physically holding a crisp, clean rectangular poster directly facing the viewer.
    - OUTPUT FORMAT: Output ONLY the final prompt in a single paragraph. Absolutely NO conversation, NO 'Option 1', NO headings, NO intro remarks."""

    IMAGE_STYLE_PROMPTS = {
        "realistic": """You are an expert realistic photography prompt engineer for Afrigen.
        Transform the idea into a 100% photorealistic photography prompt:
        - The subject MUST be a real, living African human being (Nigerian / West African skin tones, natural hair, realistic facial anatomy with real skin pores and micro-textures).
        - Shot on 35mm DSLR lens (Sony A7R V / Canon EOS 5D), f/2.8, natural ambient daylight or studio lighting, crisp optical focus.
        - ABSOLUTELY FORBIDDEN: 3D render, Pixar, cartoon, Disney, anime, CGI, plastic doll, airbrushed, digital art, stylized illustration.
        - Realistic setting (authentic African urban streets, home, office, or outdoor market).
        - If a sign, poster, or banner is mentioned, describe the subject holding an authentic cardboard poster facing forward, with the requested text prominently and legibly displayed in bold lettering.
        Return ONLY the final prompt paragraph.""" + TEXT_RULES,

        "social": """You are an expert social media and viral creator prompt engineer for Afrigen.
        Transform the idea into an eye-catching, high-converting image prompt tailored for Instagram, TikTok, and social feeds:
        - High energy, vivid contrast, punchy composition, crisp detail.
        - Authentic African creator aesthetic, modern contemporary fashion.
        - Bold, ultra-clear lettering on any signs or posters.
        Return ONLY the final prompt paragraph.""" + TEXT_RULES,

        "artistic": """You are an expert artistic image prompt engineer.
        Transform the idea into a detailed artistic prompt with:
        - Art style (oil painting, watercolor, digital art)
        - Color palette
        - African artistic elements
        - Mood and atmosphere
        Return ONLY the prompt paragraph.""" + TEXT_RULES,

        "cinematic": """You are an expert cinematic image prompt engineer.
        Transform the idea into a cinematic still image prompt with:
        - Movie still quality, 35mm film aesthetic
        - Dramatic volumetric lighting
        - African cinematic aesthetic, deep contrast
        Return ONLY the prompt paragraph.""" + TEXT_RULES,

        "african": """You are an expert African art prompt engineer.
        Transform the idea into a rich African aesthetic image prompt with:
        - Traditional African patterns, Ankara or modern African urban wear
        - African landscapes and cultural richness
        - Vibrant rich colors
        Return ONLY the prompt paragraph.""" + TEXT_RULES,

        "anime": """You are an expert anime image prompt engineer.
        Transform the idea into a detailed anime style prompt with African characters in anime aesthetic.
        Return ONLY the prompt paragraph.""" + TEXT_RULES
    }

    system_message = IMAGE_STYLE_PROMPTS.get(style, IMAGE_STYLE_PROMPTS["realistic"])

    user_message = (
        "Rewrite the following idea as one complete, detailed image-generation "
        "prompt. It must include the subject, setting, composition, lighting, colors, and mood. "
        "Output ONLY the prompt text, absolutely nothing else:\n\n" + (user_prompt or "")
    )
    try:
        response = provider_manager.generate_text(
            task_type="Prompt Refinement",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            user=user,
            max_tokens=800
        )
        response = _clean_refined_prompt(response)
    except Exception as exc:
        print("IMAGE PROMPT REFINEMENT ERROR:", str(exc))
        response = ""

    if not _refinement_is_usable(user_prompt, response):
        try:
            response = provider_manager.generate_text(
                task_type="Prompt Refinement",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": (
                        "Return ONLY one complete image prompt paragraph without any options or explanation. Original idea:\n\n" + (user_prompt or "")
                    )}
                ],
                user=user,
                max_tokens=800
            )
            response = _clean_refined_prompt(response)
        except Exception as exc:
            print("IMAGE PROMPT RETRY ERROR:", str(exc))
            response = ""

    if not _refinement_is_usable(user_prompt, response):
        response = (
            f"A photorealistic 35mm candid photograph of an African {(user_prompt or '').strip()}. "
            "Sharp focus, natural daylight, authentic rich melanin skin tones, realistic textures, "
            "vibrant African environment, cinematic composition, 8k resolution."
        )

    return _clean_refined_prompt(response)