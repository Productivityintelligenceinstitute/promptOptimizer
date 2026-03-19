from database import database
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean
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
    workflow_type = Column(String, nullable=False, default="standard")
    stable_instructions = Column(Text, nullable=True)
    role_configuration = Column(Text, nullable=True)
    retrieval_config = Column(JSONB, nullable=True)
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
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


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
    token_usage = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)

