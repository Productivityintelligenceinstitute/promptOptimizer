from datetime import date
from fastapi import HTTPException, status
from schemas.user_model import UserModel
from schemas.permission_model import PermissionModel
from schemas.packages_permission_model import PackagesPermissionModel
from schemas.subscription_model import SubscriptionsModel
from schemas.usage_log_model import UsageLogModel

def check_role(db, user_id):
    role = (
        db.query(UserModel)
        .filter(UserModel.user_id == user_id)
        .first()
    )
    
    print(role.role)
    
    
    return role.role

def check_access(db, user_id, permission_name):
    access = (
        db.query(PackagesPermissionModel)
        .join(
            PermissionModel,
            PermissionModel.permission_id == PackagesPermissionModel.permission_id
        )
        .join(
            SubscriptionsModel, 
            SubscriptionsModel.package_id == PackagesPermissionModel.package_id
        ).filter(
            SubscriptionsModel.user_id == user_id,
            SubscriptionsModel.status == "active",
            PermissionModel.permission_name == permission_name
        )
        .first()
    )
    
    return access


def check_daily_usage(db, user_id, permission_id, daily_limit: int):
    today = date.today()

    usage = (
        db.query(UsageLogModel)
        .filter(
            UsageLogModel.user_id == user_id,
            UsageLogModel.permission_id == permission_id,
            UsageLogModel.date == today
        )
        .first()
    )

    used = usage.count if usage else 0

    if daily_limit is not None and used >= daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily usage limit exceeded."
        )

def increment_daily_usage(db, user_id, permission_id):
    today = date.today()

    usage = (
        db.query(UsageLogModel)
        .filter(
            UsageLogModel.user_id == user_id,
            UsageLogModel.permission_id == permission_id,
            UsageLogModel.date == today
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
                count=1
            )
        )
    db.commit()