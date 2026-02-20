from datetime import datetime, timedelta, date
import logging
import os
import asyncio

from sqlalchemy.orm import Session

from database import database
from schemas.user_model import UserModel
from schemas.subscription_model import SubscriptionsModel
from repositories.daily_usage import UsageRepository


logger = logging.getLogger(__name__)


def _cleanup_once(db: Session, inactive_days_threshold: int = 90) -> int:
    """
    Soft delete users whose subscriptions expired more than `inactive_days_threshold`
    days ago and who have not had any usage since then.

    Returns:
        Number of users soft-deleted.
    """
    today = date.today()
    threshold_date = today - timedelta(days=inactive_days_threshold)

    # Only consider currently active, non-deleted users
    candidates = (
        db.query(UserModel)
        .filter(
            UserModel.is_active.is_(True),
            UserModel.deleted_at.is_(None),
        )
        .all()
    )

    deleted_count = 0

    for user in candidates:
        # Never soft-delete admin users
        if user.role and str(user.role).lower() == "admin":
            continue

        # Find the most recent subscription for this user (any status)
        last_sub = (
            db.query(SubscriptionsModel)
            .filter(SubscriptionsModel.user_id == user.id)
            .order_by(SubscriptionsModel.end_date.desc().nullslast())
            .first()
        )

        if not last_sub or not last_sub.end_date:
            # No subscription with an end date -> skip for now
            continue

        expiry_date = last_sub.end_date.date()
        if expiry_date > threshold_date:
            # Not expired long enough yet
            continue

        # Check last activity (optimization usage) for this user
        last_activity_date = UsageRepository.get_last_activity_date(db, user.id)

        if last_activity_date is not None and last_activity_date > threshold_date:
            # User has been active within the threshold window -> skip
            continue

        # At this point: user expired > threshold days ago AND has no activity since
        # -> soft delete
        user.is_active = False
        user.deleted_at = datetime.utcnow()
        deleted_count += 1
        logger.info(
            "Soft-deleting inactive user: id=%s email=%s (subscription ended %s, last_activity=%s)",
            user.id,
            user.email,
            expiry_date,
            last_activity_date,
        )

    if deleted_count:
        db.commit()
        logger.info("User cleanup: soft-deleted %s inactive expired user(s)", deleted_count)
    else:
        logger.info("User cleanup: no inactive expired users to delete (threshold=%s days)", inactive_days_threshold)

    return deleted_count


async def user_cleanup_loop() -> None:
    """
    Periodic cleanup loop to soft delete long-expired, inactive users.

    The interval (in seconds) is controlled by USER_CLEANUP_INTERVAL_SECONDS env var,
    defaulting to 86400 (1 day).
    """
    interval_seconds = int(os.getenv("USER_CLEANUP_INTERVAL_SECONDS", "86400"))

    logger.info(
        "User cleanup loop started; interval=%s seconds, threshold=90 days",
        interval_seconds,
    )

    # Simple infinite loop; relies on app process lifecycle
    while True:
        db = None
        try:
            db = database.SessionLocal()
            deleted = _cleanup_once(db)
            logger.info(
                "User cleanup run finished: soft-deleted=%s, next run in %ss",
                deleted,
                interval_seconds,
            )
        except Exception as e:
            logger.error("User cleanup error: %s", e, exc_info=True)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        await asyncio.sleep(interval_seconds)

