from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session
from database import database

from models.packages_permission_model import AssignPermissionRequest
from services.package_permission_service import assign_permission, get_all_package_permissions,  delete_package_permission


packages_permission_router = APIRouter(prefix="/package-permissions")

@packages_permission_router.get("")
def list_all(db: Session = Depends(database.get_db)):
    return get_all_package_permissions(db)


@packages_permission_router.post("")
def assign(payload: AssignPermissionRequest, db: Session = Depends(database.get_db)):
    return assign_permission(payload, db)


@packages_permission_router.delete("")
def remove(package_name: str, permission_name: str, db: Session = Depends(database.get_db)):
    return delete_package_permission(package_name, permission_name, db)