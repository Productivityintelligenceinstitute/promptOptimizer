"""API routes for LLM and tool provider BYOK keys."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs import provider_key_services as key_services
from context_jobs.auth import get_authenticated_user_id
from context_jobs.provider_key_schemas import (
    LlmKeyCreate,
    LlmKeyOut,
    ProviderInfo,
    ToolInfo,
    ToolKeyCreate,
    ToolKeyOut,
)
from database import database

provider_keys_router = APIRouter(prefix="/context-jobs")


@provider_keys_router.get("/llm-keys", response_model=list[LlmKeyOut], tags=["Context Jobs"])
async def list_llm_keys(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return key_services.list_llm_keys(db, owner)


@provider_keys_router.post(
    "/llm-keys",
    response_model=LlmKeyOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_llm_key(
    payload: LlmKeyCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return key_services.create_llm_key(db, owner, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@provider_keys_router.delete("/llm-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Context Jobs"])
async def revoke_llm_key(
    key_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        key_services.revoke_llm_key(db, owner, key_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return None


@provider_keys_router.post("/llm-keys/{key_id}/verify", response_model=LlmKeyOut, tags=["Context Jobs"])
async def verify_llm_key(
    key_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return key_services.verify_llm_key(db, owner, key_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@provider_keys_router.get("/tool-keys", response_model=list[ToolKeyOut], tags=["Context Jobs"])
async def list_tool_keys(
    owner: str = Depends(get_authenticated_user_id),
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
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return key_services.create_tool_key(db, owner, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@provider_keys_router.delete("/tool-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Context Jobs"])
async def revoke_tool_key(
    key_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        key_services.revoke_tool_key(db, owner, key_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return None


@provider_keys_router.get("/providers", response_model=list[ProviderInfo], tags=["Context Jobs"])
async def list_providers(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return key_services.list_provider_catalog(db, owner)


@provider_keys_router.get("/tools", response_model=list[ToolInfo], tags=["Context Jobs"])
async def list_tools(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return key_services.list_tool_catalog(db, owner)
