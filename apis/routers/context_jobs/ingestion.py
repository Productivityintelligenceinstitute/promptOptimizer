from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.errors import raise_context_jobs_http
from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services
from context_jobs.ingestion.ingestion_service import ingest_documents
from context_jobs.ingestion.types import IngestionResult


router = APIRouter(tags=["Context Jobs"])


def _raise_for_ingestion_result(result: IngestionResult) -> None:
    if result.status in {"escalated", "blocked_by_policy"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result.to_dict())
    if result.status in ("failed", "repair"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.to_dict())


def _ingestion_response(result: IngestionResult, **extra: Any) -> dict[str, Any]:
    response = result.to_dict()
    response.update(extra)
    return response


@router.post("/ingest/external", response_model=dict[str, Any])
async def ingest_into_external_db(
    payload: cj_schemas.ExternalIngestionRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    """
    Ingest documents into a saved external vector DB without linking a job.

    Contract metadata (contractId, vendor, expiryDate) is normalized on ingest.
    When creating a job, set retrievalMode=external and vectorConnectionId to the
    same connection so runs retrieve from this store.
    """
    try:
        result = cj_services.ingest_to_external_db(
            db=db,
            owner=owner,
            vector_connection_id=payload.vector_connection_id,
            documents=payload.documents,
            ingestion_config=payload.ingestion_config,
        )
        _raise_for_ingestion_result(result)
        return _ingestion_response(
            result,
            vectorConnectionId=str(payload.vector_connection_id),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/jobs/{job_id}/ingest/external", response_model=dict[str, Any])
async def ingest_job_into_external_db(
    job_id: UUID,
    payload: cj_schemas.ExternalIngestionRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    """
    Link a job to an external vector connection and ingest documents.

    Sets retrievalMode=external on the job, then ingests with contract metadata
    normalization (same path as managed Jet KB ingest).
    """
    try:
        result = cj_services.ingest_job_to_external_db(
            db=db,
            owner=owner,
            job_id=job_id,
            vector_connection_id=payload.vector_connection_id,
            documents=payload.documents,
            ingestion_config=payload.ingestion_config,
        )
        _raise_for_ingestion_result(result)
        return _ingestion_response(
            result,
            jobId=str(job_id),
            vectorConnectionId=str(payload.vector_connection_id),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/jobs/{job_id}/ingest", response_model=dict[str, Any])
async def ingest_into_job(
    job_id: UUID,
    payload: cj_schemas.IngestionRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    """
    Ingest documents into the job's configured vector target.

    Uses managed Jet KB when retrievalMode is jet_kb (default), or the job's
    saved vectorConnectionId when retrievalMode is external.
    """
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    try:
        result = ingest_documents(
            job=job,
            documents=payload.documents,
            db=db,
            ingestion_config=payload.ingestion_config,
        )
        _raise_for_ingestion_result(result)
        return _ingestion_response(result, jobId=str(job_id))

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Ingestion failed: {exc}"},
        ) from exc
