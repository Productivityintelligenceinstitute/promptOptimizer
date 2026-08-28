from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ClmConnectionCreate(BaseModel):
    name: str
    provider: str = Field(..., description="coupa | ironclad")
    config: dict[str, Any] = Field(
        ...,
        description=(
            "Provider credentials. "
            "Coupa: instance_url, client_id, client_secret, optional scope. "
            "Ironclad: api_token, optional base_url (na1|eu1|demo.ironcladapp.com), "
            "optional as_user_email."
        ),
    )
    status: str = "active"


class ClmConnectionUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class ClmConnectionOut(BaseModel):
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


class ClmConnectionTestResult(BaseModel):
    ok: bool
    provider: str
    message: str


class ClmImportRequest(BaseModel):
    """Import a contract from Coupa/Ironclad into a Context Job knowledge target."""

    connection_id: UUID = Field(..., alias="connectionId")
    url: Optional[str] = Field(
        None,
        description="Browser URL from Coupa (/contracts/show/{id}) or Ironclad (/workflow/{id} or /record/{id}).",
    )
    resource_id: Optional[str] = Field(
        None,
        alias="resourceId",
        description="Bare resource ID when URL is omitted (uses the connection provider).",
    )
    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Optional extra metadata merged into ingestion (e.g. contractId override).",
    )

    class Config:
        populate_by_name = True


class ClmImportResult(BaseModel):
    provider: str
    resource_type: str = Field(..., alias="resourceType")
    resource_id: str = Field(..., alias="resourceId")
    filename: str
    job_id: UUID = Field(..., alias="jobId")
    ingestion_status: str = Field(..., alias="ingestionStatus")
    upserted_count: int = Field(0, alias="upsertedCount")
    warnings: list[str] = Field(default_factory=list)
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        populate_by_name = True
