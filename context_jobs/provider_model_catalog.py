"""Fetch chat-capable models visible to a user's BYOK API key."""

from __future__ import annotations

import re
import threading
import time
from typing import Any

from context_jobs.providers.registry import PROVIDER_REGISTRY

_CACHE_TTL_SECONDS = 300
_cache_lock = threading.Lock()
_models_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}

_OPENAI_EXCLUDE = re.compile(
    r"(embed|embedding|tts|whisper|transcribe|audio|realtime|moderation|"
    r"dall-e|image|davinci|babbage|curie|ada|sora)",
    re.I,
)
_OPENAI_CHAT = re.compile(r"^(gpt-|o[134]|chatgpt-)", re.I)


def _format_display_name(model_id: str) -> str:
    return model_id.replace("-", " ").replace("_", " ").title()


def _cache_get(cache_key: str) -> list[dict[str, str]] | None:
    with _cache_lock:
        entry = _models_cache.get(cache_key)
        if not entry:
            return None
        fetched_at, models = entry
        if time.monotonic() - fetched_at > _CACHE_TTL_SECONDS:
            _models_cache.pop(cache_key, None)
            return None
        return models


def _cache_set(cache_key: str, models: list[dict[str, str]]) -> None:
    with _cache_lock:
        _models_cache[cache_key] = (time.monotonic(), models)


def invalidate_models_cache_for_key(key_id: str) -> None:
    with _cache_lock:
        _models_cache.pop(f"llm_key:{key_id}", None)


def _is_openai_chat_model(model_id: str) -> bool:
    if _OPENAI_EXCLUDE.search(model_id):
        return False
    return bool(_OPENAI_CHAT.match(model_id))


def _fetch_openai_models(api_key: str) -> list[str]:
    import openai

    client = openai.OpenAI(api_key=api_key)
    return sorted(
        {
            m.id
            for m in client.models.list().data
            if m.id and _is_openai_chat_model(m.id)
        }
    )


def _fetch_anthropic_models(api_key: str) -> list[str]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    models_api = getattr(client, "models", None)
    list_fn = getattr(models_api, "list", None) if models_api else None
    if callable(list_fn):
        try:
            response = list_fn()
            data = getattr(response, "data", None) or response
            ids = []
            for item in data:
                model_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
                if model_id and "claude" in str(model_id).lower():
                    ids.append(str(model_id))
            if ids:
                return sorted(set(ids))
        except Exception:
            pass

    return list(PROVIDER_REGISTRY["anthropic"]["models"])


def _fetch_google_models(api_key: str) -> list[str]:
    from google import genai

    client = genai.Client(api_key=api_key)
    list_fn = getattr(client.models, "list", None)
    if not callable(list_fn):
        return list(PROVIDER_REGISTRY["google"]["models"])

    ids: list[str] = []
    for model in list_fn():
        name = getattr(model, "name", "") or ""
        model_id = name.split("/")[-1] if "/" in name else name
        if not model_id:
            continue
        lowered = model_id.lower()
        if not lowered.startswith("gemini"):
            continue
        if any(x in lowered for x in ("embed", "image", "vision-preview", "aqa")):
            continue
        supported = getattr(model, "supported_generation_methods", None) or []
        if supported and "generateContent" not in supported:
            continue
        ids.append(model_id)

    if ids:
        return sorted(set(ids))
    return list(PROVIDER_REGISTRY["google"]["models"])


def fetch_chat_models_for_provider(provider: str, api_key: str) -> list[dict[str, str]]:
    """Return [{id, displayName}, ...] for chat models the API key can access."""
    provider = provider.lower().strip()
    if provider == "openai":
        model_ids = _fetch_openai_models(api_key)
    elif provider == "anthropic":
        model_ids = _fetch_anthropic_models(api_key)
    elif provider == "google":
        model_ids = _fetch_google_models(api_key)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    return [{"id": mid, "displayName": _format_display_name(mid)} for mid in model_ids]


def fetch_chat_models_for_key(
    provider: str,
    api_key: str,
    *,
    cache_key: str | None = None,
    use_cache: bool = True,
) -> list[dict[str, str]]:
    if use_cache and cache_key:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    models = fetch_chat_models_for_provider(provider, api_key)
    if not models:
        raise ValueError(
            f"No chat models found for provider '{provider}'. "
            "Verify the API key has model access."
        )

    if use_cache and cache_key:
        _cache_set(cache_key, models)
    return models
