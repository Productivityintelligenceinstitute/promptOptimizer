from database import database
from sqlalchemy import Column, ForeignKey, UniqueConstraint, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class LibraryModel(database.Base):
    __tablename__ = "library"

    id = Column(UUID(as_uuid= True), primary_key=True, nullable=False, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid= True), ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    message_id = Column(UUID(as_uuid= True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "message_id"),
    )
    users = relationship("UserModel", back_populates="library")
    messages = relationship("MessagesModel", back_populates="library")