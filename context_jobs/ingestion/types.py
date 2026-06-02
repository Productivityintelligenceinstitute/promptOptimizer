"""Shared types for Context Jobs vector ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class UpsertResult:
    """Result of a vector upsert operation."""

    success: bool
    upserted_count: int = 0
    failed_count: int = 0
    failed_ids: list[str] = field(default_factory=list)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "upsertedCount": self.upserted_count,
            "failedCount": self.failed_count,
            "failedIds": self.failed_ids,
            "error": self.error,
            "warnings": self.warnings,
        }


@dataclass
class IngestionTarget:
    """Resolved vector store target for an ingestion run."""

    provider: str
    embed_config: dict[str, Any]
    target_name: str
    target_dimension: int | None
    adapter: Any  # retrieval adapter with upsert support


class VectorIngestionAdapter(Protocol):
    """Ingestion capability mixed into retrieval adapters (same client, read + write)."""

    provider: str

    def target_exists(self) -> bool: ...

    def ensure_target(self, vector_dim: int, **kwargs: Any) -> tuple[bool, str]: ...

    def upsert(self, records: list[dict[str, Any]], batch_size: int = 100) -> UpsertResult: ...


@dataclass
class IngestionResult:
    """Outcome of ingest_documents (maps to Context Jobs run statuses)."""

    status: str
    outcome: str
    next_action: dict[str, str]
    upserted_count: int = 0
    failed_count: int = 0
    validation_events: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "outcome": self.outcome,
            "nextAction": self.next_action,
            "upsertedCount": self.upserted_count,
            "failedCount": self.failed_count,
            "validationEvents": self.validation_events,
            "warnings": self.warnings,
            "exceptions": self.exceptions,
            "error": self.error,
        }
