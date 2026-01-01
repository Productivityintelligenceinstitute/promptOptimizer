from sqlalchemy.orm import Session

from repositories.permission_repository import PermissionRepository


def create_permission(permission_name: str, db: Session):
    with db.begin():
        if PermissionRepository.exists(permission_name, db):
            return {
                "status": "failure",
                "message": "Permission already exists"
            }
        
        PermissionRepository.create(permission_name, db)
        
        return {
            "status": "success",
            "message": "Permission created successfully"
        }


def get_all_permissions(db: Session):
    return {
        "permissions": PermissionRepository.get_all(db)
    }


def delete_permission(permission_name: str, db: Session):
    with db.begin():
        deleted = PermissionRepository.delete(permission_name, db)
        if not deleted:
            return {
                "status": "failure",
                "message": "Permission not found"
            }
            
        return {
            "status": "success",
            "message": "Permission deleted successfully"
        }
