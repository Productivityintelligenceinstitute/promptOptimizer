"""Company plan access: package lookup and validity of a company's access window.

Companies are invoiced outside Stripe. A platform admin sets the workspace's
``package_name`` and ``access_expires_at``; members inherit that package's
permissions while the workspace is active and not expired.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from schemas.context_jobs_model import WorkspaceMemberModel, WorkspaceModel
from schemas.packages_model import PackagesModel
from schemas.packages_permission_model import PackagesPermissionModel
from schemas.permission_model import PermissionModel

COMPANY_PACKAGE_NAME = "company"
PERMISSION_PROCUREMENT_TEMPLATES = "PROCUREMENT_TEMPLATES"

KIND_PERSONAL = "personal"
KIND_COMPANY = "company"

STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
STATUS_DISABLED = "disabled"

ACCESS_ACTIVE = "active"
ACCESS_SUSPENDED = "suspended"
ACCESS_EXPIRED = "expired"
ACCESS_NO_PLAN = "no_plan"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_company(workspace: WorkspaceModel) -> bool:
    return (workspace.kind or KIND_PERSONAL) == KIND_COMPANY


def company_access_state(workspace: WorkspaceModel, now: Optional[datetime] = None) -> str:
    """Why a company workspace can or cannot be used right now."""
    if (workspace.status or STATUS_ACTIVE) != STATUS_ACTIVE:
        return ACCESS_SUSPENDED
    if not workspace.package_name:
        return ACCESS_NO_PLAN
    expires = workspace.access_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= (now or utcnow()):
            return ACCESS_EXPIRED
    return ACCESS_ACTIVE


ACCESS_MESSAGES = {
    ACCESS_SUSPENDED: "This company account is suspended. Contact your JET account manager.",
    ACCESS_EXPIRED: "This company's access has expired. Contact your JET account manager to renew.",
    ACCESS_NO_PLAN: "This company account has no active plan yet. Contact your JET account manager.",
}


def package_permission(
    db: Session, package_name: str, permission_name: str
) -> Optional[PackagesPermissionModel]:
    return (
        db.query(PackagesPermissionModel)
        .join(PackagesModel, PackagesModel.id == PackagesPermissionModel.package_id)
        .join(PermissionModel, PermissionModel.id == PackagesPermissionModel.permission_id)
        .filter(
            PackagesModel.package_name == package_name,
            PermissionModel.permission_name == permission_name,
        )
        .first()
    )


def package_grants(db: Session, package_name: Optional[str], permission_name: str) -> bool:
    if not package_name:
        return False
    row = package_permission(db, package_name, permission_name)
    return bool(row and row.is_enabled)


def active_company_workspaces_for_user(db: Session, firebase_uid: str) -> list[WorkspaceModel]:
    """Companies where the user is an active member and the company's access is valid."""
    if not firebase_uid:
        return []
    rows = (
        db.query(WorkspaceModel)
        .join(WorkspaceMemberModel, WorkspaceMemberModel.workspace_id == WorkspaceModel.id)
        .filter(
            WorkspaceMemberModel.user_id == firebase_uid,
            WorkspaceMemberModel.status == STATUS_ACTIVE,
            WorkspaceModel.kind == KIND_COMPANY,
        )
        .order_by(WorkspaceModel.created_at.asc())
        .all()
    )
    now = utcnow()
    return [ws for ws in rows if company_access_state(ws, now) == ACCESS_ACTIVE]


def company_permission_for_user(
    db: Session, firebase_uid: str, permission_name: str
) -> Optional[PackagesPermissionModel]:
    """
    Best enabled grant of ``permission_name`` from any of the user's active companies.
    Unlimited grants (query_limit is None) win over capped ones.
    """
    best: Optional[PackagesPermissionModel] = None
    for ws in active_company_workspaces_for_user(db, firebase_uid):
        row = package_permission(db, ws.package_name, permission_name)
        if not row or not row.is_enabled:
            continue
        if row.query_limit is None:
            return row
        if best is None or (best.query_limit or 0) < row.query_limit:
            best = row
    return best
