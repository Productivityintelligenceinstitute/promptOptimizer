from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import database
from models.subscription_model import UpgradeSubscriptionRequest, CancelSubscriptionRequest
from services.subscription_service import upgrade_subscription_service, cancel_subscription_service

subscription_router = APIRouter()

@subscription_router.post("/upgrade-subscription")
async def upgrade_subscription(subscription: UpgradeSubscriptionRequest, db: Session = Depends(database.get_db)):
    return upgrade_subscription_service(subscription.user_id, subscription.package_id, db)

@subscription_router.post("/cancel-subscription")
async def cancel_subscription(cancel_sub: CancelSubscriptionRequest, db: Session = Depends(database.get_db)):
    return cancel_subscription_service(cancel_sub.user_id, db)