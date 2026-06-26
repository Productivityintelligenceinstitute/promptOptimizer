"""Firebase auth helpers for Context Jobs routes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import database
from dependencies.auth import verify_firebase_token
from repositories.user_repository import UserRepository
from schemas.user_model import UserModel


@dataclass(frozen=True)
class ContextJobsActor:
    """
    Authenticated Context Jobs principal.

    - user_id: backend UUID (subscriptions, plan checks — same as prompt optimizer)
    - owner: firebase UID string (context_jobs / llm_keys row ownership)
    """

    user_id: UUID
    owner: str


def _firebase_uid_from_token(decoded_token: dict) -> str:
    user_id = decoded_token.get("uid") or decoded_token.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user id not found in token",
        )
    return str(user_id)


def resolve_context_jobs_user(db: Session, firebase_uid: str) -> UserModel:
    """
    Resolve a Firebase UID to an active users row (same requirement as /accounts/me).
    """
    user = UserRepository.get_active_by_firebase_uid(firebase_uid, db)
    if not user or not user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please create an account first.",
        )
    return user


def get_authenticated_user_id(
    decoded_token: dict = Depends(verify_firebase_token),
) -> str:
    """Firebase UID for context_jobs.owner columns (legacy storage key)."""
    return _firebase_uid_from_token(decoded_token)


def get_context_jobs_actor(
    decoded_token: dict = Depends(verify_firebase_token),
    db: Session = Depends(database.get_db),
) -> ContextJobsActor:
    """
    Authenticated principal for Context Jobs: backend user id + firebase owner key.
    """
    firebase_uid = _firebase_uid_from_token(decoded_token)
    user = resolve_context_jobs_user(db, firebase_uid)
    return ContextJobsActor(user_id=user.id, owner=firebase_uid)


def get_context_jobs_owner(
    actor: ContextJobsActor = Depends(get_context_jobs_actor),
) -> str:
    """
    Firebase UID for context_jobs.owner columns after verifying users row exists.
    Does not check Context Jobs plan/permissions — prefer get_context_jobs_owner_with_access.
    """
    return actor.owner


def get_context_jobs_owner_with_access(
    actor: ContextJobsActor = Depends(get_context_jobs_actor),
    db: Session = Depends(database.get_db),
) -> str:
    """
    Firebase UID after verifying the user may access Context Jobs (trial/pro, not essential).
    Use on all /context-jobs/* routes.
    """
    from context_jobs.errors import raise_context_jobs_http
    from context_jobs.plan_entitlements import ensure_context_jobs_access

    try:
        ensure_context_jobs_access(db, actor.owner)
    except Exception as exc:
        raise_context_jobs_http(exc)
    return actor.owner
