"""
Core ingestion service for Context Jobs.

Orchestrates validation, chunking, embedding, and upsert via retrieval adapters.
Callable from HTTP API, orchestrator tools, scripts, or admin jobs.
"""


# NOTE: Embedding always uses OpenAI (via embed_config from vector connection).
# The job's executionProvider (anthropic/openai/google) only affects LLM execution,
# not embedding. An OpenAI API key must be configured in the vector connection
# regardless of which LLM provider the job uses.


from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

_timing_log = logging.getLogger("context_jobs.ingestion.timing")


def _timing_on() -> bool:
    return os.environ.get("INGESTION_TIMING", "").strip().lower() in ("1", "true", "yes")


def _log_step(step: str, seconds: float, **extra: Any) -> None:
    if not _timing_on():
        return
    parts = " ".join(f"{k}={v}" for k, v in extra.items())
    suffix = f" {parts}" if parts else ""
    _timing_log.info("[ingestion timing] %s %.3fs%s", step, seconds, suffix)

from context_jobs.ingestion.chunk_processor import chunk_documents
from context_jobs.ingestion.config import merge_ingestion_config
from context_jobs.ingestion.metadata import normalize_document_metadata
from context_jobs.ingestion.metadata_inference import (
    infer_document_metadata_from_llm,
    merge_inferred_metadata,
)
from context_jobs.text_sanitize import sanitize_db_text, sanitize_for_db
from context_jobs.ingestion.embedding_processor import embed_chunks
from context_jobs.ingestion.pipeline import (
    build_upsert_records,
    ensure_vector_target,
    evaluate_validation_checks,
    map_upsert_failure,
)
from context_jobs.ingestion.target_resolver import resolve_ingestion_target
from context_jobs.ingestion.types import IngestionResult, IngestionTarget
from context_jobs.ingestion.validation import (
    ValidationCheck,
    check_quota_error,
    validate_dimension_match,
    validate_embedding_key,
    validate_target_exists,
)
from schemas.context_jobs_model import ContextJobModel


_SAFE_META_KEY = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_KNOWN_META_KEYS = frozenset(
    {
        "name",
        "title",
        "documentName",
        "document_name",
        "documentType",
        "document_type",
        "contractId",
        "contract_id",
        "contractName",
        "vendor",
        "vendorName",
        "vendor_name",
        "vendorId",
        "vendor_id",
        "expiryDate",
        "expiry_date",
        "complexityTier",
        "complexity_tier",
        "description",
        "category",
        "workspace_id",
        "workspaceId",
        "file",
        "source",
        "url",
    }
)
_MAX_CUSTOM_META_KEYS = 24
_MAX_META_VALUE_LEN = 512


def _coerce_metadata(metadata: Any) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if isinstance(metadata, str):
        return {"name": metadata, "title": metadata}
    if hasattr(metadata, "model_dump"):
        dumped = metadata.model_dump(by_alias=True, exclude_none=True)
        return _coerce_metadata(dumped) if dumped else None
    if isinstance(metadata, dict):
        out: dict[str, Any] = {}
        custom_count = 0
        for key, value in metadata.items():
            if not isinstance(key, str) or value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if key in _KNOWN_META_KEYS:
                if isinstance(value, (str, int, float, bool)):
                    out[key] = value if not isinstance(value, str) else value.strip()
                continue
            # Custom keys for trusted-source scoping (stringified scalars only).
            if not _SAFE_META_KEY.match(key):
                continue
            if custom_count >= _MAX_CUSTOM_META_KEYS:
                continue
            if isinstance(value, bool):
                out[key] = "true" if value else "false"
            elif isinstance(value, (int, float)):
                out[key] = str(value)[:_MAX_META_VALUE_LEN]
            elif isinstance(value, str):
                out[key] = value.strip()[:_MAX_META_VALUE_LEN]
            else:
                continue
            custom_count += 1

        doc_name = (
            out.get("name")
            or out.get("documentName")
            or out.get("document_name")
            or out.get("title")
            or out.get("file")
        )
        if doc_name:
            out.setdefault("name", doc_name)
            out.setdefault("title", doc_name)
            out.setdefault("file", doc_name)
            out.setdefault("source", doc_name)
        return out or None
    return None


def _normalize_documents(documents: list[Any]) -> list[dict[str, Any]]:
    """Accept dicts or Pydantic models; infer metadata via LLM, then normalize for upsert."""
    normalized: list[dict[str, Any]] = []
    for item in documents:
        if hasattr(item, "model_dump"):
            d = item.model_dump(by_alias=True, exclude_none=True)
        elif isinstance(item, dict):
            d = dict(item)
        else:
            d = {"text": str(item), "metadata": None, "id": None}

        # Paste ingest often omits id. Using doc_0 for every paste causes later
        # ingestions (e.g. policy after contract) to overwrite earlier vectors
        # that share the same deterministic point ids (doc_0-chunk-N).
        raw_id = d.get("id")
        doc_id = str(raw_id).strip() if raw_id is not None else ""
        if not doc_id:
            doc_id = str(uuid.uuid4())
        text = sanitize_db_text(d.get("text") or "").strip()
        client_meta = sanitize_for_db(_coerce_metadata(d.get("metadata")))
        title_hint = None
        if isinstance(client_meta, dict):
            title_hint = client_meta.get("title") or client_meta.get("name")
        # Skip LLM when caller already forced the fields alerts/monitor need.
        forced_ready = bool(
            isinstance(client_meta, dict)
            and client_meta.get("documentType")
            and (client_meta.get("contractId") or client_meta.get("contract_id"))
            and (client_meta.get("expiryDate") or client_meta.get("expiry_date"))
        )
        inferred = {} if forced_ready else infer_document_metadata_from_llm(text, title_hint=title_hint)
        merged_meta = merge_inferred_metadata(client_meta, inferred)
        meta = normalize_document_metadata(
            merged_meta,
            doc_id=doc_id,
            text=text,
        )
        normalized.append(
            {
                "text": text,
                "metadata": meta,
                "id": doc_id,
            }
        )
    return normalized


def run_preflight_checks(
    embed_config: dict[str, Any],
    provider: str,
    target_name: str,
    target_dimension: int | None,
    target_exists: bool,
    auto_create: bool,
) -> tuple[bool, bool, list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    checks: list[ValidationCheck] = [
        validate_embedding_key(embed_config),
        validate_dimension_match(embed_config, target_dimension),
        validate_target_exists(provider, target_name, exists=target_exists, auto_create=auto_create),
    ]
    return evaluate_validation_checks(checks)


def ingest_documents(
    job: ContextJobModel,
    documents: list[Any],
    db: Session,
    ingestion_config: dict[str, Any] | None = None,
) -> IngestionResult:
    """Ingest documents into the job's vector target (managed Jet KB or external connection)."""
    target = resolve_ingestion_target(db, job)
    return ingest_to_target(target, documents, db, ingestion_config=ingestion_config)


def ingest_to_target(
    target: IngestionTarget,
    documents: list[Any],
    db: Session,
    ingestion_config: dict[str, Any] | None = None,
) -> IngestionResult:
    """Ingest documents into a resolved vector target."""
    cfg = merge_ingestion_config(ingestion_config)
    documents = _normalize_documents(documents)
    auto_create = bool(cfg["auto_create_target"])
    chunk_size = int(cfg["chunk_size"])
    chunk_overlap = int(cfg["chunk_overlap"])
    batch_size = int(cfg["batch_size"])

    validation_events: list[dict[str, Any]] = []
    warnings: list[str] = []
    exceptions: list[dict[str, Any]] = []
    t_total = time.perf_counter()
    total_chars = sum(len((d.get("text") or "")) for d in documents)

    try:
        t0 = time.perf_counter()
        adapter = target.adapter
        _log_step(
            "resolve_target",
            time.perf_counter() - t0,
            provider=target.provider,
            target=target.target_name,
        )

        # Only hit the vector store for existence when it affects the outcome.
        # - jet_kb: namespace comes from DB; Pinecone creates namespace on first upsert.
        # - auto_create_target: validation passes without a remote exists check.
        t0 = time.perf_counter()
        if target.provider == "jet_kb" or auto_create:
            target_exists_flag = True
            skipped_exists_check = True
        else:
            skipped_exists_check = False
            target_exists_flag = adapter.target_exists()
        _log_step(
            "target_exists_check",
            time.perf_counter() - t0,
            skipped=skipped_exists_check,
            exists=target_exists_flag,
        )

        t0 = time.perf_counter()
        any_blocking, any_error, validation_events, warnings, exceptions = run_preflight_checks(
            target.embed_config,
            target.provider,
            target.target_name,
            target.target_dimension,
            target_exists_flag,
            auto_create,
        )
        _log_step("preflight_validation", time.perf_counter() - t0)

        if any_blocking:
            return IngestionResult(
                status="escalated",
                outcome="blocked_by_policy",
                next_action={"type": "escalate", "label": "Fix validation errors before ingestion"},
                validation_events=validation_events,
                warnings=warnings,
                exceptions=exceptions,
                error="Pre-flight validation failed with blocking errors.",
            )

        if any_error:
            return IngestionResult(
                status="repair",
                outcome="needs_review",
                next_action={"type": "repair_and_rerun", "label": "Fix errors or enable auto_create_target"},
                validation_events=validation_events,
                warnings=warnings,
                error="Pre-flight validation failed with errors.",
            )

        t0 = time.perf_counter()
        chunks = chunk_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        _log_step(
            "chunk_documents",
            time.perf_counter() - t0,
            docs=len(documents),
            chunks=len(chunks),
            chars=total_chars,
        )
        if not chunks:
            return IngestionResult(
                status="completed",
                outcome="accepted",
                next_action={"type": "use_result", "label": "No chunks to ingest"},
                upserted_count=0,
                validation_events=validation_events,
            )

        t0 = time.perf_counter()
        embedded = embed_chunks(chunks, target.embed_config, batch_size=batch_size)
        _log_step("embed_chunks_openai", time.perf_counter() - t0, chunks=len(chunks))

        t0 = time.perf_counter()
        records = build_upsert_records(embedded)
        vector_dim = len(records[0]["values"]) if records else (target.target_dimension or 1536)
        _log_step("build_records", time.perf_counter() - t0, records=len(records), dim=vector_dim)

        t0 = time.perf_counter()
        ok, ensure_msg = ensure_vector_target(adapter, vector_dim, auto_create)
        _log_step("ensure_target", time.perf_counter() - t0)
        if not ok:
            return IngestionResult(
                status="failed",
                outcome="failed",
                next_action={"type": "escalate", "label": "Failed to create vector target"},
                validation_events=validation_events,
                error=ensure_msg,
            )
        if ensure_msg:
            warnings.append(ensure_msg)

        t0 = time.perf_counter()
        upsert_result = adapter.upsert(records, batch_size=batch_size)
        _log_step(
            "pinecone_upsert",
            time.perf_counter() - t0,
            upserted=upsert_result.upserted_count,
        )

        if not upsert_result.success:
            mapped = map_upsert_failure(upsert_result, target.provider, validation_events, exceptions)
            if mapped:
                return IngestionResult(**mapped)
            return IngestionResult(
                status="failed",
                outcome="failed",
                next_action={"type": "retry", "label": "Retry after resolving error"},
                upserted_count=upsert_result.upserted_count,
                failed_count=upsert_result.failed_count,
                validation_events=validation_events,
                error=upsert_result.error,
            )

        if upsert_result.warnings:
            warnings.extend(upsert_result.warnings)

        ingested_sources = [
            {
                "id": doc.get("id"),
                "label": (doc.get("metadata") or {}).get("file"),
                "contractId": (doc.get("metadata") or {}).get("contractId"),
                "vendor": (doc.get("metadata") or {}).get("vendor"),
                "vendorId": (doc.get("metadata") or {}).get("vendorId"),
                "capabilities": (doc.get("metadata") or {}).get("capabilities"),
                "expiryDate": (doc.get("metadata") or {}).get("expiryDate"),
                "documentType": (doc.get("metadata") or {}).get("documentType"),
            }
            for doc in documents
        ]

        has_warnings = bool(warnings)
        _log_step(
            "ingest_total",
            time.perf_counter() - t_total,
            provider=target.provider,
            upserted=upsert_result.upserted_count,
        )
        return IngestionResult(
            status="completed_with_warnings" if has_warnings else "completed",
            outcome="accepted_with_warnings" if has_warnings else "accepted",
            next_action=(
                {"type": "review_result", "label": "Review warnings"}
                if has_warnings
                else {"type": "use_result", "label": "Ingestion complete"}
            ),
            upserted_count=upsert_result.upserted_count,
            failed_count=upsert_result.failed_count,
            validation_events=validation_events,
            warnings=warnings,
            ingested_sources=ingested_sources,
        )

    except ValueError as exc:
        return IngestionResult(
            status="failed",
            outcome="failed",
            next_action={"type": "repair_and_rerun", "label": str(exc)},
            validation_events=validation_events,
            error=str(exc),
        )
    except Exception as exc:
        prov = target.provider if target else "unknown"
        quota_check = check_quota_error(exc, prov)
        if quota_check:
            validation_events.append(quota_check.to_dict())
            exceptions.append(
                {
                    "code": quota_check.code,
                    "message": quota_check.message,
                    "severity": "blocking",
                    "suggestedAction": quota_check.suggested_action,
                }
            )
            return IngestionResult(
                status="escalated",
                outcome="blocked_by_policy",
                next_action={"type": "escalate", "label": "Quota or limit exceeded"},
                validation_events=validation_events,
                exceptions=exceptions,
                error=str(exc),
            )
        return IngestionResult(
            status="failed",
            outcome="failed",
            next_action={"type": "escalate", "label": "Unexpected error during ingestion"},
            validation_events=validation_events,
            error=f"Ingestion failed: {exc}",
        )


def validate_ingestion_setup(
    config: dict[str, Any],
    provider: str,
    target_name: str | None,
    target_dimension: int | None,
    auto_create: bool,
    target_exists: bool = False,
) -> list[dict[str, Any]]:
    """Public helper: run pre-flight checks only (no embed/upsert)."""
    _blocking, _error, events, _warnings, _exceptions = run_preflight_checks(
        config,
        provider,
        target_name or "",
        target_dimension,
        target_exists,
        auto_create,
    )
    return events
