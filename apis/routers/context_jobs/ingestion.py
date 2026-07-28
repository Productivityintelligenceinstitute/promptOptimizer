import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from constants.file_types import ALLOWED_EXTS
from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.errors import raise_context_jobs_http
from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services
from context_jobs.ingestion.ingestion_service import ingest_documents
from context_jobs.ingestion.types import IngestionResult
from utils.reader import read_file

import json


router = APIRouter(tags=["Context Jobs"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB per file
MAX_UPLOAD_FILES = 20


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


def _extract_text_from_upload(upload: UploadFile, raw: bytes) -> str:
    """Persist upload to a temp file with its extension and extract text via read_file."""
    ext = Path(upload.filename or "").suffix.lower()
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        return read_file(tmp_path)
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/jobs/{job_id}/ingest/upload", response_model=dict[str, Any])
async def ingest_files_into_job(
    job_id: UUID,
    files: list[UploadFile] = File(...),
    metadata_json: str | None = Form(None, alias="metadataJson"),
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    """
    Upload PDF, DOCX, or plain-text files; the server extracts text and ingests it
    into the job's configured vector target (managed Jet KB or external connection).

    Optional form field ``metadataJson``: JSON object of string metadata applied to
    every uploaded file (merged with documentName=filename) for trusted-source scoping.
    """
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files uploaded (max {MAX_UPLOAD_FILES}).",
        )

    shared_meta: dict[str, Any] = {}
    if metadata_json and metadata_json.strip():
        try:
            parsed = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"metadataJson must be valid JSON: {exc}",
            ) from exc
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metadataJson must be a JSON object of key/value pairs.",
            )
        shared_meta = parsed

    documents: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for upload in files:
        filename = upload.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTS:
            skipped.append({
                "documentName": filename,
                "reason": f"Unsupported file type '{ext or 'unknown'}'. Allowed: pdf, docx, txt, md, json.",
            })
            continue

        raw = await upload.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            skipped.append({"documentName": filename, "reason": "File exceeds the 10 MB limit."})
            continue

        try:
            text = _extract_text_from_upload(upload, raw)
        except Exception as exc:
            skipped.append({"documentName": filename, "reason": f"Could not extract text: {exc}"})
            continue

        if not text or not text.strip():
            skipped.append({
                "documentName": filename,
                "reason": "No extractable text (empty file or scanned/image-only PDF).",
            })
            continue

        meta = {**shared_meta, "documentName": filename}
        documents.append({"text": text, "metadata": meta, "id": None})

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "No ingestible documents found in upload.", "skipped": skipped},
        )

    try:
        result = ingest_documents(job=job, documents=documents, db=db, ingestion_config=None)
        _raise_for_ingestion_result(result)
        return _ingestion_response(result, jobId=str(job_id), skipped=skipped)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Ingestion failed: {exc}"},
        ) from exc
