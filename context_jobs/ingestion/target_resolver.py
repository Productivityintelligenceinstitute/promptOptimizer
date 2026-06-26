"""Resolve ingestion target (adapter + config) from a Context Job."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.embeddings.registry import MODEL_DEFAULT_DIMS
from context_jobs.ingestion.types import IngestionTarget, VectorIngestionAdapter
from context_jobs.managed_jet_kb import ensure_managed_namespace
from context_jobs.vector_connection_services import (
    decrypt_config,
    get_active_connection_for_owner,
)
from core.config import EMBED_MODEL
from schemas.context_jobs_model import ContextJobModel
from schemas.context_vector_connection_model import ContextVectorConnectionModel


def resolve_ingestion_target(db: Session, job: ContextJobModel) -> IngestionTarget:
    """
    Build an IngestionTarget for the job's retrieval mode (managed Jet KB or external).
    """
    from context_jobs.retrieval.factory import get_retrieval_adapter

    owner = (job.owner or "current_user").strip() or "current_user"
    mode = (job.retrieval_mode or "jet_kb").lower()

    if mode == "jet_kb":
        namespace = ensure_managed_namespace(db, owner)
        embed_config: dict[str, Any] = {
            "embedding_model": EMBED_MODEL,
            "embedding_provider": "openai",
        }
        dim = MODEL_DEFAULT_DIMS.get(EMBED_MODEL)
        adapter: VectorIngestionAdapter = get_retrieval_adapter("jet_kb", {"namespace": namespace})
        return IngestionTarget(
            provider="jet_kb",
            embed_config=embed_config,
            target_name=namespace,
            target_dimension=dim,
            adapter=adapter,
        )

    conn_id = job.vector_connection_id
    if not conn_id:
        raise ValueError(
            "retrievalMode external requires vectorConnectionId (pick a saved connection)."
        )

    vector_conn = get_active_connection_for_owner(db, conn_id, owner)
    return _ingestion_target_from_connection(vector_conn)


def resolve_external_ingestion_target(
    db: Session,
    owner: str,
    vector_connection_id: UUID,
) -> IngestionTarget:
    """Build an ingestion target from a saved external vector connection (no job required)."""
    vector_conn = get_active_connection_for_owner(db, vector_connection_id, owner)
    return _ingestion_target_from_connection(vector_conn)


def _ingestion_target_from_connection(
    vector_conn: ContextVectorConnectionModel,
) -> IngestionTarget:
    from context_jobs.retrieval.factory import get_retrieval_adapter

    embed_config = decrypt_config(vector_conn.encrypted_config or {})
    provider = (vector_conn.provider or "").lower().strip()
    adapter: VectorIngestionAdapter = get_retrieval_adapter(provider, embed_config)

    return IngestionTarget(
        provider=provider,
        embed_config=embed_config,
        target_name=_target_name_for_provider(provider, embed_config),
        target_dimension=_target_dimension_for_provider(provider, embed_config),
        adapter=adapter,
    )


def _target_name_for_provider(provider: str, config: dict[str, Any]) -> str:
    if provider == "pinecone":
        return (config.get("namespace") or config.get("index_name") or "").strip()
    if provider == "qdrant":
        return (config.get("collection_name") or "").strip()
    if provider == "weaviate":
        return (config.get("collection_name") or config.get("class_name") or "").strip()
    if provider in {"pgvector", "pg_vector", "postgres", "postgresql"}:
        return (config.get("table_name") or "").strip()
    return ""


def _target_dimension_for_provider(provider: str, config: dict[str, Any]) -> int | None:
    if provider == "pinecone":
        raw = config.get("index_dimension")
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    model = (config.get("embedding_model") or EMBED_MODEL).strip()
    user_dim = config.get("embedding_dimensions")
    if user_dim is not None:
        try:
            return int(user_dim)
        except (TypeError, ValueError):
            pass
    return MODEL_DEFAULT_DIMS.get(model)
