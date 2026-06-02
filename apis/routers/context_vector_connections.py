from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_authenticated_user_id
from database import database
from context_jobs.embeddings import supported_models_catalog
from context_jobs.vector_connection_schemas import (
    EmbeddingModelOption,
    VectorConnectionCreate,
    VectorConnectionOut,
    VectorConnectionTestResult,
    VectorConnectionUpdate,
)
from context_jobs import vector_connection_services as vc_services
from context_jobs.vector_connection_services import VectorConnectionTestFailed


context_vector_connections_router = APIRouter(prefix="/context-jobs/vector-connections")


@context_vector_connections_router.get(
    "/embedding-models",
    response_model=list[EmbeddingModelOption],
    tags=["Context Jobs"],
)
async def list_supported_embedding_models(
    owner: str = Depends(get_authenticated_user_id),
):
    raw = supported_models_catalog()
    return [EmbeddingModelOption.model_validate(r) for r in raw]


@context_vector_connections_router.get(
    "",
    response_model=list[VectorConnectionOut],
    tags=["Context Jobs"],
)
async def list_vector_connections(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
    include_disabled: bool = False,
):
    return vc_services.list_connections(db, owner, include_disabled=include_disabled)


@context_vector_connections_router.post(
    "",
    response_model=VectorConnectionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_vector_connection(
    payload: VectorConnectionCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return vc_services.create_connection(db, payload, owner=owner)
    except VectorConnectionTestFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "ok": False,
                "provider": exc.provider,
                "message": exc.message,
            },
        ) from exc


@context_vector_connections_router.patch(
    "/{connection_id}",
    response_model=VectorConnectionOut,
    tags=["Context Jobs"],
)
async def update_vector_connection(
    connection_id: UUID,
    payload: VectorConnectionUpdate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    conn = vc_services.get_connection(db, connection_id, owner)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector connection not found")
    try:
        return vc_services.update_connection(db, conn, payload)
    except VectorConnectionTestFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "ok": False,
                "provider": exc.provider,
                "message": exc.message,
            },
        ) from exc


@context_vector_connections_router.post(
    "/{connection_id}/test",
    response_model=VectorConnectionTestResult,
    tags=["Context Jobs"],
)
async def test_vector_connection(
    connection_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    conn = vc_services.get_connection(db, connection_id, owner)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector connection not found")
    ok, message = vc_services.test_connection(db, conn)
    return VectorConnectionTestResult(ok=ok, provider=conn.provider, message=message)


@context_vector_connections_router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Context Jobs"],
)
async def delete_vector_connection(
    connection_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    conn = vc_services.get_connection(db, connection_id, owner)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector connection not found")
    vc_services.soft_delete_connection(db, conn)
    return None
