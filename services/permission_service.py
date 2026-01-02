from sqlalchemy.orm import Session

from repositories.permission_repository import PermissionRepository
from core.exceptions.conflict import ConflictException
from core.exceptions.not_found import NotFoundException


def create_permission(payload, db: Session):
    with db.begin():
        if PermissionRepository.exists(payload.permission_name, db):
            raise ConflictException("Permission already exists")
        
        PermissionRepository.create(payload.permission_name, db)
        
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
            raise NotFoundException("Permission not found")
            
        return {
            "status": "success",
            "message": "Permission deleted successfully"
        }
