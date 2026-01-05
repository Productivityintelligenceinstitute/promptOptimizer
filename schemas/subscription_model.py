from database import database
from sqlalchemy import Column, String, ForeignKey, UniqueConstraint, Boolean, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

class SubscriptionsModel(database.Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid= True), primary_key=True, nullable=False, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid= True), ForeignKey("users.id", ondelete='CASCADE'), nullable=False)
    package_id = Column(UUID(as_uuid= True), ForeignKey("packages.id", ondelete='CASCADE'), nullable=False)
    status = Column(String, nullable=False)
    start_date = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))
    end_date = Column(TIMESTAMP(timezone=True), nullable=True)
    auto_renew = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
    __table_args__ = (
        UniqueConstraint("user_id", "package_id"),
    )
    users = relationship("UserModel",back_populates="subscriptions")
    packages = relationship("PackagesModel",back_populates="subscriptions")