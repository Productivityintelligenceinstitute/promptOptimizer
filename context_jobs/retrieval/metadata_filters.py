"""Vector adapter metadata-filter capability helpers."""

from __future__ import annotations

from typing import Any

# Providers that honor the shared Pinecone-shaped filter dialect in search().
_METADATA_FILTER_PROVIDERS = frozenset(
    {
        "pinecone",
        "jet_kb",
        "jetkb",
        "internal",
        "qdrant",
        "weaviate",
        "pgvector",
    }
)


def adapter_supports_metadata_filter(adapter: Any) -> bool:
    """True when the retrieval adapter forwards filters to a metadata-capable vector store."""
    provider = (getattr(adapter, "provider", "") or "").lower().strip()
    return provider in _METADATA_FILTER_PROVIDERS
