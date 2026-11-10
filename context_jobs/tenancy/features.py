"""Plan-gated features that depend on the active workspace."""

from __future__ import annotations

from sqlalchemy.orm import Session

from context_jobs.plan_entitlements import ContextJobsAccessError
from context_jobs.tenancy.context import TenantContext
from context_jobs.tenancy.plans import (
    ACCESS_ACTIVE,
    PERMISSION_PROCUREMENT_TEMPLATES,
    company_access_state,
    package_grants,
)
from repositories.check_access import AccessRepository
from schemas.context_jobs_model import WorkspaceModel

PROCUREMENT_TEMPLATES_LOCKED_MESSAGE = (
    "Procurement expert templates are included with JET company plans. "
    "Book a call with the JET team to enable them for your organization."
)


def procurement_templates_enabled(db: Session, tenant: TenantContext) -> bool:
    """
    Company workspaces: from the company's package. Personal workspaces: platform
    admins, or a personal package that explicitly grants PROCUREMENT_TEMPLATES.
    """
    if tenant.is_company:
        workspace = db.get(WorkspaceModel, tenant.workspace_id)
        return (
            workspace is not None
            and company_access_state(workspace) == ACCESS_ACTIVE
            and package_grants(db, workspace.package_name, PERMISSION_PROCUREMENT_TEMPLATES)
        )
    if tenant.is_platform_admin:
        return True
    grant = AccessRepository.check_access(db, tenant.user_id, PERMISSION_PROCUREMENT_TEMPLATES)
    return bool(grant and grant.is_enabled)


def require_procurement_templates(db: Session, tenant: TenantContext) -> None:
    if not procurement_templates_enabled(db, tenant):
        raise ContextJobsAccessError(PROCUREMENT_TEMPLATES_LOCKED_MESSAGE)
