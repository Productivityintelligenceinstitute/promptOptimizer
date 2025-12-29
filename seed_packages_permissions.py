from sqlalchemy.orm import Session
from sqlalchemy import select

from database import database
from schemas.packages_model import PackagesModel
from schemas.permission_model import PermissionModel
from schemas.packages_permission_model import PackagesPermissionModel


def seed_packages(db: Session):
    packages = [
        PackagesModel(
            package_id=1,
            package_name="free",
            is_custom=False,
            created_at="2025-12-17 12:03:56.012899+05"
        ),
        PackagesModel(
            package_id=2,
            package_name="essential",
            is_custom=False,
            created_at="2025-12-17 12:04:30.372097+05"
        ),
        PackagesModel(
            package_id=3,
            package_name="pro",
            is_custom=False,
            created_at="2025-12-17 12:04:39.596361+05"
        ),
    ]

    for pkg in packages:
        exists = db.execute(
            select(PackagesModel).where(PackagesModel.package_id == pkg.package_id)
        ).scalar_one_or_none()

        if not exists:
            db.add(pkg)

    db.commit()


def seed_permissions(db: Session):
    permissions = [
        PermissionModel(
            permission_id=1,
            permission_name="BASIC_OPT",
            created_at="2025-12-17 11:54:44.416465+05"
        ),
        PermissionModel(
            permission_id=2,
            permission_name="STRUCT_OPT",
            created_at="2025-12-17 11:54:58.429704+05"
        ),
        PermissionModel(
            permission_id=3,
            permission_name="MASTER_OPT",
            created_at="2025-12-17 11:55:10.487811+05"
        ),
        PermissionModel(
            permission_id=4,
            permission_name="SYS_OPT",
            created_at="2025-12-17 11:55:25.061911+05"
        ),
        PermissionModel(
            permission_id=5,
            permission_name="LIB",
            created_at="2025-12-17 13:04:23.728518+05"
        ),
    ]

    for perm in permissions:
        exists = db.execute(
            select(PermissionModel).where(PermissionModel.permission_id == perm.permission_id)
        ).scalar_one_or_none()

        if not exists:
            db.add(perm)

    db.commit()


def seed_packages_permissions(db: Session):
    relations = [
        # FREE
        (3, 1, 3, False, None),
        (4, 1, 4, False, None),
        (5, 1, 5, False, None),

        # ESSENTIAL
        (6, 2, 1, True, None),
        (7, 2, 2, True, None),
        (8, 2, 3, False, None),
        (9, 2, 4, False, None),
        (10, 2, 5, False, None),

        # PRO
        (11, 3, 1, True, None),
        (12, 3, 2, True, None),
        (13, 3, 3, True, 50),
        (14, 3, 4, True, None),
        (15, 3, 5, False, None),
    ]

    for rel in relations:
        rel_id, pkg_id, perm_id, enabled, limit = rel

        exists = db.execute(
            select(PackagesPermissionModel)
            .where(PackagesPermissionModel.id == rel_id)
        ).scalar_one_or_none()

        if not exists:
            db.add(
                PackagesPermissionModel(
                    id=rel_id,
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
