from schemas.permission_model import PermissionModel

class PermissionRepository:
    @staticmethod
    def exists(permission_name: str, db) -> bool:
        return (
            db.query(PermissionModel)
            .filter(PermissionModel.permission_name == permission_name)
            .first()
            is not None
        )
    
    @staticmethod
    def create(permission_name: str, db):
        db.add(
            PermissionModel(
                permission_name=permission_name
            )
        )
    
    @staticmethod
    def get_all(db):
        return db.query(PermissionModel).all()

    @staticmethod
    def delete(permission_name: str, db) -> bool:
        permission = (
            db.query(PermissionModel)
            .filter(PermissionModel.permission_name == permission_name)
            .first()
        )
        
        if not permission:
            return False
        
        db.delete(permission)
        return True
