from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from context_jobs.retrieval.base import NormalizedMatch
from utils.utils import embed


class QdrantAdapter:
    provider = "qdrant"

    def __init__(self, config: dict[str, Any]) -> None:
        self.url = config.get("url")
        self.api_key = config.get("api_key")
        self.collection_name = config.get("collection_name")
        self.embedding_model = config.get("embedding_model")
        self.vector_name = config.get("vector_name")

        if not self.url or not self.collection_name:
            raise ValueError("External Qdrant config requires url and collection_name.")

        self.client = QdrantClient(url=self.url, api_key=self.api_key)

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        query_vec = embed(query_text, model=self.embedding_model)

        query_filter = None
        if isinstance(filters, dict) and filters:
            try:
                query_filter = qmodels.Filter(**filters)
            except Exception:
                # Keep external caller flexibility; ignore malformed filter payloads.
                query_filter = None

        search_kwargs: dict[str, Any] = {
            "collection_name": self.collection_name,
            "query_vector": query_vec,
            "limit": top_k,
            "with_payload": True,
            "query_filter": query_filter,
        }
        if self.vector_name:
            search_kwargs["using"] = self.vector_name

        points = self.client.search(**search_kwargs)

        normalized: list[NormalizedMatch] = []
        for p in points or []:
            payload = getattr(p, "payload", None) or {}
            preview = (
                payload.get("preview")
                or payload.get("text")
                or payload.get("chunk")
                or payload.get("content")
                or ""
            )[:600]
            normalized.append(
                NormalizedMatch(
                    id=str(getattr(p, "id", "")),
                    score=float(getattr(p, "score", 0.0) or 0.0),
                    text_preview=preview,
                    metadata=payload,
                )
            )
        return normalized

    def test_connection(self) -> tuple[bool, str]:
        try:
            if not self.client.collection_exists(collection_name=self.collection_name):
                return False, f"Qdrant collection '{self.collection_name}' does not exist."
            _ = self.search("test connection", top_k=1)
            return True, "Qdrant connection test successful."
        except Exception as exc:
            return False, f"Qdrant connection failed: {exc}"

