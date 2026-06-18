from database import database
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid


class ContextJobModel(database.Base):
    __tablename__ = "context_jobs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="draft")
    goal = Column(Text, nullable=True)
    semantic_blueprint = Column(Text, nullable=True)
    output_template = Column(Text, nullable=True)
    workflow_type = Column(String, nullable=False, default="standard")
    stable_instructions = Column(Text, nullable=True)
    role_configuration = Column(Text, nullable=True)
    retrieval_config = Column(JSONB, nullable=True)
    retrieval_mode = Column(String, nullable=False, default="jet_kb")
    vector_connection_id = Column(UUID(as_uuid=True), nullable=True)
    memory_config = Column(JSONB, nullable=True)
    tool_permissions = Column(JSONB, nullable=True)
    validation_rules = Column(JSONB, nullable=True)
    escalation_policy = Column(String, nullable=True)
    budget_settings = Column(JSONB, nullable=True)
    glossary_terms = Column(JSONB, nullable=True)
    relationships = Column(JSONB, nullable=True)
    trusted_sources = Column(JSONB, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    owner = Column(String, nullable=True, default="current_user")
    approval_required = Column(Boolean, nullable=False, default=False)
    policy_profile = Column(String, nullable=True)
    execution_provider = Column(String, nullable=False, default="openai")
    execution_model = Column(String, nullable=True)
    llm_key_id = Column(UUID(as_uuid=True), ForeignKey("llm_provider_keys.id"), nullable=True)
    max_agent_turns = Column(Integer, nullable=False, default=10)
    execution_mode = Column(String, nullable=False, default="single_agent")
    workspace_id = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ContextAssetModel(database.Base):
    __tablename__ = "context_assets"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    name = Column(Text, nullable=False)
    type = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    content = Column(JSONB, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="active")
    owner = Column(String, nullable=True)
    workspace_id = Column(String, nullable=True)
    approval_status = Column(String, nullable=False, default="approved")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkspaceModel(database.Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, nullable=False)
    name = Column(Text, nullable=False)
    owner = Column(String, nullable=False, index=True)
    tool_allowlist = Column(JSONB, nullable=True)
    source_allowlist = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class WorkspaceMemberModel(database.Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_ws_user"),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, default="editor")


class ContextJobVersionModel(database.Base):
    __tablename__ = "context_job_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_context_job_versions_job_id_version"),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    job_id = Column(UUID(as_uuid=True), ForeignKey("context_jobs.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    created_by = Column(String, nullable=True)
    change_type = Column(String, nullable=False, default="save")
    is_current = Column(Boolean, nullable=False, default=False)
    rollback_from_version = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class PublishHistoryModel(database.Base):
    __tablename__ = "publish_history"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    job_id = Column(UUID(as_uuid=True), ForeignKey("context_jobs.id"), nullable=False, index=True)
    from_status = Column(String, nullable=False)
    to_status = Column(String, nullable=False)
    changed_by = Column(String, nullable=False)
    changed_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    notes = Column(Text, nullable=True)


class AuditEventModel(database.Base):
    __tablename__ = "audit_events"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    event_type = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=False, index=True)
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True)
    event_metadata = Column("metadata", JSONB, nullable=True)


class JobRunModel(database.Base):
    __tablename__ = "job_runs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    job_id = Column(UUID(as_uuid=True), nullable=False)
    state = Column(String, nullable=False, default="queued")
    user_request = Column(Text, nullable=True)
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(TIMESTAMP(timezone=True), nullable=True)
    step_logs = Column(JSONB, nullable=True)
    retrieval_events = Column(JSONB, nullable=True)
    tool_events = Column(JSONB, nullable=True)
    validation_events = Column(JSONB, nullable=True)
    source_trace_events = Column(JSONB, nullable=True)
    run_output_package = Column(JSONB, nullable=True)
    human_decision = Column(JSONB, nullable=True)
    outcome = Column(String, nullable=True)
    output_text = Column(Text, nullable=True)
    job_version = Column(Integer, nullable=True)
    token_usage = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    execution_provider = Column(String, nullable=True)
    execution_model = Column(String, nullable=True)
    total_provider_tokens = Column(Integer, nullable=False, default=0)
    total_tool_calls = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    agent_turns = Column(Integer, nullable=False, default=0)
    pending_approvals = Column(JSONB, nullable=True)
    pending_memory_changes = Column(JSONB, nullable=True)
    repair_cycles = Column(Integer, nullable=False, default=0)
    parent_run_id = Column(UUID(as_uuid=True), nullable=True)
    replay_snapshot = Column(JSONB, nullable=True)
    workspace_id = Column(String, nullable=True)

