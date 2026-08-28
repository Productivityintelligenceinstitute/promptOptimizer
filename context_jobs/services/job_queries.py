from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import or_

from context_jobs.plan_entitlements import ensure_context_jobs_access
from context_jobs.services._constants import INTERNAL_WORKFLOW_TYPES
from schemas.context_jobs_model import ContextJobModel

SYSTEM_TEMPLATE_OWNER = "__system__"


def list_jobs(db: Session, owner: str) -> List[ContextJobModel]:
    ensure_context_jobs_access(db, owner)
    return (
        db.query(ContextJobModel)
        .filter(
            ContextJobModel.owner == owner,
            or_(
                ContextJobModel.workflow_type.is_(None),
                ContextJobModel.workflow_type.notin_(tuple(INTERNAL_WORKFLOW_TYPES)),
            ),
        )
        .order_by(ContextJobModel.created_at.desc())
        .all()
    )


def get_job(db: Session, job_id: UUID, owner: str) -> Optional[ContextJobModel]:
    ensure_context_jobs_access(db, owner)
    return (
        db.query(ContextJobModel)
        .filter(ContextJobModel.id == job_id, ContextJobModel.owner == owner)
        .first()
    )


def list_template_jobs(db: Session, owner: str) -> List[ContextJobModel]:
    ensure_context_jobs_access(db, owner)
    return (
        db.query(ContextJobModel)
        .filter(ContextJobModel.owner == SYSTEM_TEMPLATE_OWNER)
        .order_by(ContextJobModel.created_at.desc())
        .all()
    )


def get_template_job(db: Session, template_id: UUID) -> Optional[ContextJobModel]:
    return (
        db.query(ContextJobModel)
        .filter(
            ContextJobModel.id == template_id,
            ContextJobModel.owner == SYSTEM_TEMPLATE_OWNER,
        )
        .first()
    )
