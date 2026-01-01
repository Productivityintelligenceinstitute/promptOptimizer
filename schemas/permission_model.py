from database import database
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class PermissionModel(database.Base):
    __tablename__ = "permissions"

    id = Column(
        UUID(as_uuid= True), 
        primary_key=True, 
        nullable=False, 
        default=uuid.uuid4
    )
    
    permission_name = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    
    packages_permission = relationship(
        "PackagesPermissionModel",
        back_populates="permissions",
        cascade="all, delete-orphan"
    )
    
    usage_logs = relationship(
        "UsageLogModel",
        back_populates="permissions",
        cascade="all, delete-orphan"
    )