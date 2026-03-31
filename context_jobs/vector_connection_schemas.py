from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class VectorConnectionCreate(BaseModel):
    name: str
    provider: str
    config: dict[str, Any]
    status: str = "active"
    owner: Optional[str] = None


class VectorConnectionUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class VectorConnectionOut(BaseModel):
    id: UUID
    owner: str
    name: str
    provider: str
    status: str
    last_tested_at: Optional[datetime] = Field(None, alias="lastTestedAt")
    last_error: Optional[str] = Field(None, alias="lastError")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class VectorConnectionTestResult(BaseModel):
    ok: bool
    provider: str
    message: str

