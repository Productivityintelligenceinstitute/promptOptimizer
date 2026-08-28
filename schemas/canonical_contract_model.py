"""Full-text canonical contract storage for amendment source fidelity."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, String, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from database import database


class CanonicalContractModel(database.Base):
    __tablename__ = "canonical_contracts"
    __table_args__ = (
        UniqueConstraint("owner", "source_doc_id", name="uq_canonical_contracts_owner_source_doc_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
    owner = Column(String, nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    source_doc_id = Column(String, nullable=True, index=True)
    contract_id = Column(String, nullable=True, index=True)
    text = Column(Text, nullable=False)
    content_hash = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
