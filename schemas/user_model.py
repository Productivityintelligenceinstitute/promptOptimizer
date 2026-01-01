from database import database
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class UserModel(database.Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid= True), 
        primary_key=True, 
        nullable=False, 
        default=uuid.uuid4
    )
    
    full_name = Column(String, nullable=True)
    role = Column(String, nullable=False, default='user')
    email = Column(String, nullable=False)
    firebase_uid = Column(String, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text('now()'), 
        nullable=False
    )
    
    chats = relationship(
        "ChatModel", 
        back_populates="users", 
        cascade="all, delete-orphan"
    )
    
    subscriptions = relationship(
        "SubscriptionsModel",
        back_populates="users",
        cascade="all, delete-orphan"
    )
    
    usage_logs = relationship(
        "UsageLogModel",
        back_populates="users",
        cascade="all, delete-orphan"
    )
    
    library = relationship(
        "LibraryModel",
        back_populates="users",
        cascade="all, delete-orphan"
    )