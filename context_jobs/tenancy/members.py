"""Workspace membership: listing, role/status changes, removal.

Membership changes are only allowed in company workspaces; a personal workspace
always has exactly one Tenant Admin. A company must keep at least one active
Tenant Admin so it can never be locked out of its own settings.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from context_jobs.tenancy.context import WorkspaceForbiddenError, WorkspaceNotFoundError
from context_jobs.tenancy.keys import personal_workspace_id
from context_jobs.tenancy.plans import (
    STATUS_ACTIVE,
    STATUS_DISABLED,
    company_access_state,
    is_company,
)
from context_jobs.tenancy.roles import ROLE_LABELS, Role, capabilities_for, parse_role
from context_jobs.workspace import ensure_personal_workspace
from schemas.context_jobs_model import WorkspaceMemberModel, WorkspaceModel
from schemas.user_model import UserModel

MEMBER_STATUSES = {STATUS_ACTIVE, STATUS_DISABLED}


class MembershipConflictError(ValueError):
    """Change would leave the workspace in an invalid state (HTTP 400)."""


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def get_company_workspace(db: Session, workspace_id: str) -> WorkspaceModel:
    workspace = db.get(WorkspaceModel, workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError("Workspace not found")
    if not is_company(workspace):
        raise MembershipConflictError("Members can only be managed in company workspaces.")
    return workspace


def serialize_workspace(workspace: WorkspaceModel) -> dict[str, Any]:
    company = is_company(workspace)
    return {
        "id": workspace.id,
        "name": workspace.name,
        "kind": workspace.kind or "personal",
        "slug": workspace.slug,
        "status": workspace.status or STATUS_ACTIVE,
        "plan": workspace.package_name if company else None,
        "accessExpiresAt": _iso(workspace.access_expires_at) if company else None,
        "accessState": company_access_state(workspace) if company else "active",
        "createdAt": _iso(workspace.created_at),
    }


def list_user_workspaces(db: Session, user: UserModel) -> list[dict[str, Any]]:
    """Workspaces the user belongs to (personal first), with their role in each."""
    firebase_uid = user.firebase_uid or ""
    ensure_personal_workspace(db, firebase_uid)
    rows = (
        db.query(WorkspaceModel, WorkspaceMemberModel)
        .join(WorkspaceMemberModel, WorkspaceMemberModel.workspace_id == WorkspaceModel.id)
        .filter(WorkspaceMemberModel.user_id == firebase_uid)
        .all()
    )
    personal_id = personal_workspace_id(firebase_uid)
    result = []
    for workspace, membership in rows:
        # Another user's personal workspace is never shared.
        if not is_company(workspace) and workspace.id != personal_id:
            continue
        role = parse_role(membership.role)
        result.append(
            {
                **serialize_workspace(workspace),
                "role": role.value if role else None,
                "roleLabel": ROLE_LABELS.get(role) if role else None,
                "capabilities": capabilities_for(role),
                "membershipStatus": membership.status or STATUS_ACTIVE,
            }
        )
    result.sort(key=lambda w: (w["kind"] != "personal", (w["name"] or "").lower()))
    return result


def serialize_member(membership: WorkspaceMemberModel, user: Optional[UserModel]) -> dict[str, Any]:
    role = parse_role(membership.role)
    return {
        "memberId": str(membership.id),
        "userId": membership.user_id,
        "email": user.email if user else None,
        "fullName": user.full_name if user else None,
        "role": role.value if role else membership.role,
        "roleLabel": ROLE_LABELS.get(role) if role else membership.role,
        "status": membership.status or STATUS_ACTIVE,
        "invitedBy": membership.invited_by,
        "joinedAt": _iso(membership.created_at),
        "lastSignInAt": _iso(user.last_login_at) if user else None,
    }


def list_members(db: Session, workspace_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(WorkspaceMemberModel, UserModel)
        .outerjoin(UserModel, UserModel.firebase_uid == WorkspaceMemberModel.user_id)
        .filter(WorkspaceMemberModel.workspace_id == workspace_id)
        .order_by(WorkspaceMemberModel.created_at.asc())
        .all()
    )
    return [serialize_member(membership, user) for membership, user in rows]


def _get_membership(db: Session, workspace_id: str, member_uid: str) -> WorkspaceMemberModel:
    row = (
        db.query(WorkspaceMemberModel)
        .filter(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == member_uid,
        )
        .first()
    )
    if row is None:
        raise WorkspaceNotFoundError("Member not found")
    return row


def _active_admin_count(db: Session, workspace_id: str, excluding_uid: Optional[str] = None) -> int:
    query = db.query(WorkspaceMemberModel).filter(
        WorkspaceMemberModel.workspace_id == workspace_id,
        WorkspaceMemberModel.role == Role.TENANT_ADMIN.value,
        WorkspaceMemberModel.status == STATUS_ACTIVE,
    )
    if excluding_uid:
        query = query.filter(WorkspaceMemberModel.user_id != excluding_uid)
    return query.count()


def _would_remove_last_admin(db: Session, membership: WorkspaceMemberModel) -> bool:
    is_active_admin = (
        parse_role(membership.role) == Role.TENANT_ADMIN
        and (membership.status or STATUS_ACTIVE) == STATUS_ACTIVE
    )
    return is_active_admin and _active_admin_count(db, membership.workspace_id, membership.user_id) == 0


def _member_user(db: Session, member_uid: str) -> Optional[UserModel]:
    return db.query(UserModel).filter(UserModel.firebase_uid == member_uid).first()


def update_member(
    db: Session,
    *,
    workspace_id: str,
    member_uid: str,
    actor_uid: str,
    role: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    get_company_workspace(db, workspace_id)
    membership = _get_membership(db, workspace_id, member_uid)

    new_role: Optional[Role] = None
    if role is not None:
        new_role = parse_role(role)
        if new_role is None:
            raise MembershipConflictError(f"Unknown role {role!r}.")
    if status is not None and status not in MEMBER_STATUSES:
        raise MembershipConflictError(f"Status must be one of: {', '.join(sorted(MEMBER_STATUSES))}.")

    demoting = new_role is not None and new_role != Role.TENANT_ADMIN
    disabling = status == STATUS_DISABLED
    if (demoting or disabling) and _would_remove_last_admin(db, membership):
        raise MembershipConflictError("A company must keep at least one active Tenant Admin.")

    before = {"role": membership.role, "status": membership.status}
    if new_role is not None:
        membership.role = new_role.value
    if status is not None:
        membership.status = status
    db.add(membership)
    db.commit()
    db.refresh(membership)

    cj_audit.write_audit_event(
        db,
        event_type="membership.updated",
        entity_type="membership",
        entity_id=member_uid,
        actor=actor_uid,
        workspace_id=workspace_id,
        metadata={"before": before, "after": {"role": membership.role, "status": membership.status}},
    )
    return serialize_member(membership, _member_user(db, member_uid))


def remove_member(db: Session, *, workspace_id: str, member_uid: str, actor_uid: str) -> None:
    get_company_workspace(db, workspace_id)
    membership = _get_membership(db, workspace_id, member_uid)
    if _would_remove_last_admin(db, membership):
        raise MembershipConflictError("A company must keep at least one active Tenant Admin.")
    removed_role = membership.role
    db.delete(membership)
    db.commit()
    cj_audit.write_audit_event(
        db,
        event_type="membership.removed",
        entity_type="membership",
        entity_id=member_uid,
        actor=actor_uid,
        workspace_id=workspace_id,
        metadata={"role": removed_role},
    )


def forbid_self_change(actor_uid: str, member_uid: str) -> None:
    """Members cannot change their own role or status; another admin must do it."""
    if actor_uid == member_uid:
        raise WorkspaceForbiddenError("You cannot change your own membership. Ask another Tenant Admin.")
