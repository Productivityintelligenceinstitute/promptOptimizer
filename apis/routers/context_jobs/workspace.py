"""Workspaces, members, invitations and audit for the active tenant.

Routes with ``{workspace_id}`` act on the active workspace only (the one resolved
from ``X-Workspace-Id``); a mismatching id returns 404 so members cannot address
other workspaces by guessing ids.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from context_jobs.auth import get_current_user, get_tenant_context, tenant_with
from context_jobs.errors import raise_context_jobs_http
from context_jobs.tenancy import invitations as tenancy_invitations
from context_jobs.tenancy import members as tenancy_members
from context_jobs.tenancy.context import TenantContext, WorkspaceNotFoundError
from context_jobs.tenancy.features import procurement_templates_enabled
from context_jobs.tenancy.roles import ROLE_LABELS, Capability, capabilities_for
from context_jobs.tenancy.schemas import AllowlistUpdate, InvitationCreate, MemberUpdate
from context_jobs.workspace import ensure_personal_workspace, get_allowlist, update_allowlist
import context_jobs.audit as cj_audit
from database import database
from schemas.user_model import UserModel

router = APIRouter(tags=["Context Jobs - Workspaces"])


def _active(tenant: TenantContext, workspace_id: str) -> None:
    if workspace_id != tenant.workspace_id:
        raise WorkspaceNotFoundError("Workspace not found")


@router.get("/workspaces")
async def list_my_workspaces(
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Workspaces the signed-in user can switch to (personal first)."""
    return tenancy_members.list_user_workspaces(db, user)


@router.get("/workspaces/current")
async def get_current_workspace(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(database.get_db),
):
    """The active workspace, the caller's role in it and what that role allows."""
    return {
        "id": tenant.workspace_id,
        "name": tenant.workspace_name,
        "kind": tenant.workspace_kind,
        "role": tenant.role.value,
        "roleLabel": ROLE_LABELS[tenant.role],
        "capabilities": capabilities_for(tenant.role),
        "isPlatformAdmin": tenant.is_platform_admin,
        "procurementTemplates": procurement_templates_enabled(db, tenant),
    }


@router.get("/workspaces/default")
async def get_default_workspace(
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    ws = ensure_personal_workspace(db, user.firebase_uid)
    return {"id": ws.id, "name": ws.name, "owner": ws.owner}


@router.get("/workspaces/{workspace_id}/members")
async def list_workspace_members(
    workspace_id: str,
    tenant: TenantContext = Depends(tenant_with(Capability.MEMBERS_MANAGE)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
        tenancy_members.get_company_workspace(db, workspace_id)
        return tenancy_members.list_members(db, workspace_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.patch("/workspaces/{workspace_id}/members/{member_user_id}")
async def update_workspace_member(
    workspace_id: str,
    member_user_id: str,
    payload: MemberUpdate,
    tenant: TenantContext = Depends(tenant_with(Capability.MEMBERS_MANAGE)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
        tenancy_members.forbid_self_change(tenant.firebase_uid, member_user_id)
        return tenancy_members.update_member(
            db,
            workspace_id=workspace_id,
            member_uid=member_user_id,
            actor_uid=tenant.firebase_uid,
            role=payload.role,
            status=payload.status,
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.delete(
    "/workspaces/{workspace_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_workspace_member(
    workspace_id: str,
    member_user_id: str,
    tenant: TenantContext = Depends(tenant_with(Capability.MEMBERS_MANAGE)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
        tenancy_members.forbid_self_change(tenant.firebase_uid, member_user_id)
        tenancy_members.remove_member(
            db, workspace_id=workspace_id, member_uid=member_user_id, actor_uid=tenant.firebase_uid
        )
    except Exception as exc:
        raise_context_jobs_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workspaces/{workspace_id}/invitations")
async def list_workspace_invitations(
    workspace_id: str,
    include_closed: bool = Query(False, alias="includeClosed"),
    tenant: TenantContext = Depends(tenant_with(Capability.MEMBERS_MANAGE)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
        tenancy_members.get_company_workspace(db, workspace_id)
        return tenancy_invitations.list_invitations(db, workspace_id, include_closed=include_closed)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/workspaces/{workspace_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_workspace_invitation(
    workspace_id: str,
    payload: InvitationCreate,
    tenant: TenantContext = Depends(tenant_with(Capability.MEMBERS_MANAGE)),
    db: Session = Depends(database.get_db),
):
    """Returns the invite link once. Share it with the invitee; it expires in 7 days."""
    try:
        _active(tenant, workspace_id)
        return tenancy_invitations.create_invitation(
            db,
            workspace_id=workspace_id,
            email=payload.email,
            role=payload.role,
            invited_by=tenant.firebase_uid,
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}")
async def revoke_workspace_invitation(
    workspace_id: str,
    invitation_id: str,
    tenant: TenantContext = Depends(tenant_with(Capability.MEMBERS_MANAGE)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
        return tenancy_invitations.revoke_invitation(
            db, workspace_id=workspace_id, invitation_id=invitation_id, actor_uid=tenant.firebase_uid
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/workspaces/{workspace_id}/audit")
async def list_workspace_audit(
    workspace_id: str,
    entity_type: str | None = Query(default=None, alias="entityType"),
    entity_id: str | None = Query(default=None, alias="entityId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    from_date: datetime | None = Query(default=None, alias="fromDate"),
    to_date: datetime | None = Query(default=None, alias="toDate"),
    limit: int = Query(200, ge=1, le=1000),
    tenant: TenantContext = Depends(tenant_with(Capability.AUDIT_VIEW)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
        rows = cj_audit.list_workspace_audit_events(
            db,
            workspace_id=workspace_id,
            owner=tenant.owner,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            from_ts=from_date,
            to_ts=to_date,
            limit=limit,
        )
    except Exception as exc:
        raise_context_jobs_http(exc)
    actors = {row.actor for row in rows}
    emails = dict(
        db.query(UserModel.firebase_uid, UserModel.email)
        .filter(UserModel.firebase_uid.in_(actors))
        .all()
    ) if actors else {}
    return [
        {
            "id": str(row.id),
            "eventType": row.event_type,
            "entityType": row.entity_type,
            "entityId": row.entity_id,
            "actor": row.actor,
            "actorEmail": emails.get(row.actor),
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "metadata": row.event_metadata or {},
        }
        for row in rows
    ]


@router.get("/workspaces/{workspace_id}/allowlist")
async def get_workspace_allowlist(
    workspace_id: str,
    tenant: TenantContext = Depends(tenant_with(Capability.WORKSPACE_VIEW)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
    except Exception as exc:
        raise_context_jobs_http(exc)
    return get_allowlist(db, workspace_id)


@router.patch("/workspaces/{workspace_id}/allowlist")
async def patch_workspace_allowlist(
    workspace_id: str,
    payload: AllowlistUpdate,
    tenant: TenantContext = Depends(tenant_with(Capability.SETTINGS_MANAGE)),
    db: Session = Depends(database.get_db),
):
    try:
        _active(tenant, workspace_id)
        result = update_allowlist(db, workspace_id, payload.tools, payload.sources)
        cj_audit.write_audit_event(
            db,
            event_type="workspace.allowlist_updated",
            entity_type="workspace",
            entity_id=workspace_id,
            actor=tenant.firebase_uid,
            metadata=result,
        )
        return result
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/invitations/{token}")
async def preview_invitation(
    token: str,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    try:
        return tenancy_invitations.preview_invitation(db, token, user)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Join the inviting company. Works without a personal Context Jobs plan."""
    try:
        return tenancy_invitations.accept_invitation(db, token, user)
    except Exception as exc:
        raise_context_jobs_http(exc)
