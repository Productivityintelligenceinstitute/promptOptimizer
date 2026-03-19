from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
from schemas.context_jobs_model import ContextJobModel, ContextAssetModel, JobRunModel


def list_jobs(db: Session) -> List[ContextJobModel]:
    return db.query(ContextJobModel).order_by(ContextJobModel.created_at.desc()).all()


def get_job(db: Session, job_id: UUID) -> Optional[ContextJobModel]:
    return db.query(ContextJobModel).filter(ContextJobModel.id == job_id).first()


def create_job(db: Session, data: cj_schemas.ContextJobCreate) -> ContextJobModel:
    job = ContextJobModel(**data.model_dump(by_alias=False))
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(
    db: Session,
    job: ContextJobModel,
    data: cj_schemas.ContextJobUpdate,
) -> ContextJobModel:
    payload = data.model_dump(exclude_unset=True, by_alias=False)
    for key, value in payload.items():
        setattr(job, key, value)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_assets(db: Session) -> List[ContextAssetModel]:
    return db.query(ContextAssetModel).order_by(ContextAssetModel.created_at.desc()).all()


def get_asset(db: Session, asset_id: UUID) -> Optional[ContextAssetModel]:
    return db.query(ContextAssetModel).filter(ContextAssetModel.id == asset_id).first()


def create_asset(db: Session, data: cj_schemas.ContextAssetCreate) -> ContextAssetModel:
    asset = ContextAssetModel(**data.model_dump(by_alias=False))
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(
    db: Session,
    asset: ContextAssetModel,
    data: cj_schemas.ContextAssetUpdate,
) -> ContextAssetModel:
    payload = data.model_dump(exclude_unset=True, by_alias=False)
    for key, value in payload.items():
        setattr(asset, key, value)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset: ContextAssetModel) -> None:
    db.delete(asset)
    db.commit()


def list_runs(db: Session) -> List[JobRunModel]:
    return db.query(JobRunModel).order_by(JobRunModel.started_at.desc()).all()


def get_run(db: Session, run_id: UUID) -> Optional[JobRunModel]:
    return db.query(JobRunModel).filter(JobRunModel.id == run_id).first()


def create_run(
    db: Session,
    job_id: UUID,
    data: cj_schemas.JobRunCreate,
) -> JobRunModel:
    run = JobRunModel(job_id=job_id, user_request=data.userRequest or "")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

