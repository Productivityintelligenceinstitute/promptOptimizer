from database import database
from sqlalchemy import Column, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid


class ContextClmConnectionModel(database.Base):
    """Encrypted Coupa / Ironclad (CLM) connection for paste-URL contract import."""

    __tablename__ = "context_clm_connections"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )
    owner = Column(String, nullable=False, default="current_user")
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False)  # coupa | ironclad
    encrypted_config = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default="active")
    last_tested_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
