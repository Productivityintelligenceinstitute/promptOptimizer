from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import database
from models.subscription_model import UpgradeSubscriptionRequest, CancelSubscriptionRequest
from services.subscription_service import upgrade_subscription_service, cancel_subscription_service

subscription_router = APIRouter()

@subscription_router.post("/upgrade-subscription")
async def upgrade_subscription(payload: UpgradeSubscriptionRequest, db: Session = Depends(database.get_db)):
    return upgrade_subscription_service(payload, db)

@subscription_router.post("/cancel-subscription")
async def cancel_subscription(payload: CancelSubscriptionRequest, db: Session = Depends(database.get_db)):
    return cancel_subscription_service(payload, db)