import os
import asyncio
import tempfile
import requests

# Nigerian English neural voice via Microsoft Edge TTS (free, no API key).
# Options: "en-NG-AbeoNeural" (male) or "en-NG-EzinneNeural" (female).
VOICEOVER_VOICE = os.environ.get("VOICEOVER_VOICE", "en-NG-AbeoNeural")


def generate_voiceover(script):
    """Synthesize a Nigerian-voice narration and return a public audio URL.

    Renders an MP3 locally with edge-tts (free Microsoft neural voices), then
    uploads it to fal storage so the ffmpeg merge step can fetch it by URL.
    Returns None on failure, in which case the caller keeps the silent video.
    """
    print("generate_voiceover called!")
    tmp_path = os.path.join(tempfile.gettempdir(), f"vo_{os.urandom(8).hex()}.mp3")
    try:
        import edge_tts
        import fal_client

        async def _synthesize():
            communicate = edge_tts.Communicate(script, VOICEOVER_VOICE)
            await communicate.save(tmp_path)

        asyncio.run(_synthesize())

        # The merge endpoint needs a publicly fetchable URL; fal storage gives a
        # CDN link without relying on the app's ephemeral local disk.
        audio_url = fal_client.upload_file(tmp_path)
        if not audio_url:
            raise Exception("No audio URL returned from upload")

        print(f"Voiceover generated: {audio_url}")
        return audio_url

    except Exception as e:
        print(f"TTS error: {e}")
        return None
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def generate_video_script(prompt, style="cinematic"):
    """Generate voiceover script from prompt"""
    from services.provider_manager import provider_manager

    response = provider_manager.generate_text(
        task_type="Audio Script",
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

    return response