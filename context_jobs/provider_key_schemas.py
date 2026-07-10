"""Pydantic schemas for LLM and tool provider key management."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LlmKeyCreate(BaseModel):
    provider: str
    key_label: str = Field(..., alias="keyLabel")
    api_key: str = Field(..., alias="apiKey")

    class Config:
        populate_by_name = True


class LlmKeyOut(BaseModel):
    id: UUID
    provider: str
    key_label: str = Field(..., alias="keyLabel")
    key_last_four: Optional[str] = Field(None, alias="keyLastFour")
    is_platform_key: bool = Field(False, alias="isPlatformKey")
    status: str
    last_verified_at: Optional[datetime] = Field(None, alias="lastVerifiedAt")
    last_error: Optional[str] = Field(None, alias="lastError")
    usage_count: int = Field(0, alias="usageCount")
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True
        from_attributes = True


class ToolKeyCreate(BaseModel):
    tool_id: str = Field(..., alias="toolId")
    provider: str
    key_label: str = Field(..., alias="keyLabel")
    api_key: str = Field(..., alias="apiKey")

    class Config:
        populate_by_name = True


class ToolKeyOut(BaseModel):
    id: UUID
    tool_id: str = Field(..., alias="toolId")
    provider: str
    key_label: str = Field(..., alias="keyLabel")
    key_last_four: Optional[str] = Field(None, alias="keyLastFour")
    status: str
    last_verified_at: Optional[datetime] = Field(None, alias="lastVerifiedAt")
    last_error: Optional[str] = Field(None, alias="lastError")
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True
        from_attributes = True


class ModelInfo(BaseModel):
    id: str
    display_name: str = Field(..., alias="displayName")

    class Config:
        populate_by_name = True


class LlmKeyModelsOut(BaseModel):
    key_id: UUID = Field(..., alias="keyId")
    provider: str
    key_label: str = Field(..., alias="keyLabel")
    models: list[ModelInfo]
    fetched_at: datetime = Field(..., alias="fetchedAt")

    class Config:
        populate_by_name = True


class ProviderInfo(BaseModel):
    provider: str
    display_name: str = Field(..., alias="displayName")
    models: list[ModelInfo]
    has_user_key: bool = Field(False, alias="hasUserKey")

    class Config:
        populate_by_name = True


class ToolInfo(BaseModel):
    id: str
    name: str
    description: str
    category: str
    is_read_only: bool = Field(True, alias="isReadOnly")
    external_provider: Optional[str] = Field(None, alias="externalProvider")
    has_user_key: bool = Field(False, alias="hasUserKey")

    class Config:
        populate_by_name = True


class EntitlementsLimits(BaseModel):
    max_jobs: int = Field(..., alias="maxJobs")
    max_runs: int = Field(..., alias="maxRuns")

    class Config:
        populate_by_name = True


class EntitlementsUsage(BaseModel):
    jobs: int
    runs: int


class SelectableProviderInfo(ProviderInfo):
    selectable: bool = True


class ContextJobsEntitlementsOut(BaseModel):
    user_id: Optional[str] = Field(None, alias="userId")
    plan: Optional[str] = None
    context_jobs_enabled: bool = Field(..., alias="contextJobsEnabled")
    message: Optional[str] = None
    upgrade_required: Optional[str] = Field(None, alias="upgradeRequired")
    key_mode: Optional[str] = Field(None, alias="keyMode")
    limits: Optional[EntitlementsLimits] = None
    usage: Optional[EntitlementsUsage] = None
    can_create_job: bool = Field(..., alias="canCreateJob")
    can_create_run: bool = Field(..., alias="canCreateRun")
    providers: list[SelectableProviderInfo] = Field(default_factory=list)

    class Config:
        populate_by_name = True
