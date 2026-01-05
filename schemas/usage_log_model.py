from database import database
from sqlalchemy import Column, ForeignKey, Date, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class UsageLogModel(database.Base):
    __tablename__ = "usage_logs"
    
    id = Column(UUID(as_uuid= True), primary_key=True, nullable=False, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid= True), ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    permission_id = Column(UUID(as_uuid= True), ForeignKey("permissions.id", ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    count = Column(Integer, default=0, nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", "date"),
    )
    users = relationship("UserModel",back_populates="usage_logs")
    permissions = relationship("PermissionModel",back_populates="usage_logs")