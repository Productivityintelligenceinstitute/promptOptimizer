from fastapi import APIRouter, Depends

from database import database
from sqlalchemy.orm import Session

from models.permission_model import CreatePermissionRequest
from services.permission_service import create_permission, get_all_permissions, delete_permission

permissioons_router = APIRouter(prefix="/permissions")

@permissioons_router.post("/create")
def create(payload: CreatePermissionRequest, db: Session = Depends(database.get_db)):
    return create_permission(payload, db)


@permissioons_router.get("")
def list_permissions(db: Session = Depends(database.get_db)):
    return get_all_permissions(db)


@permissioons_router.delete("/{permission_id}")
def remove_permission(permission_id: str, db: Session = Depends(database.get_db)):
    return delete_permission(permission_id, db)