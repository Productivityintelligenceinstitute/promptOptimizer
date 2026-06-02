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
        "default_model": "claude-sonnet-4-20250514",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-haiku-latest",
        ],
    },
    "openai": {
        "adapter_class": OpenAIAdapter,
        "display_name": "OpenAI",
        "default_model": "gpt-4.1-mini",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o4-mini"],
    },
    "google": {
        "adapter_class": GeminiAdapter,
        "display_name": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
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
