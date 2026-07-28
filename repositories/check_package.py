from datetime import datetime, timezone

from schemas.packages_model import PackagesModel
from schemas.subscription_model import SubscriptionsModel
from fastapi import HTTPException


class CheckPackageRepository:
    @staticmethod
    def get_active_package_subscription(db, user_id):
        """
        Return (package, subscription) for the user's first active subscription, or None.
        """
        return (
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

    @staticmethod
    def validate_package_subscription(package, subscription) -> None:
        """
        Ensure a package/subscription pair is currently valid.

        Raises HTTPException(403) when invalid.
        """
        now = datetime.now(timezone.utc)

        if package.package_name == "trial":
            if not subscription.end_date or subscription.end_date < now:
                raise HTTPException(
                    status_code=403,
                    detail="Your trial has expired. Please upgrade your plan to continue.",
                )
            return

        if package.package_name != "free":
            # Paid plans (pro/essential): require a started subscription.
            # end_date may be null for admin/manual grants (open-ended).
            # Stripe-backed subs always set end_date to the current period end.
            if not subscription.start_date or subscription.start_date > now:
                raise HTTPException(
                    status_code=403,
                    detail="No active subscription",
                )
            if subscription.end_date is not None and subscription.end_date < now:
                raise HTTPException(
                    status_code=403,
                    detail="No active subscription",
                )
            return

        # Legacy free plan: keep existing behavior (no time-based restriction)
        return

    @staticmethod
    def check_user_package(db, user_id):
        """
        Ensure the user has an active, time-valid subscription.

        Rules:
        - If no active subscription exists → 403
        - If package is "trial" → require end_date >= now (14-day window)
        - If package is paid (not "free" or "trial") → require start_date <= now,
          and if end_date is set then end_date >= now (null end_date = open-ended)
        - If package is "free" → legacy behavior: no time check, allowed
        """
        result = CheckPackageRepository.get_active_package_subscription(db, user_id)

        if not result:
            raise HTTPException(
                status_code=403,
                detail="No active subscription or trial has expired. Please upgrade your plan to continue.",
            )

        package, subscription = result
        CheckPackageRepository.validate_package_subscription(package, subscription)