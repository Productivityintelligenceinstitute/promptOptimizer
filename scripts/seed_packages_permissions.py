from sqlalchemy.orm import Session
from sqlalchemy import select

from database import database
from schemas.packages_model import PackagesModel
from schemas.permission_model import PermissionModel
from schemas.packages_permission_model import PackagesPermissionModel


def seed_packages(db: Session):
    packages = [
        PackagesModel(
            package_name="free",
            is_custom=False
        ),
        PackagesModel(
            package_name="essential",
            is_custom=False
        ),
        PackagesModel(
            package_name="pro",
            is_custom=False
        ),
    ]

    for pkg in packages:
        db.add(pkg)

    db.commit()


def seed_permissions(db: Session):
    permissions = [
        PermissionModel(
            permission_name="BASIC_OPT"
        ),
        PermissionModel(
            permission_name="STRUCT_OPT"
        ),
        PermissionModel(
            permission_name="MASTER_OPT"
        ),
        PermissionModel(
            permission_name="SYS_OPT"
        ),
        PermissionModel(
            permission_name="LIB"
        ),
    ]

    for perm in permissions:
        db.add(perm)

    db.commit()


def seed_packages_permissions(db: Session):
    
    free_package_id = db.query(PackagesModel).filter(PackagesModel.package_name == "free").first().id
    essential_package_id = db.query(PackagesModel).filter(PackagesModel.package_name == "essential").first().id
    pro_package_id = db.query(PackagesModel).filter(PackagesModel.package_name == "pro").first().id
    
    basic_opt_permission_id = db.query(PermissionModel).filter(PermissionModel.permission_name == "BASIC_OPT").first().id
    struct_opt_permission_id = db.query(PermissionModel).filter(PermissionModel.permission_name == "STRUCT_OPT").first().id
    master_opt_permission_id = db.query(PermissionModel).filter(PermissionModel.permission_name == "MASTER_OPT").first().id
    sys_opt_permission_id = db.query(PermissionModel).filter(PermissionModel.permission_name == "SYS_OPT").first().id
    lib_permission_id = db.query(PermissionModel).filter(PermissionModel.permission_name == "LIB").first().id
    
    relations = [
        # FREE
        (free_package_id, basic_opt_permission_id, True, 5),
        (free_package_id, struct_opt_permission_id, False, None),
        (free_package_id, master_opt_permission_id, False, None),
        (free_package_id, sys_opt_permission_id, False, None),
        (free_package_id, lib_permission_id, False, None),

        # ESSENTIAL
        (essential_package_id, basic_opt_permission_id, True, None),
        (essential_package_id, struct_opt_permission_id, True, None),
        (essential_package_id, master_opt_permission_id, False, None),
        (essential_package_id, sys_opt_permission_id, False, None),
        (essential_package_id, lib_permission_id, True, None),

        # PRO
        (pro_package_id, basic_opt_permission_id, True, None),
        (pro_package_id, struct_opt_permission_id, True, None),
        (pro_package_id, master_opt_permission_id, True, 50),
        (pro_package_id, sys_opt_permission_id, True, None),
        (pro_package_id, lib_permission_id, True, None),
    ]

    for rel in relations:
        pkg_id, perm_id, enabled, limit = rel

        db.add(
            PackagesPermissionModel(
                package_id=pkg_id,
                permission_id=perm_id,
                is_enabled=enabled,
                query_limit=limit,
            )
        )

    db.commit()


def run_seed():
    db = database.SessionLocal()
    try:
        seed_packages(db)
        seed_permissions(db)
        seed_packages_permissions(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
