from schemas.packages_model import PackagesModel
from schemas.permission_model import PermissionModel
from schemas.packages_permission_model import PackagesPermissionModel


class PackagePermissionRepository:
    @staticmethod
    def exists(package_name: str, permission_name: str, db) -> bool:
        
        package_id = db.query(PackagesModel.id).filter(
            PackagesModel.package_name == package_name
        ).scalar()
        
        permission_id = db.query(PermissionModel.id).filter(
            PermissionModel.permission_name == permission_name
        ).scalar()
        
        return (
            db.query(PackagesPermissionModel)
            .filter(
                PackagesPermissionModel.package_id == package_id,
                PackagesPermissionModel.permission_id == permission_id
            )
            .first()
            is not None
        )

    @staticmethod
    def create(package_name: str, permission_name: str, query_limit: int | None, is_enabled: bool, db):
        
        package_id = db.query(PackagesModel.id).filter(
            PackagesModel.package_name == package_name
        ).scalar()
        
        permission_id = db.query(PermissionModel.id).filter(
            PermissionModel.permission_name == permission_name
        ).scalar()
        
        db.add(
            PackagesPermissionModel(
                package_id=package_id,
                permission_id=permission_id,
                query_limit=query_limit,
                is_enabled=is_enabled
            )
        )

    @staticmethod
    def get_all(db):
        return db.query(PackagesPermissionModel).all()

    @staticmethod
    def delete(package_name: str, permission_name: str, db) -> bool:
        
        package_id = db.query(PackagesModel.id).filter(
            PackagesModel.package_name == package_name
        ).scalar()
        
        permission_id = db.query(PermissionModel.id).filter(
            PermissionModel.permission_name == permission_name
        ).scalar()
        
        entry = (
            db.query(PackagesPermissionModel)
            .filter(
                PackagesPermissionModel.package_id == package_id,
                PackagesPermissionModel.permission_id == permission_id
            )
            .first()
        )

        if not entry:
            return False

        db.delete(entry)
        return True
