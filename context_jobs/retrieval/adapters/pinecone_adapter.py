from __future__ import annotations

from typing import Any

from pinecone import Pinecone

from context_jobs.embeddings import embed_query
from context_jobs.ingestion.records import ensure_record_ids
from context_jobs.ingestion.types import UpsertResult  # shared write-path result type
from context_jobs.retrieval.base import NormalizedMatch
from core.config import EMBED_MODEL


class PineconeAdapter:
    provider = "pinecone"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config) if config else {}
        self.api_key = self.config.get("api_key")
        self.index_name = self.config.get("index_name")
        self.namespace = self.config.get("namespace")
        self.embedding_model = (
            self.config.get("embedding_model")
            or self.config.get("embed_model")
            or EMBED_MODEL
        )
        self.index_dimension = self.config.get("index_dimension")
        if not self.api_key or not self.index_name:
            raise ValueError("External Pinecone config requires api_key and index_name.")

        pc = Pinecone(api_key=self.api_key)
        self.index = pc.Index(self.index_name)

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        query_vec = embed_query(query_text, self.config)

        if self.index_dimension is not None:
            try:
                expected_dim = int(self.index_dimension)
                actual_dim = len(query_vec)
                if actual_dim != expected_dim:
                    raise ValueError(
                        f"Embedding dimension mismatch before Pinecone query: "
                        f"model '{self.embedding_model}' returns {actual_dim}, "
                        f"but index_dimension is set to {expected_dim}."
                    )
            except ValueError:
                raise
            except Exception:
                # If parsing of user-supplied dimension fails, skip strict check.
                pass

        kwargs: dict[str, Any] = {
            "vector": query_vec,
            "top_k": top_k,
            "include_metadata": True,
        }
        if self.namespace:
            kwargs["namespace"] = self.namespace
        if filters:
            kwargs["filter"] = filters

        result = self.index.query(**kwargs)
        normalized: list[NormalizedMatch] = []
        for m in result.matches or []:
            meta = getattr(m, "metadata", None) or {}
            preview = (meta.get("preview") or meta.get("text") or "")[:600]
            normalized.append(
                NormalizedMatch(
                    id=str(getattr(m, "id", "")),
                    score=float(getattr(m, "score", 0.0) or 0.0),
                    text_preview=preview,
                    metadata=meta,
                )
            )
        return normalized

    def test_connection(self) -> tuple[bool, str]:
        try:
            _ = self.search("test connection", top_k=1)
            return True, "Pinecone connection test successful."
        except Exception as exc:
            message = str(exc)
            if "Vector dimension" in message and "does not match the dimension of the index" in message:
                return (
                    False,
                    "Pinecone connection failed: embedding model dimension does not match index dimension. "
                    "Set config.embedding_model to the same model used when indexing this Pinecone index "
                    "(or provide config.index_dimension for pre-check). "
                    f"Raw error: {message}",
                )
            return False, f"Pinecone connection failed: {message}"

    def target_exists(self) -> bool:
        """True if configured namespace appears in index stats (empty ns always allowed)."""
        ns = (self.namespace or "").strip()
        if not ns:
            return True
        try:
            try:
                stats = self.index.describe_index_stats(filter={"namespace": ns})
            except TypeError:
                stats = self.index.describe_index_stats()
            namespaces = getattr(stats, "namespaces", None) or {}
            if ns in namespaces:
                return True
            total = getattr(stats, "total_vector_count", None)
            return total is not None and int(total) > 0
        except Exception:
            return False

    def ensure_target(self, vector_dim: int, **kwargs: Any) -> tuple[bool, str]:
        _ = vector_dim, kwargs
        ns = self.namespace or ""
        return True, f"Pinecone namespace '{ns or '(default)'}' is created on first upsert."

    def upsert(self, records: list[dict[str, Any]], batch_size: int = 100) -> UpsertResult:
        ensure_record_ids(records)
        ns = self.namespace or ""
        upserted = 0
        try:
            for i in range(0, len(records), batch_size):
                batch = [
                    {
                        "id": str(r["id"]),
                        "values": r["values"],
                        "metadata": r.get("metadata") or {},
                    }
                    for r in records[i : i + batch_size]
                ]
                kwargs: dict[str, Any] = {"vectors": batch}
                if ns:
                    kwargs["namespace"] = ns
                self.index.upsert(**kwargs)
                upserted += len(batch)
            return UpsertResult(success=True, upserted_count=upserted)
        except Exception as exc:
            return UpsertResult(
                success=False,
                upserted_count=upserted,
                failed_count=len(records) - upserted,
                error=f"Pinecone upsert failed: {exc}",
            )

