from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContextJobBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "draft"
    goal: Optional[str] = None

    semantic_blueprint: Optional[str] = Field(None, alias="semanticBlueprint")
    workflow_type: str = Field("standard", alias="workflowType")
    stable_instructions: Optional[str] = Field(None, alias="stableInstructions")
    role_configuration: Optional[str] = Field(None, alias="roleConfiguration")

    retrieval_config: Optional[dict] = Field(None, alias="retrievalConfig")
    memory_config: Optional[dict] = Field(None, alias="memoryConfig")
    tool_permissions: Optional[list[dict]] = Field(None, alias="toolPermissions")
    validation_rules: Optional[list[dict]] = Field(None, alias="validationRules")

    escalation_policy: Optional[str] = Field(None, alias="escalationPolicy")
    budget_settings: Optional[dict] = Field(None, alias="budgetSettings")
    glossary_terms: Optional[list[dict]] = Field(None, alias="glossaryTerms")
    relationships: Optional[list[dict]] = None
    trusted_sources: Optional[list[dict]] = Field(None, alias="trustedSources")

    version: int = 1
    owner: Optional[str] = None
    approval_required: bool = Field(False, alias="approvalRequired")
    policy_profile: Optional[str] = Field(None, alias="policyProfile")

    class Config:
        populate_by_name = True


class ContextJobCreate(ContextJobBase):
    pass


class ContextJobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    goal: Optional[str] = None

    semantic_blueprint: Optional[str] = Field(None, alias="semanticBlueprint")
    workflow_type: Optional[str] = Field(None, alias="workflowType")
    stable_instructions: Optional[str] = Field(None, alias="stableInstructions")
    role_configuration: Optional[str] = Field(None, alias="roleConfiguration")

    retrieval_config: Optional[dict] = Field(None, alias="retrievalConfig")
    memory_config: Optional[dict] = Field(None, alias="memoryConfig")
    tool_permissions: Optional[list[dict]] = Field(None, alias="toolPermissions")
    validation_rules: Optional[list[dict]] = Field(None, alias="validationRules")

    escalation_policy: Optional[str] = Field(None, alias="escalationPolicy")
    budget_settings: Optional[dict] = Field(None, alias="budgetSettings")
    glossary_terms: Optional[list[dict]] = Field(None, alias="glossaryTerms")
    relationships: Optional[list[dict]] = None
    trusted_sources: Optional[list[dict]] = Field(None, alias="trustedSources")

    version: Optional[int] = None
    owner: Optional[str] = None
    approval_required: Optional[bool] = Field(None, alias="approvalRequired")
    policy_profile: Optional[str] = Field(None, alias="policyProfile")

    class Config:
        populate_by_name = True


class ContextJobOut(ContextJobBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True


class ContextAssetBase(BaseModel):
    name: str
    type: str
    description: Optional[str] = None
    content: Optional[Any] = None
    version: int = 1
    status: str = "active"


class ContextAssetCreate(ContextAssetBase):
    pass


class ContextAssetUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    content: Optional[Any] = None
    version: Optional[int] = None
    status: Optional[str] = None


class ContextAssetOut(ContextAssetBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobRunCreate(BaseModel):
    userRequest: Optional[str] = Field("", alias="userRequest")

    class Config:
        populate_by_name = True


class JobRunOut(BaseModel):
    id: UUID
    jobId: UUID
    state: str

    userRequest: Optional[str] = None
    startedAt: datetime
    endedAt: Optional[datetime] = None

    stepLogs: Optional[list] = None
    retrievalEvents: Optional[list] = None
    toolEvents: Optional[list] = None
    validationEvents: Optional[list] = None
    sourceTraceEvents: Optional[list] = None
    runOutputPackage: Optional[dict] = None
    humanDecision: Optional[dict] = None

    outcome: Optional[str] = None
    outputText: Optional[str] = None
    tokenUsage: Optional[int] = None
    latencyMs: Optional[int] = None

    class Config:
        from_attributes = True
        populate_by_name = True

