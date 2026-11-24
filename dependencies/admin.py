"""Platform-admin guard. The caller is identified from the verified Firebase token,
never from a request parameter."""

from fastapi import Depends, HTTPException, status

from context_jobs.auth import get_current_user
from schemas.user_model import UserModel


def require_platform_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    if str(user.role or "").lower() != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin only.")
    return user
