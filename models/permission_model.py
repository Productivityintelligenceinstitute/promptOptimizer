from database import database
from sqlalchemy import Column, String, TIMESTAMP, text, Integer

class PermissionModel(database.Base):
    __tablename__ = "permissions"

    permission_id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    permission_name = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)