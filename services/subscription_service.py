from sqlalchemy.orm import Session
from repositories.subscription_repository import SubscriptionRepository
from datetime import date
from dateutil import relativedelta

def upgrade_subscription_service(user_id, package_id, db: Session):
    with db.begin(): 
        active_subscription = SubscriptionRepository.get_active(user_id, db)
        if not active_subscription:
            return {"status": "User subscription not found"}
        
        if active_subscription.package_id == package_id:
            return {"status": "User already subscribed to this package"}
        
        SubscriptionRepository.cancel(active_subscription, db)
        
        existing = SubscriptionRepository.get_by_package(user_id, package_id, db)
        if existing:
            SubscriptionRepository.activate(db, existing)
            return {"status": "Subscription reactivated"}
        
        SubscriptionRepository.create(
            db=db,
            user_id=user_id,
            package_id=package_id,
            end_date=date.today() + relativedelta.relativedelta(months=1)
        )
        
        return {"status": "Subscription upgraded"}

def cancel_subscription_service(user_id: str, db: Session):
    with db.begin():
        active_subscription = SubscriptionRepository.get_active(user_id, db)
        if not active_subscription:
            return {"status": "No active subscription to cancel"}
        
        SubscriptionRepository.cancel(active_subscription, db)
        
        free_plan = SubscriptionRepository.get_free_plan(user_id, db)
        if free_plan:
            SubscriptionRepository.activate(free_plan, db)
        
        return {"status": "Subscription cancelled"}