import os
import json
from services.provider_manager import provider_manager

CAMPAIGN_SYSTEM_PROMPT = """You are Afrigen Campaign AI, a master marketing strategist.
The user will provide details about their business and campaign goals.
You must output a highly structured, comprehensive campaign plan in JSON format.

JSON Structure:
{
    "strategy": {
        "theme": "Core campaign theme (e.g. 'Sleek & Modern Arrival')",
        "target_audience": "Who this is for",
        "key_messages": ["Message 1", "Message 2"],
        "suggested_hashtags": ["#Tag1", "#Tag2"],
        "call_to_action": "Primary CTA"
    },
    "deliverables": [
        {
            "id": "unique-id-1",
            "type": "image",
            "name": "Hero Launch Image",
            "prompt": "Highly detailed AI image generation prompt...",
            "style": "cinematic"
        },
        {
            "id": "unique-id-2",
            "type": "video",
            "name": "Teaser Video",
            "prompt": "Highly detailed AI video generation prompt...",
            "style": "cinematic",
            "aspect_ratio": "16:9"
        },
        {
            "id": "unique-id-3",
            "type": "content",
            "name": "Facebook Post",
            "prompt": "Write a compelling Facebook post using the key messages..."
        }
    ]
}

Rules:
1. ONLY return valid JSON. Do not wrap in markdown or add explanations.
2. The 'deliverables' array must contain highly optimized prompts tailored to the requested assets.
3. If they asked for 3 images, generate 3 distinct 'image' deliverables.
4. Types must be one of: "image", "video", "voice", "content".
"""

def generate_campaign_plan(data):
    # data contains: business_name, industry, audience, goal, selected_deliverables
    
    user_prompt = f"Business: {data.get('business_name')}\n"
    user_prompt += f"Industry: {data.get('industry')}\n"
    user_prompt += f"Audience: {data.get('target_audience')}\n"
    user_prompt += f"Goal: {data.get('goal')}\n"
    user_prompt += f"Requested Deliverables: {json.dumps(data.get('deliverables', []))}\n"
    user_prompt += "Generate the complete campaign strategy and exact prompts for these deliverables."

    try:
        content = provider_manager.generate_text(
            task_type="Campaign",
            messages=[
                {"role": "system", "content": CAMPAIGN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.7
        )
        return json.loads(content)
    except Exception as e:
        print("CAMPAIGN ERROR:", str(e))
        return None
