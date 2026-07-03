import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import database
from dependencies.auth import require_admin, resolve_admin
from schemas.user_model import UserModel
from models.admin_trial_model import ExtendTrialRequest
from services.extend_trial_service import extend_trial_service
from repositories.change_log_repository import ChangeLogRepository

extend_trial_router = APIRouter(prefix="/admin")

# Admin identity comes from the `?user_id=` query param (matching the other admin
# endpoints). Non-admins get a uniform 404, so these endpoints are invisible to
# anyone who is not an admin.


@extend_trial_router.put("/extend-trial")
def extend_trial(
    payload: ExtendTrialRequest,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(database.get_db),
):
    return extend_trial_service(payload, admin, db)


@extend_trial_router.get("/users/{user_id}/change-logs")
def get_user_change_logs(
    user_id: str,
    admin_user_id: str = Query(..., description="Current admin user id"),
    db: Session = Depends(database.get_db),
):
    # `user_id` (path) is the target user; the admin is identified separately to
    # avoid clashing with the path parameter name.
    resolve_admin(admin_user_id, db)

    try:
        target_id = uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Not found")

    logs = ChangeLogRepository.list_for_user(db, target_id)

    return {
        "user_id": user_id,
        "items": [
            {
                "id": str(log.id),
                "action": log.action,
                "performed_by": str(log.performed_by) if log.performed_by else None,
                "old_status": log.old_status,
                "new_status": log.new_status,
                "old_end_date": log.old_end_date.isoformat() if log.old_end_date else None,
                "new_end_date": log.new_end_date.isoformat() if log.new_end_date else None,
                "note": log.note,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }
