from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import database
from models.models import Permission
from schemas.permission_model import PermissionModel

permissioons_router = APIRouter()

@permissioons_router.post("/permissions")
async def create_permission(permission_name: Permission, db: Session = Depends(database.get_db)):
    
    if not db.query(PermissionModel).filter(PermissionModel.permission_name == permission_name.permission_name).first():
        new_permission = PermissionModel(
            permission_name=permission_name.permission_name
        )
        db.add(new_permission)
        db.commit()
        db.refresh(new_permission)
    
        return {"permission_name": permission_name, "status": "Permission created"}
    return {"status": "Permission already exists"}

@permissioons_router.get("/permissions")
async def get_permissions(db: Session = Depends(database.get_db)):
    permissions = db.query(PermissionModel).all()
    return permissions

@permissioons_router.delete("/permissions/{permission_id}")
async def delete_permission(permission_id: int, db: Session = Depends(database.get_db)):
    permission = db.query(PermissionModel).filter(PermissionModel.permission_id == permission_id).first()
    if not permission:
        return {"status": "Permission not found"}
    
    db.delete(permission)
    db.commit()
    
    return {"status": "Permission deleted"}