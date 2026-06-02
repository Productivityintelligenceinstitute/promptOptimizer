from database import database
from sqlalchemy import Column, String, Text, TIMESTAMP, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func


class ToolRegistryModel(database.Base):
    """Catalog of tools available for Context Jobs."""

    __tablename__ = "tool_registry"

    id = Column(String, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    input_schema = Column(JSONB, nullable=False)
    output_schema = Column(JSONB, nullable=True)
    is_read_only = Column(Boolean, nullable=False, default=True)
    requires_approval = Column(Boolean, nullable=False, default=False)
    max_timeout_ms = Column(Integer, nullable=False, default=30000)
    enabled = Column(Boolean, nullable=False, default=True)
    provider_support = Column(JSONB, nullable=True)
    external_provider = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
