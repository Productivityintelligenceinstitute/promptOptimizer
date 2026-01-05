from fastapi import HTTPException
from sqlalchemy.orm import Session

from repositories.permission_repository import PermissionRepository
from core.exceptions.conflict import ConflictException
from core.exceptions.not_found import NotFoundException


def create_permission(payload, db: Session):
    try:
        with db.begin():
            if PermissionRepository.exists(payload.permission_name, db):
                raise ConflictException("Permission already exists")
            
            PermissionRepository.create(payload.permission_name, db)
            
            return {
                "status": "success",
                "message": "Permission created successfully"
            }
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)

def get_all_permissions(db: Session):
    return {
        "permissions": PermissionRepository.get_all(db)
    }


def delete_permission(permission_id: int, db: Session):
    try:
        with db.begin():
            deleted = PermissionRepository.delete(permission_id, db)
            if not deleted:
                raise NotFoundException("Permission not found")
                
            return {
                "status": "success",
                "message": "Permission deleted successfully"
            }
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)