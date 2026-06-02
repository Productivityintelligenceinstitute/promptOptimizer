from database import database
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid


class RunMemoryEntryModel(database.Base):
    """Persistent memory entries across runs."""

    __tablename__ = "run_memory_entries"
    __table_args__ = (
        Index("idx_memory_owner_job", "owner", "job_id"),
        Index("idx_memory_type", "memory_type"),
        Index("idx_memory_expires", "expires_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
    owner = Column(String, nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("context_jobs.id"), nullable=True)
    memory_type = Column(String, nullable=False)
    key = Column(String, nullable=False)
    value = Column(JSONB, nullable=False)
    source_run_id = Column(UUID(as_uuid=True), ForeignKey("job_runs.id"), nullable=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
