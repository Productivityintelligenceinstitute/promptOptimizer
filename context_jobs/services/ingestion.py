"""Context Jobs ingestion service helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from context_jobs import schemas as cj_schemas
from context_jobs.ingestion.ingestion_service import ingest_to_target
from context_jobs.ingestion.target_resolver import resolve_external_ingestion_target
from context_jobs.ingestion.types import IngestionResult
from context_jobs.plan_entitlements import ensure_context_jobs_access
from context_jobs.services.job_queries import get_job
from context_jobs.services.jobs import update_job


def ingest_to_external_db(
    db: Session,
    owner: str,
    vector_connection_id: UUID,
    documents: list[Any],
    ingestion_config: dict[str, Any] | None = None,
) -> IngestionResult:
    """
    Ingest documents into a saved external vector connection without linking a job.

    Documents receive the same text sanitization and contract metadata enrichment
    as job-scoped ingestion (contractId, vendor, expiryDate, file labels).
    """
    ensure_context_jobs_access(db, owner)
    target = resolve_external_ingestion_target(db, owner, vector_connection_id)
    result = ingest_to_target(
        target,
        documents,
        db,
        ingestion_config=ingestion_config,
    )
    cj_audit.write_audit_event(
        db,
        event_type="ingestion.external",
        entity_type="vector_connection",
        entity_id=str(vector_connection_id),
        actor=owner,
        metadata={
            "vectorConnectionId": str(vector_connection_id),
            "provider": target.provider,
            "targetName": target.target_name,
            "status": result.status,
            "upsertedCount": result.upserted_count,
            "ingestedSources": result.ingested_sources,
        },
    )
    return result


def ingest_job_to_external_db(
    db: Session,
    owner: str,
    job_id: UUID,
    vector_connection_id: UUID,
    documents: list[Any],
    ingestion_config: dict[str, Any] | None = None,
) -> IngestionResult:
    """
    Wire a job to an external vector connection and ingest documents into it.

    Updates the job to retrievalMode=external + vectorConnectionId, then ingests
    with the same metadata normalization as managed Jet KB ingestion.
    """
    ensure_context_jobs_access(db, owner)
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")

    update_job(
        db,
        owner,
        job,
        cj_schemas.ContextJobUpdate(
            retrieval_mode="external",
            vector_connection_id=vector_connection_id,
        ),
    )

    result = ingest_to_external_db(
        db=db,
        owner=owner,
        vector_connection_id=vector_connection_id,
        documents=documents,
        ingestion_config=ingestion_config,
    )
    cj_audit.write_audit_event(
        db,
        event_type="ingestion.job_external",
        entity_type="job",
        entity_id=str(job_id),
        actor=owner,
        metadata={
            "jobId": str(job_id),
            "vectorConnectionId": str(vector_connection_id),
            "status": result.status,
            "upsertedCount": result.upserted_count,
            "ingestedSources": result.ingested_sources,
        },
    )
    return result
