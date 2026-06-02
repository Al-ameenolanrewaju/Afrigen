import os
import requests

def generate_voiceover(script, voice_style="nigerian_male"):
    print("generate_voiceover called!")
    try:
        import fal_client

        result = fal_client.subscribe(
            "fal-ai/kokoro/american-english",
            arguments={
                "text": script,
                "voice": "am_adam",
                "speed": 1.0
            }
        )

        audio_url = result.get("audio", {}).get("url")
        if not audio_url:
            raise Exception("No audio URL returned")

        # Return the fal-hosted CDN URL directly (matches how video_url is
        # stored). Avoids relying on local disk, which is ephemeral on
        # Railway/Render and would lose the file on redeploy.
        print(f"Voiceover generated: {audio_url}")
        return audio_url

    except Exception as e:
        print(f"FAL TTS error: {e}")
        return None


def generate_video_script(prompt, style="cinematic"):
    """Generate voiceover script from prompt"""
    from services.claude import client as groq_client

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """You are an expert African content creator.
                Generate a short engaging voiceover script (30-60 words)
                for an AI generated video.
                Make it African, cultural and engaging.
                Return ONLY the script, nothing else."""
            },
            {
                "role": "user",
                "content": f"Generate voiceover script for: {prompt}"
            }
        ],
        max_tokens=100
    )

    return response.choices[0].message.content