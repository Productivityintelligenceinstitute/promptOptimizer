from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
from context_jobs.agents.execution_modes import normalize_execution_mode
from context_jobs.managed_jet_kb import ensure_managed_namespace
from context_jobs.orchestrator import enqueue_run, get_run_queue_status
from context_jobs.provider_key_services import resolve_llm_api_key
from context_jobs.vector_connection_services import get_active_connection_for_owner
from schemas.context_jobs_model import ContextJobModel, ContextAssetModel, JobRunModel
from schemas.llm_provider_key_model import LlmProviderKeyModel


def _validate_job_vector_connection(db: Session, data: cj_schemas.ContextJobBase, owner: str) -> None:
    mode = (getattr(data, "retrieval_mode", None) or "jet_kb").lower()
    conn_id = getattr(data, "vector_connection_id", None)
    if mode == "external":
        if not conn_id:
            raise ValueError(
                "retrievalMode external requires vectorConnectionId (pick a saved connection)."
            )
        get_active_connection_for_owner(db, conn_id, owner)
    elif conn_id:
        raise ValueError("vectorConnectionId is only used when retrievalMode is external.")


def _validate_llm_key(db: Session, owner: str, llm_key_id: Optional[UUID]) -> None:
    if not llm_key_id:
        import os

        # Check if platform key exists for fallback
        provider_env_keys = {
            "openai": os.environ.get("OPENAI_API_KEY"),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "google": os.environ.get("GEMINI_API_KEY"),
        }
        if any(provider_env_keys.values()):
            return  # platform key available, allow job creation without BYOK
        raise ValueError("llmKeyId is required. Add a BYOK LLM key and assign it to this job.")
    row = (
        db.query(LlmProviderKeyModel)
        .filter(
            LlmProviderKeyModel.id == llm_key_id,
            LlmProviderKeyModel.owner == owner,
            LlmProviderKeyModel.status == "active",
        )
        .first()
    )
    if not row:
        raise ValueError("Assigned llmKeyId was not found or is inactive for this user.")


def _maybe_ensure_jet_managed_namespace(db: Session, job: ContextJobModel) -> None:
    if (job.retrieval_mode or "jet_kb").lower() != "jet_kb":
        return
    ensure_managed_namespace(db, job.owner)


def list_jobs(db: Session, owner: str) -> List[ContextJobModel]:
    return (
        db.query(ContextJobModel)
        .filter(ContextJobModel.owner == owner)
        .order_by(ContextJobModel.created_at.desc())
        .all()
    )


def get_job(db: Session, job_id: UUID, owner: str) -> Optional[ContextJobModel]:
    return (
        db.query(ContextJobModel)
        .filter(ContextJobModel.id == job_id, ContextJobModel.owner == owner)
        .first()
    )


def _normalize_job_payload(payload: dict) -> dict:
    if "execution_mode" in payload and payload["execution_mode"] is not None:
        payload["execution_mode"] = normalize_execution_mode(payload["execution_mode"])
    return payload


def create_job(db: Session, owner: str, data: cj_schemas.ContextJobCreate) -> ContextJobModel:
    payload = _normalize_job_payload(data.model_dump(by_alias=False))
    payload["owner"] = owner
    check = cj_schemas.ContextJobCreate(**payload)
    _validate_job_vector_connection(db, check, owner)
    _validate_llm_key(db, owner, check.llm_key_id)
    job = ContextJobModel(**payload)
    db.add(job)
    db.commit()
    db.refresh(job)
    _maybe_ensure_jet_managed_namespace(db, job)
    return job


def update_job(
    db: Session,
    owner: str,
    job: ContextJobModel,
    data: cj_schemas.ContextJobUpdate,
) -> ContextJobModel:
    payload = _normalize_job_payload(data.model_dump(exclude_unset=True, by_alias=False))
    merged_mode = payload.get("retrieval_mode", job.retrieval_mode)
    merged_conn = payload.get("vector_connection_id", job.vector_connection_id)
    merged_key = payload.get("llm_key_id", job.llm_key_id)
    if merged_mode is not None or merged_conn is not None:
        check = cj_schemas.ContextJobCreate(
            name=job.name,
            retrieval_mode=merged_mode,
            vector_connection_id=merged_conn,
            owner=owner,
            llm_key_id=merged_key,
        )
        _validate_job_vector_connection(db, check, owner)
    if "llm_key_id" in payload or merged_key:
        _validate_llm_key(db, owner, merged_key)
    for key, value in payload.items():
        setattr(job, key, value)
    job.owner = owner
    db.add(job)
    db.commit()
    db.refresh(job)
    _maybe_ensure_jet_managed_namespace(db, job)
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


def list_runs(db: Session, owner: str) -> List[JobRunModel]:
    return (
        db.query(JobRunModel)
        .join(ContextJobModel, JobRunModel.job_id == ContextJobModel.id)
        .filter(ContextJobModel.owner == owner)
        .order_by(JobRunModel.started_at.desc())
        .all()
    )


def get_run(db: Session, run_id: UUID, owner: str) -> Optional[JobRunModel]:
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
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    resolve_llm_api_key(db, owner, job.llm_key_id, job.execution_provider)
    run = JobRunModel(job_id=job_id, user_request=data.user_request or "")
    db.add(run)
    db.commit()
    db.refresh(run)
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
    return run


def duplicate_job(db: Session, owner: str, job: ContextJobModel) -> ContextJobModel:
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
        retrieval_mode=job.retrieval_mode,
        vector_connection_id=job.vector_connection_id,
        memory_config=job.memory_config,
        tool_permissions=job.tool_permissions,
        validation_rules=job.validation_rules,
        escalation_policy=job.escalation_policy,
        budget_settings=job.budget_settings,
        glossary_terms=job.glossary_terms,
        relationships=job.relationships,
        trusted_sources=job.trusted_sources,
        execution_provider=job.execution_provider,
        execution_model=job.execution_model,
        llm_key_id=job.llm_key_id,
        max_agent_turns=job.max_agent_turns,
        execution_mode=job.execution_mode,
        version=1,
        owner=owner,
        approval_required=job.approval_required,
        policy_profile=job.policy_profile,
    )
    db.add(duplicated)
    db.commit()
    db.refresh(duplicated)
    return duplicated


def get_job_stats(db: Session, owner: str, job_id: UUID) -> dict:
    if not get_job(db, job_id, owner):
        raise ValueError("Job not found")
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
    recent_runs = sorted(
        runs,
        key=lambda r: r.started_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:5]
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
    owner: str,
    run: JobRunModel,
    data: cj_schemas.RunDecisionRequest,
) -> JobRunModel:
    if not get_job(db, run.job_id, owner):
        raise ValueError("Run not found")
    if run.human_decision:
        raise ValueError("A decision has already been recorded for this run")
    run.human_decision = {
        "decision": data.decision,
        "decidedBy": data.decided_by or owner,
        "decidedAt": datetime.now(timezone.utc).isoformat(),
        "notes": data.notes or "",
    }
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_overall_stats(db: Session, owner: str) -> dict:
    jobs = list_jobs(db, owner)
    runs = list_runs(db, owner)
    assets = list_assets(db)
    completed_runs = [r for r in runs if r.state == "completed"]
    pass_rate = int((len(completed_runs) / len(runs)) * 100) if runs else 0
    return {
        "jobCount": len(jobs),
        "runCount": len(runs),
        "assetCount": len(assets),
        "passRate": pass_rate,
    }


def get_queue_status() -> dict:
    return get_run_queue_status()
