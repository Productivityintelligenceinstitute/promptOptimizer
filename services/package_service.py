from fastapi import HTTPException
from sqlalchemy.orm import Session

from repositories.package_repository import PackageRepository
from core.exceptions.conflict import ConflictException
from core.exceptions.not_found import NotFoundException


def create_package(payload, db: Session):
    try:
        with db.begin():
            if PackageRepository.exists(payload.package_name, db):
                raise ConflictException("Package with this name already exists")
            
            PackageRepository.create(
                db=db,
                package_name=payload.package_name,
                is_custom=payload.is_custom
            )
            
            return {
                "status": "success",
                "message": "Package created successfully"
            }
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)

def get_all_packages(db: Session):
    return {
        "packages": PackageRepository.get_all(db)
    }


def delete_package(package_id: int, db: Session):
    try:
        with db.begin():
            deleted = PackageRepository.delete(package_id, db)
            if not deleted:
                raise NotFoundException("Package not found")
            
            return {
                "status": "success",
                "message": "Package deleted successfully"
            }
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)