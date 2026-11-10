"""Seed the invoice-billed ``company`` package and the procurement templates permission."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from context_jobs.permissions_seed import _ensure_package_permission, _ensure_permission
from context_jobs.tenancy.plans import COMPANY_PACKAGE_NAME, PERMISSION_PROCUREMENT_TEMPLATES
from permissions.context_jobs_access import (
    PERMISSION_CONTEXT_JOBS,
    PERMISSION_CONTEXT_JOBS_JOB,
    PERMISSION_CONTEXT_JOBS_RUN,
)
from schemas.packages_model import PackagesModel

logger = logging.getLogger(__name__)

# Everything unlimited: companies pay by contract, not per query.
COMPANY_PERMISSIONS: tuple[str, ...] = (
    "BASIC_OPT",
    "STRUCT_OPT",
    "MASTER_OPT",
    "SYS_OPT",
    "LIB",
    PERMISSION_CONTEXT_JOBS,
    PERMISSION_CONTEXT_JOBS_JOB,
    PERMISSION_CONTEXT_JOBS_RUN,
    PERMISSION_PROCUREMENT_TEMPLATES,
)


def seed_company_package(db: Session) -> None:
    """Ensure the company package exists with its permissions (skips existing rows)."""
    if not db.query(PackagesModel).filter(PackagesModel.package_name == COMPANY_PACKAGE_NAME).first():
        db.add(PackagesModel(package_name=COMPANY_PACKAGE_NAME, is_custom=False))
        db.commit()
        logger.info("Created package %s", COMPANY_PACKAGE_NAME)

    _ensure_permission(db, PERMISSION_PROCUREMENT_TEMPLATES)
    for permission_name in COMPANY_PERMISSIONS:
        _ensure_permission(db, permission_name)
        _ensure_package_permission(db, COMPANY_PACKAGE_NAME, permission_name, True, None)
