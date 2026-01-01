from schemas.packages_model import PackagesModel
from schemas.subscription_model import SubscriptionsModel
from fastapi import HTTPException
from sqlalchemy import text

class CheckPackageRepository:
    @staticmethod
    def check_user_package(db, user_id):
        package = (
        db.query(PackagesModel)
        .join(
            SubscriptionsModel,
            SubscriptionsModel.package_id == PackagesModel.id
        )
        .filter(
            SubscriptionsModel.user_id == user_id,
            SubscriptionsModel.status == "active"
        )
        .first()
        )
        
        if package.package_name != "free":
            subscription = (
                db.query(SubscriptionsModel)
                .filter(
                    SubscriptionsModel.user_id == user_id,
                    SubscriptionsModel.status == "active",
                    SubscriptionsModel.start_date <= text('now()'),
                    SubscriptionsModel.end_date >= text('now()')
                )
                .first()
            )
            if not subscription:
                raise HTTPException(status_code=403, detail="No active subscription")