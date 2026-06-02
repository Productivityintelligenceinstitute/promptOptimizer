"""HTTP backends for embedding providers (query-time embeddings only)."""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_TIMEOUT_S = 60.0


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        raise ValueError(
            f"Embedding HTTP {resp.status_code} for {url}: {resp.text[:800]}"
        )
    return resp.json()


def embed_openai_compatible(
    text: str,
    model: str,
    api_key: str,
    base_url: str,
    dimensions: int | None = None,
) -> list[float]:
    """
    OpenAI POST /v1/embeddings shape (also used by Mistral, Jina, many gateways).
    base_url should be like https://api.openai.com/v1 (no trailing slash required).

    dimensions: optional; OpenAI text-embedding-3-* supports reducing output size (e.g. 768 for Weaviate sandbox).
    """
    root = base_url.rstrip("/")
    url = f"{root}/embeddings"
    body: dict[str, Any] = {"model": model, "input": text}
    if dimensions is not None:
        try:
            d = int(dimensions)
            if d > 0:
                body["dimensions"] = d
        except (TypeError, ValueError):
            pass
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = _post_json(url, headers, body)
    try:
        return list(map(float, data["data"][0]["embedding"]))
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected OpenAI-compatible embeddings response: {data!r}") from exc


def embed_cohere_query(text: str, model: str, api_key: str) -> list[float]:
    """Cohere v1 embed — use search_query at query time."""
    m = str(model).strip().lower()
    if m == "embed-v4":
        m = "embed-v4.0"
    url = "https://api.cohere.com/v1/embed"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload: dict[str, Any] = {
        "texts": [text],
        "model": m,
        "input_type": "search_query",
        "embedding_types": ["float"],
    }
    data = _post_json(url, headers, payload)
    # Newer responses use embeddings.float; older use embeddings as list of lists
    emb_obj = data.get("embeddings")
    if isinstance(emb_obj, dict) and "float" in emb_obj:
        vec = emb_obj["float"]
        if vec and isinstance(vec[0], list):
            return list(map(float, vec[0]))
        return list(map(float, vec))
    if isinstance(emb_obj, list) and emb_obj:
        first = emb_obj[0]
        if isinstance(first, list):
            return list(map(float, first))
        return list(map(float, emb_obj))
    raise ValueError(f"Unexpected Cohere embed response: {data!r}")


def embed_voyage_query(text: str, model: str, api_key: str) -> list[float]:
    url = "https://api.voyageai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "input": [text],
        "model": model,
        "input_type": "query",
    }
    data = _post_json(url, headers, payload)
    try:
        return list(map(float, data["data"][0]["embedding"]))
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected Voyage embeddings response: {data!r}") from exc


def embed_google_query(text: str, model: str, api_key: str) -> list[float]:
    """
    Gemini API embedContent (AI Studio key).
    model: e.g. gemini-embedding-001 or models/gemini-embedding-001
    """
    mid = model.strip()
    if not mid.startswith("models/"):
        mid = f"models/{mid}"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/{mid}:embedContent"
    )
    params = {"key": api_key}
    body = {
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_QUERY",
    }
    resp = requests.post(
        url,
        params=params,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=DEFAULT_TIMEOUT_S,
    )
    if resp.status_code != 200:
        raise ValueError(
            f"Google embedContent HTTP {resp.status_code}: {resp.text[:800]}"
        )
    data = resp.json()
    emb = data.get("embedding") or {}
    values = emb.get("values")
    if not values:
        raise ValueError(f"Unexpected Google embedContent response: {data!r}")
    return list(map(float, values))


def default_base_url_for_provider(provider: str) -> str | None:
    p = provider.lower().strip()
    if p == "openai":
        return "https://api.openai.com/v1"
    if p == "mistral":
        return "https://api.mistral.ai/v1"
    if p == "jina":
        return "https://api.jina.ai/v1"
    return None


PLATFORM_ENV_KEYS: dict[str, tuple[str, ...]] = {
    # Jet only hosts platform keys for these two; all other providers are BYO key on the connection.
    "openai": ("OPENAI_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}


def resolve_platform_api_key(provider: str) -> str | None:
    """Return a platform-managed API key from env, only for openai and google."""
    for env_name in PLATFORM_ENV_KEYS.get(provider, ()):
        val = os.getenv(env_name)
        if val and val.strip():
            return val.strip()
    return None
