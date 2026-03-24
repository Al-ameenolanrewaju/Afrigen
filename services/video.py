import os
import fal_client
import requests

# Available video styles
MODELS = {
    "cinematic": {
        "model": "fal-ai/kling-video/v2.1/standard/text-to-video",
        "name": "Cinematic 🎬",
        "description": "Professional cinematic quality"
    },
    "anime": {
        "model": "fal-ai/animatediff-v2v",
        "name": "Anime 🎌",
        "description": "Japanese anime style"
    },
    "realistic": {
        "model": "fal-ai/luma-dream-machine",
        "name": "Realistic 🌍",
        "description": "Hyper realistic videos"
    },
    "african": {
        "model": "fal-ai/minimax-video",
        "name": "African 👑",
        "description": "Rich African aesthetic"
    },
    "social": {
        "model": "fal-ai/kling-video/v1.6/standard/text-to-video",
        "name": "Social Media 📱",
        "description": "Perfect for social media"
    }
}




def generate_with_fal(prompt, style="cinematic", aspect_ratio="16:9", duration="5"):
    os.environ["FAL_KEY"] = os.environ.get("FAL_API_KEY", "")
    MODELS = {
        "cinematic": "fal-ai/kling-video/v2.1/standard/text-to-video",
        "anime": "fal-ai/animatediff-v2v",
        "realistic": "fal-ai/luma-dream-machine",
        "african": "fal-ai/minimax-video",
        "social": "fal-ai/kling-video/v1.6/standard/text-to-video"
    }
    model = MODELS.get(style, MODELS["cinematic"])
    result = fal_client.subscribe(
        model,
        arguments={
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio
        }
    )
    return result["video"]["url"]


def generate_with_replicate(prompt):
    """Try Replicate as fallback"""
    import replicate
    os.environ["REPLICATE_API_TOKEN"] = os.environ.get("REPLICATE_API_KEY", "")

    output = replicate.run(
        "anotherjesse/zeroscope-v2-xl:9f747673945c62801b13b84701c783929c0ee784e4748ec062204894dda1a351",
        input={"prompt": prompt}
    )
    return output[0] if output else None


def generate_with_huggingface(prompt):
    """Try HuggingFace as fallback"""
    API_URL = "https://api-inference.huggingface.co/models/damo-vilab/text-to-video-ms-1.7b"
    headers = {"Authorization": f"Bearer {os.environ.get('HUGGINGFACE_API_KEY')}"}

    response = requests.post(
        API_URL,
        headers=headers,
        json={"inputs": prompt}
    )

    if response.status_code == 200:
        # Save video file
        filename = f"video_{os.urandom(8).hex()}.mp4"
        filepath = os.path.join("static", "videos", filename)
        os.makedirs(os.path.join("static", "videos"), exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(response.content)

        return f"/static/videos/{filename}"
    return None


def generate_with_kie(prompt, style="cinematic"):
    """Try Kie.ai"""
    headers = {
        "Authorization": f"Bearer {os.environ.get('KIE_API_KEY')}",
        "Content-Type": "application/json"
    }

    # Try different model names
    models_to_try = [
        "veo3",
        "veo-3",
        "google-veo-3",
        "veo",
        "sora",
        "sora-2"
    ]

    for model in models_to_try:
        response = requests.post(
            "https://api.kie.ai/api/v1/veo/generate",
            headers=headers,
            json={
                "prompt": prompt,
                "model": model,
                "duration": 5,
                "aspect_ratio": "16:9"
            }
        )

        print(f"Kie.ai model {model}: {response.status_code} - {response.text[:100]}")

        if response.status_code == 200:
            data = response.json()
            if data.get("code") != 422:
                return data.get("video_url") or data.get("url") or data.get("data", {}).get("url")

    return None


def generate_with_hypereal(prompt, style="cinematic"):
    """Try Hypereal AI"""
    headers = {
        "Authorization": f"Bearer {os.environ.get('HYPEREAL_API_KEY')}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.hypereal.tech/v1/videos/generate",
        headers=headers,
        json={
            "model": "wan-2-6-t2v",
            "input": {
                "prompt": prompt,
                "duration": 5,
                "aspect_ratio": "16:9"
            }
        }
    )

    print(f"Hypereal response: {response.status_code} - {response.text[:200]}")

    if response.status_code == 200:
        data = response.json()
        return (data.get("video_url") or
                data.get("url") or
                data.get("output", {}).get("url") or
                data.get("data", {}).get("url"))
    return None


def generate_with_json2video(prompt):
    """Try JSON2Video"""
    headers = {
        "x-api-key": os.environ.get("JSON2VIDEO_API_KEY"),
        "Content-Type": "application/json"
    }

    # Create project
    response = requests.post(
        "https://api.json2video.com/v2/movies",
        headers=headers,
        json={
            "resolution": "full-hd",
            "quality": "high",
            "scenes": [{
                "comment": prompt,
                "elements": [{
                    "type": "text",
                    "text": prompt,
                    "duration": 5
                }]
            }]
        }
    )

    if response.status_code == 200:
        data = response.json()
        project_id = data.get("project")

        if project_id:
            # Poll for video URL
            import time
            for i in range(10):  # try 10 times
                time.sleep(5)  # wait 5 seconds each time

                status_response = requests.get(
                    f"https://api.json2video.com/v2/movies?project={project_id}",
                    headers=headers
                )

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"JSON2Video status: {status_data}")

                    movie = status_data.get("movie", {})
                    if movie.get("status") == "done":
                        return movie.get("url")

    return None

def generate_image_huggingface(prompt):
    """Generate image using HuggingFace FLUX - FREE!"""
    models = [
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-xl-base-1.0",
        "runwayml/stable-diffusion-v1-5"
    ]

    headers = {
        "Authorization": f"Bearer {os.environ.get('HUGGINGFACE_API_KEY')}"
    }

    for model in models:
        try:
            print(f"Trying HuggingFace image model: {model}")
            response = requests.post(
                f"https://router.huggingface.co/hf-inference/models/{model}",
                headers=headers,
                json={"inputs": prompt},
                timeout=60
            )

            if response.status_code == 200:
                filename = f"image_{os.urandom(8).hex()}.jpg"
                filepath = os.path.join("static", "images", filename)
                os.makedirs(os.path.join("static", "images"), exist_ok=True)

                with open(filepath, "wb") as f:
                    f.write(response.content)

                print(f"Image saved: {filename}")
                return f"/static/images/{filename}"
            else:
                print(f"Model {model} failed: {response.status_code}")

        except Exception as e:
            print(f"Error with {model}: {e}")
            continue

    return None


def generate_image_hypereal(prompt):
    """Generate image using Hypereal AI"""
    import time

    headers = {
        "Authorization": f"Bearer {os.environ.get('HYPEREAL_API_KEY')}",
        "Content-Type": "application/json"
    }

    # Submit job
    response = requests.post(
        "https://api.hypereal.tech/api/v1/spicy-image",
        headers=headers,
        json={
            "model": "flux-2",
            "input": {"prompt": prompt}
        }
    )

    print(f"Hypereal submit: {response.status_code} - {response.text[:200]}")

    if response.status_code == 200:
        data = response.json()
        job_id = data.get("jobId")

        if job_id:
            # Poll for result
            for i in range(20):
                time.sleep(5)

                status_response = requests.get(
                    f"https://api.hypereal.tech/api/v1/job/{job_id}",
                    headers=headers
                )

                print(f"Hypereal poll {i}: {status_response.text[:200]}")

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    image_url = (status_data.get("output") or
                                 status_data.get("image_url") or
                                 status_data.get("url"))

                    if image_url:
                        # Download and save
                        img_response = requests.get(image_url)
                        if img_response.status_code == 200:
                            filename = f"image_{os.urandom(8).hex()}.jpg"
                            filepath = os.path.join("static", "images", filename)
                            os.makedirs(os.path.join("static", "images"), exist_ok=True)
                            with open(filepath, "wb") as f:
                                f.write(img_response.content)
                            return f"/static/images/{filename}"
    return None


def generate_image(prompt):
    """Generate image with fallback"""

    # Try Hypereal first
    try:
        print("Trying Hypereal image...")
        result = generate_image_hypereal(prompt)
        if result:
            return result
    except Exception as e:
        print(f"Hypereal image failed: {e}")

    # Fallback to HuggingFace
    try:
        print("Trying HuggingFace image...")
        return generate_image_huggingface(prompt)
    except Exception as e:
        print(f"HuggingFace image failed: {e}")

    return None

def generate_video(prompt, style="cinematic", aspect_ratio="16:9", duration="5"):
    """Try all APIs with fallback"""

    # Try fal.ai first (best quality)
    try:
        print("Trying fal.ai...")
        return generate_with_fal(prompt, style, aspect_ratio, duration)
    except Exception as e:
        print(f"fal.ai failed: {e}")

    # Try Kie.ai
    try:
        print("Trying Kie.ai...")
        result = generate_with_kie(prompt, style)
        if result:
            return result
    except Exception as e:
        print(f"Kie.ai failed: {e}")


    # Try JSON2Video
    try:
        print("Trying JSON2Video...")
        result = generate_with_json2video(prompt)
        if result:
            return result
    except Exception as e:
        print(f"JSON2Video failed: {e}")

    # Try Replicate
    try:
        print("Trying Replicate...")
        return generate_with_replicate(prompt)
    except Exception as e:
        print(f"Replicate failed: {e}")

    # Try HuggingFace (last resort - free but slow)
    try:
        print("Trying HuggingFace...")
        return generate_with_huggingface(prompt)
    except Exception as e:
        print(f"HuggingFace failed: {e}")

    print("All APIs failed!")
    return None


def generate_video_from_image(image_url, prompt, style="cinematic"):
    """Generate video from image using fal.ai"""
    os.environ["FAL_KEY"] = os.environ.get("FAL_API_KEY", "")

    try:
        print("Trying image to video with fal.ai...")
        result = fal_client.subscribe(
            "fal-ai/kling-video/v1.6/pro/image-to-video",
            arguments={
                "prompt": prompt,
                "image_url": image_url,
                "duration": "5",
                "aspect_ratio": "16:9"
            }
        )
        return result["video"]["url"]
    except Exception as e:
        print(f"Image to video failed: {e}")
        return None