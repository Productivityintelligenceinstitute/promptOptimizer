from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.clm.adapters import SUPPORTED_CLM_PROVIDERS
from context_jobs.clm_connection_schemas import (
    ClmConnectionCreate,
    ClmConnectionOut,
    ClmConnectionTestResult,
    ClmConnectionUpdate,
)
from context_jobs import clm_connection_services as clm_services
from context_jobs.clm_connection_services import ClmConnectionTestFailed
from database import database


context_clm_connections_router = APIRouter(prefix="/context-jobs/clm-connections")


@context_clm_connections_router.get(
    "/providers",
    response_model=list[str],
    tags=["Context Jobs"],
)
async def list_clm_providers(
    owner: str = Depends(get_context_jobs_owner_with_access),
):
    return sorted(SUPPORTED_CLM_PROVIDERS)


@context_clm_connections_router.get(
    "",
    response_model=list[ClmConnectionOut],
    tags=["Context Jobs"],
)
async def list_clm_connections(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
    include_disabled: bool = False,
):
    return clm_services.list_connections(db, owner, include_disabled=include_disabled)


@context_clm_connections_router.post(
    "",
    response_model=ClmConnectionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_clm_connection(
    payload: ClmConnectionCreate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return clm_services.create_connection(db, payload, owner=owner)
    except ClmConnectionTestFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message or "CLM connection test failed.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@context_clm_connections_router.patch(
    "/{connection_id}",
    response_model=ClmConnectionOut,
    tags=["Context Jobs"],
)
async def update_clm_connection(
    connection_id: UUID,
    payload: ClmConnectionUpdate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    conn = clm_services.get_connection(db, connection_id, owner)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLM connection not found")
    try:
        return clm_services.update_connection(db, conn, payload)
    except ClmConnectionTestFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message or "CLM connection test failed.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@context_clm_connections_router.post(
    "/{connection_id}/test",
    response_model=ClmConnectionTestResult,
    tags=["Context Jobs"],
)
async def test_clm_connection(
    connection_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    conn = clm_services.get_connection(db, connection_id, owner)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLM connection not found")
    ok, message = clm_services.test_connection(db, conn)
    return ClmConnectionTestResult(ok=ok, provider=conn.provider, message=message)


@context_clm_connections_router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Context Jobs"],
)
async def delete_clm_connection(
    connection_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    conn = clm_services.get_connection(db, connection_id, owner)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLM connection not found")
    clm_services.soft_delete_connection(db, conn)
    return None
