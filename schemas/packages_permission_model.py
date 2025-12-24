from database import database
from sqlalchemy import Column, Integer, ForeignKey, Boolean

class PackagesPermissionModel(database.Base):
    __tablename__ = "packages_permission"

    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    package_id = Column(Integer, ForeignKey('packages.package_id'), nullable=False)
    permission_id = Column(Integer, ForeignKey('permissions.permission_id'), nullable=False)
    is_enabled = Column(Boolean, nullable=False)
    query_limit = Column(Integer, nullable=True)