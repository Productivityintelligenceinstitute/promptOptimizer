from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from context_jobs.agents.catalog import list_specialist_catalog
from context_jobs.agents.execution_modes import (
    EXECUTION_MODE_MULTI,
    EXECUTION_MODE_SINGLE,
    VALID_EXECUTION_MODES,
)
from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.errors import raise_context_jobs_http
from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services


router = APIRouter(tags=["Context Jobs"])


@router.get("/jobs", response_model=list[cj_schemas.ContextJobOut])
async def list_jobs(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.list_jobs(db, owner)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/templates", response_model=list[cj_schemas.ContextJobOut])
async def list_templates(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.list_template_jobs(db, owner)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post(
    "/templates/{template_id}/instantiate",
    response_model=cj_schemas.ContextJobCreate,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def instantiate_template(
    template_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    """
    Return a job configuration JSON from a system template without persisting.

    Same pattern as POST /jobs/from-prompt — persist with POST /jobs when ready.
    """
    try:
        return cj_services.build_job_config_from_template(db, owner, template_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/jobs/{job_id}", response_model=cj_schemas.ContextJobOut)
async def get_job(
    job_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get(
    "/jobs/{job_id}/pending-handoff",
    response_model=cj_schemas.JobPendingHandoffOut,
)
async def get_job_pending_handoff(
    job_id: UUID,
    parent_run_id: Optional[UUID] = Query(None, alias="parentRunId"),
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    """Latest lifecycle handoff waiting on this job (pre-filled next-step request)."""
    try:
        handoff = cj_services.get_pending_handoff_for_job(
            db, owner, job_id, parent_run_id=parent_run_id
        )
    except Exception as exc:
        raise_context_jobs_http(exc)
    if not handoff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending handoff")
    return handoff


@router.get("/jobs/{job_id}/versions", response_model=list[cj_schemas.ContextJobVersionOut])
async def list_job_versions(
    job_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.list_job_versions(db, owner, job_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/jobs/{job_id}/versions/latest", response_model=cj_schemas.ContextJobVersionOut)
async def get_latest_job_version(
    job_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_latest_job_version(db, owner, job_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/jobs/{job_id}/versions/{version}", response_model=cj_schemas.ContextJobVersionOut)
async def get_job_version(
    job_id: UUID,
    version: int,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_job_version(db, owner, job_id, version)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post(
    "/jobs",
    response_model=cj_schemas.ContextJobOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    payload: cj_schemas.ContextJobCreate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.create_job(db, owner, payload)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.patch("/jobs/{job_id}", response_model=cj_schemas.ContextJobOut)
async def update_job(
    job_id: UUID,
    payload: cj_schemas.ContextJobUpdate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    try:
        return cj_services.update_job(db, owner, job, payload)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post(
    "/jobs/{job_id}/duplicate",
    response_model=cj_schemas.ContextJobOut,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_job(
    job_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    try:
        return cj_services.duplicate_job(db, owner, job)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/jobs/{job_id}/publish", response_model=cj_schemas.ContextJobOut)
async def publish_job(
    job_id: UUID,
    payload: cj_schemas.JobLifecycleRequest | None = None,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.publish_job(db, owner, job_id, payload.notes if payload else None)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/jobs/{job_id}/archive", response_model=cj_schemas.ContextJobOut)
async def archive_job(
    job_id: UUID,
    payload: cj_schemas.JobLifecycleRequest | None = None,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.archive_job(db, owner, job_id, payload.notes if payload else None)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/jobs/{job_id}/rollback", response_model=cj_schemas.ContextJobOut)
async def rollback_job_version(
    job_id: UUID,
    payload: cj_schemas.JobVersionRollbackRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.rollback_job_version(db, owner, job_id, payload.version, payload.notes)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/jobs/{job_id}/publish-history", response_model=list[cj_schemas.PublishHistoryOut])
async def get_job_publish_history(
    job_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.list_publish_history(db, owner, job_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/jobs/{job_id}/identity-matches")
async def suggest_identity_matches(
    job_id: UUID,
    payload: cj_schemas.IdentityMatchRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.suggest_job_identity_matches(db, owner, job_id, payload.query)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/jobs/{job_id}/import-asset")
async def import_asset_into_job(
    job_id: UUID,
    payload: cj_schemas.AssetImportRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.import_asset_to_job(db, owner, job_id, payload.asset_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/audit-events", response_model=list[cj_schemas.AuditEventOut])
async def get_audit_events(
    entity_type: str | None = Query(default=None, alias="entityType"),
    entity_id: str | None = Query(default=None, alias="entityId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    from_date: datetime | None = Query(default=None, alias="fromDate"),
    to_date: datetime | None = Query(default=None, alias="toDate"),
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_audit_events(
        db,
        owner,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        from_ts=from_date,
        to_ts=to_date,
    )


@router.get("/execution-modes", response_model=cj_schemas.ExecutionModesOut)
async def list_execution_modes(
    owner: str = Depends(get_context_jobs_owner_with_access),
):
    labels = {
        EXECUTION_MODE_SINGLE: "Single agent (default)",
        EXECUTION_MODE_MULTI: "Provider multi-agent (opt-in delegation)",
    }
    return {
        "modes": [
            {"value": mode, "label": labels.get(mode, mode)}
            for mode in sorted(VALID_EXECUTION_MODES)
        ]
    }


@router.get("/jobs/{job_id}/specialists", response_model=list[cj_schemas.SpecialistAgentOut])
async def list_job_specialists(
    job_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return list_specialist_catalog(job)


@router.get("/jobs/{job_id}/stats")
async def get_job_stats(
    job_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_job_stats(db, owner, job_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post(
    "/jobs/from-prompt",
    response_model=cj_schemas.ContextJobCreate,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def generate_job_from_prompt(
    payload: cj_schemas.PromptToJobRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return await cj_services.generate_job_from_prompt(
            db,
            owner,
            payload.prompt,
            payload.agent_type,
        )
    except ValueError as exc:
        raise_context_jobs_http(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate job config: {exc}",
        ) from exc


@router.post(
    "/jobs/{job_id}/run",
    response_model=cj_schemas.JobRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def run_job(
    job_id: UUID,
    payload: cj_schemas.JobRunCreate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.create_run(db, owner, job_id, payload)
    except ValueError as exc:
        detail = str(exc)
        if "queue is full" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
            ) from exc
        raise_context_jobs_http(exc)


@router.get("/stats", response_model=cj_schemas.ContextJobsStatsOut)
async def get_context_jobs_stats(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    return cj_services.get_overall_stats(db, owner)
