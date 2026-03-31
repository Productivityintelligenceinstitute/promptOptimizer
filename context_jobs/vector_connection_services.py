from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.retrieval.factory import get_retrieval_adapter
from context_jobs.retrieval.security import decrypt_config, encrypt_config
from context_jobs.vector_connection_schemas import VectorConnectionCreate, VectorConnectionUpdate
from schemas.context_vector_connection_model import ContextVectorConnectionModel


def list_connections(db: Session, owner: str = "current_user") -> list[ContextVectorConnectionModel]:
    return (
        db.query(ContextVectorConnectionModel)
        .filter(ContextVectorConnectionModel.owner == owner)
        .order_by(ContextVectorConnectionModel.created_at.desc())
        .all()
    )


def get_connection(
    db: Session, connection_id: UUID, owner: str = "current_user"
) -> Optional[ContextVectorConnectionModel]:
    return (
        db.query(ContextVectorConnectionModel)
        .filter(
            ContextVectorConnectionModel.id == connection_id,
            ContextVectorConnectionModel.owner == owner,
        )
        .first()
    )


def create_connection(
    db: Session, payload: VectorConnectionCreate, owner: str = "current_user"
) -> ContextVectorConnectionModel:
    conn = ContextVectorConnectionModel(
        owner=payload.owner or owner,
        name=payload.name,
        provider=payload.provider.lower(),
        encrypted_config=encrypt_config(payload.config),
        status=payload.status,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def update_connection(
    db: Session, conn: ContextVectorConnectionModel, payload: VectorConnectionUpdate
) -> ContextVectorConnectionModel:
    if payload.name is not None:
        conn.name = payload.name
    if payload.status is not None:
        conn.status = payload.status
    if payload.config is not None:
        conn.encrypted_config = encrypt_config(payload.config)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def soft_delete_connection(db: Session, conn: ContextVectorConnectionModel) -> None:
    conn.status = "disabled"
    db.add(conn)
    db.commit()


def test_connection(db: Session, conn: ContextVectorConnectionModel) -> tuple[bool, str]:
    provider = conn.provider
    config = decrypt_config(conn.encrypted_config or {})
    adapter = get_retrieval_adapter(provider, config)
    ok, message = adapter.test_connection()
    conn.last_tested_at = datetime.now(timezone.utc)
    conn.last_error = None if ok else message
    conn.status = "active" if ok else "invalid"
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return ok, message

