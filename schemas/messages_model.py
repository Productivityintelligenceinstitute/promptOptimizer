from database import database
from sqlalchemy import Column, ForeignKey, String, Text,TIMESTAMP, text

class MessagesModel(database.Base):
    __tablename__ = "messages"

    message_id = Column(String, primary_key=True, nullable=False)
    chat_id = Column(String, ForeignKey('chat.chat_id'), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)