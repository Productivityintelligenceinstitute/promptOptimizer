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
