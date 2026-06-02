from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.retrieval.factory import get_retrieval_adapter
from context_jobs.retrieval.security import decrypt_config, encrypt_config
from context_jobs.vector_connection_schemas import VectorConnectionCreate, VectorConnectionUpdate
from schemas.context_vector_connection_model import ContextVectorConnectionModel


class VectorConnectionTestFailed(Exception):
    """Raised when adapter test_connection fails (create/update must not persist)."""

    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider


def test_connection_config(provider: str, config: dict[str, Any]) -> tuple[bool, str]:
    """Run provider adapter test against config dict (no DB row required)."""
    adapter = get_retrieval_adapter((provider or "").lower(), config or {})
    return adapter.test_connection()


def _apply_test_result(
    conn: ContextVectorConnectionModel, ok: bool, message: str
) -> None:
    conn.last_tested_at = datetime.now(timezone.utc)
    conn.last_error = None if ok else message
    conn.status = "active" if ok else "invalid"


def list_connections(
    db: Session,
    owner: str = "current_user",
    *,
    include_disabled: bool = False,
) -> list[ContextVectorConnectionModel]:
    q = db.query(ContextVectorConnectionModel).filter(ContextVectorConnectionModel.owner == owner)
    if not include_disabled:
        q = q.filter(ContextVectorConnectionModel.status != "disabled")
    return q.order_by(ContextVectorConnectionModel.created_at.desc()).all()


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
    owner_key = (payload.owner or owner).strip() or "current_user"
    provider = payload.provider.lower()
    ok, message = test_connection_config(provider, payload.config)
    if not ok:
        raise VectorConnectionTestFailed(message, provider=provider)

    conn = ContextVectorConnectionModel(
        owner=owner_key,
        name=payload.name,
        provider=provider,
        encrypted_config=encrypt_config(payload.config),
        status="active",
    )
    _apply_test_result(conn, True, message)
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
        ok, message = test_connection_config(conn.provider, payload.config)
        if not ok:
            raise VectorConnectionTestFailed(message, provider=conn.provider)
        conn.encrypted_config = encrypt_config(payload.config)
        _apply_test_result(conn, True, message)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def soft_delete_connection(db: Session, conn: ContextVectorConnectionModel) -> None:
    conn.status = "disabled"
    db.add(conn)
    db.commit()


def test_connection(db: Session, conn: ContextVectorConnectionModel) -> tuple[bool, str]:
    config = decrypt_config(conn.encrypted_config or {})
    ok, message = test_connection_config(conn.provider, config)
    _apply_test_result(conn, ok, message)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return ok, message


def get_active_connection_for_owner(
    db: Session, connection_id: UUID, owner: str
) -> ContextVectorConnectionModel:
    """Load a connection that belongs to this account and is usable on a context job."""
    conn = get_connection(db, connection_id, owner)
    if not conn:
        raise ValueError("Vector connection not found for this account.")
    if conn.status == "disabled":
        raise ValueError("Vector connection has been removed.")
    if conn.status != "active":
        raise ValueError(
            f"Vector connection is not active (status={conn.status!r}). "
            "Re-test the connection before using it on a job."
        )
    return conn

