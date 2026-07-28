from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
import context_jobs.audit as cj_audit
from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.hitl import confirm_memory_changes, resolve_tool_approval
from context_jobs.orchestrator import enqueue_run, get_run_queue_status
from context_jobs.assembly.prompt_safety import normalize_untrusted_text
from context_jobs.plan_entitlements import (
    assert_can_create_run,
    ensure_context_jobs_access,
    record_run_created,
)
from context_jobs.provider_key_services import resolve_llm_api_key
from context_jobs.run_workflows import (
    apply_decision_follow_through,
    create_replay_run,
    export_run_markdown,
    list_tool_executions,
)
from context_jobs.services.job_queries import get_job
from context_jobs.workspace import default_workspace_id
from schemas.context_jobs_model import ContextJobModel, JobRunModel, RunChainModel


def list_runs(db: Session, owner: str) -> List[JobRunModel]:
    ensure_context_jobs_access(db, owner)
    return (
        db.query(JobRunModel)
        .join(ContextJobModel, JobRunModel.job_id == ContextJobModel.id)
        .filter(ContextJobModel.owner == owner)
        .order_by(JobRunModel.started_at.desc())
        .all()
    )


def get_run(db: Session, run_id: UUID, owner: str) -> Optional[JobRunModel]:
    ensure_context_jobs_access(db, owner)
    run = db.query(JobRunModel).filter(JobRunModel.id == run_id).first()
    if not run:
        return None
    job = get_job(db, run.job_id, owner)
    if not job:
        return None
    return run


def create_run(
    db: Session,
    owner: str,
    job_id: UUID,
    data: cj_schemas.JobRunCreate,
) -> JobRunModel:
    package_name = ensure_context_jobs_access(db, owner)
    assert_can_create_run(db, owner, package_name)
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    if (job.status or "draft").lower() != "published":
        raise ValueError("Job must be published before running. Publish the job first.")
    resolve_llm_api_key(
        db, owner, job.llm_key_id, job.execution_provider, package_name=package_name
    )
    run = JobRunModel(
        job_id=job_id,
        user_request=normalize_untrusted_text(data.user_request or ""),
        job_version=job.version,
        workspace_id=getattr(job, "workspace_id", None) or default_workspace_id(owner),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    _attach_lifecycle_handoff(db, owner, job_id, run.id, getattr(data, "parent_run_id", None))
    queued = enqueue_run(run.id)
    if not queued:
        run.state = "failed"
        run.outcome = "error"
        run.run_output_package = {
            "status": "failed",
            "primaryResult": {
                "resultType": "text_output",
                "title": "Run queue is full",
                "content": "Context jobs queue is full. Please retry shortly.",
            },
        }
        db.add(run)
        db.commit()
        raise ValueError("Context jobs queue is full. Please retry shortly.")
    record_run_created(db, owner)
    return run


def _attach_lifecycle_handoff(
    db: Session,
    owner: str,
    child_job_id: UUID,
    child_run_id: UUID,
    parent_run_id: UUID | None,
) -> None:
    """Link a newly created child run to an awaiting lifecycle handoff row."""
    query = (
        db.query(RunChainModel)
        .filter(
            RunChainModel.child_job_id == child_job_id,
            RunChainModel.status == "awaiting_handoff",
            RunChainModel.child_run_id.is_(None),
        )
        .order_by(RunChainModel.created_at.desc())
    )
    if parent_run_id is not None:
        query = query.filter(RunChainModel.parent_run_id == parent_run_id)
    chain = query.first()
    if not chain:
        return
    parent = get_run(db, chain.parent_run_id, owner)
    if not parent:
        return
    chain.child_run_id = child_run_id
    chain.status = "running"
    db.add(chain)
    db.commit()


def get_pending_handoff_for_job(
    db: Session,
    owner: str,
    job_id: UUID,
    *,
    parent_run_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Return the latest awaiting handoff targeting this job, if any."""
    if not get_job(db, job_id, owner):
        raise ContextJobsNotFoundError("Job not found")

    query = (
        db.query(RunChainModel)
        .filter(
            RunChainModel.child_job_id == job_id,
            RunChainModel.status == "awaiting_handoff",
            RunChainModel.child_run_id.is_(None),
        )
        .order_by(RunChainModel.created_at.desc())
    )
    if parent_run_id is not None:
        query = query.filter(RunChainModel.parent_run_id == parent_run_id)
    chain = query.first()
    if not chain:
        return None

    parent = get_run(db, chain.parent_run_id, owner)
    if not parent:
        return None

    mapping = chain.input_mapping if isinstance(chain.input_mapping, dict) else {}
    suggested = str(mapping.get("userRequest") or "").strip()
    if not suggested:
        rop = parent.run_output_package if isinstance(parent.run_output_package, dict) else {}
        handoff = rop.get("lifecycleHandoff") if isinstance(rop, dict) else None
        if isinstance(handoff, dict):
            suggested = str(handoff.get("suggestedUserRequest") or "").strip()

    label = None
    rop = parent.run_output_package if isinstance(parent.run_output_package, dict) else {}
    handoff = rop.get("lifecycleHandoff") if isinstance(rop, dict) else None
    if isinstance(handoff, dict):
        label = handoff.get("label")

    return {
        "parentRunId": chain.parent_run_id,
        "childJobId": chain.child_job_id,
        "suggestedUserRequest": suggested,
        "label": label,
        "status": chain.status,
    }


def record_human_decision(
    db: Session,
    owner: str,
    run: JobRunModel,
    data: cj_schemas.RunDecisionRequest,
) -> JobRunModel:
    if not get_job(db, run.job_id, owner):
        raise ContextJobsNotFoundError("Run not found")
    if run.human_decision:
        raise ValueError("A decision has already been recorded for this run")
    run.human_decision = {
        "decision": data.decision,
        "decidedBy": data.decided_by or owner,
        "decidedAt": datetime.now(timezone.utc).isoformat(),
        "notes": data.notes or "",
    }
    job = get_job(db, run.job_id, owner)
    if job:
        run = apply_decision_follow_through(db, run, job, data.decision, owner)
    else:
        db.add(run)
        db.commit()
        db.refresh(run)
    decision = str(data.decision or "").strip().lower()
    if decision in {"approve", "approved", "accept", "accepted"}:
        event_type = "run.approved"
    elif decision in {"escalate", "escalated", "reject", "rejected", "request_info", "request_more_info"}:
        event_type = "run.escalated"
    else:
        event_type = None
    if event_type:
        cj_audit.write_audit_event(
            db,
            event_type=event_type,
            entity_type="run",
            entity_id=str(run.id),
            actor=data.decided_by or owner,
            metadata={
                "decision": data.decision,
                "notes": data.notes,
                "decidedBy": data.decided_by or owner,
                "runState": run.state,
            },
        )
    return run


def get_queue_status() -> dict:
    return get_run_queue_status()


def replay_run(db: Session, owner: str, run_id: UUID) -> JobRunModel:
    package_name = ensure_context_jobs_access(db, owner)
    assert_can_create_run(db, owner, package_name)
    run = get_run(db, run_id, owner)
    if not run:
        raise ContextJobsNotFoundError("Run not found")
    if not run.replay_snapshot and run.state not in {"completed", "failed", "escalated", "repair"}:
        raise ValueError("Run is not replayable")
    new_run = create_replay_run(db, owner, run)
    record_run_created(db, owner)
    return new_run


def resolve_run_tool_approval(
    db: Session,
    owner: str,
    run_id: UUID,
    approval_id: str,
    decision: str,
    notes: Optional[str] = None,
) -> JobRunModel:
    run = get_run(db, run_id, owner)
    if not run:
        raise ContextJobsNotFoundError("Run not found")
    return resolve_tool_approval(db, run, approval_id, decision, owner, notes)


def confirm_run_memory(
    db: Session,
    owner: str,
    run_id: UUID,
    approved: bool,
) -> JobRunModel:
    run = get_run(db, run_id, owner)
    if not run:
        raise ContextJobsNotFoundError("Run not found")
    job = get_job(db, run.job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
    changes = confirm_memory_changes(db, run, job, approved, owner)
    rop = dict(run.run_output_package or {})
    rop["memoryStateChanges"] = {
        "updated": bool(changes),
        "approvalRequired": False,
        "approvalGranted": approved,
        "changes": changes,
    }
    run.run_output_package = rop
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run_tool_executions(db: Session, owner: str, run_id: UUID) -> list[dict[str, Any]]:
    run = get_run(db, run_id, owner)
    if not run:
        raise ContextJobsNotFoundError("Run not found")
    return list_tool_executions(db, run_id)


def export_run_report(db: Session, owner: str, run_id: UUID) -> str:
    run = get_run(db, run_id, owner)
    if not run:
        raise ContextJobsNotFoundError("Run not found")
    job = get_job(db, run.job_id, owner)
    return export_run_markdown(run, job)


def _run_chain_summary(db: Session, owner: str, run: JobRunModel) -> dict[str, Any]:
    job = get_job(db, run.job_id, owner)
    return {
        "runId": run.id,
        "jobId": run.job_id,
        "jobName": job.name if job else "",
        "status": run.state,
        "createdAt": run.started_at,
    }


def _build_child_run_tree(db: Session, owner: str, parent_run_id: UUID) -> list[dict[str, Any]]:
    chains = (
        db.query(RunChainModel)
        .filter(RunChainModel.parent_run_id == parent_run_id)
        .order_by(RunChainModel.created_at.asc())
        .all()
    )
    children: list[dict[str, Any]] = []
    for chain in chains:
        if chain.child_run_id is None:
            continue
        child_run = db.query(JobRunModel).filter(JobRunModel.id == chain.child_run_id).first()
        if not child_run or not get_job(db, child_run.job_id, owner):
            continue
        node = _run_chain_summary(db, owner, child_run)
        node["childRuns"] = _build_child_run_tree(db, owner, child_run.id)
        children.append(node)
    return children


def get_run_chain(db: Session, owner: str, run_id: UUID) -> dict[str, Any] | None:
    """Return parent and recursive child chain lineage for a run (read-only)."""
    run = get_run(db, run_id, owner)
    if not run:
        return None

    parent_run_id: UUID | None = None
    parent_run: dict[str, Any] | None = None

    chain_as_child = (
        db.query(RunChainModel)
        .filter(RunChainModel.child_run_id == run_id)
        .first()
    )
    if chain_as_child:
        parent_run_id = chain_as_child.parent_run_id
    elif run.parent_run_id:
        parent_run_id = run.parent_run_id

    if parent_run_id is not None:
        parent_run_model = db.query(JobRunModel).filter(JobRunModel.id == parent_run_id).first()
        if parent_run_model and get_job(db, parent_run_model.job_id, owner):
            parent_run = _run_chain_summary(db, owner, parent_run_model)

    return {
        "runId": run_id,
        "parentRunId": parent_run_id,
        "parentRun": parent_run,
        "childRuns": _build_child_run_tree(db, owner, run_id),
    }
