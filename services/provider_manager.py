import os
import time
import warnings
import re
import json
from datetime import datetime, timezone, timedelta
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from flask import current_app
from models import db, ProviderHealth, ProviderLog


class ProviderAdapter(ABC):
    def __init__(self):
        self.name = self.__class__.__name__.replace("Adapter", "")

    @property
    def is_enabled(self):
        return True

    @abstractmethod
    def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass


class GroqAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__()
        self._client = None
        self._available_model = None

    @property
    def is_enabled(self):
        return bool(os.environ.get('GROQ_API_KEY'))

    def _get_client(self, api_key=None):
        if api_key:
            from groq import Groq
            return Groq(api_key=api_key)
        if not self._client:
            from groq import Groq
            self._client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
        return self._client

    def _get_model(self, client=None, use_cache=True):
        configured_model = os.environ.get('GROQ_MODEL')
        if configured_model:
            return configured_model
        if use_cache and self._available_model:
            return self._available_model

        preferred_models = (
            'openai/gpt-oss-20b',
            'llama-3.3-70b-versatile',
            'llama-3.1-8b-instant',
        )
        models = (client or self._get_client()).models.list().data
        available = {model.id for model in models}
        selected_model = next(
            (model for model in preferred_models if model in available),
            next(iter(available), None),
        )
        if not selected_model:
            raise RuntimeError('Groq returned no available chat models')
        if use_cache:
            self._available_model = selected_model
        return selected_model

    def generate(self, messages: List[Dict[str, str]], api_key=None, **kwargs) -> str:
        client = self._get_client(api_key)
        model = kwargs.get('model') or self._get_model(
            client,
            use_cache=not bool(api_key),
        )
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

        response = client.chat.completions.create(**args)
        choice = response.choices[0]
        content = choice.message.content or ""

        # If response was truncated but generated valid text, use what was produced
        if choice.finish_reason == 'length':
            if len(content.strip()) > 20:
                return content.strip()
            raise Exception("AI response was truncated due to max_tokens limit.")
        return content


class OpenRouterAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__()
        self._client = None

    @property
    def is_enabled(self):
        return bool(os.environ.get('OPENROUTER_API_KEY'))

    def _get_client(self):
        if not self._client:
            from openai import OpenAI
            self._client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ.get('OPENROUTER_API_KEY')
            )
        return self._client

    def generate(self, messages: List[Dict[str, str]], **kwargs) -> str:
        model = kwargs.get('model', os.environ.get('OPENROUTER_MODEL', 'meta-llama/llama-3.1-8b-instruct:free'))
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

        response = self._get_client().chat.completions.create(**args)
        choice = response.choices[0]
        content = choice.message.content or ""

        if choice.finish_reason == 'length':
            if len(content.strip()) > 20:
                return content.strip()
            raise Exception("AI response was truncated due to max_tokens limit.")
        return content


class OpenAIAdapter(ProviderAdapter):
    @property
    def is_enabled(self):
        # OpenAI is enabled per call only when a user supplies a key.
        return True

    def generate(self, messages: List[Dict[str, str]], api_key=None, **kwargs) -> str:
        if not api_key:
            raise ValueError("OpenAIAdapter requires a user-supplied API key")

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=kwargs.get('model', 'gpt-4o-mini'),
            messages=messages,
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=kwargs.get('max_tokens'),
        )
        return response.choices[0].message.content or ""


class AnthropicAdapter(ProviderAdapter):
    @property
    def is_enabled(self):
        # Anthropic is enabled per call only when a user supplies a key.
        return True

    def generate(self, messages: List[Dict[str, str]], api_key=None, **kwargs) -> str:
        if not api_key:
            raise ValueError("AnthropicAdapter requires a user-supplied API key")

        from anthropic import Anthropic

        system_messages = [
            message["content"]
            for message in messages
            if message.get("role") == "system"
        ]
        chat_messages = [
            message
            for message in messages
            if message.get("role") != "system"
        ]

        client = Anthropic(api_key=api_key)
        request_args = {
            "model": kwargs.get('model', 'claude-sonnet-4-5'),
            "max_tokens": kwargs.get('max_tokens', 1024),
            "messages": chat_messages,
        }
        if system_messages:
            request_args["system"] = "\n\n".join(system_messages)

        response = client.messages.create(**request_args)
        return response.content[0].text if response.content else ""


class GeminiAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__()
        self._use_new_sdk = False
        self._client = None
        self._types = None
        self._genai_module = None
        self._initialized = False

    @property
    def is_enabled(self):
        return bool(os.environ.get('GEMINI_API_KEY'))

    def _initialize(self):
        if self._initialized:
            return

        api_key = os.environ.get('GEMINI_API_KEY')
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
        self._initialized = True

    def generate(self, messages: List[Dict[str, str]], api_key=None, **kwargs) -> str:
        if api_key:
            from google import genai as google_genai
            client = google_genai.Client(api_key=api_key)
            types = google_genai.types
            use_new_sdk = True
        else:
            self._initialize()
            client = self._client
            types = self._types
            use_new_sdk = self._use_new_sdk

        if use_new_sdk:
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
            model_name = kwargs.get('model', os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash'))
            config_kwargs = {
                "temperature": kwargs.get('temperature', 0.7),
            }
            if kwargs.get('max_tokens'):
                config_kwargs["max_output_tokens"] = kwargs.get('max_tokens')
            if kwargs.get('response_format') and kwargs['response_format'].get('type') == 'json_object':
                config_kwargs["response_mime_type"] = "application/json"
            if system_instruction is not None:
                config_kwargs["system_instruction"] = system_instruction

            response = client.models.generate_content(
                model=model_name,
                contents=prompt_text,
                config=types.GenerateContentConfig(**config_kwargs),
            )

            try:
                res_text = response.text
            except (ValueError, AttributeError) as exc:
                raise RuntimeError("Gemini blocked or returned no usable content") from exc
            if hasattr(response, "candidates") and response.candidates:
                finish_reason = getattr(response.candidates[0].finish_reason, "name", "") or response.candidates[
                    0].finish_reason
                if finish_reason in ("MAX_TOKENS", 2):
                    if len(res_text.strip()) > 20:
                        return res_text.strip()
                    raise Exception("AI response was truncated due to max_tokens limit.")

            return res_text

        if self._genai_module is not None:
            genai = self._genai_module
        else:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
                import google.generativeai as genai

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

        model_name = kwargs.get('model', os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash'))

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

        try:
            res_text = response.text
        except (ValueError, AttributeError) as exc:
            raise RuntimeError("Gemini blocked or returned no usable content") from exc
        if response.candidates and hasattr(response.candidates[0], "finish_reason"):
            reason = response.candidates[0].finish_reason
            finish_reason = getattr(reason, "name", "") or reason
            if finish_reason in ("MAX_TOKENS", 2):
                if len(res_text.strip()) > 20:
                    return res_text.strip()
                raise Exception("AI response was truncated due to max_tokens limit.")

        return res_text


class ProviderManager:
    def __init__(self):
        self.adapters = {
            "Groq": GroqAdapter(),
            "Gemini": GeminiAdapter(),
            "OpenRouter": OpenRouterAdapter(),
            "OpenAI": OpenAIAdapter(),
            "Anthropic": AnthropicAdapter(),
        }

        self.task_mappings = {
            "Prompt Refinement": "Groq",
            "AI Assistant": "Groq",
            "Quick Chat": "Groq",
            "Blog Writing": "Groq",
            "Newsletter": "Groq",
            "Long-form Writing": "Groq",
            "Campaign": "Groq",
            "Audio Script": "Groq",
            "Default": "Groq"
        }

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
        previous_status = health.status
        if success:
            health.success_count += 1
            if health.status in ("offline", "degraded"):
                health.status = "healthy"
            health.last_error = None
        else:
            health.failure_count += 1
            if error_msg and "max_tokens" not in error_msg.lower():
                health.status = "degraded"
                if health.failure_count > health.success_count and (health.success_count + health.failure_count) > 5:
                    health.status = "offline"
            health.last_error = error_msg
            health.last_error_at = datetime.now(timezone.utc)
        health.avg_latency_ms = int((health.avg_latency_ms + (latency * 1000)) / 2) if health.avg_latency_ms else int(
            latency * 1000)
        try:
            from services.alerts import alert_once, clear_alert
            alert_type = f"provider:{provider_name}"
            if health.status == "offline":
                alert_once(
                    alert_type,
                    f"AI provider offline: {provider_name}",
                    health.last_error or "Provider transitioned to offline.",
                )
            elif previous_status == "offline":
                clear_alert(alert_type)
        except Exception as exc:
            print(f"Provider alert error: {exc}")
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

    def generate_text(
        self,
        task_type: str,
        messages: List[Dict[str, str]],
        user=None,
        **kwargs
    ) -> str:
        # Enforce token thresholds only for unspecified calls
        # Respect explicit max_tokens from caller (e.g., image prompt refinement uses 500)
        if "max_tokens" not in kwargs or kwargs["max_tokens"] == 0:
            if task_type in ["Prompt Refinement", "AI Assistant"]:
                kwargs["max_tokens"] = 1000
            else:
                kwargs["max_tokens"] = 800
        else:
            # Caller explicitly set max_tokens; respect it
            pass

        primary_provider_name = self.task_mappings.get(
            task_type,
            self.task_mappings["Default"],
        )

        user_keys = {}
        if user is not None:
            from utils.encryption import decrypt_token

            for credential in user.service_credentials:
                if credential.service_type != "ai" or not credential.encrypted_key:
                    continue
                decrypted_key = decrypt_token(credential.encrypted_key)
                if decrypted_key:
                    user_keys[credential.provider.lower()] = decrypted_key

        preferred_provider = (getattr(user, "default_ai_provider", None) or "").lower()
        provider_aliases = {
            "groq": "Groq",
            "gemini": "Gemini",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
        }
        preferred_provider_name = provider_aliases.get(preferred_provider)
        if preferred_provider_name and (
            preferred_provider in ("groq", "gemini")
            or preferred_provider in user_keys
        ):
            primary_provider_name = preferred_provider_name

        attempt_sequence = [primary_provider_name]
        for p in self.fallback_chain:
            if p not in attempt_sequence:
                attempt_sequence.append(p)

        last_error = None
        fallback_triggered = False
        skipped_providers = []

        for provider_name in attempt_sequence:
            adapter = self.adapters.get(provider_name)
            if not adapter or not getattr(adapter, "is_enabled", True):
                skipped_providers.append(f"{provider_name} (disabled)")
                continue

            health = self._get_health(provider_name)
            offline_cooldown = timedelta(minutes=5)
            last_error_at = health.last_error_at
            if last_error_at and last_error_at.tzinfo is None:
                last_error_at = last_error_at.replace(tzinfo=timezone.utc)
            is_recently_offline = (
                health.status == "offline"
                and last_error_at
                and datetime.now(timezone.utc) - last_error_at < offline_cooldown
            )
            if is_recently_offline:
                skipped_providers.append(f"{provider_name} (offline)")
                continue

            start_time = time.time()
            try:
                result = adapter.generate(
                    messages,
                    api_key=user_keys.get(provider_name.lower()),
                    **kwargs,
                )
                latency = time.time() - start_time

                self._update_health(provider_name, success=True, latency=latency)
                self._log_request(task_type, provider_name, latency, fallback_triggered, success=True)

                return result
            except Exception as e:
                latency = time.time() - start_time
                error_msg = str(e)

                match = re.search(r"(\{.*\})", error_msg, re.DOTALL)
                if match:
                    try:
                        err_json = json.loads(match.group(1))
                        if "error" in err_json and "message" in err_json["error"]:
                            error_msg = err_json["error"]["message"]
                    except Exception:
                        pass

                self._update_health(provider_name, success=False, latency=latency, error_msg=error_msg)
                self._log_request(task_type, provider_name, latency, fallback_triggered, success=False,
                                  error_msg=error_msg)

                last_error = error_msg
                fallback_triggered = True
                print(f"[ProviderManager] {provider_name} failed: {error_msg}. Falling back...")

        if last_error is None:
            skipped = ", ".join(skipped_providers) or "none"
            raise Exception(f"All AI providers were unavailable. Skipped: {skipped}")

        raise Exception(f"All AI providers failed. Last error: {last_error}")


provider_manager = ProviderManager()