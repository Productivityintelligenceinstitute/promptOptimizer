"""Firebase auth + workspace tenancy dependencies for Context Jobs routes.

Route dependencies, from least to most specific:

- ``get_context_jobs_actor``: signed-in user, no workspace or plan checks
  (invitation acceptance, workspace listing).
- ``get_tenant_context``: verified active workspace membership, no plan check.
- ``get_context_jobs_owner_with_access``: data owner key for read routes
  (plan check + ``WORKSPACE_VIEW``).
- ``owner_with(cap)`` / ``tenant_with(cap)``: plan check + a specific capability.
  Every mutating route must use one of these; a route-coverage test enforces it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from context_jobs.tenancy.context import WORKSPACE_HEADER, TenantContext, resolve_tenant_context
from context_jobs.tenancy.request_actor import RequestActor, bind_request_actor, clear_request_actor
from context_jobs.tenancy.roles import Capability
from database import database
from dependencies.auth import verify_firebase_token
from repositories.user_repository import UserRepository
from schemas.user_model import UserModel

# Attribute set on capability dependencies so tests can audit route coverage.
CAPABILITY_ATTR = "__tenancy_capability__"


@dataclass(frozen=True)
class ContextJobsActor:
    """
    Authenticated Context Jobs principal.

    - user_id: backend UUID (subscriptions, plan checks — same as prompt optimizer)
    - owner: firebase UID string (the user's personal data partition)
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


def get_current_user(
    decoded_token: dict = Depends(verify_firebase_token),
    db: Session = Depends(database.get_db),
) -> UserModel:
    return resolve_context_jobs_user(db, _firebase_uid_from_token(decoded_token))


def get_context_jobs_actor(
    user: UserModel = Depends(get_current_user),
) -> ContextJobsActor:
    """Authenticated principal for Context Jobs: backend user id + firebase uid."""
    return ContextJobsActor(user_id=user.id, owner=user.firebase_uid)


async def get_tenant_context(
    request: Request,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(database.get_db),
) -> AsyncIterator[TenantContext]:
    """
    Active workspace for this request after verifying membership (no plan check).

    Async on purpose: the request actor bound here must be visible to the endpoint,
    and context variables set in threadpool-run sync dependencies are discarded.
    The actor is cleared afterwards so it can never outlive the request.
    """
    from context_jobs.errors import raise_context_jobs_http

    try:
        tenant = resolve_tenant_context(db, user, request.headers.get(WORKSPACE_HEADER))
    except Exception as exc:
        raise_context_jobs_http(exc)
        raise
    bind_request_actor(
        RequestActor(
            firebase_uid=tenant.firebase_uid,
            workspace_id=tenant.workspace_id,
            owner=tenant.owner,
        )
    )
    try:
        yield tenant
    finally:
        clear_request_actor()


def _ensure_plan(db: Session, tenant: TenantContext) -> None:
    from context_jobs.errors import raise_context_jobs_http
    from context_jobs.plan_entitlements import ensure_context_jobs_access

    try:
        if tenant.is_company:
            ensure_context_jobs_access(db, tenant.owner)
        else:
            ensure_context_jobs_access(db, tenant.user_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


def _require(tenant: TenantContext, capability: Capability) -> None:
    from context_jobs.errors import raise_context_jobs_http

    try:
        tenant.require(capability)
    except Exception as exc:
        raise_context_jobs_http(exc)


def tenant_with(capability: Capability) -> Callable[..., TenantContext]:
    """Dependency: plan check + ``capability`` in the active workspace."""

    def dependency(
        tenant: TenantContext = Depends(get_tenant_context),
        db: Session = Depends(database.get_db),
    ) -> TenantContext:
        _ensure_plan(db, tenant)
        _require(tenant, capability)
        return tenant

    setattr(dependency, CAPABILITY_ATTR, capability)
    dependency.__name__ = f"tenant_with_{capability.name.lower()}"
    return dependency


def owner_with(capability: Capability) -> Callable[..., str]:
    """Dependency: like ``tenant_with`` but returns the data owner key."""
    tenant_dependency = tenant_with(capability)

    def dependency(tenant: TenantContext = Depends(tenant_dependency)) -> str:
        return tenant.owner

    setattr(dependency, CAPABILITY_ATTR, capability)
    dependency.__name__ = f"owner_with_{capability.name.lower()}"
    return dependency


def get_context_jobs_owner(
    tenant: TenantContext = Depends(get_tenant_context),
) -> str:
    """
    Data owner key for the active workspace after verifying membership.
    Does not check Context Jobs plan/permissions — prefer get_context_jobs_owner_with_access.
    """
    return tenant.owner


def get_context_jobs_owner_with_access(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(database.get_db),
) -> str:
    """
    Data owner key after verifying the plan includes Context Jobs and the member may view.
    Read-only routes only; mutating routes use ``owner_with``/``tenant_with``.
    """
    _ensure_plan(db, tenant)
    _require(tenant, Capability.WORKSPACE_VIEW)
    return tenant.owner


setattr(get_context_jobs_owner_with_access, CAPABILITY_ATTR, Capability.WORKSPACE_VIEW)
