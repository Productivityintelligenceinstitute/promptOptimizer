"""Evaluate job chain_config after a successful parent run."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
from context_jobs.services.job_queries import get_template_job
from context_jobs.services.jobs import duplicate_job
from context_jobs.services.runs import create_run
from schemas.context_jobs_model import ContextJobModel, JobRunModel, RunChainModel

logger = logging.getLogger(__name__)


def _chain_config(job: ContextJobModel) -> dict[str, Any]:
    config = job.chain_config if isinstance(job.chain_config, dict) else {}
    return dict(config)


def _primary_result_content(rop: dict[str, Any] | None) -> str:
    primary = (rop or {}).get("primaryResult") or {}
    if not isinstance(primary, dict):
        return ""
    return str(primary.get("content") or "")


def _build_child_user_request(chain_config: dict[str, Any], rop: dict[str, Any] | None) -> str:
    content = _primary_result_content(rop)
    input_mapping = chain_config.get("inputMapping")
    if not isinstance(input_mapping, dict):
        return content
    template = input_mapping.get("userRequest")
    if template is None:
        return content
    return str(template).replace("{primaryResult}", content)


def _find_chain_root_run_id(db: Session, run_id: UUID) -> UUID:
    current = run_id
    while True:
        row = (
            db.query(RunChainModel)
            .filter(RunChainModel.child_run_id == current)
            .first()
        )
        if not row:
            return current
        current = row.parent_run_id


def _max_chain_depth(db: Session, root_run_id: UUID) -> int:
    def _depth(run_id: UUID, visited: set[UUID]) -> int:
        if run_id in visited:
            return 0
        visited.add(run_id)
        rows = (
            db.query(RunChainModel)
            .filter(RunChainModel.parent_run_id == run_id)
            .all()
        )
        if not rows:
            return 0
        child_depths = [
            1 + _depth(row.child_run_id, visited)
            for row in rows
            if row.child_run_id is not None
        ]
        return max(child_depths) if child_depths else 0

    return _depth(root_run_id, set())


def evaluate_chain(run_id: UUID, rop: dict[str, Any] | None, db: Session) -> None:
    """Enqueue a chained child run when the parent job's chain_config allows it."""
    run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
    if not run:
        return
    job = db.query(ContextJobModel).filter(ContextJobModel.id == run.job_id).first()
    if not job:
        return

    chain_config = _chain_config(job)
    if not chain_config or not chain_config.get("triggerOnSuccess"):
        return

    child_job_id_raw = chain_config.get("childJobId")
    if not child_job_id_raw:
        logger.warning("chain_config missing childJobId for job %s; skipping chain.", job.id)
        return

    try:
        child_template_id = UUID(str(child_job_id_raw))
    except (TypeError, ValueError):
        logger.warning("Invalid childJobId on job %s; skipping chain.", job.id)
        return

    max_depth = 3
    try:
        max_depth = int(chain_config.get("maxDepth") or 3)
    except (TypeError, ValueError):
        max_depth = 3
    max_depth = max(1, max_depth)

    root_run_id = _find_chain_root_run_id(db, run_id)
    depth = _max_chain_depth(db, root_run_id)
    if depth >= max_depth:
        logger.warning(
            "Chain depth limit reached for root run %s (depth=%s, maxDepth=%s); skipping chain.",
            root_run_id,
            depth,
            max_depth,
        )
        return

    child_template = get_template_job(db, child_template_id)
    if not child_template:
        logger.warning(
            "Child template job %s not found for parent run %s; skipping chain.",
            child_template_id,
            run_id,
        )
        return

    owner = job.owner or "current_user"
    child_job = duplicate_job(db, owner, child_template)
    child_job.status = "published"
    db.add(child_job)
    db.commit()
    db.refresh(child_job)

    user_request = _build_child_user_request(chain_config, rop)
    input_mapping: dict[str, Any] = {"userRequest": user_request}
    raw_mapping = chain_config.get("inputMapping")
    if isinstance(raw_mapping, dict):
        input_mapping.update(raw_mapping)
        input_mapping["userRequest"] = user_request

    try:
        child_run = create_run(
            db,
            owner,
            child_job.id,
            cj_schemas.JobRunCreate(user_request=user_request),
        )
    except ValueError as exc:
        logger.error(
            "Failed to enqueue chained run for parent %s -> child job %s: %s",
            run_id,
            child_job.id,
            exc,
        )
        return

    child_run.parent_run_id = run_id
    db.add(child_run)

    chain_row = RunChainModel(
        parent_run_id=run_id,
        child_job_id=child_job.id,
        child_run_id=child_run.id,
        status="pending",
        input_mapping=input_mapping,
    )
    db.add(chain_row)
    db.commit()

    logger.info(
        "Created run chain parent_run=%s child_job=%s child_run=%s depth=%s",
        run_id,
        child_job.id,
        child_run.id,
        depth + 1,
    )
