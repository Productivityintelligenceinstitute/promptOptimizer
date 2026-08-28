from datetime import date, datetime
import json
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, model_validator


class ContextJobBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "draft"
    goal: Optional[str] = None

    semantic_blueprint: Optional[str] = Field(None, alias="semanticBlueprint")
    output_template: Optional[str] = Field(None, alias="outputTemplate")
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
    chain_config: Optional[dict] = Field(None, alias="chainConfig")
    linked_child_job_id: Optional[UUID] = Field(None, alias="linkedChildJobId")

    version: int = 1
    owner: Optional[str] = None
    approval_required: bool = Field(False, alias="approvalRequired")
    policy_profile: Optional[str] = Field(None, alias="policyProfile")
    execution_provider: str = Field("openai", alias="executionProvider")
    execution_model: Optional[str] = Field(None, alias="executionModel")
    llm_key_id: Optional[UUID] = Field(None, alias="llmKeyId")
    max_agent_turns: int = Field(10, alias="maxAgentTurns")
    execution_mode: str = Field("single_agent", alias="executionMode")
    workspace_id: Optional[str] = Field(None, alias="workspaceId")

    class Config:
        populate_by_name = True


class ContextJobCreate(ContextJobBase):
    asset_ids: Optional[list[UUID]] = Field(None, alias="assetIds")


class ContextJobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    goal: Optional[str] = None

    semantic_blueprint: Optional[str] = Field(None, alias="semanticBlueprint")
    output_template: Optional[str] = Field(None, alias="outputTemplate")
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
    chain_config: Optional[dict] = Field(None, alias="chainConfig")
    linked_child_job_id: Optional[UUID] = Field(None, alias="linkedChildJobId")

    version: Optional[int] = None
    owner: Optional[str] = None
    approval_required: Optional[bool] = Field(None, alias="approvalRequired")
    policy_profile: Optional[str] = Field(None, alias="policyProfile")
    execution_provider: Optional[str] = Field(None, alias="executionProvider")
    execution_model: Optional[str] = Field(None, alias="executionModel")
    llm_key_id: Optional[UUID] = Field(None, alias="llmKeyId")
    max_agent_turns: Optional[int] = Field(None, alias="maxAgentTurns")
    execution_mode: Optional[str] = Field(None, alias="executionMode")
    workspace_id: Optional[str] = Field(None, alias="workspaceId")
    asset_ids: Optional[list[UUID]] = Field(None, alias="assetIds")

    class Config:
        populate_by_name = True


class ContextJobOut(ContextJobBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    asset_ids: list[UUID] = Field(default_factory=list, alias="assetIds")

    @model_validator(mode="before")
    @classmethod
    def _hydrate_asset_ids(cls, data: Any) -> Any:
        """Map ORM linked_asset_ids into API assetIds for responses."""
        if data is None:
            return data

        if hasattr(data, "__table__"):
            payload = {col.name: getattr(data, col.name) for col in data.__table__.columns}
            raw = payload.get("linked_asset_ids") or []
            payload["asset_ids"] = raw if isinstance(raw, list) else []
            return payload

        if isinstance(data, dict):
            if "asset_ids" not in data and "assetIds" not in data:
                raw = data.get("linked_asset_ids") or data.get("linkedAssetIds") or []
                return {**data, "asset_ids": raw if isinstance(raw, list) else []}
            return data

        return data

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
    owner: Optional[str] = None
    workspace_id: Optional[str] = Field(None, alias="workspaceId")
    approval_status: str = Field("approved", alias="approvalStatus")


class ContextAssetCreate(ContextAssetBase):
    pass


class ContextAssetUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    content: Optional[Any] = None
    version: Optional[int] = None
    status: Optional[str] = None
    approval_status: Optional[str] = Field(None, alias="approvalStatus")


class ContextAssetOut(ContextAssetBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobRunCreate(BaseModel):
    user_request: Optional[str] = Field("", alias="userRequest")
    parent_run_id: Optional[UUID] = Field(
        None,
        alias="parentRunId",
        description="Optional parent run id when continuing a lifecycle handoff.",
    )

    class Config:
        populate_by_name = True


class JobPendingHandoffOut(BaseModel):
    parent_run_id: UUID = Field(..., alias="parentRunId")
    child_job_id: UUID = Field(..., alias="childJobId")
    suggested_user_request: str = Field("", alias="suggestedUserRequest")
    label: Optional[str] = None
    status: str = "awaiting_handoff"

    class Config:
        populate_by_name = True


class PromptToJobRequest(BaseModel):
    prompt: str
    agent_type: Optional[str] = Field(None, alias="agentType")

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
    job_version: Optional[int] = Field(None, alias="jobVersion")
    token_usage: Optional[int] = Field(None, alias="tokenUsage")
    latency_ms: Optional[int] = Field(None, alias="latencyMs")
    execution_provider: Optional[str] = Field(None, alias="executionProvider")
    execution_model: Optional[str] = Field(None, alias="executionModel")
    total_provider_tokens: Optional[int] = Field(None, alias="totalProviderTokens")
    total_tool_calls: Optional[int] = Field(None, alias="totalToolCalls")
    estimated_cost_usd: Optional[float] = Field(None, alias="estimatedCostUsd")
    agent_turns: Optional[int] = Field(None, alias="agentTurns")
    pending_approvals: Optional[list] = Field(None, alias="pendingApprovals")
    pending_memory_changes: Optional[dict] = Field(None, alias="pendingMemoryChanges")
    repair_cycles: Optional[int] = Field(None, alias="repairCycles")
    parent_run_id: Optional[UUID] = Field(None, alias="parentRunId")
    amendment_run_id: Optional[UUID] = Field(None, alias="amendmentRunId")
    amendment_state: Optional[str] = Field(None, alias="amendmentState")
    amendment_validation: Optional[dict] = Field(None, alias="amendmentValidation")
    amendment_source_status: Optional[str] = Field(None, alias="amendmentSourceStatus")
    workspace_id: Optional[str] = Field(None, alias="workspaceId")

    class Config:
        from_attributes = True
        populate_by_name = True

    @staticmethod
    def _normalize_output_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            return str(value)

        text = value.strip()
        if not text:
            return text

        current: Any = text
        for _ in range(2):
            if not isinstance(current, str):
                break
            candidate = current.strip()
            try:
                parsed = json.loads(candidate)
            except Exception:
                break
            current = parsed

        if isinstance(current, (dict, list)):
            return json.dumps(current, ensure_ascii=False, separators=(",", ":"))
        if isinstance(current, str):
            return current
        return text

    @field_serializer("output_text", when_used="json")
    def serialize_output_text(self, value: Any) -> Optional[str]:
        return self._normalize_output_text(value)

    @model_validator(mode="after")
    def mask_while_awaiting_approval(self) -> "JobRunOut":
        from context_jobs.hitl import (
            WAITING_ON_APPROVAL_MESSAGE,
            build_waiting_run_output_package,
            summarize_pending_approvals,
            waiting_message_for_tools,
        )

        if self.state == "awaiting_tool_approval":
            pending = self.pending_approvals
            self.output_text = waiting_message_for_tools(pending)
            self.run_output_package = build_waiting_run_output_package(pending)
            self.pending_approvals = summarize_pending_approvals(pending)
            self.tool_events = None
            self.outcome = None
        elif self.state == "awaiting_memory_approval":
            self.output_text = WAITING_ON_APPROVAL_MESSAGE
            self.pending_memory_changes = None
            if not self.run_output_package:
                self.run_output_package = {
                    "status": "awaiting_memory_approval",
                    "primaryResult": {
                        "resultType": "text_output",
                        "title": "Waiting for approval",
                        "content": WAITING_ON_APPROVAL_MESSAGE,
                    },
                    "nextAction": {
                        "type": "request_approval",
                        "label": WAITING_ON_APPROVAL_MESSAGE,
                    },
                }
        return self


class RunChainParentOut(BaseModel):
    run_id: UUID = Field(..., alias="runId")
    job_id: UUID = Field(..., alias="jobId")
    job_name: str = Field(..., alias="jobName")
    status: str
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        populate_by_name = True


class RunChainNodeOut(BaseModel):
    run_id: UUID = Field(..., alias="runId")
    job_id: UUID = Field(..., alias="jobId")
    job_name: str = Field(..., alias="jobName")
    status: str
    created_at: datetime = Field(..., alias="createdAt")
    child_runs: list["RunChainNodeOut"] = Field(default_factory=list, alias="childRuns")

    class Config:
        populate_by_name = True


class RunChainOut(BaseModel):
    run_id: UUID = Field(..., alias="runId")
    parent_run_id: UUID | None = Field(None, alias="parentRunId")
    parent_run: RunChainParentOut | None = Field(None, alias="parentRun")
    child_runs: list[RunChainNodeOut] = Field(default_factory=list, alias="childRuns")

    class Config:
        populate_by_name = True


RunChainNodeOut.model_rebuild()


class ContextJobVersionOut(BaseModel):
    id: UUID
    job_id: UUID = Field(..., alias="jobId")
    version: int
    created_at: datetime = Field(..., alias="createdAt")
    created_by: Optional[str] = Field(None, alias="createdBy")
    change_type: Optional[str] = Field(None, alias="changeType")
    is_current: bool = Field(..., alias="isCurrent")
    rollback_from_version: Optional[int] = Field(None, alias="rollbackFromVersion")
    notes: Optional[str] = None
    job_snapshot: dict[str, Any] = Field(..., alias="jobSnapshot")

    class Config:
        populate_by_name = True
        from_attributes = True


class PublishHistoryOut(BaseModel):
    id: UUID
    job_id: UUID = Field(..., alias="jobId")
    from_status: str = Field(..., alias="fromStatus")
    to_status: str = Field(..., alias="toStatus")
    changed_by: str = Field(..., alias="changedBy")
    changed_at: datetime = Field(..., alias="changedAt")
    notes: Optional[str] = None

    class Config:
        populate_by_name = True
        from_attributes = True


class AuditEventOut(BaseModel):
    id: UUID
    event_type: str = Field(..., alias="eventType")
    entity_type: str = Field(..., alias="entityType")
    entity_id: str = Field(..., alias="entityId")
    actor: str
    timestamp: datetime
    metadata: Optional[dict[str, Any]] = None

    class Config:
        populate_by_name = True
        from_attributes = True


class RunDecisionRequest(BaseModel):
    decision: str
    notes: Optional[str] = None
    decided_by: str = Field("current_user", alias="decidedBy")

    class Config:
        populate_by_name = True


class JobVersionRollbackRequest(BaseModel):
    version: int = Field(..., ge=1, alias="version")
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


class JobLifecycleRequest(BaseModel):
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


class ContextJobsStatsOut(BaseModel):
    jobCount: int
    runCount: int
    assetCount: int
    passRate: int


class RunArtifactOut(BaseModel):
    path: str
    filename: Optional[str] = None
    size_bytes: Optional[int] = Field(None, alias="sizeBytes")
    mime_type: Optional[str] = Field(None, alias="mimeType")
    tool_id: Optional[str] = Field(None, alias="toolId")
    purpose: Optional[str] = None

    class Config:
        populate_by_name = True


class RunArtifactsOut(BaseModel):
    runId: UUID
    artifacts: list[RunArtifactOut]


class SpecialistAgentOut(BaseModel):
    name: str
    description: str
    toolIds: list[str] = Field(..., alias="toolIds")
    maxTurns: int = Field(..., alias="maxTurns")

    class Config:
        populate_by_name = True


class ExecutionModesOut(BaseModel):
    modes: list[dict[str, str]]


class ProcurementAlertOut(BaseModel):
    id: UUID
    owner: str
    workspace_id: str | None = Field(None, alias="workspaceId")
    vendor: str | None = None
    contract_document_id: str = Field(..., alias="contractDocumentId")
    expiry_date: date = Field(..., alias="expiryDate")
    complexity_tier: str = Field(..., alias="complexityTier")
    lead_months_threshold: int = Field(..., alias="leadMonthsThreshold")
    complexity_tier_defaulted: bool = Field(..., alias="complexityTierDefaulted")
    description: str | None = None
    alerted_at: datetime = Field(..., alias="alertedAt")
    dismissed: bool
    suggested_job_id: UUID | None = Field(None, alias="suggestedJobId")

    class Config:
        populate_by_name = True
        from_attributes = True


class ProcurementContractRegisterOut(BaseModel):
    """Result of registering a contract into the caller's Jet managed KB for expiry alerts."""

    contract_document_id: str = Field(..., alias="contractDocumentId")
    expiry_date: date = Field(..., alias="expiryDate")
    vendor: str | None = None
    description: str | None = None
    complexity_tier: str = Field(..., alias="complexityTier")
    namespace: str
    ingestion_status: str = Field(..., alias="ingestionStatus")
    upserted_count: int = Field(0, alias="upsertedCount")
    warnings: list[str] = Field(default_factory=list)
    message: str

    class Config:
        populate_by_name = True


class IngestionDocumentMetadata(BaseModel):
    """
    Client-provided ingest metadata.

    Known procurement fields are first-class. Additional string keys are allowed
    (extra=\"allow\") so jobs can stamp custom identifiers for trusted-source filters
    (e.g. contractId, file, vendor). Unknown nested objects are rejected at coerce time.
    """

    name: str | None = None
    document_name: str | None = Field(None, alias="documentName")
    title: str | None = None
    document_type: str | None = Field(None, alias="documentType")
    contract_id: str | None = Field(None, alias="contractId")
    contract_name: str | None = Field(None, alias="contractName")
    vendor: str | None = None
    vendor_name: str | None = Field(None, alias="vendorName")
    vendor_id: str | None = Field(None, alias="vendorId")
    expiry_date: str | None = Field(None, alias="expiryDate")
    complexity_tier: str | None = Field(None, alias="complexityTier")
    description: str | None = None
    category: str | None = None
    file: str | None = None
    source: str | None = None
    url: str | None = None

    class Config:
        populate_by_name = True
        extra = "allow"

class IngestionDocument(BaseModel):
    """Single document for ingestion."""

    text: str
    metadata: IngestionDocumentMetadata | str | None = None
    id: str | None = None


class IngestionRequest(BaseModel):
    """Request payload for document ingestion."""

    documents: list[IngestionDocument]
    ingestion_config: dict[str, Any] | None = Field(None, alias="ingestionConfig")

    class Config:
        populate_by_name = True


class ExternalIngestionRequest(IngestionRequest):
    """Ingest documents into a saved external vector connection (no job required)."""

    vector_connection_id: UUID = Field(..., alias="vectorConnectionId")

    class Config:
        populate_by_name = True


class ToolApprovalRequest(BaseModel):
    decision: str
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


class MemoryConfirmRequest(BaseModel):
    approved: bool

    class Config:
        populate_by_name = True


class AttachContractRequest(BaseModel):
    contract_text: str = Field(..., alias="contractText", min_length=50)

    class Config:
        populate_by_name = True


class WorkspaceMemberCreate(BaseModel):
    user_id: str = Field(..., alias="userId")
    role: str = "editor"

    class Config:
        populate_by_name = True


class AllowlistUpdate(BaseModel):
    tools: Optional[list[str]] = None
    sources: Optional[list[str]] = None

    class Config:
        populate_by_name = True


class AssetImportRequest(BaseModel):
    asset_id: UUID = Field(..., alias="assetId")

    class Config:
        populate_by_name = True


class IdentityMatchRequest(BaseModel):
    query: str

    class Config:
        populate_by_name = True


class ProcurementDemoSetupRequest(BaseModel):
    template_id: Optional[UUID] = Field(None, alias="templateId")
    template_name: Optional[str] = Field(None, alias="templateName")
    enable_chain: bool = Field(False, alias="enableChain")

    class Config:
        populate_by_name = True


class ProcurementDemoIngestionOut(BaseModel):
    status: str
    outcome: str
    upserted_count: int = Field(0, alias="upsertedCount")
    failed_count: int = Field(0, alias="failedCount")
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    ingested_sources: list[dict[str, Any]] = Field(default_factory=list, alias="ingestedSources")

    class Config:
        populate_by_name = True


class ProcurementDemoSetupOut(BaseModel):
    job: ContextJobOut
    ingestion: ProcurementDemoIngestionOut

    class Config:
        populate_by_name = True

