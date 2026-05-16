import fal_client


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

    try:

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

        return {
            "success": True,
            "video_url": video_url
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }


def generate_video_from_image(image_url, prompt):
    import os
    import fal_client

    os.environ["FAL_KEY"] = os.environ.get("FAL_API_KEY", "")

    models = [
        "fal-ai/kling-video/v1.6/pro/image-to-video",
        "fal-ai/ltx-video-v095/image-to-video",
    ]

    for model in models:
        try:
            print(f"Trying image-to-video: {model}")

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

        except Exception as e:
            print(f"{model} failed: {e}")

            # Better user-friendly errors
            if "Exhausted balance" in str(e):
                raise Exception(
                    "Video generation service balance exhausted."
                )

            elif "403" in str(e):
                raise Exception(
                    "Access denied by video provider."
                )

            elif "404" in str(e):
                print(f"Skipping invalid model: {model}")

            continue

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

    try:

        result = fal_client.subscribe(
            model,
            arguments={
                "prompt": prompt
            }
        )

        image_url = None

        if isinstance(result, dict):

            if result.get("images"):

                images = result.get("images")

                if isinstance(images, list) and len(images) > 0:

                    first = images[0]

                    if isinstance(first, dict):
                        image_url = first.get("url")

        return {
            "success": True,
            "image_url": image_url
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }