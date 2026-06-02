"""
Known embedding model ids → provider and optional default dimensions.

Sources: provider embedding docs (OpenAI, Google Gemini API, Cohere, Voyage, Mistral, Jina).
Benchmark scores (e.g. MTEB) change over time — this list prioritizes current vendor IDs,
legacy install base, and models compatible with our HTTP embeddings adapters.

Excluded by design:
  voyage-context-3 — uses Voyage's separate contextualized API (/v1/contextualizedembeddings),
  not POST /v1/embeddings; would require a dedicated code path.

Extend MODEL_TO_PROVIDER / MODEL_DEFAULT_DIMS as vendors ship new stable ids.
"""

from __future__ import annotations

from typing import Any

# model_id (lowercase) → provider key used by embed_query router
MODEL_TO_PROVIDER: dict[str, str] = {
    # --- OpenAI (api.openai.com/v1/embeddings) ---
    "text-embedding-3-small": "openai",
    "text-embedding-3-large": "openai",
    "text-embedding-ada-002": "openai",
    # --- Google Gemini API embedContent (generativelanguage.googleapis.com) ---
    "gemini-embedding-001": "google",
    "gemini-embedding-2": "google",
    # --- Cohere (api.cohere.com/v1/embed) ---
    "embed-english-v3.0": "cohere",
    "embed-multilingual-v3.0": "cohere",
    "embed-v4.0": "cohere",
    "embed-v4": "cohere",
    # --- Voyage (api.voyageai.com/v1/embeddings) — standard text embeddings only ---
    "voyage-4-large": "voyage",
    "voyage-4": "voyage",
    "voyage-4-lite": "voyage",
    "voyage-code-3": "voyage",
    "voyage-code-2": "voyage",
    "voyage-finance-2": "voyage",
    "voyage-law-2": "voyage",
    "voyage-3-large": "voyage",
    "voyage-3.5": "voyage",
    "voyage-3.5-lite": "voyage",
    "voyage-3": "voyage",
    "voyage-3-lite": "voyage",
    "voyage-multilingual-2": "voyage",
    # --- Mistral (api.mistral.ai/v1/embeddings) ---
    "mistral-embed": "mistral",
    "codestral-embed-2505": "mistral",
    # --- Jina (api.jina.ai/v1/embeddings) ---
    "jina-embeddings-v3": "jina",
    "jina-embeddings-v4": "jina",
    "jina-embeddings-v5-text-small": "jina",
    "jina-embeddings-v5-text-nano": "jina",
}

# Default float dimensions at listed models’ defaults (Matryoshka/truncation may change effective dim).
MODEL_DEFAULT_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "gemini-embedding-001": 3072,
    "gemini-embedding-2": 3072,
    "embed-english-v3.0": 1024,
    "embed-multilingual-v3.0": 1024,
    "embed-v4.0": 1536,
    "embed-v4": 1536,
    "voyage-4-large": 1024,
    "voyage-4": 1024,
    "voyage-4-lite": 1024,
    "voyage-code-3": 1024,
    "voyage-code-2": 1536,
    "voyage-finance-2": 1024,
    "voyage-law-2": 1024,
    "voyage-3-large": 1024,
    "voyage-3.5": 1024,
    "voyage-3.5-lite": 1024,
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-multilingual-2": 1024,
    "mistral-embed": 1024,
    "codestral-embed-2505": 1536,
    "jina-embeddings-v3": 1024,
    "jina-embeddings-v4": 2048,
    "jina-embeddings-v5-text-small": 1024,
    "jina-embeddings-v5-text-nano": 768,
}

PREFIX_PROVIDER_RULES: tuple[tuple[str, str], ...] = (
    ("text-embedding-3-", "openai"),
    ("text-embedding-ada-", "openai"),
    ("gemini-embedding-", "google"),
    ("embed-english-", "cohere"),
    ("embed-multilingual-", "cohere"),
    ("embed-v", "cohere"),
    ("voyage-", "voyage"),
    ("mistral-embed", "mistral"),
    ("codestral-embed-", "mistral"),
    ("jina-", "jina"),
)


def infer_provider(model_id: str | None) -> str | None:
    """Best-effort provider guess from model id; returns None if unknown."""
    if not model_id:
        return None
    mid = model_id.strip().lower()
    if mid in MODEL_TO_PROVIDER:
        return MODEL_TO_PROVIDER[mid]
    for prefix, provider in PREFIX_PROVIDER_RULES:
        if mid.startswith(prefix):
            return provider
    return None


def default_dimensions_hint(model_id: str | None) -> int | None:
    if not model_id:
        return None
    mid = model_id.strip().lower()
    if mid in MODEL_DEFAULT_DIMS:
        return MODEL_DEFAULT_DIMS[mid]
    return None


def supported_models_catalog() -> list[dict[str, Any]]:
    """Flat list for UI / GET endpoint — static allowlist."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for model_id, provider in sorted(MODEL_TO_PROVIDER.items(), key=lambda x: x[0]):
        if model_id in seen:
            continue
        seen.add(model_id)
        rows.append(
            {
                "modelId": model_id,
                "provider": provider,
                "defaultDimensions": MODEL_DEFAULT_DIMS.get(model_id),
            }
        )
    return rows
