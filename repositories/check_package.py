from datetime import datetime, timezone

from schemas.packages_model import PackagesModel
from schemas.subscription_model import SubscriptionsModel
from fastapi import HTTPException


class CheckPackageRepository:
    @staticmethod
    def check_user_package(db, user_id):
        """
        Ensure the user has an active, time-valid subscription.

        Rules:
        - If no active subscription exists → 403
        - If package is "trial" → require end_date >= now (14-day window)
        - If package is paid (not "free" or "trial") → require start_date <= now <= end_date
        - If package is "free" → legacy behavior: no time check, allowed
        """
        result = (
            db.query(PackagesModel, SubscriptionsModel)
            .join(
                SubscriptionsModel,
                SubscriptionsModel.package_id == PackagesModel.id,
            )
            .filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.status == "active",
            )
            .first()
        )

        if not result:
            # No active subscription at all (no trial, no paid, no free)
            raise HTTPException(
                status_code=403,
                detail="No active subscription or trial has expired. Please upgrade your plan to continue.",
            )

        package, subscription = result
        now = datetime.now(timezone.utc)

        # New behavior: 14-day trial must be within its validity window
        if package.package_name == "trial":
            if not subscription.end_date or subscription.end_date < now:
                raise HTTPException(
                    status_code=403,
                    detail="Your trial has expired. Please upgrade your plan to continue.",
                )
            return

        # Paid subscriptions (e.g., essential, pro) must be currently valid
        if package.package_name != "free":
            if (
                not subscription.start_date
                or not subscription.end_date
                or subscription.start_date > now
                or subscription.end_date < now
            ):
                raise HTTPException(
                    status_code=403,
                    detail="No active subscription",
                )
            return

        # Legacy free plan: keep existing behavior (no time-based restriction)
        # Users on the historical free tier are allowed to proceed.
        return