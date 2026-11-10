"""Expiring, single-use workspace invitations.

The raw token is returned once at creation (as part of the invite link) and only
its SHA-256 is stored. Acceptance requires the signed-in account's email to match
the invited address, so a forwarded link cannot be used by someone else.
Delivery is out of band for now (the admin copies the link); email sending can be
added later without changing this module.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from context_jobs.tenancy.context import WorkspaceForbiddenError, WorkspaceNotFoundError
from context_jobs.tenancy.members import MembershipConflictError, get_company_workspace
from context_jobs.tenancy.plans import STATUS_ACTIVE, utcnow
from context_jobs.tenancy.roles import ROLE_LABELS, parse_role
from core.config import FRONTEND_URL
from schemas.context_jobs_model import WorkspaceInvitationModel, WorkspaceMemberModel, WorkspaceModel
from schemas.user_model import UserModel

INVITATION_TTL = timedelta(days=7)
INVITE_PATH = "/invite"

STATE_PENDING = "pending"
STATE_ACCEPTED = "accepted"
STATE_REVOKED = "revoked"
STATE_EXPIRED = "expired"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvitationError(ValueError):
    """Invitation cannot be used (HTTP 400)."""


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not _EMAIL_RE.match(value):
        raise MembershipConflictError("Enter a valid email address.")
    return value


def invite_url(raw_token: str) -> str:
    return f"{FRONTEND_URL.rstrip('/')}{INVITE_PATH}/{raw_token}"


def invitation_state(row: WorkspaceInvitationModel) -> str:
    if row.revoked_at is not None:
        return STATE_REVOKED
    if row.accepted_at is not None:
        return STATE_ACCEPTED
    expires = row.expires_at
    if expires is not None and expires <= utcnow():
        return STATE_EXPIRED
    return STATE_PENDING


def serialize_invitation(row: WorkspaceInvitationModel) -> dict[str, Any]:
    role = parse_role(row.role)
    return {
        "id": str(row.id),
        "workspaceId": row.workspace_id,
        "email": row.email,
        "role": role.value if role else row.role,
        "roleLabel": ROLE_LABELS.get(role) if role else row.role,
        "state": invitation_state(row),
        "invitedBy": row.invited_by,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "expiresAt": row.expires_at.isoformat() if row.expires_at else None,
        "acceptedAt": row.accepted_at.isoformat() if row.accepted_at else None,
    }


def _member_with_email(db: Session, workspace_id: str, email: str) -> Optional[WorkspaceMemberModel]:
    return (
        db.query(WorkspaceMemberModel)
        .join(UserModel, UserModel.firebase_uid == WorkspaceMemberModel.user_id)
        .filter(
            WorkspaceMemberModel.workspace_id == workspace_id,
            func.lower(UserModel.email) == email,
        )
        .first()
    )


def create_invitation(
    db: Session,
    *,
    workspace_id: str,
    email: str,
    role: str,
    invited_by: str,
) -> dict[str, Any]:
    """Create an invitation; an earlier pending invite to the same email is revoked."""
    get_company_workspace(db, workspace_id)
    normalized = normalize_email(email)
    parsed_role = parse_role(role)
    if parsed_role is None:
        raise MembershipConflictError(f"Unknown role {role!r}.")
    existing_member = _member_with_email(db, workspace_id, normalized)
    if existing_member is not None and (existing_member.status or STATUS_ACTIVE) == STATUS_ACTIVE:
        raise MembershipConflictError(f"{normalized} is already a member of this workspace.")

    now = utcnow()
    for previous in (
        db.query(WorkspaceInvitationModel)
        .filter(
            WorkspaceInvitationModel.workspace_id == workspace_id,
            WorkspaceInvitationModel.email == normalized,
            WorkspaceInvitationModel.accepted_at.is_(None),
            WorkspaceInvitationModel.revoked_at.is_(None),
        )
        .all()
    ):
        previous.revoked_at = now
        db.add(previous)

    raw_token = secrets.token_urlsafe(32)
    row = WorkspaceInvitationModel(
        workspace_id=workspace_id,
        email=normalized,
        role=parsed_role.value,
        token_hash=hash_token(raw_token),
        invited_by=invited_by,
        expires_at=now + INVITATION_TTL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    cj_audit.write_audit_event(
        db,
        event_type="invitation.created",
        entity_type="invitation",
        entity_id=str(row.id),
        actor=invited_by,
        workspace_id=workspace_id,
        metadata={"email": normalized, "role": parsed_role.value},
    )
    return {**serialize_invitation(row), "inviteUrl": invite_url(raw_token), "token": raw_token}


def list_invitations(db: Session, workspace_id: str, *, include_closed: bool = False) -> list[dict[str, Any]]:
    rows = (
        db.query(WorkspaceInvitationModel)
        .filter(WorkspaceInvitationModel.workspace_id == workspace_id)
        .order_by(WorkspaceInvitationModel.created_at.desc())
        .all()
    )
    items = [serialize_invitation(row) for row in rows]
    if include_closed:
        return items
    return [item for item in items if item["state"] in (STATE_PENDING, STATE_EXPIRED)]


def revoke_invitation(db: Session, *, workspace_id: str, invitation_id: str, actor_uid: str) -> dict[str, Any]:
    row = (
        db.query(WorkspaceInvitationModel)
        .filter(
            WorkspaceInvitationModel.workspace_id == workspace_id,
            WorkspaceInvitationModel.id == invitation_id,
        )
        .first()
    )
    if row is None:
        raise WorkspaceNotFoundError("Invitation not found")
    if invitation_state(row) == STATE_ACCEPTED:
        raise MembershipConflictError("This invitation was already accepted. Remove the member instead.")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        cj_audit.write_audit_event(
            db,
            event_type="invitation.revoked",
            entity_type="invitation",
            entity_id=str(row.id),
            actor=actor_uid,
            workspace_id=workspace_id,
            metadata={"email": row.email},
        )
    return serialize_invitation(row)


def _find_by_token(db: Session, raw_token: str) -> WorkspaceInvitationModel:
    row = (
        db.query(WorkspaceInvitationModel)
        .filter(WorkspaceInvitationModel.token_hash == hash_token(raw_token or ""))
        .first()
    )
    if row is None:
        raise WorkspaceNotFoundError("Invitation not found")
    return row


def preview_invitation(db: Session, raw_token: str, user: UserModel) -> dict[str, Any]:
    """What the invite page shows before the user accepts."""
    row = _find_by_token(db, raw_token)
    workspace = db.get(WorkspaceModel, row.workspace_id)
    role = parse_role(row.role)
    return {
        "workspaceName": workspace.name if workspace else None,
        "role": role.value if role else row.role,
        "roleLabel": ROLE_LABELS.get(role) if role else row.role,
        "email": row.email,
        "state": invitation_state(row),
        "expiresAt": row.expires_at.isoformat() if row.expires_at else None,
        "emailMatches": (user.email or "").strip().lower() == row.email,
    }


def accept_invitation(db: Session, raw_token: str, user: UserModel) -> dict[str, Any]:
    row = _find_by_token(db, raw_token)
    state = invitation_state(row)
    if state == STATE_EXPIRED:
        raise InvitationError("This invitation has expired. Ask your Tenant Admin for a new one.")
    if state == STATE_REVOKED:
        raise InvitationError("This invitation was cancelled. Ask your Tenant Admin for a new one.")
    if state == STATE_ACCEPTED:
        raise InvitationError("This invitation has already been used.")
    if (user.email or "").strip().lower() != row.email:
        raise WorkspaceForbiddenError(
            f"This invitation was sent to {row.email}. Sign in with that email to accept it."
        )

    workspace = get_company_workspace(db, row.workspace_id)
    firebase_uid = user.firebase_uid or ""
    membership = (
        db.query(WorkspaceMemberModel)
        .filter(
            WorkspaceMemberModel.workspace_id == workspace.id,
            WorkspaceMemberModel.user_id == firebase_uid,
        )
        .first()
    )
    if membership is None:
        membership = WorkspaceMemberModel(workspace_id=workspace.id, user_id=firebase_uid)
    membership.role = row.role
    membership.status = STATUS_ACTIVE
    membership.invited_by = row.invited_by
    db.add(membership)

    row.accepted_at = utcnow()
    row.accepted_by = firebase_uid
    db.add(row)
    db.commit()

    cj_audit.write_audit_event(
        db,
        event_type="invitation.accepted",
        entity_type="invitation",
        entity_id=str(row.id),
        actor=firebase_uid,
        workspace_id=workspace.id,
        metadata={"email": row.email, "role": row.role},
    )
    return {"workspaceId": workspace.id, "workspaceName": workspace.name, "role": row.role}
