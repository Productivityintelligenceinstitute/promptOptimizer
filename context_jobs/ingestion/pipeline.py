"""Reusable ingestion pipeline helpers (validation → vectors → result mapping)."""

from __future__ import annotations

import uuid
from typing import Any

from context_jobs.ingestion.records import ensure_record_ids
from context_jobs.ingestion.types import UpsertResult
from context_jobs.ingestion.validation import ValidationCheck, check_quota_error
from context_jobs.text_sanitize import sanitize_db_text


def build_upsert_records(embedded_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize embedded chunks into provider-neutral upsert records.

    Each record: {id, values, metadata} plus provider aliases set in adapters.
    """
    records: list[dict[str, Any]] = []
    for idx, emb in enumerate(embedded_chunks):
        meta = dict(emb.get("metadata") or {})
        if emb.get("text"):
            clean_text = sanitize_db_text(emb["text"])
            meta.setdefault("preview", clean_text[:300])
            meta.setdefault("text", clean_text)
        rid = emb.get("source_doc_id")
        if rid is not None and emb.get("chunk_index") is not None:
            rid = f"{rid}-chunk-{emb['chunk_index']}"
        records.append(
            {
                "id": rid or str(uuid.uuid4()),
                "values": emb["embedding"],
                "metadata": meta,
            }
        )
    ensure_record_ids(records)
    return records


def evaluate_validation_checks(
    checks: list[ValidationCheck],
) -> tuple[bool, bool, list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """
    Aggregate validation checks into flags and event payloads.

    Returns:
        (any_blocking, any_error, validation_events, warnings, exceptions)
    """
    validation_events: list[dict[str, Any]] = []
    warnings: list[str] = []
    exceptions: list[dict[str, Any]] = []
    any_blocking = False
    any_error = False

    for check in checks:
        validation_events.append(check.to_dict())
        if check.passed:
            continue
        if check.severity == "blocking":
            any_blocking = True
            exceptions.append(
                {
                    "code": check.code or "validation_failed",
                    "message": check.message,
                    "severity": "blocking",
                    "suggestedAction": check.suggested_action,
                }
            )
        elif check.severity == "error":
            any_error = True
            warnings.append(check.message)

    return any_blocking, any_error, validation_events, warnings, exceptions


def map_upsert_failure(
    upsert_result: UpsertResult,
    provider: str,
    validation_events: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    If upsert failed, return IngestionResult kwargs dict for escalation/failure.
    Returns None if caller should use default failed mapping.
    """
    if upsert_result.success or not upsert_result.error:
        return None
    quota_check = check_quota_error(Exception(upsert_result.error), provider)
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
        return {
            "status": "escalated",
            "outcome": "blocked_by_policy",
            "next_action": {"type": "escalate", "label": "Quota or limit exceeded"},
            "upserted_count": upsert_result.upserted_count,
            "failed_count": upsert_result.failed_count,
            "validation_events": validation_events,
            "warnings": [],
            "exceptions": exceptions,
            "error": upsert_result.error,
        }
    return None


def ensure_vector_target(adapter: Any, vector_dim: int, auto_create: bool) -> tuple[bool, str]:
    """
    Optionally create namespace/collection/table when auto_create is enabled.

    Returns (success, message). Message is informational on success (e.g. already exists).
    """
    if not auto_create or not hasattr(adapter, "ensure_target"):
        return True, ""
    return adapter.ensure_target(vector_dim=vector_dim)
