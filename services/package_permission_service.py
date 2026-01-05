from sqlalchemy.orm import Session

from repositories.package_permission_repository import PackagePermissionRepository
from core.exceptions.conflict import ConflictException
from core.exceptions.not_found import NotFoundException


def assign_permission(payload, db: Session):
    with db.begin():
        if PackagePermissionRepository.exists(payload.package_name, payload.permission_name, db):
            raise ConflictException("Permission already assigned to package")
        
        PackagePermissionRepository.create(payload.package_name, payload.permission_name, payload.query_limit, payload.is_enabled, db)
        
        return {
            "status": "success",
            "message": "Permission assigned to package"
        }


def get_all_package_permissions(db: Session):
    return {
        "package_permissions": PackagePermissionRepository.get_all(db)
    }


def delete_package_permission(package_id: int, permission_id: int, db: Session):
    with db.begin():
        deleted = PackagePermissionRepository.delete(package_id, permission_id, db)
        
        if not deleted:
            raise NotFoundException("Package-Permission mapping not found")
        
        return {
            "status": "success",
            "message": "Package-Permission entry deleted"
        }
