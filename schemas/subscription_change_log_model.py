from database import database
from sqlalchemy import Column, String, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid


class SubscriptionChangeLogModel(database.Base):
    __tablename__ = "subscription_change_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
    # The user whose subscription was changed
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Admin who performed the change; NULL means the change was made by the system (cron)
    performed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = Column(String, nullable=False)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    old_end_date = Column(TIMESTAMP(timezone=True), nullable=True)
    new_end_date = Column(TIMESTAMP(timezone=True), nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    user = relationship("UserModel", foreign_keys=[user_id])
    performed_by_user = relationship("UserModel", foreign_keys=[performed_by])
