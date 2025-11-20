from database import database
from sqlalchemy import Column, String, TIMESTAMP, text

class ChatModel(database.Base):
    __tablename__ = "chat"

    chat_id = Column(String, primary_key=True, nullable=False)
    chat_title = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)