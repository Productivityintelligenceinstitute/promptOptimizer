"""Default ingestion configuration (overridable per request or job)."""

from __future__ import annotations

from typing import Any

DEFAULT_INGESTION_CONFIG: dict[str, Any] = {
    "auto_create_target": False,
    "chunk_size": 500,
    "chunk_overlap": 50,
    "batch_size": 50,
}


def _normalize_numeric(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def merge_ingestion_config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Merge caller overrides onto defaults."""
    merged = dict(DEFAULT_INGESTION_CONFIG)
    if overrides:
        merged.update(overrides)
        # Accept character-based overlap aliases from API callers.
        if "characterOverlap" in overrides:
            merged["chunk_overlap"] = _normalize_numeric(
                overrides.get("characterOverlap"),
                merged["chunk_overlap"],
            )
        elif "character_overlap" in overrides:
            merged["chunk_overlap"] = _normalize_numeric(
                overrides.get("character_overlap"),
                merged["chunk_overlap"],
            )
        if "characterChunkSize" in overrides:
            merged["chunk_size"] = _normalize_numeric(
                overrides.get("characterChunkSize"),
                merged["chunk_size"],
            )
        elif "character_chunk_size" in overrides:
            merged["chunk_size"] = _normalize_numeric(
                overrides.get("character_chunk_size"),
                merged["chunk_size"],
            )
    return merged
