from schemas.packages_model import PackagesModel


class PackageRepository:
    @staticmethod
    def exists(package_name: str, db) -> bool:
        return (
            db.query(PackagesModel)
            .filter(PackagesModel.package_name == package_name)
            .first()
            is not None
        )
    
    @staticmethod
    def create(package_name: str, is_custom: bool, db):
        db.add(
            PackagesModel(
                package_name=package_name,
                is_custom=is_custom
            )
        )
    
    @staticmethod
    def get_all(db):
        return db.query(PackagesModel).all()
    
    @staticmethod
    def get_by_name(package_name: str, db):
        return (
            db.query(PackagesModel)
            .filter(PackagesModel.package_name == package_name)
            .first()
        )
    
    @staticmethod
    def delete(package_id: int, db) -> bool:
        package = (
            db.query(PackagesModel)
            .filter(PackagesModel.id == package_id)
            .first()
        )
        
        if not package:
            return False
        
        db.delete(package)
        return True
