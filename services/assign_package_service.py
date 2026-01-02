from repositories.user_repository import UserRepository
from repositories.package_repository import PackageRepository
from repositories.subscription_repository import SubscriptionRepository

from core.exceptions.not_found import NotFoundException

from datetime import date
from dateutil import relativedelta

def assign_package_service(payload, db):
    user = UserRepository.get_user_by_email(payload.email, db)
    if not user:
        raise NotFoundException("User not found")
    
    package = PackageRepository.get_by_name(payload.package_name, db)
    if not package:
        raise NotFoundException("Package not found")
    
    SubscriptionRepository.create(
        db=db,
        user_id=user.user_id,
        package_id=package.package_id,
        end_date=date.today() + relativedelta.relativedelta(months=1)
    )
    
    return {"status": f"{package.package_name} assigned to {user.email}"}