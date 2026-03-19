from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services


context_jobs_router = APIRouter(prefix="/context-jobs")


@context_jobs_router.get(
    "/jobs",
    response_model=list[cj_schemas.ContextJobOut],
    tags=["Context Jobs"],
)
async def list_jobs(db: Session = Depends(database.get_db)):
    return cj_services.list_jobs(db)


@context_jobs_router.get(
    "/jobs/{job_id}",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def get_job(job_id: UUID, db: Session = Depends(database.get_db)):
    job = cj_services.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@context_jobs_router.post(
    "/jobs",
    response_model=cj_schemas.ContextJobOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_job(payload: cj_schemas.ContextJobCreate, db: Session = Depends(database.get_db)):
    return cj_services.create_job(db, payload)


@context_jobs_router.patch(
    "/jobs/{job_id}",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def update_job(
    job_id: UUID,
    payload: cj_schemas.ContextJobUpdate,
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return cj_services.update_job(db, job, payload)


@context_jobs_router.post(
    "/jobs/{job_id}/run",
    response_model=cj_schemas.JobRunOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def run_job(
    job_id: UUID,
    payload: cj_schemas.JobRunCreate,
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return cj_services.create_run(db, job_id, payload)


@context_jobs_router.get(
    "/runs",
    response_model=list[cj_schemas.JobRunOut],
    tags=["Context Jobs"],
)
async def list_runs(db: Session = Depends(database.get_db)):
    return cj_services.list_runs(db)


@context_jobs_router.get(
    "/runs/{run_id}",
    response_model=cj_schemas.JobRunOut,
    tags=["Context Jobs"],
)
async def get_run(run_id: UUID, db: Session = Depends(database.get_db)):
    run = cj_services.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@context_jobs_router.get(
    "/assets",
    response_model=list[cj_schemas.ContextAssetOut],
    tags=["Context Jobs"],
)
async def list_assets(db: Session = Depends(database.get_db)):
    return cj_services.list_assets(db)


@context_jobs_router.post(
    "/assets",
    response_model=cj_schemas.ContextAssetOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_asset(payload: cj_schemas.ContextAssetCreate, db: Session = Depends(database.get_db)):
    return cj_services.create_asset(db, payload)


@context_jobs_router.patch(
    "/assets/{asset_id}",
    response_model=cj_schemas.ContextAssetOut,
    tags=["Context Jobs"],
)
async def update_asset(
    asset_id: UUID,
    payload: cj_schemas.ContextAssetUpdate,
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
async def delete_asset(asset_id: UUID, db: Session = Depends(database.get_db)):
    asset = cj_services.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    cj_services.delete_asset(db, asset)
    return None

