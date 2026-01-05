from fastapi import HTTPException
from sqlalchemy.orm import Session
from repositories.subscription_repository import SubscriptionRepository
from datetime import date
from dateutil import relativedelta
from core.exceptions.not_found import NotFoundException
from core.exceptions.conflict import ConflictException

def upgrade_subscription_service(payload, db: Session):
    try:
        with db.begin(): 
            active_subscription = SubscriptionRepository.get_active(payload.user_id, db)
            if not active_subscription:
                raise NotFoundException("User subscription not found")
            
            if active_subscription.package_id == payload.package_id:
                raise ConflictException("User already subscribed to this package")
            
            SubscriptionRepository.cancel(active_subscription, db)
            
            existing = SubscriptionRepository.get_by_package(payload.user_id, payload.package_id, db)
            if existing:
                SubscriptionRepository.activate(db, existing)
                return {"status": "Subscription reactivated"}
            
            SubscriptionRepository.create(
                db=db,
                user_id=payload.user_id,
                package_id=payload.package_id,
                end_date=date.today() + relativedelta.relativedelta(months=1)
            )
            
            return {"status": "Subscription upgraded"}
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)

def cancel_subscription_service(payload, db: Session):
    try:
        with db.begin():
            active_subscription = SubscriptionRepository.get_active(payload.user_id, db)
            if not active_subscription:
                return {"status": "No active subscription to cancel"}
            
            SubscriptionRepository.cancel(active_subscription, db)
            
            free_plan = SubscriptionRepository.get_free_plan(payload.user_id, db)
            if free_plan:
                SubscriptionRepository.activate(free_plan, db)
            
            return {"status": "Subscription cancelled"}
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)