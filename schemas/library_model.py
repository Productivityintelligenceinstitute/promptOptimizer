from database import database
from sqlalchemy import Column, String, ForeignKey, UniqueConstraint, TIMESTAMP, text

class LibraryModel(database.Base):
    __tablename__ = "library"

    library_id = Column(String, primary_key=True, nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    message_id = Column(String, ForeignKey("messages.message_id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "message_id"),
    )