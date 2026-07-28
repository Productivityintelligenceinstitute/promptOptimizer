"""Procurement intelligence API routes (Tier 3)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from constants.file_types import ALLOWED_EXTS
from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.errors import raise_context_jobs_http
from context_jobs.procurement_demo_kb import (
    DEFAULT_TEMPLATE_NAME,
    find_system_template,
    seed_demo_kb_for_job,
)
from context_jobs.schemas import (
    ContextJobOut,
    ProcurementAlertOut,
    ProcurementContractRegisterOut,
    ProcurementDemoIngestionOut,
    ProcurementDemoSetupOut,
    ProcurementDemoSetupRequest,
)
from context_jobs.services import procurement_alerts as alert_services
from context_jobs.services.jobs import instantiate_template_job
from context_jobs.services.procurement_contract_register import register_contract_for_alerts
from database import database
from utils.reader import read_file

router = APIRouter(prefix="/procurement", tags=["Context Jobs - Procurement"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _extract_text_from_upload(upload: UploadFile, raw: bytes) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        return read_file(tmp_path)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@router.get("/alerts", response_model=list[ProcurementAlertOut])
async def list_procurement_alerts(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
) -> list[ProcurementAlertOut]:
    alerts = alert_services.list_undismissed_alerts(db, owner)
    return [ProcurementAlertOut.model_validate(alert) for alert in alerts]


@router.post("/alerts/{alert_id}/dismiss", response_model=ProcurementAlertOut)
async def dismiss_procurement_alert(
    alert_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
) -> ProcurementAlertOut:
    alert = alert_services.dismiss_alert(db, owner, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    return ProcurementAlertOut.model_validate(alert)


@router.post(
    "/alerts/register-contract",
    response_model=ProcurementContractRegisterOut,
    status_code=status.HTTP_201_CREATED,
)
async def register_procurement_alert_contract(
    expiryDate: str = Form(...),
    description: str = Form(...),
    vendor: str | None = Form(None),
    contractId: str | None = Form(None),
    complexityTier: str | None = Form("medium"),
    file: UploadFile | None = File(None),
    contractText: str | None = Form(None),
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
) -> ProcurementContractRegisterOut:
    """
    Ingest a contract into the caller's Jet managed KB with forced expiry metadata.

    Does not run the monitor immediately — the scheduled job creates the alert later.
    """
    try:
        text = (contractText or "").strip()
        document_name = None
        if file is not None and (file.filename or "").strip():
            filename = file.filename or "contract"
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_EXTS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type '{ext or 'unknown'}'. Allowed: pdf, docx, txt, md, json.",
                )
            raw = await file.read()
            if len(raw) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File exceeds the 10 MB limit.",
                )
            extracted = _extract_text_from_upload(file, raw).strip()
            if not extracted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No extractable text (empty file or scanned/image-only PDF).",
                )
            text = extracted
            document_name = filename

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide a contract file or contractText.",
            )

        result = register_contract_for_alerts(
            db,
            owner,
            text=text,
            expiry_date=expiryDate,
            description=description,
            vendor=vendor,
            contract_id=contractId,
            complexity_tier=complexityTier,
            document_name=document_name,
        )
        return ProcurementContractRegisterOut.model_validate(result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise_context_jobs_http(exc)
        raise


@router.post(
    "/demo-setup",
    response_model=ProcurementDemoSetupOut,
    status_code=status.HTTP_201_CREATED,
)
async def setup_procurement_demo(
    payload: ProcurementDemoSetupRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
) -> ProcurementDemoSetupOut:
    """
    Persist a system template into the caller's workspace and ingest the demo KB bundle.

    Lifecycle chaining is disabled; ``enableChain`` is accepted for API compatibility
    and ignored.
    """
    try:
        _ = payload.enable_chain
        template = None
        if payload.template_id is not None:
            from context_jobs.services.job_queries import get_template_job

            template = get_template_job(db, payload.template_id)
        else:
            template = find_system_template(
                db,
                (payload.template_name or DEFAULT_TEMPLATE_NAME).strip() or DEFAULT_TEMPLATE_NAME,
            )
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

        job = instantiate_template_job(db, owner, template.id)

        ingestion = seed_demo_kb_for_job(db, owner, job.id)
        return ProcurementDemoSetupOut(
            job=ContextJobOut.model_validate(job),
            ingestion=ProcurementDemoIngestionOut(
                status=ingestion.status,
                outcome=ingestion.outcome,
                upserted_count=ingestion.upserted_count,
                failed_count=ingestion.failed_count,
                warnings=list(ingestion.warnings or []),
                error=ingestion.error,
                ingested_sources=list(ingestion.ingested_sources or []),
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise_context_jobs_http(exc)
        raise
