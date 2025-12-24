from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import database
from models.models import Package
from schemas.packages_model import PackagesModel

packages_router = APIRouter()

@packages_router.post("/packages")
async def create_package(package_name: Package, db: Session = Depends(database.get_db)):
    
    if not db.query(PackagesModel).filter(PackagesModel.package_name == package_name.package_name).first():
        new_package = PackagesModel(
            package_name=package_name.package_name,
            is_custom=package_name.is_custom
        )
        db.add(new_package)
        db.commit()
        db.refresh(new_package)
    
        return {"package_name": package_name, "status": "Package created"}
    return {"status": "Package already exists"}

@packages_router.get("/packages")
async def get_packages(db: Session = Depends(database.get_db)):
    packages = db.query(PackagesModel).all()
    
    return {"packages": packages}

@packages_router.delete("/packages/{package_id}")
async def delete_package(package_id: int, db: Session = Depends(database.get_db)):
    package = db.query(PackagesModel).filter(PackagesModel.package_id == package_id).first()
    if not package:
        return {"status": "Package not found"}
    
    db.delete(package)
    db.commit()
    
    return {"status": "Package deleted"}