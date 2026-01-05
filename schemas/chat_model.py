from database import database
from sqlalchemy import Column, String, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class ChatModel(database.Base):
    __tablename__ = "chats"

    id = Column(UUID(as_uuid= True), primary_key=True, nullable=False, default=uuid.uuid4)
    chat_title = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid= True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    users = relationship("UserModel", back_populates="chats")
    messages = relationship("MessagesModel", back_populates="chats", cascade="all, delete-orphan")