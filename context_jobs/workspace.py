"""Workspace model and role-based access control."""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from schemas.context_jobs_model import ContextJobModel, WorkspaceMemberModel, WorkspaceModel

ROLE_HIERARCHY = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}

DEFAULT_WORKSPACE_SUFFIX = "_default"


def default_workspace_id(user_id: str) -> str:
    return f"ws_{user_id}{DEFAULT_WORKSPACE_SUFFIX}"


def ensure_default_workspace(db: Session, user_id: str) -> WorkspaceModel:
    ws_id = default_workspace_id(user_id)
    # Check if workspace already exists
    ws = db.query(WorkspaceModel).filter(WorkspaceModel.id == ws_id).first()
    if ws:
        return ws

    # Create and commit workspace first to ensure it exists in the database
    ws = WorkspaceModel(id=ws_id, name=f"{user_id}'s workspace", owner=user_id)
    db.add(ws)
    db.commit()
    db.refresh(ws)

    # Now create the member - workspace is guaranteed to exist
    try:
        member = WorkspaceMemberModel(
            workspace_id=ws_id,
            user_id=user_id,
            role="owner",
        )
        db.add(member)
        db.commit()
    except Exception:
        db.rollback()
        # If member creation fails, workspace exists but member doesn't - this is ok for idempotency
        # Just return the workspace
        pass

    return ws


def get_member_role(db: Session, workspace_id: str, user_id: str) -> Optional[str]:
    row = (
        db.query(WorkspaceMemberModel)
        .filter(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == user_id,
        )
        .first()
    )
    return row.role if row else None


def require_role(db: Session, workspace_id: str, user_id: str, min_role: str) -> str:
    role = get_member_role(db, workspace_id, user_id)
    if not role:
        # Fallback: user owns jobs directly without workspace membership
        if workspace_id == default_workspace_id(user_id) or workspace_id == "default":
            # Auto-create default workspace if it doesn't exist
            ensure_default_workspace(db, user_id)
            return "owner"
        raise ValueError("Access denied: not a workspace member")
    if ROLE_HIERARCHY.get(role, 0) < ROLE_HIERARCHY.get(min_role, 99):
        raise ValueError(f"Access denied: requires {min_role} role")
    return role


def can_read(db: Session, workspace_id: str, user_id: str) -> bool:
    try:
        require_role(db, workspace_id, user_id, "viewer")
        return True
    except ValueError:
        return False


def can_write(db: Session, workspace_id: str, user_id: str) -> bool:
    try:
        require_role(db, workspace_id, user_id, "editor")
        return True
    except ValueError:
        return False


def can_admin(db: Session, workspace_id: str, user_id: str) -> bool:
    try:
        require_role(db, workspace_id, user_id, "admin")
        return True
    except ValueError:
        return False


def add_workspace_member(
    db: Session,
    workspace_id: str,
    actor: str,
    user_id: str,
    role: str,
) -> WorkspaceMemberModel:
    require_role(db, workspace_id, actor, "admin")
    if role not in ROLE_HIERARCHY:
        raise ValueError(f"Invalid role {role!r}")

    # Verify workspace exists before adding member
    ws = db.query(WorkspaceModel).filter(WorkspaceModel.id == workspace_id).first()
    if not ws:
        raise ValueError(f"Workspace {workspace_id!r} does not exist")

    existing = (
        db.query(WorkspaceMemberModel)
        .filter(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == user_id,
        )
        .first()
    )
    if existing:
        existing.role = role
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    row = WorkspaceMemberModel(workspace_id=workspace_id, user_id=user_id, role=role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_allowlist(db: Session, workspace_id: str) -> dict:
    ws = db.query(WorkspaceModel).filter(WorkspaceModel.id == workspace_id).first()
    if not ws:
        return {"tools": [], "sources": []}
    return {
        "tools": list(ws.tool_allowlist or []),
        "sources": list(ws.source_allowlist or []),
    }


def update_allowlist(
    db: Session,
    workspace_id: str,
    actor: str,
    tools: Optional[list] = None,
    sources: Optional[list] = None,
) -> dict:
    require_role(db, workspace_id, actor, "admin")
    ws = db.query(WorkspaceModel).filter(WorkspaceModel.id == workspace_id).first()
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
