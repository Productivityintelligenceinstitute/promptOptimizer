from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_authenticated_user_id
from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services
from context_jobs.ingestion.ingestion_service import ingest_documents


context_jobs_router = APIRouter(prefix="/context-jobs")


@context_jobs_router.get(
    "/jobs",
    response_model=list[cj_schemas.ContextJobOut],
    tags=["Context Jobs"],
)
async def list_jobs(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_jobs(db, owner)


@context_jobs_router.get(
    "/jobs/{job_id}",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def get_job(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@context_jobs_router.post(
    "/jobs",
    response_model=cj_schemas.ContextJobOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_job(
    payload: cj_schemas.ContextJobCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.create_job(db, owner, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.patch(
    "/jobs/{job_id}",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def update_job(
    job_id: UUID,
    payload: cj_schemas.ContextJobUpdate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    try:
        return cj_services.update_job(db, owner, job, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/duplicate",
    response_model=cj_schemas.ContextJobOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def duplicate_job(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return cj_services.duplicate_job(db, owner, job)


@context_jobs_router.get(
    "/jobs/{job_id}/stats",
    tags=["Context Jobs"],
)
async def get_job_stats(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_job_stats(db, owner, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/run",
    response_model=cj_schemas.JobRunOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def run_job(
    job_id: UUID,
    payload: cj_schemas.JobRunCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.create_run(db, owner, job_id, payload)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_429_TOO_MANY_REQUESTS if "queue is full" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc


@context_jobs_router.get(
    "/runs",
    response_model=list[cj_schemas.JobRunOut],
    tags=["Context Jobs"],
)
async def list_runs(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_runs(db, owner)


@context_jobs_router.get(
    "/runs/queue-status",
    tags=["Context Jobs"],
)
async def get_runs_queue_status(
    owner: str = Depends(get_authenticated_user_id),
):
    return cj_services.get_queue_status()


@context_jobs_router.get(
    "/runs/{run_id}",
    response_model=cj_schemas.JobRunOut,
    tags=["Context Jobs"],
)
async def get_run(
    run_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@context_jobs_router.patch(
    "/runs/{run_id}/decision",
    response_model=cj_schemas.JobRunOut,
    tags=["Context Jobs"],
)
async def record_run_decision(
    run_id: UUID,
    payload: cj_schemas.RunDecisionRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.state not in {"completed", "failed", "escalated", "repair"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot record a decision on a run that is still in progress",
        )
    try:
        return cj_services.record_human_decision(db, owner, run, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@context_jobs_router.get(
    "/assets",
    response_model=list[cj_schemas.ContextAssetOut],
    tags=["Context Jobs"],
)
async def list_assets(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_assets(db)


@context_jobs_router.post(
    "/assets",
    response_model=cj_schemas.ContextAssetOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_asset(
    payload: cj_schemas.ContextAssetCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.create_asset(db, payload)


@context_jobs_router.patch(
    "/assets/{asset_id}",
    response_model=cj_schemas.ContextAssetOut,
    tags=["Context Jobs"],
)
async def update_asset(
    asset_id: UUID,
    payload: cj_schemas.ContextAssetUpdate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    asset = cj_services.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return cj_services.update_asset(db, asset, payload)


@context_jobs_router.delete(
    "/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Context Jobs"],
)
async def delete_asset(
    asset_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    asset = cj_services.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    cj_services.delete_asset(db, asset)
    return None


@context_jobs_router.get(
    "/stats",
    response_model=cj_schemas.ContextJobsStatsOut,
    tags=["Context Jobs"],
)
async def get_context_jobs_stats(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.get_overall_stats(db, owner)


@context_jobs_router.post(
    "/jobs/{job_id}/ingest",
    response_model=dict[str, Any],
    tags=["Context Jobs"],
)
async def ingest_into_job(
    job_id: UUID,
    payload: cj_schemas.IngestionRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    try:
        doc_payloads = [d.model_dump() for d in payload.documents]
        result = ingest_documents(
            job=job,
            documents=doc_payloads,
            db=db,
            ingestion_config=payload.ingestion_config,
        )

        if result.status in {"escalated", "blocked_by_policy"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result.to_dict())
        if result.status in ("failed", "repair"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.to_dict())

        return result.to_dict()

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Ingestion failed: {exc}"},
        ) from exc
