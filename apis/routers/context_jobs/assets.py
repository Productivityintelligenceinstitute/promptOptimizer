from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_context_jobs_owner_with_access
from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services


router = APIRouter(tags=["Context Jobs"])


@router.get("/assets", response_model=list[cj_schemas.ContextAssetOut])
async def list_assets(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_assets(db, owner)


@router.post(
    "/assets",
    response_model=cj_schemas.ContextAssetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset(
    payload: cj_schemas.ContextAssetCreate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    return cj_services.create_asset(db, owner, payload)


@router.patch("/assets/{asset_id}", response_model=cj_schemas.ContextAssetOut)
async def update_asset(
    asset_id: UUID,
    payload: cj_schemas.ContextAssetUpdate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    asset = cj_services.get_asset(db, asset_id, owner)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return cj_services.update_asset(db, asset, payload)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    asset = cj_services.get_asset(db, asset_id, owner)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    cj_services.delete_asset(db, asset)
    return None


@router.get("/source-packs", response_model=list[cj_schemas.ContextAssetOut])
async def list_source_packs(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_source_packs(db, owner)
