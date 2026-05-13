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


def generate_video_from_image(
    image_url,
    prompt,
    style="cinematic",
    aspect_ratio="16:9"
):

    MODELS = {
        "cinematic": "fal-ai/ltx-video-v095/image-to-video",
        "realistic": "fal-ai/kling-video/v2.1/image-to-video",
        "social": "fal-ai/kling-video/v1.6/image-to-video"
    }

    model = MODELS.get(style, MODELS["cinematic"])

    try:

        result = fal_client.subscribe(
            model,
            arguments={
                "prompt": prompt,
                "image_url": image_url,
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