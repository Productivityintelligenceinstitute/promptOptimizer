from database import database
from sqlalchemy import Column, String, Text, TIMESTAMP, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid


class ToolProviderKeyModel(database.Base):
    """Encrypted BYOK credentials for external tool providers (e.g. tavily for web-search)."""

    __tablename__ = "tool_provider_keys"
    __table_args__ = (
        UniqueConstraint("owner", "tool_id", "key_label", name="uq_tool_keys_owner_tool_label"),
        Index("idx_tool_keys_owner", "owner"),
        Index("idx_tool_keys_owner_tool", "owner", "tool_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
    owner = Column(String, nullable=False)
    tool_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    key_label = Column(String, nullable=False)
    encrypted_key = Column(Text, nullable=False)
    key_last_four = Column(String(4), nullable=True)
    status = Column(String, nullable=False, default="active")
    last_verified_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
