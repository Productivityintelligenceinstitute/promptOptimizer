from database import database
from sqlalchemy import Column, String, Text, TIMESTAMP, Integer, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid


class ToolExecutionModel(database.Base):
    """Audit log for tool calls during runs."""

    __tablename__ = "tool_executions"
    __table_args__ = (Index("idx_tool_exec_run", "run_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("job_runs.id"), nullable=False)
    tool_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    action = Column(String, nullable=False)
    status = Column(String, nullable=False)
    arguments = Column(JSONB, nullable=True)
    result_summary = Column(Text, nullable=True)
    denial_reason = Column(Text, nullable=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
