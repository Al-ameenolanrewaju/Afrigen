import os
import time
import requests
import fal_client

os.environ["FAL_KEY"] = os.environ.get("FAL_KEY", "")

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries


def generate_video(
    prompt,
    style="cinematic",
    aspect_ratio="16:9"
):
    MODELS = {
        "cinematic": "fal-ai/ltx-video-v095/text-to-video",
        "anime": "fal-ai/fast-animatediff/text-to-video",
        "realistic": "fal-ai/kling-video/v2.1/standard/text-to-video",
        "african": "fal-ai/minimax-video",
        "social": "fal-ai/kling-video/v1.6/standard/text-to-video"
    }

    model = MODELS.get(style, MODELS["cinematic"])
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Video attempt {attempt}/{MAX_RETRIES} - model: {model}")
            print("FAL KEY LOADED:", os.getenv("FAL_KEY")[:12])

            result = fal_client.subscribe(
                model,
                arguments={
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio
                }
            )

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


def generate_video_from_image(image_url, prompt):
    models = [
        "fal-ai/kling-video/v1.6/pro/image-to-video",
        "fal-ai/ltx-video-v095/image-to-video",
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
                        "duration": 5,
                        "aspect_ratio": "16:9"
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

                if "Exhausted balance" in error_str:
                    raise Exception("Video generation service balance exhausted.")

                elif "403" in error_str:
                    raise Exception("Access denied by video provider.")

                elif "404" in error_str:
                    print(f"Skipping invalid model: {model}")
                    break  # skip to next model

                if attempt < MAX_RETRIES:
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)

    return None


def generate_image(
        prompt,
        style="realistic",
        aspect_ratio="1:1"
):
    MODELS = {
        "realistic": "fal-ai/flux/dev",
        "anime": "fal-ai/anime-image-generator",
        "cinematic": "fal-ai/flux-pro/v1.1",
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