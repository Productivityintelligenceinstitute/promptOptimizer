from schemas.permission_model import PermissionModel
from schemas.packages_permission_model import PackagesPermissionModel
from schemas.subscription_model import SubscriptionsModel

class AccessRepository:
    @staticmethod
    def check_access(db, user_id, permission_name):
        access = (
            db.query(PackagesPermissionModel)
            .join(
                PermissionModel,
                PermissionModel.id == PackagesPermissionModel.permission_id
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