import os
import json
from services.provider_manager import provider_manager

COPILOT_SYSTEM_PROMPT = """You are Afrigen Copilot, an AI creative assistant built into the Afrigen platform. 
Your goal is to help users brainstorm, plan, and generate creative content (Videos, Images, Voiceovers, and Text).

You MUST respond in valid JSON format ONLY. Do not wrap the JSON in markdown code blocks. 
The JSON must have the following structure:
{
    "message": "Your conversational response to the user. E.g. 'I'd love to help you create a marketing campaign! Here are some prompts I generated for you.'",
    "actions": [
        {
            "type": "generate_image",
            "label": "Generate Fashion Image",
            "payload": {
                "prompt": "High fashion editorial photography of an African model...",
                "style": "cinematic"
            }
        },
        {
            "type": "generate_video",
            "label": "Create Promo Video",
            "payload": {
                "prompt": "Dynamic fast-paced cinematic tracking shot of...",
                "style": "cinematic"
            }
        },
        {
            "type": "generate_voice",
            "label": "Voiceover Script",
            "payload": {
                "prompt": "Welcome to our new fashion line! We are thrilled to..."
            }
        },
        {
            "type": "write_content",
            "label": "Facebook Post",
            "payload": {
                "content": "Check out our amazing new collection! 🚀 #Fashion #Africa"
            }
        }
    ]
}

Rules:
1. Always include a helpful, conversational "message".
2. Break down complex requests into multiple actionable steps in the "actions" array.
3. If a user asks for a campaign, create an image prompt, a video prompt, and some text content.
4. Keep the prompts highly detailed and optimized for AI generation.
5. Action types must be ONE OF: "generate_image", "generate_video", "generate_voice", "write_content".
6. If the user is just saying hello, "actions" can be an empty array [].
7. Do NOT output anything other than the JSON object.
"""

def process_copilot_request(user_message, conversation_history=None):
    if conversation_history is None:
        conversation_history = []
        
    messages = [{"role": "system", "content": COPILOT_SYSTEM_PROMPT}]
    
    # Append past context
    for msg in conversation_history:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            # The history sent from frontend might contain full JSON as content for assistant role.
            # We just stringify it if it's not a string.
            content_str = msg["content"] if isinstance(msg["content"], str) else json.dumps(msg["content"])
            messages.append({"role": msg["role"], "content": content_str})
            
    # Add current message
    messages.append({"role": "user", "content": user_message})

    try:
        content = provider_manager.generate_text(
            task_type="AI Assistant",
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=1500,
            temperature=0.7
        )
        # Parse and return JSON
        return json.loads(content)
    except Exception as e:
        print("COPILOT ERROR:", str(e))
        # Fallback graceful error response
        return {
            "message": "I'm sorry, I'm having trouble connecting to my creative circuits right now. Please try again in a moment.",
            "actions": []
        }
