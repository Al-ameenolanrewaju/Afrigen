import os
from fal_client import fal_client


def generate_with_fal(
    prompt,
    style="cinematic",
    aspect_ratio="16:9"
):
    """
    Generate video using fal.ai text-to-video models
    """

    MODELS = {
        "cinematic": "fal-ai/ltx-video-v095/text-to-video",
        "anime": "fal-ai/fast-animatediff/text-to-video",
        "realistic": "fal-ai/kling-video/v2.1/standard/text-to-video",
        "african": "fal-ai/minimax-video",
        "social": "fal-ai/kling-video/v1.6/standard/text-to-video"
    }

    # Pick model
    model = MODELS.get(style, MODELS["cinematic"])

    print("\n==========================")
    print("STARTING VIDEO GENERATION")
    print("==========================")
    print("MODEL:", model)
    print("PROMPT:", prompt)
    print("ASPECT RATIO:", aspect_ratio)

    try:

        # Generate final video directly
        result = fal_client.run(
            model,
            arguments={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio
            }
        )

        print("\n==========================")
        print("RAW FAL RESPONSE")
        print("==========================")
        print(result)

        video_url = None

        # Structure 1
        try:
            if result.get("video"):
                video_url = result["video"]["url"]
        except Exception:
            pass

        # Structure 2
        if not video_url:
            try:
                if result.get("data"):
                    if result["data"].get("video"):
                        video_url = result["data"]["video"]["url"]
            except Exception:
                pass

        # Structure 3
        if not video_url:
            try:
                outputs = result.get("outputs")

                if outputs and isinstance(outputs, list):
                    first = outputs[0]

                    if isinstance(first, dict):
                        video_url = first.get("url")
            except Exception:
                pass

        # Final validation
        if not video_url:
            raise Exception(
                f"Could not extract video URL from response: {result}"
            )

        print("\n==========================")
        print("VIDEO GENERATED SUCCESSFULLY")
        print("==========================")
        print("VIDEO URL:", video_url)

        return {
            "success": True,
            "video_url": video_url
        }

    except Exception as e:

        print("\n==========================")
        print("VIDEO GENERATION FAILED")
        print("==========================")
        print(str(e))

        return {
            "success": False,
            "error": str(e)
        }