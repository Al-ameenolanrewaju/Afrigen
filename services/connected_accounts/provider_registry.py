from typing import Type, Dict
from .base import BaseProviderAdapter

_registry: Dict[str, Type[BaseProviderAdapter]] = {}

def register_provider(name: str, adapter_cls: Type[BaseProviderAdapter]):
    """Register a provider adapter."""
    _registry[name] = adapter_cls

def get_adapter(name: str) -> BaseProviderAdapter:
    """Get an instantiated adapter for the given provider."""
    adapter_cls = _registry.get(name)
    if not adapter_cls:
        raise ValueError(f"Provider {name} is not registered or not supported.")
    return adapter_cls()

def get_all_providers() -> list:
    """Return a list of all registered provider names."""
    return list(_registry.keys())

# Register all adapters
import os
import importlib

# Automatically register all adapters in the adapters/ folder
adapters_dir = os.path.join(os.path.dirname(__file__), "adapters")
if os.path.exists(adapters_dir):
    for filename in os.listdir(adapters_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            provider_name = filename[:-3]
            try:
                module = importlib.import_module(f".adapters.{provider_name}", package="services.connected_accounts")
                class_name = f"{provider_name.capitalize()}Adapter"
                if hasattr(module, class_name):
                    adapter_cls = getattr(module, class_name)
                    register_provider(provider_name, adapter_cls)
            except Exception as e:
                print(f"Failed to register adapter {provider_name}: {e}")
