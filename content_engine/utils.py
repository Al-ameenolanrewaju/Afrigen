import os
import re
import logging
from typing import Callable, Tuple, Any
from groq import Groq

# Same Groq client configuration as scripts/generate_content.py
MODEL = os.environ.get("BLOG_MODEL", "llama-3.3-70b-versatile")
_client = None

def get_logger(name: str) -> logging.Logger:
    """Get a standard logger for the Content Engine."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(name)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger

def _groq():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client

def generate_with_llm(system: str, user: str, max_tokens: int = 2000, json_mode: bool = False, model: str = MODEL) -> str:
    """Single Groq chat call. Returns stripped text content."""
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
        
    resp = _groq().chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()

def strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap output in."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    return text

def generate_with_validation(
    system: str, 
    user: str, 
    validator_fn: Callable[..., Tuple[bool, str]],
    validator_args: tuple = (),
    max_tokens: int = 2000, 
    max_attempts: int = 2,
    logger: logging.Logger = None,
    json_mode: bool = False
) -> str:
    """Generate content using LLM with an enforced validation pipeline.
    If validation fails, it regenerates up to max_attempts.
    """
    logger = logger or get_logger("ContentEngine")
    
    attempts = 0
    content = ""
    while attempts < max_attempts:
        attempts += 1
        prompt_suffix = "\n\nNote: Previous attempt failed validation. Please adhere strictly to the rules." if attempts > 1 else ""
        
        try:
            content = generate_with_llm(
                system=system,
                user=user + prompt_suffix,
                max_tokens=max_tokens,
                json_mode=json_mode
            )
            content = strip_fences(content)
        except Exception as e:
            logger.warning(f"API Error (attempt {attempts}): {e}")
            continue
        
        is_valid, reason = validator_fn(content, *validator_args)
        if is_valid:
            return content
        logger.warning(f"Validation failed (attempt {attempts}): {reason}")
    
    logger.error("All validation attempts failed. Returning last generated content.")
    return content
