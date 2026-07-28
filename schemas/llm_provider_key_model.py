from database import database
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid


class LlmProviderKeyModel(database.Base):
    """Encrypted BYOK credentials for LLM providers (anthropic, openai, google)."""

    __tablename__ = "llm_provider_keys"
    __table_args__ = (
        UniqueConstraint("owner", "provider", "key_label", name="uq_llm_keys_owner_provider_label"),
        Index("idx_llm_keys_owner", "owner"),
        Index("idx_llm_keys_owner_provider", "owner", "provider"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
    owner = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    key_purpose = Column(String, nullable=False, default="llm")
    key_label = Column(String, nullable=False)
    encrypted_key = Column(Text, nullable=False)
    key_last_four = Column(String(4), nullable=True)
    is_platform_key = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="active")
    last_verified_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    usage_count = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
