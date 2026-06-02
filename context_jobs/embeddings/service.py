"""
Unified query embedding for vector connection configs.

embedding_provider values:
  openai | mistral | jina | cohere | voyage | google

For OpenAI at a non-default host, set embedding_provider=openai and embedding_base_url.

OpenAI / Google: if embedding_api_key is set, it is used; if omitted or empty, Jet uses server env
OPENAI_API_KEY or GOOGLE_API_KEY/GEMINI_API_KEY. Other providers always require embedding_api_key.
embedding_dimensions: optional int; for embedding_provider openai only, passed to OpenAI embeddings API
as dimensions (e.g. 768 for Matryoshka models / Weaviate Cloud sandbox limits).
"""

from __future__ import annotations

from typing import Any

from core.config import EMBED_MODEL

from context_jobs.embeddings.backends import (
    default_base_url_for_provider,
    embed_cohere_query,
    embed_google_query,
    embed_openai_compatible,
    embed_voyage_query,
    resolve_platform_api_key,
)
from context_jobs.embeddings.registry import infer_provider


def embed_query(text: str, connection_config: dict[str, Any]) -> list[float]:
    """
    Produce a query embedding vector using the embedding profile in connection_config.

    Backward compatible: if only embedding_model is set, provider is inferred (usually openai).
    """
    cfg = connection_config or {}
    model = (
        cfg.get("embedding_model")
        or cfg.get("embed_model")
        or EMBED_MODEL
    )
    provider_raw = (cfg.get("embedding_provider") or "").strip().lower()
    provider = provider_raw or infer_provider(str(model)) or "openai"

    api_key = cfg.get("embedding_api_key")
    if isinstance(api_key, str) and not api_key.strip():
        api_key = None

    # Option A: BYO key if present; otherwise OpenAI/Google may use platform keys from env.
    if not api_key and provider in {"openai", "google"}:
        api_key = resolve_platform_api_key(provider)

    if not api_key:
        if provider in {"openai", "google"}:
            hint = (
                "Provide embedding_api_key on the vector connection, or configure OPENAI_API_KEY / "
                "GOOGLE_API_KEY or GEMINI_API_KEY on the server to use Jet-hosted embedding keys."
            )
        else:
            hint = (
                f"Set embedding_api_key on the vector connection for provider '{provider}'. "
                "Jet does not supply a platform API key for this provider."
            )
        raise ValueError(f"No API key for embedding provider '{provider}'. {hint}")

    base_url = cfg.get("embedding_base_url")
    if isinstance(base_url, str):
        base_url = base_url.strip() or None

    if provider in {"openai", "mistral", "jina"}:
        root = base_url or default_base_url_for_provider(provider)
        if not root:
            raise ValueError(f"embedding_base_url required for provider '{provider}'.")
        oai_dims = None
        if provider == "openai":
            raw_d = cfg.get("embedding_dimensions")
            if raw_d is not None:
                try:
                    oai_dims = int(raw_d)
                except (TypeError, ValueError):
                    oai_dims = None
        return embed_openai_compatible(text, str(model), api_key, root, dimensions=oai_dims)

    if provider == "cohere":
        return embed_cohere_query(text, str(model), api_key)

    if provider == "voyage":
        return embed_voyage_query(text, str(model), api_key)

    if provider == "google":
        return embed_google_query(text, str(model), api_key)

    raise ValueError(f"Unsupported embedding_provider: {provider}")
