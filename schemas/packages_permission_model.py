from database import database
from sqlalchemy import Column, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class PackagesPermissionModel(database.Base):
    __tablename__ = "packages_permission"

    id = Column(
        UUID(as_uuid= True), 
        primary_key=True, 
        nullable=False, 
        default=uuid.uuid4
    )
    
    package_id = Column(UUID(as_uuid= True), ForeignKey('packages.id', ondelete='CASCADE'), nullable=False)
    permission_id = Column(UUID(as_uuid= True), ForeignKey('permissions.id', ondelete='CASCADE'), nullable=False)
    is_enabled = Column(Boolean, nullable=False)
    query_limit = Column(Integer, nullable=True)
    
    packages = relationship(
        "PackagesModel",
        back_populates="packages_permission"
    )
    
    permissions = relationship(
        "PermissionModel",
        back_populates="packages_permission"
    )