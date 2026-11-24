"""Platform-admin management of company workspaces (invoice-billed tenants).

Platform admins create companies, set their plan and access window, suspend or
reactivate them, and invite the first Tenant Admin. They do not become members:
company data stays private to the company unless a member grants access.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from context_jobs.tenancy.context import WorkspaceNotFoundError
from context_jobs.tenancy.invitations import create_invitation, list_invitations
from context_jobs.tenancy.keys import new_company_workspace_id
from context_jobs.tenancy.members import (
    MembershipConflictError,
    list_members,
    serialize_workspace,
)
from context_jobs.tenancy.plans import (
    COMPANY_PACKAGE_NAME,
    KIND_COMPANY,
    STATUS_ACTIVE,
    STATUS_SUSPENDED,
    package_grants,
)
from context_jobs.tenancy.roles import Role
from permissions.context_jobs_access import PERMISSION_CONTEXT_JOBS
from schemas.context_jobs_model import WorkspaceMemberModel, WorkspaceModel
from schemas.packages_model import PackagesModel

COMPANY_STATUSES = {STATUS_ACTIVE, STATUS_SUSPENDED}
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_UNSET = object()


def _slugify(name: str) -> str:
    return _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")[:48] or "company"


def _unique_slug(db: Session, base: str, exclude_id: Optional[str] = None) -> str:
    candidate, n = base, 2
    while True:
        query = db.query(WorkspaceModel.id).filter(WorkspaceModel.slug == candidate)
        if exclude_id:
            query = query.filter(WorkspaceModel.id != exclude_id)
        if query.first() is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def _validate_package(db: Session, package_name: Optional[str]) -> Optional[str]:
    if package_name is None:
        return None
    name = package_name.strip().lower()
    if not db.query(PackagesModel).filter(PackagesModel.package_name == name).first():
        raise MembershipConflictError(f"Package {name!r} does not exist.")
    if not package_grants(db, name, PERMISSION_CONTEXT_JOBS):
        raise MembershipConflictError(f"Package {name!r} does not include Context Jobs.")
    return name


def _get_company(db: Session, workspace_id: str) -> WorkspaceModel:
    workspace = db.get(WorkspaceModel, workspace_id)
    if workspace is None or workspace.kind != KIND_COMPANY:
        raise WorkspaceNotFoundError("Company not found")
    return workspace


def _member_counts(db: Session, workspace_ids: list[str]) -> dict[str, int]:
    if not workspace_ids:
        return {}
    rows = (
        db.query(WorkspaceMemberModel.workspace_id, func.count(WorkspaceMemberModel.id))
        .filter(
            WorkspaceMemberModel.workspace_id.in_(workspace_ids),
            WorkspaceMemberModel.status == STATUS_ACTIVE,
        )
        .group_by(WorkspaceMemberModel.workspace_id)
        .all()
    )
    return {workspace_id: count for workspace_id, count in rows}


def list_companies(db: Session, *, query: Optional[str] = None) -> list[dict[str, Any]]:
    q = db.query(WorkspaceModel).filter(WorkspaceModel.kind == KIND_COMPANY)
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(WorkspaceModel.name.ilike(like) | WorkspaceModel.slug.ilike(like))
    companies = q.order_by(WorkspaceModel.created_at.desc()).all()
    counts = _member_counts(db, [c.id for c in companies])
    return [
        {**serialize_workspace(c), "notes": c.notes, "activeMembers": counts.get(c.id, 0)}
        for c in companies
    ]


def get_company_detail(db: Session, workspace_id: str) -> dict[str, Any]:
    company = _get_company(db, workspace_id)
    members = list_members(db, company.id)
    return {
        **serialize_workspace(company),
        "notes": company.notes,
        "activeMembers": sum(1 for m in members if m["status"] == STATUS_ACTIVE),
        "members": members,
        "invitations": list_invitations(db, company.id),
    }


def create_company(
    db: Session,
    *,
    name: str,
    actor_uid: str,
    package_name: Optional[str] = COMPANY_PACKAGE_NAME,
    access_expires_at: Optional[datetime] = None,
    notes: Optional[str] = None,
    admin_email: Optional[str] = None,
) -> dict[str, Any]:
    clean_name = (name or "").strip()
    if not clean_name:
        raise MembershipConflictError("Company name is required.")
    workspace_id = new_company_workspace_id()
    company = WorkspaceModel(
        id=workspace_id,
        name=clean_name,
        # Company rows are partitioned by the workspace id itself.
        owner=workspace_id,
        kind=KIND_COMPANY,
        status=STATUS_ACTIVE,
        slug=_unique_slug(db, _slugify(clean_name)),
        package_name=_validate_package(db, package_name),
        access_expires_at=access_expires_at,
        created_by=actor_uid,
        notes=notes,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    cj_audit.write_audit_event(
        db,
        event_type="workspace.created",
        entity_type="workspace",
        entity_id=company.id,
        actor=actor_uid,
        workspace_id=company.id,
        metadata={
            "name": company.name,
            "plan": company.package_name,
            "accessExpiresAt": access_expires_at.isoformat() if access_expires_at else None,
        },
    )

    invitation = None
    if admin_email:
        invitation = create_invitation(
            db,
            workspace_id=company.id,
            email=admin_email,
            role=Role.TENANT_ADMIN.value,
            invited_by=actor_uid,
        )
    return {**get_company_detail(db, company.id), "adminInvitation": invitation}


def update_company(
    db: Session,
    workspace_id: str,
    *,
    actor_uid: str,
    name: Any = _UNSET,
    status: Any = _UNSET,
    package_name: Any = _UNSET,
    access_expires_at: Any = _UNSET,
    notes: Any = _UNSET,
) -> dict[str, Any]:
    """Patch semantics: only arguments that are passed are changed (None clears expiry/notes)."""
    company = _get_company(db, workspace_id)
    before = serialize_workspace(company)

    if name is not _UNSET:
        clean = (name or "").strip()
        if not clean:
            raise MembershipConflictError("Company name is required.")
        company.name = clean
    if status is not _UNSET:
        if status not in COMPANY_STATUSES:
            raise MembershipConflictError(
                f"Status must be one of: {', '.join(sorted(COMPANY_STATUSES))}."
            )
        company.status = status
    if package_name is not _UNSET:
        company.package_name = _validate_package(db, package_name)
    if access_expires_at is not _UNSET:
        company.access_expires_at = access_expires_at
    if notes is not _UNSET:
        company.notes = notes

    db.add(company)
    db.commit()
    db.refresh(company)
    after = serialize_workspace(company)
    event_type = "workspace.updated"
    if before["status"] != after["status"]:
        event_type = "workspace.suspended" if after["status"] == STATUS_SUSPENDED else "workspace.reactivated"
    cj_audit.write_audit_event(
        db,
        event_type=event_type,
        entity_type="workspace",
        entity_id=company.id,
        actor=actor_uid,
        workspace_id=company.id,
        metadata={"before": before, "after": after},
    )
    return get_company_detail(db, company.id)
