import os
import re
import logging
from typing import Callable, Tuple, Any

import logging

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

# We use ProviderManager for LLM generation to benefit from health tracking and fallback.
from flask import current_app
from app import app
from services.provider_manager import provider_manager

# Model parameter is kept for signature compatibility, but ProviderManager dictates the model via task_type.
def generate_with_llm(system: str, user: str, max_tokens: int = 2000, json_mode: bool = False, model: str = None) -> str:
    """Generate text via ProviderManager. Returns stripped text content."""
    kwargs = {
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
        
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    def do_generate():
        return provider_manager.generate_text("AI Assistant", messages, **kwargs).strip()

    # If running standalone outside a Flask request, we need an app context for DB logging
    if not current_app:
        with app.app_context():
            return do_generate()
    return do_generate()

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
