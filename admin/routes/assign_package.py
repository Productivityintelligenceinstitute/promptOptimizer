from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session
from database import database

from models.packages_model import AssignPackage
from services.assign_package_service import assign_package_service

assign_package_router = APIRouter(prefix="/admin/assign-package")

@assign_package_router.put("")
def assign_package_to_user(payload: AssignPackage, db: Session = Depends(database.get_db)):
    return assign_package_service(payload, db)