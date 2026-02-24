from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import database
from schemas.user_model import UserModel
from repositories.check_role import RoleRepository
from repositories.subscription_repository import SubscriptionRepository
from repositories.daily_usage import UsageRepository

users_admin_router = APIRouter()


@users_admin_router.get("/admin/users")
async def list_users(
    user_id: str = Query(..., description="Current admin user id"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    q: str | None = Query(None, description="Search by email or full name"),
    db: Session = Depends(database.get_db),
):
    # Ensure requester is admin
    role = RoleRepository.check_role(db, user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can list users")

    # Only list active (non-deleted) users by default
    query = db.query(UserModel).filter(
        UserModel.is_active.is_(True),
        UserModel.deleted_at.is_(None),
    )

    if q:
        like = f"%{q}%"
        query = query.filter(
            (UserModel.email.ilike(like)) | (UserModel.full_name.ilike(like))
        )

    total = query.count()
    users = (
        query.order_by(UserModel.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    now = datetime.now(timezone.utc)

    def _subscription_status_display(sub, pkg, has_active, is_expired_flag):
        """Map subscription and package to client display: Trialing / Active / Past Due / Suspended / Canceled / Expired / No subscription."""
        if has_active and sub and pkg:
            if pkg.package_name == "trial" and sub.end_date and sub.end_date >= now:
                return "Trialing"
            return "Active"
        if not sub:
            return "No subscription"
        raw = (sub.status or "").strip().lower()
        if raw in ("cancelled", "canceled"):
            return "Canceled"
        if raw == "past_due":
            return "Past Due"
        if raw == "suspended" or raw == "unpaid":
            return "Suspended"
        if raw == "trialing":
            return "Trialing" if sub.end_date and sub.end_date >= now else "Expired"
        if is_expired_flag:
            return "Expired"
        return raw.title() if raw else "Expired"

    items = []
    for u in users:
        sub_with_pkg = SubscriptionRepository.get_active_with_package(u.id, db)
        package_name = None
        trial_ends_at = None
        is_expired = False
        sub_for_status = None
        pkg_for_status = None

        if sub_with_pkg:
            sub, pkg = sub_with_pkg
            sub_for_status = sub
            pkg_for_status = pkg
            package_name = pkg.package_name
            if sub.end_date:
                try:
                    trial_ends_at = sub.end_date.isoformat()
                    if sub.end_date < now:
                        is_expired = True
                except (AttributeError, ValueError):
                    trial_ends_at = None
        else:
            is_expired = True
            latest = SubscriptionRepository.get_latest_subscription_with_package(u.id, db)
            if latest:
                sub_for_status, pkg_for_status = latest
                if not package_name and pkg_for_status:
                    package_name = pkg_for_status.package_name

        subscription_status = _subscription_status_display(
            sub_for_status, pkg_for_status, sub_with_pkg is not None, is_expired
        )

        # Expiry: current package end date, or last package end date if no active subscription
        expiry_date = None
        sub_for_expiry = sub_with_pkg[0] if sub_with_pkg else (sub_for_status if sub_for_status else None)
        if sub_for_expiry and sub_for_expiry.end_date:
            try:
                expiry_date = sub_for_expiry.end_date.isoformat()
            except (AttributeError, ValueError):
                pass

        last_activity_date = UsageRepository.get_last_activity_date(db, u.id)
        last_activity_at = (
            last_activity_date.isoformat() if last_activity_date is not None else None
        )

        items.append(
            {
                "user_id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "firebase_uid": u.firebase_uid,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "package_name": package_name,
                "trial_ends_at": trial_ends_at,
                "expiry_date": expiry_date,
                "last_activity_at": last_activity_at,
                "is_expired": is_expired,
                "subscription_status": subscription_status,
            }
        )

    pages = (total + size - 1) // size if size else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


