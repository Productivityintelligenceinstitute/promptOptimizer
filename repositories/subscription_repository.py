from schemas.subscription_model import SubscriptionsModel
from schemas.packages_model import PackagesModel
from datetime import date

class SubscriptionRepository:
    @staticmethod
    def get_active(user_id, db):
        return (
            db.query(SubscriptionsModel)
            .filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.status == "active"
            )
            .first()
        )
    
    @staticmethod
    def get_by_package(user_id, package_id, db):
        return (
            db.query(SubscriptionsModel)
            .filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.package_id == package_id
            )
            .first()
        )
    
    @staticmethod
    def create(user_id, package_id, end_date, db):
        db.add(
            SubscriptionsModel(
                user_id=user_id,
                package_id=package_id,
                status="active",
                end_date=end_date,
                auto_renew=True
            )
        )
    
    @staticmethod
    def cancel(subscription, db):
        subscription.status = "cancelled"
        subscription.updated_at = date.today()
    
    @staticmethod
    def activate(subscription, db):
        subscription.status = "active"
        subscription.updated_at = date.today()
    
    @staticmethod
    def get_free_plan(user_id, db):
        free_package = db.query(PackagesModel).filter(PackagesModel.package_name == "free").first()
        
        return (
            db.query(SubscriptionsModel)
            .filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.package_id == free_package.id 
            )
            .first()
        )

    @staticmethod
    def get_active_with_package(user_id, db):
        """
        Return the first active subscription for a user along with its package.

        Returns:
            (subscription, package) tuple or None.
        """
        result = (
            db.query(SubscriptionsModel, PackagesModel)
            .join(PackagesModel, SubscriptionsModel.package_id == PackagesModel.id)
            .filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.status == "active",
            )
            .first()
        )
        return result

    @staticmethod
    def get_latest_subscription_with_package(user_id, db):
        """
        Return the most recent subscription for a user (any status) with its package.
        Used for admin display of subscription status (e.g. Canceled, Past Due).

        Returns:
            (subscription, package) tuple or None.
        """
        result = (
            db.query(SubscriptionsModel, PackagesModel)
            .join(PackagesModel, SubscriptionsModel.package_id == PackagesModel.id)
            .filter(SubscriptionsModel.user_id == user_id)
            .order_by(SubscriptionsModel.updated_at.desc())
            .first()
        )
        return result