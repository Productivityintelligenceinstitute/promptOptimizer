from database import database
from sqlalchemy import Column, Integer, String, Boolean , TIMESTAMP, text

class PackagesModel(database.Base):
    __tablename__ = "packages"

    package_id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    package_name = Column(String, nullable=False, unique=True)
    is_custom = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)