from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
from context_jobs.orchestrator import enqueue_mock_run, get_mock_queue_status
from schemas.context_jobs_model import ContextJobModel, ContextAssetModel, JobRunModel


def list_jobs(db: Session) -> List[ContextJobModel]:
    return db.query(ContextJobModel).order_by(ContextJobModel.created_at.desc()).all()


def get_job(db: Session, job_id: UUID) -> Optional[ContextJobModel]:
    return db.query(ContextJobModel).filter(ContextJobModel.id == job_id).first()


def create_job(db: Session, data: cj_schemas.ContextJobCreate) -> ContextJobModel:
    job = ContextJobModel(**data.model_dump(by_alias=False))
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(
    db: Session,
    job: ContextJobModel,
    data: cj_schemas.ContextJobUpdate,
) -> ContextJobModel:
    payload = data.model_dump(exclude_unset=True, by_alias=False)
    for key, value in payload.items():
        setattr(job, key, value)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_assets(db: Session) -> List[ContextAssetModel]:
    return db.query(ContextAssetModel).order_by(ContextAssetModel.created_at.desc()).all()


def get_asset(db: Session, asset_id: UUID) -> Optional[ContextAssetModel]:
    return db.query(ContextAssetModel).filter(ContextAssetModel.id == asset_id).first()


def create_asset(db: Session, data: cj_schemas.ContextAssetCreate) -> ContextAssetModel:
    asset = ContextAssetModel(**data.model_dump(by_alias=False))
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(
    db: Session,
    asset: ContextAssetModel,
    data: cj_schemas.ContextAssetUpdate,
) -> ContextAssetModel:
    payload = data.model_dump(exclude_unset=True, by_alias=False)
    for key, value in payload.items():
        setattr(asset, key, value)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset: ContextAssetModel) -> None:
    db.delete(asset)
    db.commit()


def list_runs(db: Session) -> List[JobRunModel]:
    return db.query(JobRunModel).order_by(JobRunModel.started_at.desc()).all()


def get_run(db: Session, run_id: UUID) -> Optional[JobRunModel]:
    return db.query(JobRunModel).filter(JobRunModel.id == run_id).first()


def create_run(
    db: Session,
    job_id: UUID,
    data: cj_schemas.JobRunCreate,
) -> JobRunModel:
    run = JobRunModel(job_id=job_id, user_request=data.user_request or "")
    db.add(run)
    db.commit()
    db.refresh(run)
    queued = enqueue_mock_run(run.id)
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
    return run


def duplicate_job(db: Session, job: ContextJobModel) -> ContextJobModel:
    duplicated = ContextJobModel(
        name=f"{job.name} (Copy)",
        description=job.description,
        status="draft",
        goal=job.goal,
        semantic_blueprint=job.semantic_blueprint,
        workflow_type=job.workflow_type,
        stable_instructions=job.stable_instructions,
        role_configuration=job.role_configuration,
        retrieval_config=job.retrieval_config,
        memory_config=job.memory_config,
        tool_permissions=job.tool_permissions,
        validation_rules=job.validation_rules,
        escalation_policy=job.escalation_policy,
        budget_settings=job.budget_settings,
        glossary_terms=job.glossary_terms,
        relationships=job.relationships,
        trusted_sources=job.trusted_sources,
        version=1,
        owner=job.owner,
        approval_required=job.approval_required,
        policy_profile=job.policy_profile,
    )
    db.add(duplicated)
    db.commit()
    db.refresh(duplicated)
    return duplicated


def get_job_stats(db: Session, job_id: UUID) -> dict:
    runs = db.query(JobRunModel).filter(JobRunModel.job_id == job_id).all()
    total_runs = len(runs)
    completed_runs = len([r for r in runs if r.state == "completed"])
    failed_runs = len([r for r in runs if r.state == "failed"])
    escalated_runs = len([r for r in runs if r.state == "escalated"])
    repair_runs = len([r for r in runs if r.state == "repair"])
    terminal_runs = [r for r in runs if r.state in {"completed", "failed", "escalated", "repair"}]
    completion_rate = int((completed_runs / len(terminal_runs)) * 100) if terminal_runs else 0
    avg_latency = (
        round(sum((r.latency_ms or 0) for r in terminal_runs) / len(terminal_runs), 2)
        if terminal_runs
        else 0
    )
    recent_runs = sorted(runs, key=lambda r: r.started_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:5]
    return {
        "totalRuns": total_runs,
        "completedRuns": completed_runs,
        "failedRuns": failed_runs,
        "escalatedRuns": escalated_runs,
        "repairRuns": repair_runs,
        "completionRate": completion_rate,
        "averageLatencyMs": avg_latency,
        "recentRuns": [
            {
                "runId": str(r.id),
                "state": r.state,
                "startedAt": r.started_at.isoformat() if r.started_at else None,
                "endedAt": r.ended_at.isoformat() if r.ended_at else None,
                "outcome": r.outcome,
            }
            for r in recent_runs
        ],
    }


def record_human_decision(
    db: Session,
    run: JobRunModel,
    data: cj_schemas.RunDecisionRequest,
) -> JobRunModel:
    if run.human_decision:
        raise ValueError("A decision has already been recorded for this run")
    run.human_decision = {
        "decision": data.decision,
        "decidedBy": data.decided_by,
        "decidedAt": datetime.now(timezone.utc).isoformat(),
        "notes": data.notes or "",
    }
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_overall_stats(db: Session) -> dict:
    jobs = db.query(ContextJobModel).all()
    runs = db.query(JobRunModel).all()
    assets = db.query(ContextAssetModel).all()
    completed_runs = [r for r in runs if r.state == "completed"]
    pass_rate = int((len(completed_runs) / len(runs)) * 100) if runs else 0
    return {
        "jobCount": len(jobs),
        "runCount": len(runs),
        "assetCount": len(assets),
        "passRate": pass_rate,
    }


def get_queue_status() -> dict:
    return get_mock_queue_status()

