"""
Weaviate v4 retrieval (dense near_vector) using Jet-side embed_query vectors.

Connection config (stored on vector connection, same pattern as Qdrant/Pinecone)
---------------------------------------------------------------------------
Required:
  collection_name   Weaviate collection name (v4 "class" name).

One of these deployment styles:

  A) Weaviate Cloud (recommended for SaaS)
     deployment: "cloud"   (default when cluster_url looks like *.weaviate.network / *.weaviate.cloud)
     cluster_url: REST endpoint — full https URL or hostname only (e.g. xxx.gcp.weaviate.cloud); host-only is normalized to https://…
     api_key:     Weaviate Cloud admin / read key (WCS dashboard)
     No separate gRPC URL in config: the v4 client derives gRPC for Cloud from this URL (gRPC must still be reachable on the network).

  B) Local Docker / compose (default REST 8080, gRPC 50051)
     deployment: "local"
     http_host:   default localhost
     http_port:   default 8080
     grpc_port:   default 50051
     api_key:     optional if auth disabled

  C) Custom host (self-hosted TLS or non-default ports)
     deployment: "custom"
     cluster_url: https://host:8080  OR  http://host:8080
     api_key:     optional
     grpc_host:   optional; defaults to same host as HTTP URL
     grpc_port:   optional; defaults 443 if http_secure else 50051
     grpc_secure: optional; defaults to match HTTP scheme

Embedding (query-time, same as other external adapters):
  embedding_model, embedding_provider, embedding_api_key (BYO or empty for OpenAI/Google platform keys)

Optional:
  text_property     Property name used for text_preview (default "text").
  target_vector     Name of named vector when the collection uses Configure.Vectors.named / multi-vector.
  skip_init_checks  If true, pass skip_init_checks=True to the client (faster / air-gapped).

Notes:
  - Python client v4 requires Weaviate server 1.23.7+ and gRPC reachable (open gRPC port on firewalls).
  - Dimension mismatch (wrong embedding_model vs stored vectors) surfaces as Weaviate errors; we normalize
    common messages in search() similar to Qdrant.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.query import MetadataQuery

from context_jobs.embeddings import embed_query
from context_jobs.ingestion.records import ensure_record_ids
from context_jobs.ingestion.types import UpsertResult
from context_jobs.retrieval.base import NormalizedMatch
from core.config import EMBED_MODEL
from weaviate.classes.config import Configure, DataType, Property, VectorDistances


def normalize_weaviate_cluster_url(url: str) -> str:
    """Strip and ensure Weaviate Cloud REST URL has a scheme.

    Weaviate Cloud consoles often show the REST host without ``https://`` (e.g.
    ``*.gcp.weaviate.cloud``). The Python client expects a proper URL for
    ``connect_to_weaviate_cloud``."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    low = u.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return u
    if "weaviate." in low:
        return "https://" + u.lstrip("/")
    return u


def _distance_to_score(distance: float | None) -> float:
    """Map Weaviate cosine distance to a higher-is-better score (UI parity with other adapters)."""
    if distance is None:
        return 0.0
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return 0.0
    # Cosine distance in [0, 2] for normalized vectors; clamp similarity-style score.
    return max(0.0, min(1.0, 1.0 - d / 2.0))


class WeaviateAdapter:
    provider = "weaviate"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config) if config else {}
        self.collection_name = (
            self.config.get("collection_name") or self.config.get("class_name") or ""
        ).strip()
        if not self.collection_name:
            raise ValueError("Weaviate config requires collection_name (Weaviate v4 collection name).")

        self.deployment = (
            self.config.get("deployment") or self.config.get("weaviate_deployment") or "auto"
        ).strip().lower()
        raw_cluster = (self.config.get("cluster_url") or self.config.get("url") or "").strip()
        self.cluster_url = normalize_weaviate_cluster_url(raw_cluster)
        raw_key = self.config.get("api_key") or self.config.get("weaviate_api_key")
        self.api_key = str(raw_key).strip() if raw_key else None

        self.http_host = (self.config.get("http_host") or "").strip() or None
        self.http_port = self.config.get("http_port")
        self.grpc_host = (self.config.get("grpc_host") or "").strip() or None
        self.grpc_port = self.config.get("grpc_port")
        self.grpc_secure = self.config.get("grpc_secure")

        self.target_vector = (self.config.get("target_vector") or "").strip() or None
        self.text_property = (self.config.get("text_property") or "text").strip() or "text"
        self.embedding_model = self.config.get("embedding_model") or EMBED_MODEL

        self.skip_init_checks = bool(self.config.get("skip_init_checks", False))

    def _resolved_deployment(self) -> str:
        dep = self.deployment
        if dep != "auto":
            return dep
        u = self.cluster_url.lower()
        if "weaviate.network" in u or "weaviate.cloud" in u:
            return "cloud"
        if self.cluster_url:
            return "custom"
        return "local"

    def _open_client(self) -> weaviate.WeaviateClient:
        dep = self._resolved_deployment()
        if dep == "cloud":
            if not self.cluster_url:
                raise ValueError("Weaviate Cloud requires cluster_url (e.g. https://xxx.weaviate.network).")
            if not self.api_key:
                raise ValueError("Weaviate Cloud requires api_key (from Weaviate Cloud console).")
            return weaviate.connect_to_weaviate_cloud(
                cluster_url=self.cluster_url.rstrip("/"),
                auth_credentials=AuthApiKey(api_key=self.api_key),
                skip_init_checks=self.skip_init_checks,
            )

        if dep == "local":
            host = self.http_host or "localhost"
            port = int(self.http_port or 8080)
            grpc_port = int(self.grpc_port or 50051)
            auth = AuthApiKey(api_key=self.api_key) if self.api_key else None
            return weaviate.connect_to_local(
                host=host,
                port=port,
                grpc_port=grpc_port,
                auth_credentials=auth,
                skip_init_checks=self.skip_init_checks,
            )

        if dep == "custom":
            if not self.cluster_url:
                raise ValueError("Weaviate custom deployment requires cluster_url (http(s)://host:port).")
            parsed = urlparse(self.cluster_url)
            host = self.http_host or parsed.hostname
            if not host:
                raise ValueError("Could not parse http host from cluster_url; set http_host explicitly.")
            scheme = (parsed.scheme or "http").lower()
            secure = scheme == "https"
            port = int(self.http_port if self.http_port is not None else (parsed.port or (443 if secure else 8080)))
            gh = self.grpc_host or host
            default_grpc = 443 if secure else 50051
            gp = int(self.grpc_port if self.grpc_port is not None else default_grpc)
            gs = self.grpc_secure if self.grpc_secure is not None else secure
            auth = AuthApiKey(api_key=self.api_key) if self.api_key else None
            return weaviate.connect_to_custom(
                http_host=host,
                http_port=port,
                http_secure=secure,
                grpc_host=gh,
                grpc_port=gp,
                grpc_secure=bool(gs),
                auth_credentials=auth,
                skip_init_checks=self.skip_init_checks,
            )

        raise ValueError(
            f"Unsupported Weaviate deployment={dep!r}. Use cloud | local | custom | auto."
        )

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        _ = filters
        query_vec = embed_query(query_text, self.config)
        client = self._open_client()
        try:
            coll = client.collections.get(self.collection_name)
            nv_kwargs: dict[str, Any] = {
                "near_vector": query_vec,
                "limit": top_k,
                "return_metadata": MetadataQuery(distance=True),
            }
            if self.target_vector:
                nv_kwargs["target_vector"] = self.target_vector

            try:
                resp = coll.query.near_vector(**nv_kwargs)
            except Exception as exc:
                raw = str(exc).lower()
                if "vector" in raw and (
                    "length" in raw
                    or "dimension" in raw
                    or "size" in raw
                    or "len" in raw
                ):
                    raise ValueError(
                        "Weaviate near_vector failed due to vector length / dimension mismatch. "
                        f"embedding_model={self.embedding_model!r} produced length {len(query_vec)}. "
                        "Use the same embedding model (and dimension) as objects stored in this collection. "
                        f"Raw error: {exc}"
                    ) from exc
                raise ValueError(f"Weaviate query failed: {exc}") from exc

            out: list[NormalizedMatch] = []
            for obj in resp.objects or []:
                props: dict[str, Any] = dict(obj.properties or {})
                text_val = props.get(self.text_property)
                preview = (
                    (str(text_val) if text_val is not None else "")
                    or props.get("preview")
                    or props.get("content")
                    or ""
                )[:600]

                dist = None
                if obj.metadata is not None:
                    dist = getattr(obj.metadata, "distance", None)
                score = _distance_to_score(dist)

                oid = str(obj.uuid) if getattr(obj, "uuid", None) is not None else "unknown"
                meta = {k: v for k, v in props.items() if isinstance(k, str)}
                out.append(
                    NormalizedMatch(
                        id=oid,
                        score=score,
                        text_preview=preview,
                        metadata=meta,
                    )
                )
            return out
        finally:
            try:
                client.close()
            except Exception:
                pass

    def test_connection(self) -> tuple[bool, str]:
        try:
            _ = self.search("test connection", top_k=1)
            return True, "Weaviate connection test successful."
        except Exception as exc:
            msg = str(exc)
            low = msg.lower()
            if (
                "embedding http" in low
                or "/v1/embeddings" in low
                or "model_not_found" in low
                or "invalid_request_error" in low
            ):
                return (
                    False,
                    "Query embedding failed (embedding_model, embedding_dimensions, embedding_api_key, or provider). "
                    f"Details: {msg}",
                )
            if "401" in msg or "unauthorized" in low:
                return (
                    False,
                    "Weaviate authentication failed. Check api_key for Cloud or auth on self-hosted. "
                    f"Details: {msg}",
                )
            if "404" in msg or "not found" in low or "does not exist" in low:
                return (
                    False,
                    f"Weaviate reported missing resource (collection={self.collection_name!r}). {msg}",
                )
            if "connection" in low or "refused" in low or "timeout" in low or "unreachable" in low:
                return (
                    False,
                    "Weaviate network error: cannot reach cluster (HTTP/gRPC). Check URL, ports, firewall, "
                    f"and that gRPC is enabled. Details: {msg}",
                )
            return False, f"Weaviate connection failed: {msg}"

    def target_exists(self) -> bool:
        client = self._open_client()
        try:
            return bool(client.collections.exists(self.collection_name))
        except Exception:
            return False
        finally:
            try:
                client.close()
            except Exception:
                pass

    def ensure_target(self, vector_dim: int, distance: str = "cosine", **kwargs: Any) -> tuple[bool, str]:
        _ = vector_dim, kwargs
        client = self._open_client()
        try:
            if client.collections.exists(self.collection_name):
                return True, f"Weaviate collection '{self.collection_name}' already exists."
            distance_map = {
                "cosine": VectorDistances.COSINE,
                "l2": VectorDistances.L2_SQUARED,
                "l2-squared": VectorDistances.L2_SQUARED,
                "dot": VectorDistances.DOT,
                "hamming": VectorDistances.HAMMING,
                "manhattan": VectorDistances.MANHATTAN,
            }
            dist_enum = distance_map.get(distance.lower(), VectorDistances.COSINE)
            client.collections.create(
                name=self.collection_name,
                properties=[
                    Property(name=self.text_property, data_type=DataType.TEXT),
                    Property(name="preview", data_type=DataType.TEXT),
                ],
                vector_config=Configure.Vectors.self_provided(
                    vector_index_config=Configure.VectorIndex.hnsw(distance_metric=dist_enum)
                ),
            )
            return True, f"Created Weaviate collection '{self.collection_name}' (BYO vectors, {distance})."
        except Exception as exc:
            return False, f"Failed to create Weaviate collection: {exc}"
        finally:
            try:
                client.close()
            except Exception:
                pass

    def upsert(self, records: list[dict[str, Any]], batch_size: int = 100) -> UpsertResult:
        ensure_record_ids(records)
        client = self._open_client()
        upserted = 0
        try:
            coll = client.collections.get(self.collection_name)
            for i in range(0, len(records), batch_size):
                for rec in records[i : i + batch_size]:
                    props = dict(rec.get("metadata") or {})
                    text_val = props.get("text") or props.get("preview") or ""
                    if text_val and self.text_property not in props:
                        props[self.text_property] = text_val
                    coll.data.insert(properties=props, vector=rec["values"])
                    upserted += 1
            return UpsertResult(success=True, upserted_count=upserted)
        except Exception as exc:
            return UpsertResult(
                success=False,
                upserted_count=upserted,
                failed_count=len(records) - upserted,
                error=f"Weaviate upsert failed: {exc}",
            )
        finally:
            try:
                client.close()
            except Exception:
                pass
