import os
from groq import Groq

client = Groq(api_key=os.environ['GROQ_API_KEY'])

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
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=40,
        )
        text = (response.choices[0].message.content or "").strip()
        # Strip wrapping quotes the model sometimes adds, and guard against it
        # narrating "none"/"no text" instead of returning empty.
        text = text.strip().strip('"').strip("'").strip()
        if text.lower() in ("", "none", "no text", "n/a", "empty"):
            return ""
        return text
    except Exception as e:
        print("EXTRACT TEXT ERROR:", str(e))
        return ""


def refine_prompt(user_prompt, style="cinematic"):
    system_message = STYLE_PROMPTS.get(style, STYLE_PROMPTS["cinematic"]) + VIDEO_FIDELITY_RULES

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": (
                "Refine this video prompt. Keep my subject and intent, and keep "
                "any on-screen words exactly as written:\n\n" + user_prompt
            )}
        ],
        max_tokens=300
    )

    return response.choices[0].message.content


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

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": (
                "Refine this image prompt. If it contains any words that should "
                "appear in the image, keep those words exactly as written and "
                "make them bold and legible:\n\n" + user_prompt
            )}
        ],
        max_tokens=300
    )

    return response.choices[0].message.content