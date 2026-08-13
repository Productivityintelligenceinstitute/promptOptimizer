"""CRUD + test for encrypted CLM connections (Coupa / Ironclad)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.clm.adapters import SUPPORTED_CLM_PROVIDERS, get_clm_adapter
from context_jobs.clm_connection_schemas import ClmConnectionCreate, ClmConnectionUpdate
from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.retrieval.security import decrypt_config, encrypt_config
from schemas.context_clm_connection_model import ContextClmConnectionModel


class ClmConnectionTestFailed(Exception):
    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider


def _normalize_provider(provider: str) -> str:
    key = (provider or "").strip().lower()
    if key not in SUPPORTED_CLM_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_CLM_PROVIDERS))
        raise ValueError(f"Unsupported CLM provider '{provider}'. Supported: {supported}.")
    return key


def _validate_config(provider: str, config: dict) -> dict:
    cfg = dict(config or {})
    if provider == "coupa":
        instance = (
            cfg.get("instance_url") or cfg.get("instanceUrl") or cfg.get("site_url") or ""
        ).strip()
        client_id = (cfg.get("client_id") or cfg.get("clientId") or "").strip()
        client_secret = (cfg.get("client_secret") or cfg.get("clientSecret") or "").strip()
        if not instance or not client_id or not client_secret:
            raise ValueError(
                "Coupa requires instance_url, client_id, and client_secret."
            )
        # Canonicalize keys
        return {
            "instance_url": instance if instance.startswith("http") else f"https://{instance}",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": (cfg.get("scope") or "core.contract.read").strip() or "core.contract.read",
        }

    if provider == "ironclad":
        token = (
            cfg.get("api_token")
            or cfg.get("apiToken")
            or cfg.get("api_key")
            or cfg.get("apiKey")
            or ""
        ).strip()
        if not token:
            raise ValueError("Ironclad requires api_token.")
        out = {
            "api_token": token,
            "base_url": (
                cfg.get("base_url") or cfg.get("baseUrl") or cfg.get("host") or "na1.ironcladapp.com"
            ).strip()
            or "na1.ironcladapp.com",
        }
        as_email = (cfg.get("as_user_email") or cfg.get("asUserEmail") or "").strip()
        if as_email:
            out["as_user_email"] = as_email
        return out

    raise ValueError(f"Unsupported CLM provider: {provider}")


def test_connection_config(provider: str, config: dict) -> tuple[bool, str]:
    provider_key = _normalize_provider(provider)
    normalized = _validate_config(provider_key, config)
    adapter = get_clm_adapter(provider_key)
    return adapter.test_connection(normalized)


def _apply_test_result(conn: ContextClmConnectionModel, ok: bool, message: str) -> None:
    conn.last_tested_at = datetime.now(timezone.utc)
    conn.last_error = None if ok else message
    conn.status = "active" if ok else "invalid"


def list_connections(
    db: Session,
    owner: str,
    *,
    include_disabled: bool = False,
) -> list[ContextClmConnectionModel]:
    q = db.query(ContextClmConnectionModel).filter(ContextClmConnectionModel.owner == owner)
    if not include_disabled:
        q = q.filter(ContextClmConnectionModel.status != "disabled")
    return q.order_by(ContextClmConnectionModel.created_at.desc()).all()


def get_connection(
    db: Session, connection_id: UUID, owner: str
) -> Optional[ContextClmConnectionModel]:
    return (
        db.query(ContextClmConnectionModel)
        .filter(
            ContextClmConnectionModel.id == connection_id,
            ContextClmConnectionModel.owner == owner,
        )
        .first()
    )


def create_connection(
    db: Session, payload: ClmConnectionCreate, owner: str
) -> ContextClmConnectionModel:
    from context_jobs.security.key_encryption import KeyEncryptionError

    provider = _normalize_provider(payload.provider)
    normalized = _validate_config(provider, payload.config)
    ok, message = test_connection_config(provider, normalized)
    if not ok:
        raise ClmConnectionTestFailed(message, provider=provider)

    try:
        encrypted = encrypt_config(normalized)
    except KeyEncryptionError as exc:
        raise ValueError(str(exc)) from exc

    conn = ContextClmConnectionModel(
        owner=owner,
        name=(payload.name or "").strip() or f"{provider.title()} connection",
        provider=provider,
        encrypted_config=encrypted,
        status="active",
    )
    _apply_test_result(conn, True, message)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def update_connection(
    db: Session, conn: ContextClmConnectionModel, payload: ClmConnectionUpdate
) -> ContextClmConnectionModel:
    if payload.name is not None:
        conn.name = payload.name.strip() or conn.name
    if payload.status is not None:
        conn.status = payload.status
    if payload.config is not None:
        normalized = _validate_config(conn.provider, payload.config)
        ok, message = test_connection_config(conn.provider, normalized)
        if not ok:
            raise ClmConnectionTestFailed(message, provider=conn.provider)
        conn.encrypted_config = encrypt_config(normalized)
        _apply_test_result(conn, True, message)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def soft_delete_connection(db: Session, conn: ContextClmConnectionModel) -> None:
    conn.status = "disabled"
    db.add(conn)
    db.commit()


def test_connection(db: Session, conn: ContextClmConnectionModel) -> tuple[bool, str]:
    config = decrypt_config(conn.encrypted_config or {})
    ok, message = test_connection_config(conn.provider, config)
    _apply_test_result(conn, ok, message)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return ok, message


def get_active_connection_for_owner(
    db: Session, connection_id: UUID, owner: str
) -> ContextClmConnectionModel:
    conn = get_connection(db, connection_id, owner)
    if not conn:
        raise ContextJobsNotFoundError("CLM connection not found")
    if conn.status == "disabled":
        raise ValueError("CLM connection has been removed.")
    if conn.status != "active":
        raise ValueError(
            f"CLM connection is not active (status={conn.status!r}). "
            "Re-test the connection before importing."
        )
    return conn


def decrypted_config_for(conn: ContextClmConnectionModel) -> dict:
    return decrypt_config(conn.encrypted_config or {})
