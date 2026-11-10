"""Workspace roles and the capability matrix (single source of truth for RBAC).

Routes ask "may this member do X" via ``Capability``; they never compare role
names directly. Anything not granted here is denied.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class Role(str, Enum):
    TENANT_ADMIN = "tenant_admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Capability(str, Enum):
    # Read access to the workspace's jobs, runs, outputs and knowledge.
    WORKSPACE_VIEW = "workspace.view"
    # Members, invitations, roles.
    MEMBERS_MANAGE = "members.manage"
    # Workspace settings: name, tool/source allowlists, provider keys.
    SETTINGS_MANAGE = "settings.manage"
    JOBS_CREATE = "jobs.create"
    # Edit/rollback any job. Analysts may only edit their own drafts (see policy).
    JOBS_EDIT_ANY = "jobs.edit_any"
    JOBS_PUBLISH = "jobs.publish"
    RUNS_EXECUTE = "runs.execute"
    # Human-in-the-loop decisions: output decisions, tool approvals, memory writes.
    RUNS_APPROVE = "runs.approve"
    # Vector/CLM connections and workspace-level knowledge sources.
    KNOWLEDGE_MANAGE = "knowledge.manage"
    # Upload documents into jobs, register contracts, manage alerts.
    KNOWLEDGE_CONTRIBUTE = "knowledge.contribute"
    AUDIT_VIEW = "audit.view"


_ALL = frozenset(Capability)

ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.TENANT_ADMIN: _ALL,
    Role.MANAGER: frozenset(
        {
            Capability.WORKSPACE_VIEW,
            Capability.JOBS_CREATE,
            Capability.JOBS_EDIT_ANY,
            Capability.JOBS_PUBLISH,
            Capability.RUNS_EXECUTE,
            Capability.RUNS_APPROVE,
            Capability.KNOWLEDGE_MANAGE,
            Capability.KNOWLEDGE_CONTRIBUTE,
            Capability.AUDIT_VIEW,
        }
    ),
    Role.ANALYST: frozenset(
        {
            Capability.WORKSPACE_VIEW,
            Capability.JOBS_CREATE,
            Capability.RUNS_EXECUTE,
            Capability.KNOWLEDGE_CONTRIBUTE,
        }
    ),
    Role.VIEWER: frozenset({Capability.WORKSPACE_VIEW}),
}

ROLE_LABELS: dict[Role, str] = {
    Role.TENANT_ADMIN: "Tenant Admin",
    Role.MANAGER: "Manager",
    Role.ANALYST: "Analyst",
    Role.VIEWER: "Viewer",
}

# Values written by the pre-tenancy workspace module.
_LEGACY_ROLES: dict[str, Role] = {
    "owner": Role.TENANT_ADMIN,
    "admin": Role.TENANT_ADMIN,
    "editor": Role.ANALYST,
}


def parse_role(value: Optional[str]) -> Optional[Role]:
    """Return the Role for a stored or submitted value, or None if unknown."""
    key = (value or "").strip().lower()
    if not key:
        return None
    try:
        return Role(key)
    except ValueError:
        return _LEGACY_ROLES.get(key)


def has_capability(role: Optional[Role], capability: Capability) -> bool:
    if role is None:
        return False
    return capability in ROLE_CAPABILITIES.get(role, frozenset())


def capabilities_for(role: Optional[Role]) -> list[str]:
    if role is None:
        return []
    return sorted(c.value for c in ROLE_CAPABILITIES.get(role, frozenset()))
