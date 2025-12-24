from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import database
from models.models import PackagePermission
from schemas.packages_permission_model import PackagesPermissionModel

packages_permission_router = APIRouter()

@packages_permission_router.post("/packages-permission")
async def assign_permission_to_package(package_permission: PackagePermission, db: Session = Depends(database.get_db)):
    
    existing_entry = db.query(PackagesPermissionModel).filter(
        PackagesPermissionModel.package_id == package_permission.package_id,
        PackagesPermissionModel.permission_id == package_permission.permission_id
    ).first()
    
    if not existing_entry:
        new_entry = PackagesPermissionModel(
            package_id=package_permission.package_id,
            permission_id=package_permission.permission_id,
            query_limit=package_permission.query_limit,
            is_enabled=package_permission.access
        )
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)
    
        return {"status": "Permission assigned to package"}
    return {"status": "Permission already assigned to package"}

@packages_permission_router.get("/packages-permission")
async def get_package_permissions(db: Session = Depends(database.get_db)):
    packages_permission_list = db.query(PackagesPermissionModel).all()
    
    return {"package_permissions": packages_permission_list}

@packages_permission_router.delete("/packages-permission")
async def delete_package_permission(package_id: int, permission_id: int, db: Session = Depends(database.get_db)):
    entry = db.query(PackagesPermissionModel).filter(
        PackagesPermissionModel.package_id == package_id,
        PackagesPermissionModel.permission_id == permission_id
    ).first()
    if not entry:
        return {"status": "Package-Permission entry not found"}
    
    db.delete(entry)
    db.commit()
    
    return {"status": "Package-Permission entry deleted"}