"""BYOK key purpose helpers (LLM chat vs embedding)."""

from __future__ import annotations

LLM_KEY_PROVIDERS = frozenset({"openai", "google", "anthropic"})
EMBEDDING_KEY_PROVIDERS = frozenset({"openai", "google", "cohere", "voyage", "mistral", "jina"})
PLATFORM_EMBEDDING_PROVIDERS = frozenset({"openai", "google"})

KEY_PURPOSES = frozenset({"llm", "embedding", "both"})


def normalize_key_purpose(value: str | None) -> str:
    purpose = (value or "llm").strip().lower()
    if purpose not in KEY_PURPOSES:
        raise ValueError("keyPurpose must be one of: llm, embedding, both")
    return purpose


def providers_for_purpose(purpose: str) -> frozenset[str]:
    purpose = normalize_key_purpose(purpose)
    if purpose == "llm":
        return LLM_KEY_PROVIDERS
    if purpose == "embedding":
        return EMBEDDING_KEY_PROVIDERS
    return LLM_KEY_PROVIDERS & EMBEDDING_KEY_PROVIDERS


def purpose_allows_llm(purpose: str | None) -> bool:
    return normalize_key_purpose(purpose) in {"llm", "both"}


def purpose_allows_embedding(purpose: str | None) -> bool:
    return normalize_key_purpose(purpose) in {"embedding", "both"}


def embedding_key_required(provider: str) -> bool:
    return (provider or "").strip().lower() not in PLATFORM_EMBEDDING_PROVIDERS
