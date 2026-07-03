from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer
from firebase_admin import auth
from sqlalchemy.orm import Session
import logging

from database import database
from schemas.user_model import UserModel

logger = logging.getLogger(__name__)
security = HTTPBearer()

def verify_firebase_token(token=Depends(security)):
    try:
        decoded_token = auth.verify_id_token(token.credentials)
        return decoded_token
    except ValueError as e:
        # Firebase Admin SDK not initialized
        logger.error(f"Firebase Admin SDK error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase Admin SDK not initialized",
        )
    except Exception as e:
        # Token verification failed
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token",
        )


# Shared 404 so non-admins cannot distinguish "not allowed" from "does not exist".
_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def resolve_admin(user_id: str, db: Session) -> UserModel:
    """
    Resolve an admin user by internal UUID or firebase_uid (mirrors
    RoleRepository.check_role resolution), considering only active users.

    Raises a uniform 404 if the id does not map to an active admin, so the
    existence of admin-only endpoints is never revealed to non-admins.
    """
    user = (
        db.query(UserModel)
        .filter(
            (UserModel.id == user_id) | (UserModel.firebase_uid == user_id),
            UserModel.is_active.is_(True),
            UserModel.deleted_at.is_(None),
        )
        .first()
    )
    if not user or (user.role or "").strip().lower() != "admin":
        raise _NOT_FOUND
    return user


def require_admin(
    user_id: str = Query(..., description="Current admin user id"),
    db: Session = Depends(database.get_db),
) -> UserModel:
    """
    Authorize the caller as an admin via the `?user_id=` query param, matching
    the existing admin endpoints (e.g. /admin/users). Returns the admin's
    UserModel on success, or a uniform 404 for any non-admin caller.
    """
    return resolve_admin(user_id, db)
