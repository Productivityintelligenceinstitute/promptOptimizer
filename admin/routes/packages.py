from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session
from database import database

from services.package_service import create_package, get_all_packages, delete_package
from models.packages_model import CreatePackageRequest

packages_router = APIRouter(prefix="/packages")

@packages_router.post("/add")
def create(payload: CreatePackageRequest, db: Session = Depends(database.get_db)):
    return create_package(payload, db)


@packages_router.get("")
def list_packages(db: Session = Depends(database.get_db)):
    return get_all_packages(db)


@packages_router.delete("/{package_id}")
def remove_package(package_id: int, db: Session = Depends(database.get_db)):
    return delete_package(package_id, db)