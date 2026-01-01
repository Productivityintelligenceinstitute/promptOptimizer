from repositories.check_role import RoleRepository
from repositories.check_package import CheckPackageRepository
from repositories.check_access import AccessRepository
from repositories.daily_usage import UsageRepository
from fastapi import HTTPException

def validate_access(db, user_id, permission):
    role = RoleRepository.check_role(db, user_id)
    
    if role == "admin":
        return
    
    CheckPackageRepository.check_user_package(db, user_id)
    
    access = AccessRepository.check_access(db, user_id, permission)
    if not access or not access.is_enabled:
        raise HTTPException(status_code=403, detail="Access denied")
    
    UsageRepository.check_daily_usage(
        db, user_id, access.permission_id, access.query_limit
    )

    UsageRepository.increment_daily_usage(db, user_id, access.permission_id)
