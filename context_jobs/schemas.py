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
    retrieval_mode: str = Field("jet_kb", alias="retrievalMode")
    vector_connection_id: Optional[UUID] = Field(None, alias="vectorConnectionId")
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
    execution_provider: str = Field("openai", alias="executionProvider")
    execution_model: Optional[str] = Field(None, alias="executionModel")
    llm_key_id: Optional[UUID] = Field(None, alias="llmKeyId")
    max_agent_turns: int = Field(10, alias="maxAgentTurns")

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
    retrieval_mode: Optional[str] = Field(None, alias="retrievalMode")
    vector_connection_id: Optional[UUID] = Field(None, alias="vectorConnectionId")
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
    execution_provider: Optional[str] = Field(None, alias="executionProvider")
    execution_model: Optional[str] = Field(None, alias="executionModel")
    llm_key_id: Optional[UUID] = Field(None, alias="llmKeyId")
    max_agent_turns: Optional[int] = Field(None, alias="maxAgentTurns")

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
    user_request: Optional[str] = Field("", alias="userRequest")

    class Config:
        populate_by_name = True


class JobRunOut(BaseModel):
    id: UUID
    job_id: UUID = Field(..., alias="jobId")
    state: str

    user_request: Optional[str] = Field(None, alias="userRequest")
    started_at: datetime = Field(..., alias="startedAt")
    ended_at: Optional[datetime] = Field(None, alias="endedAt")

    step_logs: Optional[list] = Field(None, alias="stepLogs")
    retrieval_events: Optional[list] = Field(None, alias="retrievalEvents")
    tool_events: Optional[list] = Field(None, alias="toolEvents")
    validation_events: Optional[list] = Field(None, alias="validationEvents")
    source_trace_events: Optional[list] = Field(None, alias="sourceTraceEvents")
    run_output_package: Optional[dict] = Field(None, alias="runOutputPackage")
    human_decision: Optional[dict] = Field(None, alias="humanDecision")

    outcome: Optional[str] = None
    output_text: Optional[str] = Field(None, alias="outputText")
    token_usage: Optional[int] = Field(None, alias="tokenUsage")
    latency_ms: Optional[int] = Field(None, alias="latencyMs")
    execution_provider: Optional[str] = Field(None, alias="executionProvider")
    execution_model: Optional[str] = Field(None, alias="executionModel")
    total_provider_tokens: Optional[int] = Field(None, alias="totalProviderTokens")
    total_tool_calls: Optional[int] = Field(None, alias="totalToolCalls")
    estimated_cost_usd: Optional[float] = Field(None, alias="estimatedCostUsd")
    agent_turns: Optional[int] = Field(None, alias="agentTurns")

    class Config:
        from_attributes = True
        populate_by_name = True


class RunDecisionRequest(BaseModel):
    decision: str
    notes: Optional[str] = None
    decided_by: str = Field("current_user", alias="decidedBy")

    class Config:
        populate_by_name = True


class ContextJobsStatsOut(BaseModel):
    jobCount: int
    runCount: int
    assetCount: int
    passRate: int


class IngestionDocument(BaseModel):
    """Single document for ingestion."""

    text: str
    metadata: dict[str, Any] | None = None
    id: str | None = None


class IngestionRequest(BaseModel):
    """Request payload for document ingestion."""

    documents: list[IngestionDocument]
    ingestion_config: dict[str, Any] | None = Field(None, alias="ingestionConfig")

    class Config:
        populate_by_name = True

