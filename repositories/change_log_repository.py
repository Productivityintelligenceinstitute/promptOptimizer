from schemas.subscription_change_log_model import SubscriptionChangeLogModel


class ChangeLogRepository:
    @staticmethod
    def add_log(
        db,
        user_id,
        action,
        performed_by=None,
        old_status=None,
        new_status=None,
        old_end_date=None,
        new_end_date=None,
        note=None,
        commit=False,
    ):
        """
        Record a subscription change for a user.

        Set commit=True to flush + commit immediately (e.g. from an admin action).
        Leave commit=False to batch several logs inside a caller-managed transaction
        (e.g. the daily expiry cron), then commit once at the end.
        """
        log = SubscriptionChangeLogModel(
            user_id=user_id,
            performed_by=performed_by,
            action=action,
            old_status=old_status,
            new_status=new_status,
            old_end_date=old_end_date,
            new_end_date=new_end_date,
            note=note,
        )
        db.add(log)
        if commit:
            db.commit()
            db.refresh(log)
        return log

    @staticmethod
    def list_for_user(db, user_id):
        """Return all change-log entries for a user, most recent first."""
        return (
            db.query(SubscriptionChangeLogModel)
            .filter(SubscriptionChangeLogModel.user_id == user_id)
            .order_by(SubscriptionChangeLogModel.created_at.desc())
            .all()
        )
