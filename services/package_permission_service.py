from sqlalchemy.orm import Session

from repositories.package_permission_repository import PackagePermissionRepository


def assign_permission(payload, db: Session):
    with db.begin():
        if PackagePermissionRepository.exists(payload.package_name, payload.permission_name, db):
            return {
                "status": "failure",
                "message": "Permission already assigned to package"
            }
        
        PackagePermissionRepository.create(payload.package_name, payload.permission_name, payload.query_limit, payload.is_enabled, db)
        
        return {
            "status": "success",
            "message": "Permission assigned to package"
        }


def get_all_package_permissions(db: Session):
    return {
        "package_permissions": PackagePermissionRepository.get_all(db)
    }


def delete_package_permission(package_name: str, permission_name: str, db: Session):
    with db.begin():
        deleted = PackagePermissionRepository.delete(package_name, permission_name, db)
        
        if not deleted:
            return {
                "status": "failure",
                "message": "Package-Permission entry not found"
            }
        
        return {
            "status": "success",
            "message": "Package-Permission entry deleted"
        }
