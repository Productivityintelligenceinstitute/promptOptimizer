"""Idempotent seed for packages, core permissions, and default admin user."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from schemas.packages_model import PackagesModel
from schemas.permission_model import PermissionModel
from schemas.packages_permission_model import PackagesPermissionModel
from schemas.user_model import UserModel

logger = logging.getLogger(__name__)

DEFAULT_PACKAGE_NAMES = ("free", "trial", "essential", "pro")

CORE_PERMISSION_NAMES = ("BASIC_OPT", "STRUCT_OPT", "MASTER_OPT", "SYS_OPT", "LIB")

DEFAULT_ADMIN_EMAIL = "jetpromptoptimizer@gmail.com"


def seed_packages(db: Session) -> None:
    """Ensure default subscription packages exist."""
    created = False
    for package_name in DEFAULT_PACKAGE_NAMES:
        existing = (
            db.query(PackagesModel)
            .filter(PackagesModel.package_name == package_name)
            .first()
        )
        if existing:
            continue
        db.add(PackagesModel(package_name=package_name, is_custom=False))
        created = True
        logger.info("Created package %s", package_name)

    if created:
        db.commit()


def seed_permissions(db: Session) -> None:
    """Ensure core optimizer permission names exist."""
    created = False
    for permission_name in CORE_PERMISSION_NAMES:
        existing = (
            db.query(PermissionModel)
            .filter(PermissionModel.permission_name == permission_name)
            .first()
        )
        if existing:
            continue
        db.add(PermissionModel(permission_name=permission_name))
        created = True
        logger.info("Created permission %s", permission_name)

    if created:
        db.commit()


def seed_packages_permissions(db: Session) -> None:
    """Ensure package-to-permission mappings for optimizer features exist."""
    free_package = (
        db.query(PackagesModel).filter(PackagesModel.package_name == "free").first()
    )
    trial_package = (
        db.query(PackagesModel).filter(PackagesModel.package_name == "trial").first()
    )
    essential_package = (
        db.query(PackagesModel)
        .filter(PackagesModel.package_name == "essential")
        .first()
    )
    pro_package = (
        db.query(PackagesModel).filter(PackagesModel.package_name == "pro").first()
    )

    basic_opt_permission = (
        db.query(PermissionModel)
        .filter(PermissionModel.permission_name == "BASIC_OPT")
        .first()
    )
    struct_opt_permission = (
        db.query(PermissionModel)
        .filter(PermissionModel.permission_name == "STRUCT_OPT")
        .first()
    )
    master_opt_permission = (
        db.query(PermissionModel)
        .filter(PermissionModel.permission_name == "MASTER_OPT")
        .first()
    )
    sys_opt_permission = (
        db.query(PermissionModel)
        .filter(PermissionModel.permission_name == "SYS_OPT")
        .first()
    )
    lib_permission = (
        db.query(PermissionModel).filter(PermissionModel.permission_name == "LIB").first()
    )

    if not all(
        [
            free_package,
            trial_package,
            essential_package,
            pro_package,
            basic_opt_permission,
            struct_opt_permission,
            master_opt_permission,
            sys_opt_permission,
            lib_permission,
        ]
    ):
        logger.warning(
            "Some packages or permissions are missing; skipping package-permission seed"
        )
        return

    relations = [
        (free_package.id, basic_opt_permission.id, True, 5),
        (free_package.id, struct_opt_permission.id, False, None),
        (free_package.id, master_opt_permission.id, False, None),
        (free_package.id, sys_opt_permission.id, False, None),
        (free_package.id, lib_permission.id, False, None),
        (trial_package.id, basic_opt_permission.id, True, 5),
        (trial_package.id, struct_opt_permission.id, True, 1),
        (trial_package.id, master_opt_permission.id, True, None),
        (trial_package.id, sys_opt_permission.id, False, None),
        (trial_package.id, lib_permission.id, True, None),
        (essential_package.id, basic_opt_permission.id, True, None),
        (essential_package.id, struct_opt_permission.id, True, None),
        (essential_package.id, master_opt_permission.id, False, None),
        (essential_package.id, sys_opt_permission.id, False, None),
        (essential_package.id, lib_permission.id, True, None),
        (pro_package.id, basic_opt_permission.id, True, None),
        (pro_package.id, struct_opt_permission.id, True, None),
        (pro_package.id, master_opt_permission.id, True, 50),
        (pro_package.id, sys_opt_permission.id, True, None),
        (pro_package.id, lib_permission.id, True, None),
    ]

    created = False
    for pkg_id, perm_id, enabled, limit in relations:
        existing = (
            db.query(PackagesPermissionModel)
            .filter(
                PackagesPermissionModel.package_id == pkg_id,
                PackagesPermissionModel.permission_id == perm_id,
            )
            .first()
        )
        if existing:
            continue
        db.add(
            PackagesPermissionModel(
                package_id=pkg_id,
                permission_id=perm_id,
                is_enabled=enabled,
                query_limit=limit,
            )
        )
        created = True

    if created:
        db.commit()


def seed_default_user(db: Session) -> None:
    """Ensure the default admin user row exists."""
    existing = (
        db.query(UserModel)
        .filter(UserModel.email == DEFAULT_ADMIN_EMAIL)
        .first()
    )
    if existing:
        return

    db.add(
        UserModel(
            full_name="JPO Admin",
            role="admin",
            email=DEFAULT_ADMIN_EMAIL,
            firebase_uid="5yO8C3AZ8yULnZM0i78r8eRHxah2",
        )
    )
    db.commit()
    logger.info("Created default admin user %s", DEFAULT_ADMIN_EMAIL)


def seed_bootstrap(db: Session) -> None:
    """Run package, permission, and default-user seeds in order."""
    seed_packages(db)
    seed_permissions(db)
    seed_packages_permissions(db)
    seed_default_user(db)
