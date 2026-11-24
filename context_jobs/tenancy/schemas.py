"""Request bodies for workspace, membership, invitation and platform-admin routes."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Body(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class MemberUpdate(_Body):
    role: Optional[str] = None
    status: Optional[str] = None


class InvitationCreate(_Body):
    email: str = Field(..., max_length=320)
    role: str


class AllowlistUpdate(_Body):
    tools: Optional[list[str]] = None
    sources: Optional[list[str]] = None


class CompanyCreate(_Body):
    name: str = Field(..., min_length=1, max_length=200)
    plan: Optional[str] = "company"
    access_expires_at: Optional[datetime] = Field(None, alias="accessExpiresAt")
    notes: Optional[str] = Field(None, max_length=2000)
    admin_email: Optional[str] = Field(None, alias="adminEmail", max_length=320)


class CompanyUpdate(_Body):
    """Only fields present in the request are changed; send null to clear expiry or notes."""

    name: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = None
    plan: Optional[str] = None
    access_expires_at: Optional[datetime] = Field(None, alias="accessExpiresAt")
    notes: Optional[str] = Field(None, max_length=2000)
