"""Default ingestion configuration (overridable per request or job)."""

from __future__ import annotations

from typing import Any

DEFAULT_INGESTION_CONFIG: dict[str, Any] = {
    "auto_create_target": False,
    "chunk_size": 500,
    "chunk_overlap": 50,
    "batch_size": 50,
}


def merge_ingestion_config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Merge caller overrides onto defaults."""
    merged = dict(DEFAULT_INGESTION_CONFIG)
    if overrides:
        merged.update(overrides)
    return merged
