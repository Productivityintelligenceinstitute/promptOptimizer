from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from context_jobs.embeddings import embed_query
from context_jobs.ingestion.records import ensure_record_ids, qdrant_point_id
from context_jobs.ingestion.types import UpsertResult
from context_jobs.retrieval.base import NormalizedMatch
from context_jobs.retrieval.filter_dialect import collect_filter_fields, to_qdrant_filter
from core.config import EMBED_MODEL

_COMMON_PAYLOAD_INDEX_FIELDS = (
    "contractId",
    "documentType",
    "vendor",
    "vendorId",
    "expiryDate",
    "file",
    "source",
    "url",
    "title",
    "name",
    "complexityTier",
    "category",
)


class QdrantAdapter:
    provider = "qdrant"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config) if config else {}
        self.url = self.config.get("url")
        self.api_key = self.config.get("api_key")
        self.collection_name = self.config.get("collection_name")
        self.embedding_model = self.config.get("embedding_model") or EMBED_MODEL
        self.vector_name = self.config.get("vector_name")

        if not self.url or not self.collection_name:
            raise ValueError("External Qdrant config requires url and collection_name.")

        self.client = QdrantClient(url=self.url, api_key=self.api_key)

    def _resolve_vector_name(self) -> str | None:
        info = self.client.get_collection(self.collection_name)
        params = getattr(getattr(info, "config", None), "params", None)
        vectors = getattr(params, "vectors", None)
        sparse_vectors = getattr(params, "sparse_vectors", None)

        if sparse_vectors:
            raise ValueError(
                "Qdrant collection uses sparse vectors. This integration currently supports only "
                "dense vectors."
            )

        if isinstance(vectors, dict):
            vector_names = list(vectors.keys())
            if self.vector_name:
                if self.vector_name not in vector_names:
                    raise ValueError(
                        f"Qdrant vector_name '{self.vector_name}' not found in collection. "
                        f"Available vector names: {vector_names}"
                    )
                return self.vector_name

            if len(vector_names) == 1:
                return vector_names[0]

            raise ValueError(
                "Qdrant collection has multiple named dense vectors. "
                f"Provide config.vector_name. Available vector names: {vector_names}"
            )

        if self.vector_name:
            raise ValueError(
                "config.vector_name was provided, but this Qdrant collection uses a single unnamed dense vector. "
                "Remove vector_name from config."
            )

        return None

    def ensure_payload_indexes(self, fields: list[str] | tuple[str, ...] | set[str]) -> None:
        """Create keyword payload indexes required for filtered search on Qdrant Cloud."""
        for field in fields:
            if not isinstance(field, str) or not field.strip():
                continue
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field.strip(),
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                # Index may already exist or field not yet present — safe to continue.
                continue

    def _normalize_points(
        self,
        points: list[Any] | None,
        *,
        default_score: float | None = None,
    ) -> list[NormalizedMatch]:
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
            score = getattr(p, "score", None)
            if score is None:
                score = default_score if default_score is not None else 0.0
            normalized.append(
                NormalizedMatch(
                    id=str(getattr(p, "id", "")),
                    score=float(score or 0.0),
                    text_preview=preview,
                    metadata=payload,
                )
            )
        return normalized

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        query_vec = embed_query(query_text, self.config)
        using_vector = self._resolve_vector_name()
        if filters:
            self.ensure_payload_indexes(collect_filter_fields(filters))
        qfilter = to_qdrant_filter(filters)
        try:
            points = self._execute_dense_query(query_vec, top_k, using_vector, qfilter)
        except Exception as exc:
            message = str(exc)
            if "dimension" in message.lower():
                raise ValueError(
                    "Qdrant query failed due to vector dimension mismatch. "
                    "Use a collection dimension that matches your embedding model output "
                    f"(model='{self.embedding_model}'). Raw error: {message}"
                ) from exc
            raise ValueError(f"Qdrant query failed: {message}") from exc

        return self._normalize_points(points)

    def search_by_metadata_filter(
        self,
        filters: dict[str, Any],
        top_k: int = 50,
    ) -> list[NormalizedMatch]:
        """Fetch chunks by metadata filter only (no semantic ranking)."""
        self.ensure_payload_indexes(collect_filter_fields(filters))
        qfilter = to_qdrant_filter(filters)
        if qfilter is None:
            return []
        try:
            if hasattr(self.client, "scroll"):
                points, _next = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=qfilter,
                    limit=top_k,
                    with_payload=True,
                    with_vectors=False,
                )
                return self._normalize_points(points, default_score=1.0)

            dim = 1536
            try:
                info = self.client.get_collection(self.collection_name)
                vectors = getattr(getattr(getattr(info, "config", None), "params", None), "vectors", None)
                if hasattr(vectors, "size"):
                    dim = int(vectors.size)
            except Exception:
                pass
            using_vector = self._resolve_vector_name()
            points = self._execute_dense_query([0.0] * dim, top_k, using_vector, qfilter)
            return self._normalize_points(points, default_score=1.0)
        except Exception as exc:
            raise ValueError(f"Qdrant metadata filter query failed: {exc}") from exc

    def _execute_dense_query(
        self,
        query_vec: list[float],
        top_k: int,
        using_vector: str | None,
        qfilter: Any | None = None,
    ) -> list[Any]:
        if hasattr(self.client, "search"):
            search_kwargs: dict[str, Any] = {
                "collection_name": self.collection_name,
                "query_vector": query_vec,
                "limit": top_k,
                "with_payload": True,
            }
            if using_vector:
                search_kwargs["using"] = using_vector
            if qfilter is not None:
                search_kwargs["query_filter"] = qfilter
            return self.client.search(**search_kwargs)

        if hasattr(self.client, "query_points"):
            query_kwargs: dict[str, Any] = {
                "collection_name": self.collection_name,
                "query": query_vec,
                "limit": top_k,
                "with_payload": True,
            }
            if using_vector:
                query_kwargs["using"] = using_vector
            if qfilter is not None:
                query_kwargs["query_filter"] = qfilter
            result = self.client.query_points(**query_kwargs)
            return getattr(result, "points", None) or []

        raise ValueError(
            "Unsupported qdrant-client version: missing both 'search' and 'query_points'. "
            "Install a compatible qdrant-client release."
        )

    def test_connection(self) -> tuple[bool, str]:
        try:
            if not self.client.collection_exists(collection_name=self.collection_name):
                return False, f"Qdrant collection '{self.collection_name}' does not exist."
            _ = self._resolve_vector_name()
            _ = self.search("test connection", top_k=1)
            return True, "Qdrant connection test successful."
        except Exception as exc:
            return False, f"Qdrant connection failed: {exc}"

    def target_exists(self) -> bool:
        try:
            return bool(self.client.collection_exists(collection_name=self.collection_name))
        except Exception:
            return False

    def ensure_target(self, vector_dim: int, distance: str = "Cosine", **kwargs: Any) -> tuple[bool, str]:
        _ = kwargs
        if self.target_exists():
            return True, f"Qdrant collection '{self.collection_name}' already exists."
        distance_map = {
            "cosine": Distance.COSINE,
            "euclid": Distance.EUCLID,
            "euclidean": Distance.EUCLID,
            "dot": Distance.DOT,
            "manhattan": Distance.MANHATTAN,
        }
        dist_enum = distance_map.get(distance.lower(), Distance.COSINE)
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_dim, distance=dist_enum),
            )
            return True, f"Created Qdrant collection '{self.collection_name}' ({vector_dim}-dim)."
        except Exception as exc:
            return False, f"Failed to create Qdrant collection: {exc}"

    def upsert(self, records: list[dict[str, Any]], batch_size: int = 100) -> UpsertResult:
        ensure_record_ids(records)
        upserted = 0
        try:
            for i in range(0, len(records), batch_size):
                structs = [
                    PointStruct(
                        id=qdrant_point_id(r["id"]),
                        vector=r["values"],
                        payload=r.get("metadata") or {},
                    )
                    for r in records[i : i + batch_size]
                ]
                self.client.upsert(collection_name=self.collection_name, points=structs)
                upserted += len(structs)
            # Ensure common filter fields are indexed for subsequent filtered search.
            keyed = set(_COMMON_PAYLOAD_INDEX_FIELDS)
            for rec in records:
                meta = rec.get("metadata") or {}
                if isinstance(meta, dict):
                    keyed.update(str(k) for k in meta.keys() if isinstance(k, str))
            self.ensure_payload_indexes(keyed)
            return UpsertResult(success=True, upserted_count=upserted)
        except Exception as exc:
            return UpsertResult(
                success=False,
                upserted_count=upserted,
                failed_count=len(records) - upserted,
                error=f"Qdrant upsert failed: {exc}",
            )
