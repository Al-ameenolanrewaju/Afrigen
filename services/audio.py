import os
import requests

# Available African voices (for when ElevenLabs works)
VOICES = {
    "nigerian_male": "pNInz6obpgDQGcFmaJgB",
    "nigerian_female": "21m00Tcm4TlvDq8ikWAM",
    "deep_african": "VR6AewLTigWG4xSOukaG",
    "professional": "ErXwobaYiN019PkySvjV",
    "energetic": "MF3mGyEYCl7XYWbV9V6O"
}


def generate_voiceover(script, voice_style="nigerian_male"):
    print("generate_voiceover called!")  # ← add this

    try:
        audio = generate_with_elevenlabs(script, voice_style)
        if audio:
            return audio
    except Exception as e:
        print(f"ElevenLabs failed: {e}")

    print("Trying HuggingFace TTS...")  # ← add this
    try:
        audio = generate_with_huggingface_tts(script)
        if audio:
            print("HuggingFace TTS succeeded!")  # ← add this
            return audio
    except Exception as e:
        print(f"HuggingFace TTS failed: {e}")

    print("All audio APIs failed!")  # ← add this
    return None


def generate_with_elevenlabs(script, voice_style="nigerian_male"):
    """ElevenLabs - best quality"""
    from elevenlabs import ElevenLabs

    client = ElevenLabs(api_key=os.environ.get("ELEVENLABS_API_KEY"))
    voice_id = VOICES.get(voice_style, VOICES["nigerian_male"])

    audio = client.text_to_speech.convert(
        text=script,
        voice_id=voice_id,
        model_id="eleven_multilingual_v2"
    )

    filename = f"voiceover_{os.urandom(8).hex()}.mp3"
    filepath = os.path.join("static", "audio", filename)
    os.makedirs(os.path.join("static", "audio"), exist_ok=True)

    with open(filepath, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return filename


def generate_with_huggingface_tts(script):
    """HuggingFace TTS - completely free"""
    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(
            provider="hf-inference",
            api_key=os.environ.get("HUGGINGFACE_API_KEY")
        )

        print("Trying HuggingFace TTS: facebook/mms-tts-eng")

        audio = client.text_to_speech(
            script,
            model="facebook/mms-tts-eng"
        )

        filename = f"voiceover_{os.urandom(8).hex()}.flac"
        filepath = os.path.join("static", "audio", filename)
        os.makedirs(os.path.join("static", "audio"), exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(audio)

        print(f"Audio saved: {filename}")
        return filename

    except Exception as e:
        print(f"HuggingFace TTS failed: {e}")
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