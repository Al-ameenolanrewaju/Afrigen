"""Admin-only health and account status checks for media providers."""
import os
from typing import Any, Dict

import requests


def _fal_token() -> str:
    return (
        os.environ.get("FAL_KEY_ID")
        or os.environ.get("FAL_API_KEY")
        or os.environ.get("FAL_KEY")
        or ""
    )


def _huggingface_token() -> str:
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_API_KEY")
        or os.environ.get("HUGGINGFACE_TOKEN")
        or ""
    )


def _error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("error") or payload.get("message") or response.text[:240])
    except ValueError:
        return response.text[:240] or f"HTTP {response.status_code}"


def get_provider_status() -> Dict[str, Dict[str, Any]]:
    """Return safe, non-secret provider status data for the admin dashboard."""
    fal_token = _fal_token()
    fal = {
        "name": "FAL",
        "status": "not_configured" if not fal_token else "offline",
        "detail": "FAL key is not configured." if not fal_token else "Checking FAL API...",
        "credits": None,
        "credits_detail": "Set FAL_CREDITS_URL to display the current balance.",
        "dashboard_url": "https://fal.ai/dashboard/billing",
    }
    if fal_token:
        try:
            response = requests.get(
                "https://api.fal.ai/v1/models",
                headers={"Authorization": f"Key {fal_token}"},
                timeout=8,
            )
            if response.ok:
                fal["status"] = "healthy"
                fal["detail"] = "FAL API key accepted; model catalog reachable."
            else:
                fal["detail"] = _error_message(response)
        except requests.RequestException as exc:
            fal["detail"] = str(exc)[:240]

        credits_url = os.environ.get("FAL_CREDITS_URL")
        if credits_url:
            try:
                response = requests.get(
                    credits_url,
                    headers={"Authorization": f"Key {fal_token}"},
                    timeout=8,
                )
                if response.ok:
                    payload = response.json()
                    fal["credits"] = (
                        payload.get("credits")
                        or payload.get("balance")
                        or payload.get("remaining")
                    )
                    fal["credits_detail"] = "Balance retrieved from FAL_CREDITS_URL."
                else:
                    fal["credits_detail"] = _error_message(response)
            except (requests.RequestException, ValueError) as exc:
                fal["credits_detail"] = str(exc)[:240]

    hf_token = _huggingface_token()
    hf_model = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    hf = {
        "name": "Hugging Face",
        "status": "not_configured" if not hf_token else "offline",
        "detail": "HF_TOKEN is not configured." if not hf_token else "Checking model access...",
        "model": hf_model,
    }
    if hf_token:
        try:
            response = requests.get(
                f"https://huggingface.co/api/models/{hf_model}",
                headers={"Authorization": f"Bearer {hf_token}"},
                timeout=8,
            )
            if response.ok:
                hf["status"] = "healthy"
                hf["detail"] = "Token accepted; configured image model is reachable."
            else:
                hf["detail"] = _error_message(response)
        except requests.RequestException as exc:
            hf["detail"] = str(exc)[:240]

    return {"fal": fal, "huggingface": hf}
