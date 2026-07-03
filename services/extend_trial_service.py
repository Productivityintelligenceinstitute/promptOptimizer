from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from schemas.user_model import UserModel
from schemas.packages_model import PackagesModel
from schemas.subscription_model import SubscriptionsModel
from repositories.change_log_repository import ChangeLogRepository

TRIAL_PACKAGE_NAME = "trial"


def _as_aware(dt):
    """Treat naive datetimes as UTC so comparisons with tz-aware `now` are safe."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def extend_trial_service(payload, admin: UserModel, db: Session):
    """
    Extend a trial user's trial by `payload.days` days.

    Guards:
    - Target user must exist and be active.
    - Target must have a trial subscription (else 404 to avoid revealing details).
    - Target must not have an active non-trial (paid) subscription.

    Side effects:
    - Extends the trial end_date from max(now, current end_date).
    - Reactivates the trial (status -> "active") if it had been expired.
    - Records the change in subscription_change_logs.
    """
    now = datetime.now(timezone.utc)

    user = (
        db.query(UserModel)
        .filter(
            UserModel.email == payload.user_email,
            UserModel.is_active.is_(True),
            UserModel.deleted_at.is_(None),
        )
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Trial user not found")

    # Reject if the user has an active paid (non-trial) subscription -> not a trial user.
    active_paid = (
        db.query(SubscriptionsModel)
        .join(PackagesModel, SubscriptionsModel.package_id == PackagesModel.id)
        .filter(
            SubscriptionsModel.user_id == user.id,
            SubscriptionsModel.status == "active",
            PackagesModel.package_name != TRIAL_PACKAGE_NAME,
            PackagesModel.package_name != "free",
        )
        .first()
    )
    if active_paid:
        raise HTTPException(
            status_code=400,
            detail="User is on a paid plan, not a trial. Trials can only be extended for trial users.",
        )

    # Find the user's trial subscription (any status).
    trial_sub = (
        db.query(SubscriptionsModel)
        .join(PackagesModel, SubscriptionsModel.package_id == PackagesModel.id)
        .filter(
            SubscriptionsModel.user_id == user.id,
            PackagesModel.package_name == TRIAL_PACKAGE_NAME,
        )
        .order_by(SubscriptionsModel.end_date.desc().nullslast())
        .first()
    )
    if not trial_sub:
        raise HTTPException(status_code=400, detail="User is not a trial user")

    old_status = trial_sub.status
    old_end_date = trial_sub.end_date

    base = _as_aware(old_end_date)
    if base is None or base < now:
        base = now
    new_end_date = base + timedelta(days=payload.days)

    trial_sub.end_date = new_end_date
    trial_sub.status = "active"
    trial_sub.updated_at = now

    ChangeLogRepository.add_log(
        db,
        user_id=user.id,
        action="trial_extended",
        performed_by=admin.id,
        old_status=old_status,
        new_status="active",
        old_end_date=old_end_date,
        new_end_date=new_end_date,
        note=f"Trial extended by {payload.days} day(s) by admin {admin.email}",
    )

    db.commit()
    db.refresh(trial_sub)

    return {
        "status": "success",
        "user_email": user.email,
        "days_added": payload.days,
        "previous_end_date": old_end_date.isoformat() if old_end_date else None,
        "new_end_date": new_end_date.isoformat(),
        "subscription_status": trial_sub.status,
    }
