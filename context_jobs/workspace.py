"""Workspace lookup by data owner key, personal workspace provisioning, and allowlists.

Every owner-scoped row stores the workspace's partition key in ``owner``: a Firebase
UID for a personal workspace, the ``org_<hex>`` workspace id for a company. The
helpers here map an owner key back to its workspace. Role checks live in
``context_jobs.tenancy`` (capability matrix), not here.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from context_jobs.tenancy.keys import is_company_owner_key, personal_workspace_id
from context_jobs.tenancy.plans import KIND_PERSONAL, STATUS_ACTIVE
from context_jobs.tenancy.roles import Role
from schemas.context_jobs_model import ContextJobModel, WorkspaceMemberModel, WorkspaceModel

PERSONAL_WORKSPACE_NAME = "Personal workspace"


def default_workspace_id(owner: str) -> str:
    """Workspace id for a data owner key."""
    if is_company_owner_key(owner):
        return owner
    return personal_workspace_id(owner)


def ensure_personal_workspace(db: Session, firebase_uid: str) -> WorkspaceModel:
    """Get or create the user's personal workspace and their Tenant Admin membership."""
    ws_id = personal_workspace_id(firebase_uid)
    ws = db.get(WorkspaceModel, ws_id)
    if ws is None:
        try:
            ws = WorkspaceModel(
                id=ws_id,
                name=PERSONAL_WORKSPACE_NAME,
                owner=firebase_uid,
                kind=KIND_PERSONAL,
                status=STATUS_ACTIVE,
            )
            db.add(ws)
            db.commit()
        except IntegrityError:
            # Concurrent first request created it.
            db.rollback()
        ws = db.get(WorkspaceModel, ws_id)

    has_member = (
        db.query(WorkspaceMemberModel.id)
        .filter(
            WorkspaceMemberModel.workspace_id == ws_id,
            WorkspaceMemberModel.user_id == firebase_uid,
        )
        .first()
    )
    if not has_member:
        try:
            db.add(
                WorkspaceMemberModel(
                    workspace_id=ws_id,
                    user_id=firebase_uid,
                    role=Role.TENANT_ADMIN.value,
                    status=STATUS_ACTIVE,
                )
            )
            db.commit()
        except IntegrityError:
            db.rollback()
    return ws


def ensure_default_workspace(db: Session, owner: str) -> WorkspaceModel:
    """Workspace that owns rows keyed by ``owner`` (provisioned for personal owners)."""
    if is_company_owner_key(owner):
        ws = db.get(WorkspaceModel, owner)
        if ws is None:
            raise ValueError("Workspace not found")
        return ws
    return ensure_personal_workspace(db, owner)


def get_allowlist(db: Session, workspace_id: str) -> dict:
    ws = db.get(WorkspaceModel, workspace_id)
    if not ws:
        return {"tools": [], "sources": []}
    return {
        "tools": list(ws.tool_allowlist or []),
        "sources": list(ws.source_allowlist or []),
    }


def update_allowlist(
    db: Session,
    workspace_id: str,
    tools: Optional[list] = None,
    sources: Optional[list] = None,
) -> dict:
    """Caller must already hold Capability.SETTINGS_MANAGE on ``workspace_id``."""
    ws = db.get(WorkspaceModel, workspace_id)
    if not ws:
        raise ValueError("Workspace not found")
    if tools is not None:
        ws.tool_allowlist = tools
    if sources is not None:
        ws.source_allowlist = sources
    db.add(ws)
    db.commit()
    return get_allowlist(db, workspace_id)


def check_tool_allowlist(db: Session, job: ContextJobModel, tool_id: str) -> None:
    # Job-level toolPermissions override workspace allowlist when explicitly enabled
    for perm in job.tool_permissions or []:
        if isinstance(perm, dict):
            pid = perm.get("toolId") or perm.get("tool_id")
            if pid == tool_id and perm.get("enabled"):
                return

    ws_id = getattr(job, "workspace_id", None) or default_workspace_id(job.owner or "")
    allowlist = get_allowlist(db, ws_id).get("tools") or []
    if allowlist and tool_id not in allowlist:
        raise ValueError(f"Tool {tool_id!r} is not on the workspace allowlist")
