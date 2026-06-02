from __future__ import annotations

from typing import Any

from core.config import index
from utils.utils import embed

from context_jobs.ingestion.records import ensure_record_ids
from context_jobs.ingestion.types import UpsertResult
from context_jobs.retrieval.base import NormalizedMatch


class JetKbAdapter:
    """
    Managed Jet knowledge base: platform Pinecone index + optional per-owner namespace.

    Uses the platform embedding model from utils.embed / core EMBED_MODEL (same geometry as indexing).
    """

    provider = "jet_kb"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = dict(config) if config else {}
        self.namespace = cfg.get("namespace")

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        _ = filters
        q_emb = embed(query_text)
        kwargs: dict[str, Any] = {
            "vector": q_emb,
            "top_k": top_k,
            "include_metadata": True,
        }
        if self.namespace:
            kwargs["namespace"] = self.namespace

        result = index.query(**kwargs)
        matches = getattr(result, "matches", None) or []
        normalized: list[NormalizedMatch] = []
        for m in matches:
            meta = getattr(m, "metadata", None) or {}
            preview = (meta.get("preview") or "")[:600]
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
            _ = self.search("test retrieval", top_k=1)
            return True, "JET KB adapter is healthy."
        except Exception as exc:
            return False, f"JET KB retrieval failed: {exc}"

    def target_exists(self) -> bool:
        ns = (self.namespace or "").strip()
        if not ns:
            return True
        try:
            # Namespace filter avoids full-index stats (very slow on large indexes).
            try:
                stats = index.describe_index_stats(filter={"namespace": ns})
            except TypeError:
                stats = index.describe_index_stats()
            namespaces = getattr(stats, "namespaces", None) or {}
            if ns in namespaces:
                return True
            total = getattr(stats, "total_vector_count", None)
            return total is not None and int(total) > 0
        except Exception:
            return False

    def ensure_target(self, vector_dim: int, **kwargs: Any) -> tuple[bool, str]:
        _ = vector_dim, kwargs
        return True, f"Managed namespace '{self.namespace}' is created on first upsert."

    def upsert(self, records: list[dict[str, Any]], batch_size: int = 100) -> UpsertResult:
        if not self.namespace:
            return UpsertResult(success=False, error="Managed Jet KB requires a namespace.")
        ensure_record_ids(records)
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
                index.upsert(vectors=batch, namespace=self.namespace)
                upserted += len(batch)
            return UpsertResult(success=True, upserted_count=upserted)
        except Exception as exc:
            return UpsertResult(
                success=False,
                upserted_count=upserted,
                failed_count=len(records) - upserted,
                error=f"Jet KB upsert failed: {exc}",
            )
