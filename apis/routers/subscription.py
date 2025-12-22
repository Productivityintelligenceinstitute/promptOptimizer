from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import database
from validator.validator import Subscription
from models.subscription_model import SubscriptionsModel
from uuid import uuid4
from datetime import date
from dateutil import relativedelta

subscription_router = APIRouter()

@subscription_router.post("/upgrade-subscription")
async def upgrade_subscription(subscription: Subscription, db: Session = Depends(database.get_db)):
    
    user = db.query(SubscriptionsModel).filter(SubscriptionsModel.user_id == subscription.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.package_id != subscription.package_id:
        user.status = "cancelled"
        user.updated_at = date.today()
        db.commit()
    
    existing_subscription = db.query(SubscriptionsModel).filter(
        SubscriptionsModel.user_id == subscription.user_id,
        SubscriptionsModel.package_id == subscription.package_id
    ).first()
    
    if existing_subscription:
        if existing_subscription.status == "active":
            return {"status": "User is already subscribed to this package"}
        else:
            existing_subscription.status = "active"
            existing_subscription.updated_at = date.today()
            db.commit()
            return {"status": "Subscription reactivated"}
    
    new_subscription = SubscriptionsModel(
        subscription_id=str(uuid4()),
        user_id=subscription.user_id,
        package_id=subscription.package_id,
        status="active",
        end_date=date.today() + relativedelta.relativedelta(months=1),
        auto_renew=True
    )
    db.add(new_subscription)
    db.commit()
    db.refresh(new_subscription)
    
    return {"status": "Subscription upgraded"}

@subscription_router.post("/cancel-subscription")
async def cancel_subscription(user_id: str, db: Session = Depends(database.get_db)):
    existing_subscription = db.query(SubscriptionsModel).filter(
        SubscriptionsModel.user_id == user_id,
        SubscriptionsModel.status == "active"
    ).first()
    
    if not existing_subscription or existing_subscription.status != "active":
        return {"status": "User is not subscribed to any active package"}
    
    existing_subscription.status = "cancelled"
    existing_subscription.updated_at = date.today()
    db.commit()
    
    previous_package = db.query(SubscriptionsModel).filter(
        SubscriptionsModel.user_id == user_id,
        SubscriptionsModel.package_id == 1,
        SubscriptionsModel.status == "cancelled"
    ).first()
    
    if previous_package:
        previous_package.status = "active"
        previous_package.updated_at = date.today()
        db.commit()
    
    return {"status": "Subscription cancelled"}

# @subscription_router.post("/subscribe")
# async def subscribe(subscription: Subscription, db: Session = Depends(database.get_db)):
    
#     existing_subscription = db.query(SubscriptionsModel).filter(
#         SubscriptionsModel.user_id == subscription.user_id,
#         SubscriptionsModel.package_id == subscription.package_id
#     ).first()
    
#     if existing_subscription:
#         if existing_subscription.is_active:
#             return {"status": "User is already subscribed to this package"}
#         else:
#             existing_subscription.is_active = True
#             db.commit()
#             return {"status": "Subscription reactivated"}
    
#     new_subscription = SubscriptionsModel(
#         user_id=subscription.user_id,
#         package_id=subscription.package_id,
#         is_active=True
#     )
#     db.add(new_subscription)
#     db.commit()
#     db.refresh(new_subscription)
    
#     return {"status": "User subscribed to package"}

# @subscription_router.post("/unsubscribe")
# async def unsubscribe(subscription: Subscription, db: Session = Depends(database.get_db)):
#     existing_subscription = db.query(SubscriptionsModel).filter(
#         SubscriptionsModel.user_id == subscription.user_id,
#         SubscriptionsModel.package_id == subscription.package_id
#     ).first()
    
#     if not existing_subscription or not existing_subscription.is_active:
#         return {"status": "User is not subscribed to this package"}
    
#     existing_subscription.is_active = False
#     db.commit()
    
#     return {"status": "User unsubscribed from package"}
