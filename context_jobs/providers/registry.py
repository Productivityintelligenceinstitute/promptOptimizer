"""Provider registry and adapter factory."""

from __future__ import annotations

from context_jobs.providers.anthropic_adapter import ClaudeAdapter
from context_jobs.providers.base import ProviderAdapter
from context_jobs.providers.google_adapter import GeminiAdapter
from context_jobs.providers.openai_adapter import OpenAIAdapter


PROVIDER_REGISTRY: dict[str, dict] = {
    "anthropic": {
        "adapter_class": ClaudeAdapter,
        "display_name": "Anthropic Claude",
        "default_model": "claude-haiku-4-5",
        "models": [
            "claude-haiku-4-5",
            "claude-sonnet-4-5",
            "claude-opus-4-5",
        ],
    },
    "openai": {
        "adapter_class": OpenAIAdapter,
        "display_name": "OpenAI",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
    },
    "google": {
        "adapter_class": GeminiAdapter,
        "display_name": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
    },
}


def get_default_model(provider: str) -> str:
    entry = PROVIDER_REGISTRY.get((provider or "openai").lower())
    if not entry:
        raise ValueError(f"Unknown provider: {provider}")
    return entry["default_model"]


def get_provider_adapter(provider: str) -> ProviderAdapter:
    entry = PROVIDER_REGISTRY.get((provider or "").lower())
    if not entry:
        raise ValueError(f"Unknown provider: {provider}")
    adapter_cls = entry["adapter_class"]
    return adapter_cls()
