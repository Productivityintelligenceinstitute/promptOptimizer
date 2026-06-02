"""Factory for vector store adapters with ingestion support."""

from __future__ import annotations

from typing import Any

from context_jobs.retrieval.factory import get_retrieval_adapter


def get_ingestion_adapter(provider: str, config: dict[str, Any] | None = None):
    """
    Return the same adapter used for retrieval; it also implements upsert/target_exists.

    Prefer resolve_ingestion_target() in ingestion_service when you have a Context Job.
    """
    adapter = get_retrieval_adapter(provider, config)
    for method in ("target_exists", "ensure_target", "upsert"):
        if not callable(getattr(adapter, method, None)):
            raise ValueError(
                f"Provider '{provider}' does not support ingestion (missing {method})."
            )
    return adapter
