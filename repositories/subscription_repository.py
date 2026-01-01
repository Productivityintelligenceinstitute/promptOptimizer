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