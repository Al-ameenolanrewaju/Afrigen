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

def refine_prompt(user_prompt, style="cinematic"):
    system_message = STYLE_PROMPTS.get(style, STYLE_PROMPTS["cinematic"])

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Refine this video prompt: {user_prompt}"}
        ],
        max_tokens=300
    )

    return response.choices[0].message.content


def refine_image_prompt(user_prompt, style="realistic"):
    """Refine prompt for image generation"""

    IMAGE_STYLE_PROMPTS = {
        "realistic": """You are an expert image prompt engineer.
        Transform the idea into a detailed realistic image prompt with:
        - Photorealistic details
        - Lighting description
        - Camera settings (lens, aperture)
        - African cultural elements where relevant
        - Ultra high definition quality
        Keep under 150 words. Return ONLY the prompt.""",

        "artistic": """You are an expert artistic image prompt engineer.
        Transform the idea into a detailed artistic prompt with:
        - Art style (oil painting, watercolor, digital art)
        - Color palette
        - African artistic elements
        - Mood and atmosphere
        Keep under 150 words. Return ONLY the prompt.""",

        "cinematic": """You are an expert cinematic image prompt engineer.
        Transform the idea into a cinematic still image prompt with:
        - Movie still quality
        - Dramatic lighting
        - African cinematic aesthetic
        - Professional photography details
        Keep under 150 words. Return ONLY the prompt.""",

        "african": """You are an expert African art prompt engineer.
        Transform the idea into a rich African aesthetic image prompt with:
        - Traditional African patterns and clothing
        - African landscapes and settings
        - Cultural elements (Yoruba, Igbo, Hausa etc.)
        - Vibrant African colors
        Keep under 150 words. Return ONLY the prompt.""",

        "anime": """You are an expert anime image prompt engineer.
        Transform the idea into a detailed anime style prompt with:
        - Japanese anime aesthetic
        - Vibrant colors
        - African characters in anime style
        - Dynamic composition
        Keep under 150 words. Return ONLY the prompt."""
    }

    system_message = IMAGE_STYLE_PROMPTS.get(style, IMAGE_STYLE_PROMPTS["realistic"])

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Refine this image prompt: {user_prompt}"}
        ],
        max_tokens=200
    )

    return response.choices[0].message.content