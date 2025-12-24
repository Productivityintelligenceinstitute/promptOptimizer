from database import database
from sqlalchemy import Column, String, ForeignKey, Date, Integer, UniqueConstraint

class UsageLogModel(database.Base):
    __tablename__ = "usage_logs"

    log_id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.permission_id"), nullable=False)
    date = Column(Date, nullable=False)
    count = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", "date"),
    )