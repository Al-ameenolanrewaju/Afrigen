import os
import time
import warnings
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from flask import current_app
from models import db, ProviderHealth, ProviderLog

class ProviderAdapter(ABC):
    def __init__(self):
        self.name = self.__class__.__name__.replace("Adapter", "")
        self.is_enabled = True

    @abstractmethod
    def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass


class GroqAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__()
        api_key = os.environ.get('GROQ_API_KEY')
        if not api_key:
            self.is_enabled = False
        else:
            from groq import Groq
            self.client = Groq(api_key=api_key)
            self.default_model = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')

    def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        model = kwargs.get('model', self.default_model)
        max_tokens = kwargs.get('max_tokens')
        temperature = kwargs.get('temperature', 0.7)
        
        args = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        if max_tokens:
            args["max_tokens"] = max_tokens
        if kwargs.get('response_format'):
            args["response_format"] = kwargs['response_format']
            
        response = self.client.chat.completions.create(**args)
        return response.choices[0].message.content


class OpenRouterAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__()
        api_key = os.environ.get('OPENROUTER_API_KEY')
        if not api_key:
            self.is_enabled = False
        else:
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key
            )
            self.default_model = os.environ.get('OPENROUTER_MODEL', 'meta-llama/llama-3.3-70b-instruct:free')

    def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        model = kwargs.get('model', self.default_model)
        max_tokens = kwargs.get('max_tokens')
        temperature = kwargs.get('temperature', 0.7)
        
        args = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        if max_tokens:
            args["max_tokens"] = max_tokens
        if kwargs.get('response_format'):
            args["response_format"] = kwargs['response_format']
            
        response = self.client.chat.completions.create(**args)
        return response.choices[0].message.content


class GeminiAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__()
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            self.is_enabled = False
        else:
            self.default_model = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
            self._use_new_sdk = False
            self._client = None
            self._types = None
            self._genai_module = None

            try:
                from google import genai as google_genai
                self._client = google_genai.Client(api_key=api_key)
                self._types = google_genai.types
                self._use_new_sdk = True
            except Exception:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", FutureWarning)
                    import google.generativeai as genai
                if hasattr(genai, "configure"):
                    genai.configure(api_key=api_key)
                    self._genai_module = genai
                else:
                    self.is_enabled = False

    def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        if self._use_new_sdk:
            system_instruction = None
            prompt_parts = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    prompt_parts.append(f"User: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"Assistant: {content}")

            prompt_text = "\n".join(prompt_parts)
            model_name = kwargs.get('model', self.default_model)
            config_kwargs = {
                "temperature": kwargs.get('temperature', 0.7),
            }
            if kwargs.get('max_tokens'):
                config_kwargs["max_output_tokens"] = kwargs.get('max_tokens')
            if kwargs.get('response_format') and kwargs['response_format'].get('type') == 'json_object':
                config_kwargs["response_mime_type"] = "application/json"
            if system_instruction is not None:
                config_kwargs["system_instruction"] = system_instruction

            response = self._client.models.generate_content(
                model=model_name,
                contents=prompt_text,
                config=self._types.GenerateContentConfig(**config_kwargs),
            )
            return getattr(response, "text", str(response))

        if self._genai_module is not None:
            genai = self._genai_module
        else:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
                import google.generativeai as genai

        # Convert standard OpenAI messages to Gemini format
        system_instruction = None
        gemini_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                system_instruction = content
            elif role == "user":
                gemini_messages.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_messages.append({"role": "model", "parts": [content]})

        model_name = kwargs.get('model', self.default_model)

        generation_config = genai.types.GenerationConfig(
            temperature=kwargs.get('temperature', 0.7)
        )
        if kwargs.get('max_tokens'):
            generation_config.max_output_tokens = kwargs.get('max_tokens')

        if kwargs.get('response_format') and kwargs['response_format'].get('type') == 'json_object':
            generation_config.response_mime_type = "application/json"

        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )

        response = model.generate_content(
            gemini_messages,
            generation_config=generation_config
        )
        return response.text


class ProviderManager:
    def __init__(self):
        self.adapters = {
            "Groq": GroqAdapter(),
            "Gemini": GeminiAdapter(),
            "OpenRouter": OpenRouterAdapter()
        }
        
        self.task_mappings = {
            "Prompt Refinement": "Groq",
            "AI Assistant": "Groq",
            "Quick Chat": "Groq",
            "Blog Writing": "Gemini",
            "Newsletter": "Gemini",
            "Long-form Writing": "OpenRouter",
            "Campaign": "Groq",
            "Audio Script": "Groq",
            "Default": "Groq"
        }
        
        # Define fallback chain
        self.fallback_chain = ["Groq", "Gemini", "OpenRouter"]

    def _get_health(self, provider_name: str) -> ProviderHealth:
        health = ProviderHealth.query.filter_by(provider=provider_name).first()
        if not health:
            health = ProviderHealth(provider=provider_name, status="healthy")
            db.session.add(health)
            db.session.commit()
        return health
        
    def _update_health(self, provider_name: str, success: bool, latency: float, error_msg: str = None):
        health = self._get_health(provider_name)
        if success:
            health.success_count += 1
            if health.status in ("offline", "degraded"):
                health.status = "healthy"
            health.last_error = None
        else:
            health.failure_count += 1
            health.status = "degraded"
            if health.failure_count > health.success_count and (health.success_count + health.failure_count) > 5:
                health.status = "offline"
            health.last_error = error_msg
        health.avg_latency_ms = int((health.avg_latency_ms + (latency * 1000)) / 2) if health.avg_latency_ms else int(latency * 1000)
        db.session.commit()

    def _log_request(self, task_type, provider_name, latency, fallback_triggered, success, error_msg=None):
        log = ProviderLog(
            task_type=task_type,
            provider_used=provider_name,
            fallback_triggered=fallback_triggered,
            latency=latency,
            status="success" if success else "error",
            error_message=error_msg
        )
        db.session.add(log)
        db.session.commit()

    def generate_text(self, task_type: str, messages: List[Dict[str, str]], **kwargs) -> str:
        # Determine preferred provider
        primary_provider_name = self.task_mappings.get(task_type, self.task_mappings["Default"])
        
        # Build attempt sequence starting with primary, then falling back based on chain
        attempt_sequence = [primary_provider_name]
        for p in self.fallback_chain:
            if p not in attempt_sequence:
                attempt_sequence.append(p)
                
        last_error = None
        fallback_triggered = False
        
        for provider_name in attempt_sequence:
            adapter = self.adapters.get(provider_name)
            if not adapter or not adapter.is_enabled:
                continue
                
            # Check health
            health = self._get_health(provider_name)
            if health.status == "offline":
                continue # Skip dead providers
                
            start_time = time.time()
            try:
                # Attempt generation
                result = adapter.generate(messages, **kwargs)
                latency = time.time() - start_time
                
                self._update_health(provider_name, success=True, latency=latency)
                self._log_request(task_type, provider_name, latency, fallback_triggered, success=True)
                
                return result
            except Exception as e:
                latency = time.time() - start_time
                error_msg = str(e)
                self._update_health(provider_name, success=False, latency=latency, error_msg=error_msg)
                self._log_request(task_type, provider_name, latency, fallback_triggered, success=False, error_msg=error_msg)
                
                last_error = error_msg
                fallback_triggered = True
                print(f"[ProviderManager] {provider_name} failed: {error_msg}. Falling back...")
                
        # If all providers fail
        raise Exception(f"All AI providers failed. Last error: {last_error}")

provider_manager = ProviderManager()
