"""Platform console: company tenants (accounts, members, roles, invitations).

Unlike the legacy admin routes, the caller is identified from the verified
Firebase token, never from a query parameter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from context_jobs.errors import raise_context_jobs_http
from context_jobs.tenancy import companies, invitations, members
from context_jobs.tenancy.roles import ROLE_LABELS, Role
from context_jobs.tenancy.schemas import CompanyCreate, CompanyUpdate, InvitationCreate, MemberUpdate
from database import database
from dependencies.admin import require_platform_admin
from schemas.user_model import UserModel

tenants_admin_router = APIRouter(prefix="/admin/tenants", tags=["Admin - Tenants"])


@tenants_admin_router.get("/roles")
async def list_roles(_admin: UserModel = Depends(require_platform_admin)):
    """Role reference for the console (Gerald's PDF §2, Phase 1 roles)."""
    return [{"value": role.value, "label": ROLE_LABELS[role]} for role in Role]


@tenants_admin_router.get("")
async def list_companies(
    q: str | None = Query(None, description="Search by name or slug"),
    _admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    return companies.list_companies(db, query=q)


@tenants_admin_router.post("", status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    """Create a company; with ``adminEmail`` the first Tenant Admin invite link is returned."""
    try:
        return companies.create_company(
            db,
            name=payload.name,
            actor_uid=admin.firebase_uid,
            package_name=payload.plan,
            access_expires_at=payload.access_expires_at,
            notes=payload.notes,
            admin_email=payload.admin_email,
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@tenants_admin_router.get("/{workspace_id}")
async def get_company(
    workspace_id: str,
    _admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    try:
        return companies.get_company_detail(db, workspace_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@tenants_admin_router.patch("/{workspace_id}")
async def update_company(
    workspace_id: str,
    payload: CompanyUpdate,
    admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    """Rename, suspend/reactivate (``status``), change plan or access expiry."""
    fields = payload.model_fields_set
    changes = {
        key: getattr(payload, attr)
        for key, attr in (
            ("name", "name"),
            ("status", "status"),
            ("package_name", "plan"),
            ("access_expires_at", "access_expires_at"),
            ("notes", "notes"),
        )
        if attr in fields
    }
    try:
        return companies.update_company(db, workspace_id, actor_uid=admin.firebase_uid, **changes)
    except Exception as exc:
        raise_context_jobs_http(exc)


@tenants_admin_router.post("/{workspace_id}/invitations", status_code=status.HTTP_201_CREATED)
async def invite_member(
    workspace_id: str,
    payload: InvitationCreate,
    admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    try:
        return invitations.create_invitation(
            db,
            workspace_id=workspace_id,
            email=payload.email,
            role=payload.role,
            invited_by=admin.firebase_uid,
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@tenants_admin_router.delete("/{workspace_id}/invitations/{invitation_id}")
async def revoke_invitation(
    workspace_id: str,
    invitation_id: str,
    admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    try:
        return invitations.revoke_invitation(
            db, workspace_id=workspace_id, invitation_id=invitation_id, actor_uid=admin.firebase_uid
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@tenants_admin_router.patch("/{workspace_id}/members/{member_user_id}")
async def update_member(
    workspace_id: str,
    member_user_id: str,
    payload: MemberUpdate,
    admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    """Assign a role or disable/enable a member (support / account management)."""
    try:
        return members.update_member(
            db,
            workspace_id=workspace_id,
            member_uid=member_user_id,
            actor_uid=admin.firebase_uid,
            role=payload.role,
            status=payload.status,
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@tenants_admin_router.delete(
    "/{workspace_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    workspace_id: str,
    member_user_id: str,
    admin: UserModel = Depends(require_platform_admin),
    db: Session = Depends(database.get_db),
):
    try:
        members.remove_member(
            db, workspace_id=workspace_id, member_uid=member_user_id, actor_uid=admin.firebase_uid
        )
    except Exception as exc:
        raise_context_jobs_http(exc)
