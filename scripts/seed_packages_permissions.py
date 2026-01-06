import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from sqlalchemy import select

from database import database
from schemas.packages_model import PackagesModel
from schemas.permission_model import PermissionModel
from schemas.packages_permission_model import PackagesPermissionModel
from schemas.user_model import UserModel


def seed_packages(db: Session):
    package_names = ["free", "essential", "pro"]
    
    for package_name in package_names:
        # Check if package already exists
        existing = db.query(PackagesModel).filter(PackagesModel.package_name == package_name).first()
        if not existing:
            new_package = PackagesModel(
                package_name=package_name,
                is_custom=False
            )
            db.add(new_package)
    
    db.commit()


def seed_permissions(db: Session):
    permission_names = ["BASIC_OPT", "STRUCT_OPT", "MASTER_OPT", "SYS_OPT", "LIB"]
    
    for permission_name in permission_names:
        # Check if permission already exists
        existing = db.query(PermissionModel).filter(PermissionModel.permission_name == permission_name).first()
        if not existing:
            new_permission = PermissionModel(
                permission_name=permission_name
            )
            db.add(new_permission)
    
    db.commit()


def seed_packages_permissions(db: Session):
    
    free_package = db.query(PackagesModel).filter(PackagesModel.package_name == "free").first()
    essential_package = db.query(PackagesModel).filter(PackagesModel.package_name == "essential").first()
    pro_package = db.query(PackagesModel).filter(PackagesModel.package_name == "pro").first()
    
    basic_opt_permission = db.query(PermissionModel).filter(PermissionModel.permission_name == "BASIC_OPT").first()
    struct_opt_permission = db.query(PermissionModel).filter(PermissionModel.permission_name == "STRUCT_OPT").first()
    master_opt_permission = db.query(PermissionModel).filter(PermissionModel.permission_name == "MASTER_OPT").first()
    sys_opt_permission = db.query(PermissionModel).filter(PermissionModel.permission_name == "SYS_OPT").first()
    lib_permission = db.query(PermissionModel).filter(PermissionModel.permission_name == "LIB").first()
    
    if not all([free_package, essential_package, pro_package, basic_opt_permission, struct_opt_permission, master_opt_permission, sys_opt_permission, lib_permission]):
        print("Warning: Some packages or permissions are missing. Skipping package-permission seeding.")
        return
    
    free_package_id = free_package.id
    essential_package_id = essential_package.id
    pro_package_id = pro_package.id
    
    basic_opt_permission_id = basic_opt_permission.id
    struct_opt_permission_id = struct_opt_permission.id
    master_opt_permission_id = master_opt_permission.id
    sys_opt_permission_id = sys_opt_permission.id
    lib_permission_id = lib_permission.id
    
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
        
        # Check if relation already exists
        existing = db.query(PackagesPermissionModel).filter(
            PackagesPermissionModel.package_id == pkg_id,
            PackagesPermissionModel.permission_id == perm_id
        ).first()
        
        if not existing:
            db.add(
                PackagesPermissionModel(
                    package_id=pkg_id,
                    permission_id=perm_id,
                    is_enabled=enabled,
                    query_limit=limit,
                )
            )

    db.commit()

def seed_default_user(db: Session):
    default_admin = UserModel(
        full_name="JPO Admin",
        role="admin",
        email="jetpromptoptimizer@gmail.com",
        firebase_uid="my-firebase-uid"
    )
    
    db.add(default_admin)
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
