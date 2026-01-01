from database import database
from sqlalchemy import Column, ForeignKey, String, Text,TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class MessagesModel(database.Base):
    __tablename__ = "messages"

    id = Column(
        UUID(as_uuid= True), 
        primary_key=True, 
        nullable=False, 
        default=uuid.uuid4
    )
    
    chat_id = Column(UUID(as_uuid= True), ForeignKey('chats.id', ondelete='CASCADE'))
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    
    chats = relationship(
        "ChatModel",
        back_populates="messages"
    )
    
    library = relationship(
        "LibraryModel",
        back_populates="messages",
        cascade="all, delete-orphan"
    )