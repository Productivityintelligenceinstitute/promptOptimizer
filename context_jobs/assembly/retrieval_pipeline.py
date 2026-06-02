"""Enhanced retrieval pipeline for Context Jobs runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from context_jobs.managed_jet_kb import ensure_managed_namespace
from context_jobs.retrieval.factory import get_retrieval_adapter
from context_jobs.retrieval.security import decrypt_config
from context_jobs.vector_connection_services import get_active_connection_for_owner
from schemas.context_jobs_model import ContextJobModel
from schemas.context_vector_connection_model import ContextVectorConnectionModel


@dataclass
class RetrievalResult:
    rag_context: str
    retrieval_events: list[dict[str, Any]]
    source_trace_events: list[dict[str, Any]]


def _score_to_strength(score: float | None) -> str:
    try:
        val = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        val = 0.0
    if val >= 0.7:
        return "strong"
    if val >= 0.45:
        return "moderate"
    return "weak"


def _apply_trusted_sources_filter(
    matches: list[Any],
    trusted_sources: list[dict] | None,
) -> list[Any]:
    if not trusted_sources:
        return matches
    allowed = {
        (s.get("value") or s.get("name") or "").lower()
        for s in trusted_sources
        if isinstance(s, dict)
    }
    if not allowed:
        return matches
    filtered = []
    for m in matches:
        meta = getattr(m, "metadata", None) or {}
        source_name = (meta.get("file") or meta.get("source") or meta.get("url") or "").lower()
        if any(a in source_name or source_name in a for a in allowed if a):
            filtered.append(m)
    return filtered or matches


def execute_retrieval(job: ContextJobModel, user_request: str, db: Session) -> RetrievalResult:
    retrieval_config = job.retrieval_config or {}
    top_k = 8
    if isinstance(retrieval_config, dict):
        try:
            top_k = int(retrieval_config.get("maxDocuments") or top_k)
        except (TypeError, ValueError):
            top_k = 8
    top_k = max(1, min(50, top_k))

    combined_query = f"{job.goal or ''}\n\n{user_request or ''}".strip() or "general request"
    if isinstance(retrieval_config, dict) and retrieval_config.get("queryRewriting"):
        combined_query = f"{combined_query}\n\nRelated terms: {job.name or ''}"

    retrieval_mode = (job.retrieval_mode or "jet_kb").lower()
    adapter = None
    if retrieval_mode == "external":
        if not job.vector_connection_id:
            raise ValueError("Job retrieval_mode is external but vector_connection_id is not set.")
        vector_conn = get_active_connection_for_owner(db, job.vector_connection_id, job.owner)
        conn_config = decrypt_config(vector_conn.encrypted_config or {})
        adapter = get_retrieval_adapter(vector_conn.provider, conn_config)
    else:
        namespace = ensure_managed_namespace(db, job.owner)
        adapter = get_retrieval_adapter("jet_kb", {"namespace": namespace})

    matches = adapter.search(combined_query, top_k=top_k) or []
    matches = _apply_trusted_sources_filter(matches, job.trusted_sources)

    if isinstance(retrieval_config, dict) and retrieval_config.get("reranking"):
        matches = sorted(matches, key=lambda m: getattr(m, "score", 0) or 0, reverse=True)

    context_blocks: list[str] = []
    retrieval_events: list[dict[str, Any]] = []
    source_trace_events: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for match in matches:
        meta = getattr(match, "metadata", None) or {}
        file_name = meta.get("file") or meta.get("source") or "Workspace Knowledge"
        preview = (getattr(match, "text_preview", None) or meta.get("preview") or "")[:600]
        score = getattr(match, "score", None)
        evidence_strength = _score_to_strength(score)

        context_blocks.append(f"[source:{file_name}]\n{preview}")
        retrieval_events.append(
            {
                "query": combined_query,
                "source": file_name,
                "resultCount": 1,
                "timestamp": now_iso,
            }
        )
        source_trace_events.append(
            {
                "sourceId": str(getattr(match, "id", file_name)),
                "sourceName": file_name,
                "sourceType": meta.get("source") or "document",
                "factsCited": 1,
                "trustLevel": "preferred",
                "lastUpdated": None,
                "freshnessStatus": "current",
                "warnings": ["WEAK_EVIDENCE"] if evidence_strength == "weak" else [],
                "evidenceStrength": evidence_strength,
            }
        )

    rag_context = "\n\n---\n\n".join(context_blocks) if context_blocks else "No context retrieved."
    return RetrievalResult(
        rag_context=rag_context,
        retrieval_events=retrieval_events,
        source_trace_events=source_trace_events,
    )
