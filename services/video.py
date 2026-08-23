import os
import time
import subprocess
import tempfile
import requests
import fal_client

os.environ["FAL_KEY"] = os.environ.get("FAL_KEY", "")

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries

# Bold TTF bundled in the repo so drawtext always has a font, regardless of host.
FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "fonts", "DejaVuSans-Bold.ttf",
)


def generate_video(
    prompt,
    style="cinematic",
    aspect_ratio="16:9",
    extended=False
):
    # Same model selection as the website's async path: Pro users (extended=True)
    # get the premium 10s Kling clip on cinematic/realistic/african and a longer
    # AnimateDiff clip on anime/social; everyone else gets the short LTX clip.
    # This call is synchronous (fal_client.subscribe blocks until the video is
    # ready), which is what the Telegram bot needs.
    model, arguments = _build_t2v_request(prompt, style, aspect_ratio, extended)
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Video attempt {attempt}/{MAX_RETRIES} - model: {model}")

            result = fal_client.subscribe(model, arguments=arguments)

            video_url = None
            if isinstance(result, dict):
                if result.get("video"):
                    video = result.get("video")
                    if isinstance(video, dict):
                        video_url = video.get("url")

            if video_url:
                print(f"Video generated successfully on attempt {attempt}")
                return {"success": True, "video_url": video_url}
            else:
                raise Exception("No video URL in response")

        except Exception as e:
            error_str = str(e)
            last_error = error_str
            print(f"Attempt {attempt} failed: {error_str}")

            # Don't retry on balance/auth errors
            if "Exhausted balance" in error_str or "403" in error_str or "401" in error_str:
                return {
                    "success": False,
                    "error": "Account balance exhausted. Please add credits at fal.ai/dashboard/billing"
                }

            if attempt < MAX_RETRIES:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)

    return {"success": False, "error": f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}"}


# Text-to-video models, by length capability:
#   LTX 2.3 clean-plate - free-user default model for short, clean video output.
#   AnimateDiff         - frame count up to 32 @ 8fps (~4s); uses video_size, not aspect_ratio.
#   Kling t2v pro       - real duration control: "5" or "10" seconds.
LTX_MODEL = "fal-ai/ltx-video"
ANIMATEDIFF_MODEL = "fal-ai/fast-animatediff/text-to-video"
KLING_T2V_MODEL = "fal-ai/kling-video/v1/standard/text-to-video"

ANIMATEDIFF_STYLES = {"anime", "social"}

# Credit pricing. Premium Kling videos cost more than the cheaper AnimateDiff path.
KLING_VIDEO_COST = 10
CHEAP_VIDEO_COST = 5


def text_to_video_cost(style, extended=False, duration="5"):
    """Credits for a text-to-video generation.

    Duration-based premium pricing lets Pro users extend the clip beyond the
    default 5s base. The legacy `extended` boolean remains supported for older
    call sites; newer ones can pass `duration` directly.
    """
    duration = str(duration or "5")
    if duration not in {"5", "10", "15", "20"}:
        duration = "5"

    if style in ANIMATEDIFF_STYLES:
        if duration in {"10", "15", "20"}:
            return int(duration)
        return CHEAP_VIDEO_COST

    if duration in {"10", "15", "20"}:
        return int(duration)
    if extended:
        return KLING_VIDEO_COST
    return CHEAP_VIDEO_COST

# AnimateDiff takes a video_size enum instead of an aspect_ratio string.
ANIMATEDIFF_VIDEO_SIZE = {
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",
    "1:1": "square_hd",
}


def _build_t2v_request(prompt, style, aspect_ratio, extended, duration="5"):
    """Pick the text-to-video model + arguments for a given style/quality.

    The single source of truth shared by the website's async path
    (generate_video_async) and the bot's synchronous path (generate_video), so
    both produce identical videos:
      - anime/social  -> AnimateDiff (longer 32-frame clip when extended)
      - extended       -> premium Kling clip (cinematic/realistic/african)
      - otherwise      -> short LTX clip
    """
    duration = str(duration or "5")
    if duration not in {"5", "10", "15", "20"}:
        duration = "5"

    if style in ANIMATEDIFF_STYLES:
        model = ANIMATEDIFF_MODEL
    elif extended or duration in {"10", "15", "20"}:
        model = KLING_T2V_MODEL
    else:
        model = LTX_MODEL

    arguments = {"prompt": prompt}

    if model in (ANIMATEDIFF_MODEL, KLING_T2V_MODEL):
        arguments["aspect_ratio"] = aspect_ratio if aspect_ratio in ("16:9", "9:16", "1:1") else "16:9"
        arguments["duration"] = "10" if duration in {"10", "15", "20"} else "5"
    else:
        arguments["aspect_ratio"] = aspect_ratio if aspect_ratio in ("16:9", "9:16") else "16:9"

    return model, arguments


def generate_video_async(prompt, style="cinematic", aspect_ratio="16:9", webhook_url=None, extended=False, duration="5", request_id=None, original_prompt=None):
    model, arguments = _build_t2v_request(prompt, style, aspect_ratio, extended, duration=duration)
    prompt_text = prompt.strip() if isinstance(prompt, str) else ""
    if not prompt_text:
        print(f"FAL submission skipped request_id={request_id} status=invalid_prompt original_prompt={original_prompt!r} refined_prompt={prompt!r}")
        return {"success": False, "error": "The refined prompt was empty. Please try again."}

    arguments["prompt"] = prompt_text
    print(
        f"FAL submission request_id={request_id} status=attempting "
        f"original_prompt={original_prompt!r} refined_prompt={prompt_text!r} "
        f"model={model} arguments={arguments!r}"
    )
    try:
        # Submit exactly once. A timeout after acceptance is ambiguous and must
        # not trigger another potentially billable Fal job.
        handler = fal_client.submit(
            model,
            arguments=arguments,
            webhook_url=webhook_url
        )
        fal_request_id = getattr(handler, "request_id", None)
        print(
            f"FAL submission request_id={request_id} status=accepted "
            f"fal_request_id={fal_request_id}"
        )
        if not fal_request_id:
            return {"success": False, "error": "Fal accepted the request without returning a request ID."}
        return {"success": True, "request_id": fal_request_id}
    except Exception as e:
        error_str = str(e)
        print(
            f"FAL submission request_id={request_id} status=unknown_error "
            f"model={model} error={error_str}"
        )
        return {"success": False, "error": f"Fal submission failed or is unknown: {error_str}"}


def generate_video_from_image(image_url, prompt, duration="5", aspect_ratio="16:9"):
    # Kling expects duration as the string "5" or "10". Guard against anything else.
    duration = str(duration)
    if duration not in ("5", "10"):
        duration = "5"

    if aspect_ratio not in ("16:9", "9:16", "1:1"):
        aspect_ratio = "16:9"

    models = [
        "fal-ai/kling-video/v3/pro/image-to-video",
        "fal-ai/kling-video/v3/standard/image-to-video",
    ]

    for model in models:
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"Image-to-video attempt {attempt}/{MAX_RETRIES} - model: {model}")

                result = fal_client.subscribe(
                    model,
                    arguments={
                        "prompt": str(prompt),
                        "image_url": str(image_url),
                        "duration": duration,
                        "aspect_ratio": aspect_ratio
                    }
                )

                print("SUCCESS:", result)

                if result and "video" in result:
                    return result["video"]["url"]

                raise Exception("No video in response")

            except Exception as e:
                error_str = str(e)
                last_error = error_str
                print(f"{model} attempt {attempt} failed: {error_str}")

                if "Exhausted balance" in error_str or "403" in error_str or "401" in error_str:
                    print(f"Model unavailable for this request ({model}). Trying next fallback model.")
                    break

                elif "404" in error_str:
                    print(f"Skipping invalid model: {model}")
                    break

                if attempt < MAX_RETRIES:
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)

    if last_error:
        raise Exception(f"Image-to-video generation failed for all models. Last error: {last_error}")

    return None


def add_text_overlay(video_url, text):
    """Burn `text` onto the finished video as a bold, legible caption.

    The AI video models render text poorly, so we overlay it ourselves with a
    real ffmpeg drawtext pass (ffmpeg binary shipped by the imageio-ffmpeg pip
    package - no system install needed). The captioned file is re-uploaded to
    fal's CDN so it survives the host's ephemeral disk.

    Best-effort: on ANY problem (no text, download/ffmpeg/upload failure) the
    original `video_url` is returned unchanged, so a caption never costs us the
    video itself.
    """
    if not text or not text.strip():
        return video_url

    import textwrap

    # Keep captions short and wrapped so they stay readable on screen.
    wrapped = "\n".join(textwrap.wrap(text.strip()[:80], width=22)[:3])

    in_path = out_path = txt_path = None
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        # Download the source video.
        fd_in, in_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd_in)
        with requests.get(video_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(in_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)

        # drawtext reads the caption from a file (textfile=), which sidesteps
        # all the filter-string escaping headaches for arbitrary user text and
        # handles multi-line cleanly.
        fd_txt, txt_path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd_txt, "w", encoding="utf-8") as f:
            f.write(wrapped)

        fd_out, out_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd_out)

        # Forward slashes + single quotes keep paths valid inside the filtergraph
        # on both Windows (local) and Linux (Render).
        font = FONT_PATH.replace("\\", "/")
        txt = txt_path.replace("\\", "/")
        drawtext = (
            f"drawtext=fontfile='{font}':textfile='{txt}'"
            ":fontcolor=white:fontsize=h/14:line_spacing=8"
            ":box=1:boxcolor=black@0.5:boxborderw=20"
            ":borderw=3:bordercolor=black@0.9"
            ":x=(w-text_w)/2:y=h-text_h-(h*0.08)"
        )

        cmd = [
            ffmpeg_exe, "-y", "-i", in_path,
            "-vf", drawtext,
            "-codec:a", "copy",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-800:]
            lowered = stderr_tail.lower()
            if "drawtext" in lowered or "filter not found" in lowered or "no such filter" in lowered:
                print("DRAWTEXT FILTER UNAVAILABLE; skipping text overlay gracefully:", stderr_tail)
                return video_url
            print("DRAWTEXT FFMPEG ERROR:", stderr_tail)
            return video_url

        new_url = fal_client.upload_file(out_path)
        return new_url or video_url

    except Exception as e:
        print("TEXT OVERLAY ERROR:", str(e))
        return video_url
    finally:
        for p in (in_path, out_path, txt_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def merge_audio_into_video(video_url, audio_url):
    """Bake an audio track into a video via fal's hosted ffmpeg endpoint.

    Returns the merged video's CDN URL, or None on failure (caller falls back
    to the original silent video).
    """
    try:
        result = fal_client.subscribe(
            "fal-ai/ffmpeg-api/merge-audio-video",
            arguments={
                "video_url": video_url,
                "audio_url": audio_url,
            }
        )
        return result.get("video", {}).get("url")
    except Exception as e:
        print(f"MERGE ERROR: {e}")
        return None


def generate_image(prompt, style="realistic", aspect_ratio="1:1"):
    MODELS = {
        "realistic": "fal-ai/flux/dev",
        "anime": "fal-ai/flux/dev",
        "cinematic": "fal-ai/flux-pro/v1.1",
        "african": "fal-ai/flux/dev",
        "social": "fal-ai/flux/schnell"
    }

    model = MODELS.get(style, MODELS["realistic"])

    api_key = os.environ.get('FAL_KEY_ID')
    if not api_key:
        api_key = os.environ.get('FAL_API_KEY') or os.environ.get('FAL_KEY')

    if not api_key:
        print("ERROR: FAL_KEY_ID environment variable not set")
        return {
            "success": False,
            "error": "API key not configured. Please set FAL_KEY_ID environment variable."
        }

    size_map = {
        "1:1": "square_hd",
        "16:9": "landscape_4_3",
        "9:16": "portrait_4_3"
    }
    image_size = size_map.get(aspect_ratio, "square_hd")
    url = f"https://fal.run/{model}"
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "image_size": image_size,
        "num_inference_steps": 30,
        "guidance_scale": 7.5,
        "num_images": 1
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Image attempt {attempt}/{MAX_RETRIES} - sending request to {url}")
            response = requests.post(url, json=payload, headers=headers)
            print(f"Response status: {response.status_code}")

            if response.status_code == 401:
                return {"success": False, "error": "Invalid API key."}

            elif response.status_code == 403:
                return {"success": False, "error": "Account balance exhausted. Please add credits at fal.ai/dashboard/billing"}

            response.raise_for_status()
            result = response.json()
            print("API Response:", result)

            image_url = None
            if result.get('images'):
                image_url = result['images'][0].get('url')
            elif result.get('image', {}).get('url'):
                image_url = result['image']['url']

            if not image_url:
                raise Exception(f"No image URL in response: {result}")

            print(f"Image generated successfully on attempt {attempt}")
            return {"success": True, "image_url": image_url}

        except requests.exceptions.RequestException as e:
            last_error = str(e)
            print(f"HTTP ERROR on attempt {attempt}: {last_error}")
            if attempt < MAX_RETRIES:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)

        except Exception as e:
            last_error = str(e)
            print(f"ERROR on attempt {attempt}: {last_error}")
            if attempt < MAX_RETRIES:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)

    return {"success": False, "error": f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}"}