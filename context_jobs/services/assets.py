from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
from context_jobs.asset_taxonomy import (
    import_asset_into_job,
    list_source_pack_assets,
    validate_asset_content,
    validate_asset_type,
)
from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.services.job_queries import get_job
from context_jobs.workspace import default_workspace_id
from schemas.context_jobs_model import ContextAssetModel, ContextJobModel

SYSTEM_ASSET_OWNER = "__system__"


def list_assets(db: Session, owner: str) -> List[ContextAssetModel]:
    q = db.query(ContextAssetModel).filter(
        (ContextAssetModel.owner == owner) | (ContextAssetModel.owner.is_(None))
    )
    return q.order_by(ContextAssetModel.created_at.desc()).all()


def get_importable_asset(
    db: Session, asset_id: UUID, owner: str
) -> Optional[ContextAssetModel]:
    return (
        db.query(ContextAssetModel)
        .filter(
            ContextAssetModel.id == asset_id,
            (ContextAssetModel.owner == owner)
            | (ContextAssetModel.owner.is_(None))
            | (ContextAssetModel.owner == SYSTEM_ASSET_OWNER),
        )
        .first()
    )


def get_asset(db: Session, asset_id: UUID, owner: Optional[str] = None) -> Optional[ContextAssetModel]:
    q = db.query(ContextAssetModel).filter(ContextAssetModel.id == asset_id)
    if owner:
        q = q.filter(
            (ContextAssetModel.owner == owner) | (ContextAssetModel.owner.is_(None))
        )
    return q.first()


def create_asset(db: Session, owner: str, data: cj_schemas.ContextAssetCreate) -> ContextAssetModel:
    validate_asset_type(data.type)
    validate_asset_content(data.type, data.content)
    payload = data.model_dump(by_alias=False)
    payload["owner"] = owner
    payload["workspace_id"] = payload.get("workspace_id") or default_workspace_id(owner)
    asset = ContextAssetModel(**payload)
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
    if payload.get("type"):
        validate_asset_type(payload["type"])
    if "content" in payload:
        validate_asset_content(payload.get("type") or asset.type, payload["content"])
    for key, value in payload.items():
        setattr(asset, key, value)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset: ContextAssetModel) -> None:
    db.delete(asset)
    db.commit()


def import_assets_into_job(
    db: Session, owner: str, job: ContextJobModel, asset_ids: list[UUID]
) -> list[dict[str, Any]]:
    if not asset_ids:
        return []
    summaries: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        asset = get_importable_asset(db, asset_id, owner)
        if not asset:
            raise ContextJobsNotFoundError("Asset not found")
        if getattr(asset, "approval_status", "approved") not in {None, "approved", "active"}:
            raise ValueError(f"Asset {asset_id} is not approved for import")
        summaries.append(import_asset_into_job(job, asset))
    return summaries


def import_asset_to_job(
    db: Session, owner: str, job_id: UUID, asset_id: UUID
) -> dict[str, Any]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    summaries = import_assets_into_job(db, owner, job, [asset_id])
    db.add(job)
    db.commit()
    db.refresh(job)
    return summaries[0]


def list_source_packs(db: Session, owner: str) -> list[ContextAssetModel]:
    ws_id = default_workspace_id(owner)
    return list_source_pack_assets(db, owner, ws_id)
