"""Seed Context Jobs rows in permissions + packages_permission (idempotent).

Mirrors docs/context_jobs_permissions_seed.sql: CONTEXT_JOBS permission names and
trial/essential/pro package mappings (trial: 5 job/run limit; essential: disabled; pro: unlimited).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from permissions.context_jobs_access import (
    PERMISSION_CONTEXT_JOBS,
    PERMISSION_CONTEXT_JOBS_JOB,
    PERMISSION_CONTEXT_JOBS_RUN,
)
from repositories.package_permission_repository import PackagePermissionRepository
from repositories.permission_repository import PermissionRepository
from schemas.packages_model import PackagesModel

logger = logging.getLogger(__name__)

CONTEXT_JOBS_PERMISSIONS = (
    PERMISSION_CONTEXT_JOBS,
    PERMISSION_CONTEXT_JOBS_JOB,
    PERMISSION_CONTEXT_JOBS_RUN,
)

# package_name -> [(permission_name, is_enabled, query_limit)]
PACKAGE_RULES: dict[str, list[tuple[str, bool, int | None]]] = {
    "trial": [
        (PERMISSION_CONTEXT_JOBS, True, None),
        (PERMISSION_CONTEXT_JOBS_JOB, True, 5),
        (PERMISSION_CONTEXT_JOBS_RUN, True, 5),
    ],
    "essential": [
        (PERMISSION_CONTEXT_JOBS, False, None),
        (PERMISSION_CONTEXT_JOBS_JOB, False, None),
        (PERMISSION_CONTEXT_JOBS_RUN, False, None),
    ],
    "pro": [
        (PERMISSION_CONTEXT_JOBS, True, None),
        (PERMISSION_CONTEXT_JOBS_JOB, True, None),
        (PERMISSION_CONTEXT_JOBS_RUN, True, None),
    ],
}


def _ensure_permission(db: Session, permission_name: str) -> None:
    if not PermissionRepository.exists(permission_name, db):
        PermissionRepository.create(permission_name, db)
        db.commit()
        logger.info("Created permission %s", permission_name)


def _ensure_package_permission(
    db: Session,
    package_name: str,
    permission_name: str,
    is_enabled: bool,
    query_limit: int | None,
) -> None:
    package = (
        db.query(PackagesModel)
        .filter(PackagesModel.package_name == package_name)
        .first()
    )
    if not package:
        logger.warning("Package %s not found; skipping permission seed", package_name)
        return

    if PackagePermissionRepository.exists(package_name, permission_name, db):
        return

    PackagePermissionRepository.create(
        package_name,
        permission_name,
        query_limit,
        is_enabled,
        db,
    )
    db.commit()
    logger.info(
        "Assigned %s -> %s (enabled=%s, query_limit=%s)",
        package_name,
        permission_name,
        is_enabled,
        query_limit,
    )


def seed_context_jobs_permissions(db: Session) -> None:
    """Ensure Context Jobs permission names and package mappings exist."""
    for name in CONTEXT_JOBS_PERMISSIONS:
        _ensure_permission(db, name)

    for package_name, rules in PACKAGE_RULES.items():
        for permission_name, is_enabled, query_limit in rules:
            _ensure_package_permission(
                db,
                package_name,
                permission_name,
                is_enabled,
                query_limit,
            )
