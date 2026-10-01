from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
# from schemas.user_model import UserModel
# from schemas.packages_model import PackagesModel
# from schemas.permission_model import PermissionModel
# from schemas.packages_permission_model import PackagesPermissionModel
# from schemas.subscription_model import SubscriptionModel
# from schemas.chat_model import ChatModel
# from schemas.messages_model import MessageModel
# from schemas.library_model import LibraryModel
# from schemas.usage_log_model import UsageLogModel
from dotenv import load_dotenv
import os

load_dotenv()


def normalize_database_url(url: str | None) -> str | None:
    """Force psycopg2 dialect — SQLAlchemy 2.1+ defaults postgresql:// to psycopg v3."""
    if not url:
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    return url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL"))

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def create_db_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()