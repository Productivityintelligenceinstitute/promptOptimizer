from database import database
from sqlalchemy import Column, String, Boolean , TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class PackagesModel(database.Base):
    __tablename__ = "packages"

    id = Column(UUID(as_uuid= True), primary_key=True, nullable=False, default=uuid.uuid4)
    package_name = Column(String, nullable=False, unique=True)
    is_custom = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    packages_permission = relationship( "PackagesPermissionModel",back_populates="packages",cascade="all, delete-orphan")
    subscriptions = relationship("SubscriptionsModel",back_populates="packages",cascade="all, delete-orphan")