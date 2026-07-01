"""Run workflows: repair, replay, export, decision follow-through."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

import context_jobs.audit as cj_audit
from context_jobs.errors import ContextJobsNotFoundError
from schemas.context_jobs_model import ContextJobModel, JobRunModel
from schemas.tool_execution_model import ToolExecutionModel


MAX_REPAIR_CYCLES = 1


def build_replay_snapshot(
    run: JobRunModel,
    job: ContextJobModel,
    response_content: str,
    retrieval_events: list,
    source_traces: list,
    validation_events: list,
) -> dict[str, Any]:
    return {
        "userRequest": run.user_request,
        "jobVersion": run.job_version,
        "outputText": response_content,
        "retrievalEvents": retrieval_events,
        "sourceTraceEvents": source_traces,
        "validationEvents": validation_events,
        "stepLogs": run.step_logs,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "jobId": str(job.id),
    }


def create_replay_run(db: Session, owner: str, source_run: JobRunModel) -> JobRunModel:
    job = (
        db.query(ContextJobModel)
        .filter(ContextJobModel.id == source_run.job_id, ContextJobModel.owner == owner)
        .first()
    )
    if not job:
        raise ContextJobsNotFoundError("Run not found")
    snapshot = source_run.replay_snapshot or {}
    user_request = snapshot.get("userRequest") or source_run.user_request or ""
    job_version = snapshot.get("jobVersion") or source_run.job_version or job.version
    new_run = JobRunModel(
        job_id=job.id,
        user_request=user_request,
        job_version=job_version,
        parent_run_id=source_run.id,
        repair_cycles=0,
    )
    db.add(new_run)
    db.commit()
    db.refresh(new_run)
    # Lazy import avoids circular dependency: orchestrator → run_engine → run_workflows
    from context_jobs.orchestrator import enqueue_run

    if not enqueue_run(new_run.id):
        raise ValueError("Context jobs queue is full. Please retry shortly.")
    cj_audit.write_audit_event(
        db,
        event_type="run.replayed",
        entity_type="run",
        entity_id=str(new_run.id),
        actor=owner,
        metadata={"sourceRunId": str(source_run.id), "jobId": str(job.id)},
    )
    return new_run


def should_attempt_repair(run: JobRunModel, validation_status: str) -> bool:
    cycles = int(getattr(run, "repair_cycles", None) or 0)
    return validation_status == "needs_repair" and cycles < MAX_REPAIR_CYCLES


def export_run_markdown(run: JobRunModel, job: Optional[ContextJobModel] = None) -> str:
    rop = run.run_output_package or {}
    primary = rop.get("primaryResult") or {}
    validation = rop.get("validationSummary") or {}
    lines = [
        f"# Run Report — {job.name if job else run.job_id}",
        "",
        f"**Run ID:** {run.id}",
        f"**Status:** {rop.get('status') or run.state}",
        f"**Outcome:** {run.outcome or 'n/a'}",
        "",
        "## Primary Result",
        "",
        primary.get("content") or run.output_text or "",
        "",
        "## Validation",
        "",
        f"- Decision: {validation.get('overallDecision')}",
        f"- Confidence: {validation.get('confidenceLevel')}",
    ]
    for check in validation.get("checks") or []:
        if isinstance(check, dict):
            lines.append(f"- [{check.get('status', '?')}] {check.get('name', check.get('rule', 'check'))}")
    lines.extend(["", "## Cost & Time", ""])
    cost = rop.get("costTimeSummary") or {}
    lines.append(f"- Runtime: {cost.get('runtimeSeconds')}s")
    lines.append(f"- Cost: {cost.get('estimatedCost')}")
    if run.human_decision:
        lines.extend(["", "## Human Decision", "", json.dumps(run.human_decision, indent=2)])
    return "\n".join(lines)


def apply_decision_follow_through(
    db: Session,
    run: JobRunModel,
    job: ContextJobModel,
    decision: str,
    owner: str,
) -> JobRunModel:
    """Update run state/outcome based on human decision."""
    d = str(decision or "").strip().lower()
    rop = dict(run.run_output_package or {})

    if d in {"approve", "approved", "accept", "accepted", "stored"}:
        if run.state in {"escalated", "repair"}:
            run.state = "completed"
            run.outcome = "accepted" if d != "stored" else "accepted_with_warnings"
        rop["status"] = "completed"
        rop.setdefault("nextAction", {"type": "use_result", "label": "Approved — result is ready to use"})
        if rop.get("auditMetadata"):
            rop["auditMetadata"]["approvalState"] = "approved"

    elif d in {"reject", "rejected"}:
        run.outcome = "escalated"
        rop.setdefault("nextAction", {"type": "escalate", "label": "Rejected — escalate for review"})

    elif d in {"escalate", "escalated"}:
        run.state = "escalated"
        run.outcome = "escalated"
        rop.setdefault("nextAction", {"type": "escalate", "label": "Escalated for review"})

    elif d in {"info_requested", "request_info", "request_more_info"}:
        rop.setdefault("nextAction", {"type": "provide_more_input", "label": "More input requested"})

    run.run_output_package = rop
    db.add(run)
    db.commit()
    db.refresh(run)

    # Optionally re-enqueue repair run when approved after repair state
    if d in {"approve", "approved"} and run.state == "repair":
        cj_audit.write_audit_event(
            db,
            event_type="run.repair_approved",
            entity_type="run",
            entity_id=str(run.id),
            actor=owner,
            metadata={"jobId": str(job.id)},
        )

    return run


def list_tool_executions(db: Session, run_id: UUID) -> list[dict[str, Any]]:
    rows = (
        db.query(ToolExecutionModel)
        .filter(ToolExecutionModel.run_id == run_id)
        .order_by(ToolExecutionModel.created_at.asc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "runId": str(r.run_id),
            "toolId": r.tool_id,
            "toolName": r.tool_name,
            "action": r.action,
            "status": r.status,
            "arguments": r.arguments,
            "resultSummary": r.result_summary,
            "denialReason": r.denial_reason,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
