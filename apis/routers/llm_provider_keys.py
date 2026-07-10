"""API routes for LLM and tool provider BYOK keys."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_context_jobs_owner, get_context_jobs_owner_with_access
from context_jobs import provider_key_services as key_services
from context_jobs.errors import raise_context_jobs_http
from context_jobs.plan_entitlements import (
    assert_byok_llm_keys_allowed,
    build_entitlements,
    ensure_context_jobs_access,
)
from context_jobs.provider_key_schemas import (
    ContextJobsEntitlementsOut,
    LlmKeyCreate,
    LlmKeyModelsOut,
    LlmKeyOut,
    ProviderInfo,
    ToolInfo,
    ToolKeyCreate,
    ToolKeyOut,
)
from database import database

provider_keys_router = APIRouter(prefix="/context-jobs")


def _require_pro_byok_keys(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
) -> str:
    """Pro-only BYOK key routes (trial uses platform keys; essential blocked upstream)."""
    try:
        assert_byok_llm_keys_allowed(db, owner)
    except Exception as exc:
        raise_context_jobs_http(exc)
    return owner


@provider_keys_router.get("/llm-keys", response_model=list[LlmKeyOut], tags=["Context Jobs"])
async def list_llm_keys(
    provider: str | None = None,
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    """
    List BYOK keys for the authenticated user, newest first.

    Optional `provider` query filters to one provider (openai, google, anthropic).
    Use after the user picks a provider in the job editor; default selection = first row (latest).
    """
    return key_services.list_llm_keys(db, owner, provider=provider)


@provider_keys_router.get(
    "/llm-keys/{key_id}/models",
    response_model=LlmKeyModelsOut,
    tags=["Context Jobs"],
)
async def list_llm_key_models(
    key_id: UUID,
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    """
    Chat models accessible to a specific BYOK key (live provider API, cached ~5 min).

    Call after the user selects a key in the job editor to populate the model dropdown.
    """
    try:
        return key_services.list_models_for_llm_key(db, owner, key_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise_context_jobs_http(exc)


@provider_keys_router.post(
    "/llm-keys",
    response_model=LlmKeyOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_llm_key(
    payload: LlmKeyCreate,
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    try:
        return key_services.create_llm_key(db, owner, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@provider_keys_router.delete("/llm-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Context Jobs"])
async def revoke_llm_key(
    key_id: UUID,
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    try:
        key_services.revoke_llm_key(db, owner, key_id)
    except Exception as exc:
        raise_context_jobs_http(exc)
    return None


@provider_keys_router.post("/llm-keys/{key_id}/verify", response_model=LlmKeyOut, tags=["Context Jobs"])
async def verify_llm_key(
    key_id: UUID,
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    try:
        return key_services.verify_llm_key(db, owner, key_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@provider_keys_router.get("/tool-keys", response_model=list[ToolKeyOut], tags=["Context Jobs"])
async def list_tool_keys(
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    return key_services.list_tool_keys(db, owner)


@provider_keys_router.post(
    "/tool-keys",
    response_model=ToolKeyOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_tool_key(
    payload: ToolKeyCreate,
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    try:
        return key_services.create_tool_key(db, owner, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@provider_keys_router.delete("/tool-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Context Jobs"])
async def revoke_tool_key(
    key_id: UUID,
    owner: str = Depends(_require_pro_byok_keys),
    db: Session = Depends(database.get_db),
):
    try:
        key_services.revoke_tool_key(db, owner, key_id)
    except Exception as exc:
        raise_context_jobs_http(exc)
    return None


@provider_keys_router.get(
    "/entitlements",
    response_model=ContextJobsEntitlementsOut,
    tags=["Context Jobs"],
)
async def get_context_jobs_entitlements(
    owner: str = Depends(get_context_jobs_owner),
    db: Session = Depends(database.get_db),
):
    # UI gating: return plan-aware payload for every package (including essential).
    return build_entitlements(db, owner)


@provider_keys_router.get("/providers", response_model=list[ProviderInfo], tags=["Context Jobs"])
async def list_providers(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    package_name = ensure_context_jobs_access(db, owner)
    return key_services.list_provider_catalog(db, owner, package_name=package_name)


@provider_keys_router.get("/tools", response_model=list[ToolInfo], tags=["Context Jobs"])
async def list_tools(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    return key_services.list_tool_catalog(db, owner)
