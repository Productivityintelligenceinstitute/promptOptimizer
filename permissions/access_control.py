from datetime import date

from repositories.check_role import RoleRepository
from repositories.check_package import CheckPackageRepository
from repositories.check_access import AccessRepository
from repositories.daily_usage import UsageRepository
from schemas.subscription_model import SubscriptionsModel
from schemas.packages_model import PackagesModel

from core.exceptions.access import AccessDeniedException


def validate_access(db, user_id, permission):
    role = RoleRepository.check_role(db, user_id)

    if role == "admin":
        return

    # Ensure user has an active, time-valid package (trial or paid)
    CheckPackageRepository.check_user_package(db, user_id)

    access = AccessRepository.check_access(db, user_id, permission)
    if not access or not access.is_enabled:
        raise AccessDeniedException("Access denied for optimization feature")

    # Enforce per-day limits (configured via package-permission query_limit)
    UsageRepository.check_daily_usage(
        db, user_id, access.permission_id, access.query_limit
    )

    # For Master-level optimization on a trial, also enforce a 5-total cap
    if permission == "MASTER_OPT":
        trial_subscription = (
            db.query(SubscriptionsModel, PackagesModel)
            .join(PackagesModel, SubscriptionsModel.package_id == PackagesModel.id)
            .filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.status == "active",
                PackagesModel.package_name == "trial",
            )
            .first()
        )

        if trial_subscription:
            sub, _pkg = trial_subscription
            if sub.start_date and sub.end_date:
                trial_start = sub.start_date
                trial_end = sub.end_date

                # Convert to date boundaries for UsageLogModel.date comparisons
                UsageRepository.check_trial_total_usage(
                    db=db,
                    user_id=user_id,
                    permission_id=access.permission_id,
                    trial_start_date=trial_start.date(),
                    trial_end_date=trial_end.date(),
                    total_limit=5,
                )

    # If all checks passed, record today's usage
    UsageRepository.increment_daily_usage(db, user_id, access.permission_id)
