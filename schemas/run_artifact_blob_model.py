"""Persisted run artifacts as PostgreSQL BYTEA blobs."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Integer, LargeBinary, String, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from database import database


class RunArtifactBlobModel(database.Base):
    __tablename__ = "run_artifact_blobs"
    __table_args__ = (
        UniqueConstraint("run_id", "path", name="uq_run_artifact_blobs_run_id_path"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
    owner = Column(String, nullable=False, index=True)
    run_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    visible_on_run_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    path = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    tool_id = Column(String, nullable=True)
    purpose = Column(String, nullable=False, default="artifact")
    size_bytes = Column(Integer, nullable=False)
    content = Column(LargeBinary, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
