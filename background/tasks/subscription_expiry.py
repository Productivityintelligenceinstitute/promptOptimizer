from datetime import datetime, timezone
import logging
import os
import asyncio

from sqlalchemy.orm import Session

from database import database
from schemas.subscription_model import SubscriptionsModel
from repositories.change_log_repository import ChangeLogRepository


logger = logging.getLogger(__name__)

# Statuses considered "live" that should be flipped to "expired" once past end_date.
ACTIVE_STATUSES = ("active", "trialing")
EXPIRED_STATUS = "expired"


def _expire_once(db: Session) -> int:
    """
    Flip every past-due subscription (end_date < now) that is still in a live
    status to "expired", logging each change to subscription_change_logs.

    Returns the number of subscriptions expired.
    """
    now = datetime.now(timezone.utc)

    due_subscriptions = (
        db.query(SubscriptionsModel)
        .filter(
            SubscriptionsModel.status.in_(ACTIVE_STATUSES),
            SubscriptionsModel.end_date.isnot(None),
            SubscriptionsModel.end_date < now,
        )
        .all()
    )

    expired_count = 0
    for sub in due_subscriptions:
        old_status = sub.status
        sub.status = EXPIRED_STATUS
        sub.updated_at = now

        ChangeLogRepository.add_log(
            db,
            user_id=sub.user_id,
            action="subscription_expired",
            performed_by=None,  # system / cron
            old_status=old_status,
            new_status=EXPIRED_STATUS,
            old_end_date=sub.end_date,
            new_end_date=sub.end_date,
            note="Auto-expired by daily cron: end_date passed",
        )
        expired_count += 1

    if expired_count:
        db.commit()
        logger.info("Subscription expiry: marked %s subscription(s) as expired", expired_count)
    else:
        logger.info("Subscription expiry: no past-due subscriptions to expire")

    return expired_count


async def subscription_expiry_loop() -> None:
    """
    Periodic loop that expires past-due subscriptions once per day.

    Interval (seconds) is controlled by SUBSCRIPTION_EXPIRY_INTERVAL_SECONDS,
    defaulting to 86400 (1 day).
    """
    interval_seconds = int(os.getenv("SUBSCRIPTION_EXPIRY_INTERVAL_SECONDS", "86400"))

    logger.info(
        "Subscription expiry loop started; interval=%s seconds", interval_seconds
    )

    while True:
        db = None
        try:
            db = database.SessionLocal()
            expired = _expire_once(db)
            logger.info(
                "Subscription expiry run finished: expired=%s, next run in %ss",
                expired,
                interval_seconds,
            )
        except Exception as e:
            logger.error("Subscription expiry error: %s", e, exc_info=True)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        await asyncio.sleep(interval_seconds)
