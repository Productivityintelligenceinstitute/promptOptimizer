"""Per-request tenant resolution.

The active workspace comes from the ``X-Workspace-Id`` header, but it is only
honoured after verifying an active membership for the authenticated user. The
client never chooses the data partition directly: ``TenantContext.owner`` is read
from the workspace row. Without the header the user acts in their personal
workspace, which keeps pre-tenancy clients working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.plan_entitlements import ContextJobsAccessError
from context_jobs.tenancy.keys import personal_workspace_id
from context_jobs.tenancy.plans import (
    ACCESS_ACTIVE,
    ACCESS_MESSAGES,
    KIND_COMPANY,
    STATUS_ACTIVE,
    company_access_state,
    is_company,
)
from context_jobs.tenancy.roles import Capability, Role, has_capability, parse_role
from context_jobs.workspace import ensure_personal_workspace
from schemas.context_jobs_model import ContextJobModel, JobRunModel, WorkspaceMemberModel, WorkspaceModel
from schemas.user_model import UserModel

WORKSPACE_HEADER = "X-Workspace-Id"

JOB_STATUS_DRAFT = "draft"
APPROVED_DECISIONS = frozenset({"approve", "approved", "accept", "accepted"})


class WorkspaceForbiddenError(ContextJobsAccessError):
    """Authenticated member lacks the capability (HTTP 403)."""


class WorkspaceNotFoundError(ContextJobsNotFoundError):
    """Workspace missing or caller is not a member (HTTP 404, existence not disclosed)."""


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    firebase_uid: str
    email: str
    is_platform_admin: bool
    workspace_id: str
    workspace_name: str
    workspace_kind: str
    # Data partition key for owner-scoped rows.
    owner: str
    role: Role

    @property
    def is_company(self) -> bool:
        return self.workspace_kind == KIND_COMPANY

    def can(self, capability: Capability) -> bool:
        return has_capability(self.role, capability)

    def require(self, capability: Capability) -> None:
        if not self.can(capability):
            raise WorkspaceForbiddenError(
                "Your role in this workspace does not allow this action."
            )

    def can_edit_job(self, job: ContextJobModel) -> bool:
        """Managers/admins edit any job; analysts edit only their own drafts."""
        if self.can(Capability.JOBS_EDIT_ANY):
            return True
        return (
            self.can(Capability.JOBS_CREATE)
            and job.created_by == self.firebase_uid
            and (job.status or JOB_STATUS_DRAFT).lower() == JOB_STATUS_DRAFT
        )

    def can_view_run(self, run: JobRunModel) -> bool:
        """Members who run or approve work see every run; viewers see approved outputs only."""
        if self.can(Capability.RUNS_EXECUTE) or self.can(Capability.RUNS_APPROVE):
            return True
        decision = run.human_decision if isinstance(run.human_decision, dict) else {}
        return str(decision.get("decision") or "").strip().lower() in APPROVED_DECISIONS

    def require_job_edit(self, job: ContextJobModel) -> None:
        if not self.can_edit_job(job):
            raise WorkspaceForbiddenError(
                "Only managers can change this job. Analysts can edit their own drafts; "
                "duplicate a published job to propose changes."
            )


def _active_membership(
    db: Session, workspace_id: str, firebase_uid: str
) -> Optional[WorkspaceMemberModel]:
    return (
        db.query(WorkspaceMemberModel)
        .filter(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == firebase_uid,
        )
        .first()
    )


def resolve_tenant_context(
    db: Session,
    user: UserModel,
    requested_workspace_id: Optional[str],
) -> TenantContext:
    """Verify the caller may act in the requested workspace and build its context."""
    firebase_uid = user.firebase_uid or ""
    if not firebase_uid:
        raise ContextJobsAccessError("User account is missing a sign-in identity.")

    requested = (requested_workspace_id or "").strip()
    personal_id = personal_workspace_id(firebase_uid)
    if not requested or requested == personal_id:
        workspace = ensure_personal_workspace(db, firebase_uid)
    else:
        workspace = db.get(WorkspaceModel, requested)
        if workspace is None:
            raise WorkspaceNotFoundError("Workspace not found")

    # A personal workspace is its owner's alone, whatever legacy membership rows say:
    # its partition key is the owner's Firebase UID.
    if not is_company(workspace) and workspace.owner != firebase_uid:
        raise WorkspaceNotFoundError("Workspace not found")

    membership = _active_membership(db, workspace.id, firebase_uid)
    if membership is None:
        raise WorkspaceNotFoundError("Workspace not found")
    if (membership.status or STATUS_ACTIVE) != STATUS_ACTIVE:
        raise WorkspaceForbiddenError("Your access to this workspace has been disabled.")

    if is_company(workspace):
        state = company_access_state(workspace)
        if state != ACCESS_ACTIVE:
            raise WorkspaceForbiddenError(ACCESS_MESSAGES[state])

    role = parse_role(membership.role)
    if role is None:
        raise WorkspaceForbiddenError("Your workspace role is not recognised.")

    return TenantContext(
        user_id=user.id,
        firebase_uid=firebase_uid,
        email=user.email or "",
        is_platform_admin=str(user.role or "").lower() == "admin",
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_kind=workspace.kind or "personal",
        owner=workspace.owner,
        role=role,
    )
