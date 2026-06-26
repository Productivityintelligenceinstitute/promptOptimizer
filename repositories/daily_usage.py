from datetime import date

from sqlalchemy import func

from schemas.usage_log_model import UsageLogModel
from core.exceptions.rate_limit import RateLimitExceededException


class UsageRepository:
    @staticmethod
    def check_daily_usage(db, user_id, permission_id, daily_limit: int):
        today = date.today()

        usage = (
            db.query(UsageLogModel)
            .filter(
                UsageLogModel.user_id == user_id,
                UsageLogModel.permission_id == permission_id,
                UsageLogModel.date == today,
            )
            .first()
        )

        used = usage.count if usage else 0

        if daily_limit is not None and used >= daily_limit:
            raise RateLimitExceededException("Daily usage limit exceeded.")

    @staticmethod
    def check_trial_total_usage(
        db,
        user_id,
        permission_id,
        trial_start_date,
        trial_end_date,
        total_limit: int,
    ):
        """
        Enforce a total cap on usage for a given permission within the trial window.

        This is used for MASTER_OPT in the 14-day trial:
        - Sum all UsageLogModel.count values between trial_start_date and trial_end_date (inclusive)
        - If the total is >= total_limit (e.g., 5), raise a limit exception.
        """
        if total_limit is None or not trial_start_date or not trial_end_date:
            return

        total_used = (
            db.query(func.coalesce(func.sum(UsageLogModel.count), 0))
            .filter(
                UsageLogModel.user_id == user_id,
                UsageLogModel.permission_id == permission_id,
                UsageLogModel.date >= trial_start_date,
                UsageLogModel.date <= trial_end_date,
            )
            .scalar()
        )

        if total_used is not None and total_used >= total_limit:
            raise RateLimitExceededException(
                "Trial usage limit exceeded for this optimization level."
            )

    @staticmethod
    def get_trial_total_usage(
        db,
        user_id,
        permission_id,
        trial_start_date,
        trial_end_date,
    ) -> int:
        if not trial_start_date or not trial_end_date:
            return 0
        total_used = (
            db.query(func.coalesce(func.sum(UsageLogModel.count), 0))
            .filter(
                UsageLogModel.user_id == user_id,
                UsageLogModel.permission_id == permission_id,
                UsageLogModel.date >= trial_start_date,
                UsageLogModel.date <= trial_end_date,
            )
            .scalar()
        )
        return int(total_used or 0)

    @staticmethod
    def increment_daily_usage(db, user_id, permission_id):
        today = date.today()

        usage = (
            db.query(UsageLogModel)
            .filter(
                UsageLogModel.user_id == user_id,
                UsageLogModel.permission_id == permission_id,
                UsageLogModel.date == today,
            )
            .with_for_update()
            .first()
        )

        if usage:
            usage.count += 1
        else:
            db.add(
                UsageLogModel(
                    user_id=user_id,
                    permission_id=permission_id,
                    date=today,
                    count=1,
                )
            )
        db.commit()

    @staticmethod
    def get_last_activity_date(db, user_id):
        """
        Return the most recent usage date for the given user, or None if no usage.
        """
        return (
            db.query(func.max(UsageLogModel.date))
            .filter(UsageLogModel.user_id == user_id)
            .scalar()
        )