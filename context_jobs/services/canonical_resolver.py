"""Resolve full canonical contract text for amendment generation.

Resolution waterfall:
  1. canonical_store   — by job_id
  2. canonical_by_contract_id — from parent run source traces
  3. vector_stitch     — reassemble chunks from trusted-source vector hits
  4. knowledge_sources — inline text attached to the job
  5. user_request_snapshot — parent run user_request if contract-shaped
  6. not_found
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.services.canonical_contract import (
    load_canonical_by_contract_id,
    load_canonical_by_source_doc_id,
    load_canonical_for_job,
)
from schemas.context_jobs_model import ContextJobModel, JobRunModel

logger = logging.getLogger(__name__)

_LEGAL_KEYWORDS = re.compile(
    r"(agreement|contract|hereinafter|governing law|indemnif|liability|termination)",
    re.IGNORECASE,
)
_NUMBERING_PATTERN = re.compile(r"^\s*\d+\.\s", re.MULTILINE)


def _extract_contract_ids_from_traces(run: JobRunModel) -> list[str]:
    """Pull contractId values from source_trace_events or retrieval_events."""
    ids: list[str] = []
    for events in (run.source_trace_events, run.retrieval_events):
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            meta = event.get("metadata") or event
            cid = meta.get("contractId") or meta.get("contract_id")
            if cid and str(cid).strip():
                ids.append(str(cid).strip())
            for source in event.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                scid = source.get("contractId") or source.get("contract_id")
                if scid and str(scid).strip():
                    ids.append(str(scid).strip())
    seen: set[str] = set()
    deduped: list[str] = []
    for cid in ids:
        if cid not in seen:
            seen.add(cid)
            deduped.append(cid)
    return deduped


def _try_vector_stitch(
    db: Session,
    owner: str,
    job: ContextJobModel,
) -> str | None:
    """Reassemble contract text from vector store chunks ordered by chunk_index."""
    trusted_sources = job.trusted_sources
    if not trusted_sources:
        return None

    try:
        from context_jobs.managed_jet_kb import ensure_managed_namespace
        from context_jobs.retrieval.factory import get_retrieval_adapter
        from context_jobs.retrieval.trusted_sources import build_trusted_sources_metadata_filter

        metadata_filter = build_trusted_sources_metadata_filter(trusted_sources)
        if not metadata_filter:
            return None

        retrieval_mode = (job.retrieval_mode or "jet_kb").lower()
        if retrieval_mode == "external":
            if not job.vector_connection_id:
                return None
            from context_jobs.retrieval.security import decrypt_config, hydrate_embedding_credentials
            from context_jobs.vector_connection_services import get_active_connection_for_owner

            vector_conn = get_active_connection_for_owner(db, job.vector_connection_id, job.owner)
            conn_config = hydrate_embedding_credentials(
                decrypt_config(vector_conn.encrypted_config or {}),
                db=db,
                owner=job.owner,
            )
            adapter = get_retrieval_adapter(vector_conn.provider, conn_config)
        else:
            namespace = ensure_managed_namespace(db, owner)
            adapter = get_retrieval_adapter("jet_kb", {"namespace": namespace})

        search_fn = getattr(adapter, "search_by_metadata_filter", None)
        if not callable(search_fn):
            return None

        matches = search_fn(metadata_filter, top_k=200) or []
        if not matches:
            return None

        by_source: dict[str, list[tuple[int, str]]] = {}
        for match in matches:
            meta = getattr(match, "metadata", None) or {}
            source_id = str(
                meta.get("source_doc_id")
                or meta.get("documentName")
                or meta.get("file")
                or "unknown"
            )
            chunk_idx = 0
            raw_idx = meta.get("chunk_index") or meta.get("chunkIndex")
            if raw_idx is not None:
                try:
                    chunk_idx = int(raw_idx)
                except (TypeError, ValueError):
                    pass
            preview = getattr(match, "text_preview", None) or meta.get("preview") or ""
            by_source.setdefault(source_id, []).append((chunk_idx, str(preview)))

        best_source = max(by_source, key=lambda k: len(by_source[k]))
        chunks = by_source[best_source]
        chunks.sort(key=lambda c: c[0])
        stitched = "\n\n".join(text for _, text in chunks)
        if len(stitched) < 200:
            return None
        return stitched
    except Exception:
        logger.debug("vector_stitch failed", exc_info=True)
        return None


def _try_knowledge_sources(job: ContextJobModel) -> str | None:
    """Check retrieval_config.knowledgeSources for inline contract text."""
    retrieval_config = job.retrieval_config
    if not isinstance(retrieval_config, dict):
        return None
    sources = retrieval_config.get("knowledgeSources")
    if not isinstance(sources, list):
        return None

    for source in sources:
        if not isinstance(source, dict):
            continue
        if str(source.get("type") or "").lower() != "text":
            continue
        value = str(source.get("value") or "").strip()
        if not value or len(value) < 500:
            continue
        label = str(source.get("label") or "").lower()
        label_looks_contract = any(kw in label for kw in ("agreement", "contract", "msa"))
        if label_looks_contract or len(value) > 1000:
            return value
    return None


def _try_user_request(parent_run: JobRunModel) -> str | None:
    """Use parent run's user_request if it looks like a pasted contract."""
    text = (parent_run.user_request or "").strip()
    if len(text) < 1000:
        return None
    numbering_matches = len(_NUMBERING_PATTERN.findall(text[:3000]))
    legal_matches = len(_LEGAL_KEYWORDS.findall(text[:3000]))
    if numbering_matches >= 3 and legal_matches >= 2:
        return text
    return None


def resolve_canonical_source(
    db: Session,
    owner: str,
    parent_run: JobRunModel,
    parent_job: ContextJobModel,
) -> tuple[str | None, str]:
    """Return (full_text, resolution_method) or (None, "not_found")."""

    # 1. Canonical by job_id
    text = load_canonical_for_job(db, owner, parent_job.id)
    if text:
        return text, "canonical_store"

    # 2. Canonical by contract_id from parent run source traces
    for cid in _extract_contract_ids_from_traces(parent_run):
        text = load_canonical_by_contract_id(db, owner, cid)
        if text:
            return text, "canonical_by_contract_id"

    # 3. Trusted-sources vector stitch
    text = _try_vector_stitch(db, owner, parent_job)
    if text:
        return text, "vector_stitch"

    # 4. Job knowledgeSources inline text
    text = _try_knowledge_sources(parent_job)
    if text:
        return text, "knowledge_sources"

    # 5. Parent run user_request snapshot
    text = _try_user_request(parent_run)
    if text:
        return text, "user_request_snapshot"

    return None, "not_found"
