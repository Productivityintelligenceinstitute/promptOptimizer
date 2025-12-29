from pickle import TRUE
from database import database
from sqlalchemy import Column, String, TIMESTAMP, text

class UserModel(database.Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, nullable=False)
    email = Column(String, nullable=False)
    full_name = Column(String, nullable=TRUE)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'), nullable=False)
    role = Column(String, nullable=False, default='user')
    firebase_uid = Column(String, nullable=True)
