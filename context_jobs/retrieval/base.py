from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from context_jobs.ingestion.types import UpsertResult


@dataclass
class NormalizedMatch:
    id: str
    score: float
    text_preview: str
    metadata: dict[str, Any]


class RetrievalAdapter(Protocol):
    """Query-time vector search."""

    provider: str

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        ...

    def test_connection(self) -> tuple[bool, str]:
        ...


class VectorStoreAdapter(RetrievalAdapter, Protocol):
    """
    Full vector store adapter: search (retrieval) + ingest (upsert).

    Implemented by PineconeAdapter, QdrantAdapter, WeaviateAdapter, PgVectorAdapter, JetKbAdapter.
    """

    def target_exists(self) -> bool: ...

    def ensure_target(self, vector_dim: int, **kwargs: Any) -> tuple[bool, str]: ...

    def upsert(self, records: list[dict[str, Any]], batch_size: int = 100) -> UpsertResult: ...

