from datetime import datetime, timezone
import json
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
import context_jobs.audit as cj_audit
from context_jobs.agents.execution_modes import normalize_execution_mode
from context_jobs.asset_taxonomy import (
    import_asset_into_job,
    list_source_pack_assets,
    validate_asset_content,
    validate_asset_type,
)
from context_jobs.governance import normalize_escalation_policy, suggest_identity_matches
from context_jobs.hitl import confirm_memory_changes, list_pending_tool_approvals, resolve_tool_approval
from context_jobs.managed_jet_kb import ensure_managed_namespace
from context_jobs.orchestrator import enqueue_run, get_run_queue_status
from context_jobs.provider_key_services import resolve_llm_api_key
from context_jobs.run_workflows import (
    apply_decision_follow_through,
    create_replay_run,
    export_run_markdown,
    list_tool_executions,
)
from context_jobs.vector_connection_services import get_active_connection_for_owner
from context_jobs.workspace import (
    add_workspace_member,
    default_workspace_id,
    ensure_default_workspace,
    get_allowlist,
    update_allowlist,
)
from schemas.context_jobs_model import (
    ContextAssetModel,
    ContextJobModel,
    ContextJobVersionModel,
    PublishHistoryModel,
    JobRunModel,
)
from schemas.llm_provider_key_model import LlmProviderKeyModel


JOB_VERSION_SNAPSHOT_FIELDS = (
    "name",
    "description",
    "status",
    "goal",
    "semantic_blueprint",
    "output_template",
    "workflow_type",
    "stable_instructions",
    "role_configuration",
    "retrieval_config",
    "retrieval_mode",
    "vector_connection_id",
    "memory_config",
    "tool_permissions",
    "validation_rules",
    "escalation_policy",
    "budget_settings",
    "glossary_terms",
    "relationships",
    "trusted_sources",
    "version",
    "owner",
    "approval_required",
    "policy_profile",
    "execution_provider",
    "execution_model",
    "llm_key_id",
    "max_agent_turns",
    "execution_mode",
    "workspace_id",
)


def _job_snapshot(job: ContextJobModel) -> dict[str, Any]:
    raw = {field: getattr(job, field) for field in JOB_VERSION_SNAPSHOT_FIELDS}
    return json.loads(json.dumps(raw, default=str))


def _apply_job_snapshot(job: ContextJobModel, snapshot: dict[str, Any]) -> None:
    for field in JOB_VERSION_SNAPSHOT_FIELDS:
        if field in snapshot:
            value = snapshot[field]
            if field in {"vector_connection_id", "llm_key_id"} and value:
                value = UUID(str(value))
            setattr(job, field, value)


def _ensure_job_version_seed(db: Session, job: ContextJobModel, created_by: Optional[str] = None) -> None:
    existing = (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job.id)
        .first()
    )
    if existing:
        return
    seed_version = int(job.version or 1)
    db.add(
        ContextJobVersionModel(
            job_id=job.id,
            version=seed_version,
            snapshot=_job_snapshot(job),
            created_by=created_by or job.owner,
            change_type="seed",
            is_current=True,
        )
    )
    db.commit()


def _clear_current_version_flags(db: Session, job_id: UUID) -> None:
    (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job_id)
        .update({"is_current": False}, synchronize_session=False)
    )


def _set_current_version(db: Session, job_id: UUID, version: int) -> None:
    _clear_current_version_flags(db, job_id)
    row = (
        db.query(ContextJobVersionModel)
        .filter(
            ContextJobVersionModel.job_id == job_id,
            ContextJobVersionModel.version == version,
        )
        .first()
    )
    if row:
        row.is_current = True


def _normalize_current_version(db: Session, job: ContextJobModel) -> None:
    rows = _get_version_rows(db, job.id)
    if not rows:
        return
    current_rows = [row for row in rows if bool(row.is_current)]
    if len(current_rows) == 1 and int(job.version or 0) == int(current_rows[0].version or 0):
        return
    target = next(
        (row for row in current_rows if int(row.version or 0) == int(job.version or 0)),
        None,
    )
    if not target:
        target = next((row for row in rows if int(row.version or 0) == int(job.version or 0)), None)
    if not target:
        target = current_rows[0] if current_rows else rows[0]
    _clear_current_version_flags(db, job.id)
    target.is_current = True
    db.commit()


def _record_job_version(
    db: Session,
    job: ContextJobModel,
    *,
    created_by: Optional[str] = None,
    change_type: str = "save",
    rollback_from_version: Optional[int] = None,
    notes: Optional[str] = None,
) -> ContextJobVersionModel:
    _clear_current_version_flags(db, job.id)
    entry = ContextJobVersionModel(
        job_id=job.id,
        version=int(job.version or 1),
        snapshot=_job_snapshot(job),
        created_by=created_by or job.owner,
        change_type=change_type,
        is_current=True,
        rollback_from_version=rollback_from_version,
        notes=notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _get_version_rows(db: Session, job_id: UUID) -> list[ContextJobVersionModel]:
    return (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job_id)
        .order_by(ContextJobVersionModel.version.desc(), ContextJobVersionModel.created_at.desc())
        .all()
    )


def _latest_job_version_number(db: Session, job_id: UUID) -> int:
    rows = _get_version_rows(db, job_id)
    if rows:
        return int(rows[0].version or 1)
    job = db.query(ContextJobModel).filter(ContextJobModel.id == job_id).first()
    return int(job.version or 1) if job else 1


def _serialize_job_version(
    job: ContextJobModel,
    version_row: ContextJobVersionModel,
) -> dict[str, Any]:
    return {
        "id": version_row.id,
        "jobId": version_row.job_id,
        "version": version_row.version,
        "createdAt": version_row.created_at,
        "createdBy": version_row.created_by,
        "changeType": version_row.change_type,
        "rollbackFromVersion": version_row.rollback_from_version,
        "notes": version_row.notes,
        "isCurrent": bool(version_row.is_current),
        "jobSnapshot": version_row.snapshot or {},
    }


def _record_publish_history(
    db: Session,
    *,
    job_id: UUID,
    from_status: str,
    to_status: str,
    changed_by: str,
    notes: Optional[str] = None,
) -> PublishHistoryModel:
    row = PublishHistoryModel(
        job_id=job_id,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
    if "escalation_policy" in payload and payload["escalation_policy"] is not None:
        payload["escalation_policy"] = normalize_escalation_policy(payload["escalation_policy"])
    return payload


def create_job(db: Session, owner: str, data: cj_schemas.ContextJobCreate) -> ContextJobModel:
    ws = ensure_default_workspace(db, owner)
    payload = _normalize_job_payload(data.model_dump(by_alias=False))
    payload["owner"] = owner
    payload["workspace_id"] = payload.get("workspace_id") or ws.id
    payload["status"] = "published"
    check = cj_schemas.ContextJobCreate(**payload)
    _validate_job_vector_connection(db, check, owner)
    _validate_llm_key(db, owner, check.llm_key_id)
    job = ContextJobModel(**payload)
    db.add(job)
    db.commit()
    db.refresh(job)
    _record_job_version(db, job, created_by=owner, change_type="create")
    _record_publish_history(
        db,
        job_id=job.id,
        from_status="draft",
        to_status="published",
        changed_by=owner,
        notes="Auto-published on create",
    )
    cj_audit.write_audit_event(
        db,
        event_type="job.published",
        entity_type="job",
        entity_id=str(job.id),
        actor=owner,
        metadata={
            "fromStatus": "draft",
            "toStatus": "published",
            "notes": "Auto-published on create",
            "jobVersion": job.version,
        },
    )
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
    _ensure_job_version_seed(db, job, created_by=owner)
    for key, value in payload.items():
        setattr(job, key, value)
    job.owner = owner
    job.version = _latest_job_version_number(db, job.id) + 1
    db.add(job)
    db.commit()
    db.refresh(job)
    _record_job_version(db, job, created_by=owner, change_type="save")
    _maybe_ensure_jet_managed_namespace(db, job)
    return job


def list_assets(db: Session, owner: str) -> List[ContextAssetModel]:
    q = db.query(ContextAssetModel).filter(
        (ContextAssetModel.owner == owner) | (ContextAssetModel.owner.is_(None))
    )
    return q.order_by(ContextAssetModel.created_at.desc()).all()


def list_publish_history(db: Session, owner: str, job_id: UUID) -> list[dict[str, Any]]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    rows = (
        db.query(PublishHistoryModel)
        .filter(PublishHistoryModel.job_id == job_id)
        .order_by(PublishHistoryModel.changed_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "jobId": row.job_id,
            "fromStatus": row.from_status,
            "toStatus": row.to_status,
            "changedBy": row.changed_by,
            "changedAt": row.changed_at,
            "notes": row.notes,
        }
        for row in rows
    ]


def suggest_job_identity_matches(
    db: Session, owner: str, job_id: UUID, query: str
) -> list[dict[str, Any]]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    return suggest_identity_matches(job, query)


def list_audit_events(
    db: Session,
    owner: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    rows = cj_audit.list_audit_events(
        db,
        owner=owner,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return [
        {
            "id": row.id,
            "eventType": row.event_type,
            "entityType": row.entity_type,
            "entityId": row.entity_id,
            "actor": row.actor,
            "timestamp": row.timestamp,
            "metadata": row.event_metadata or {},
        }
        for row in rows
    ]


def list_job_versions(db: Session, owner: str, job_id: UUID) -> List[dict[str, Any]]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    _ensure_job_version_seed(db, job, created_by=owner)
    _normalize_current_version(db, job)
    return [_serialize_job_version(job, row) for row in _get_version_rows(db, job.id)]


def get_job_version(db: Session, owner: str, job_id: UUID, version: int) -> dict[str, Any]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    _ensure_job_version_seed(db, job, created_by=owner)
    _normalize_current_version(db, job)
    row = (
        db.query(ContextJobVersionModel)
        .filter(
            ContextJobVersionModel.job_id == job.id,
            ContextJobVersionModel.version == version,
        )
        .first()
    )
    if not row:
        raise ValueError("Version not found")
    return _serialize_job_version(job, row)


def get_latest_job_version(db: Session, owner: str, job_id: UUID) -> dict[str, Any]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    _ensure_job_version_seed(db, job, created_by=owner)
    _normalize_current_version(db, job)
    row = (
        db.query(ContextJobVersionModel)
        .filter(ContextJobVersionModel.job_id == job.id, ContextJobVersionModel.is_current.is_(True))
        .order_by(ContextJobVersionModel.created_at.desc(), ContextJobVersionModel.version.desc())
        .first()
    )
    if not row:
        row = (
            db.query(ContextJobVersionModel)
            .filter(ContextJobVersionModel.job_id == job.id)
            .order_by(ContextJobVersionModel.created_at.desc(), ContextJobVersionModel.version.desc())
            .first()
        )
    if not row:
        raise ValueError("Version not found")
    return _serialize_job_version(job, row)


def publish_job(
    db: Session,
    owner: str,
    job_id: UUID,
    notes: Optional[str] = None,
) -> ContextJobModel:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    from_status = (job.status or "draft").lower()
    if from_status == "published":
        raise ValueError("Job is already published")
    if from_status not in {"draft", "archived"}:
        raise ValueError(f"Cannot publish a job from status {job.status!r}")
    job.status = "published"
    db.add(job)
    db.commit()
    db.refresh(job)
    _record_publish_history(
        db,
        job_id=job.id,
        from_status=from_status,
        to_status="published",
        changed_by=owner,
        notes=notes,
    )
    cj_audit.write_audit_event(
        db,
        event_type="job.published",
        entity_type="job",
        entity_id=str(job.id),
        actor=owner,
        metadata={
            "fromStatus": from_status,
            "toStatus": "published",
            "notes": notes,
            "jobVersion": job.version,
        },
    )
    return job


def archive_job(
    db: Session,
    owner: str,
    job_id: UUID,
    notes: Optional[str] = None,
) -> ContextJobModel:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    from_status = (job.status or "draft").lower()
    if from_status == "archived":
        raise ValueError("Job is already archived")
    job.status = "archived"
    db.add(job)
    db.commit()
    db.refresh(job)
    _record_publish_history(
        db,
        job_id=job.id,
        from_status=from_status,
        to_status="archived",
        changed_by=owner,
        notes=notes,
    )
    cj_audit.write_audit_event(
        db,
        event_type="job.archived",
        entity_type="job",
        entity_id=str(job.id),
        actor=owner,
        metadata={
            "fromStatus": from_status,
            "toStatus": "archived",
            "notes": notes,
            "jobVersion": job.version,
        },
    )
    return job


def rollback_job_version(
    db: Session,
    owner: str,
    job_id: UUID,
    target_version: int,
    notes: Optional[str] = None,
) -> ContextJobModel:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    _ensure_job_version_seed(db, job, created_by=owner)
    row = (
        db.query(ContextJobVersionModel)
        .filter(
            ContextJobVersionModel.job_id == job.id,
            ContextJobVersionModel.version == target_version,
        )
        .first()
    )
    if not row:
        raise ValueError("Version not found")
    previous_version = int(job.version or 1)
    snapshot = dict(row.snapshot or {})
    _apply_job_snapshot(job, snapshot)
    _set_current_version(db, job.id, target_version)
    job.version = int(target_version)
    job.owner = owner
    db.add(job)
    db.commit()
    db.refresh(job)
    cj_audit.write_audit_event(
        db,
        event_type="job.rolled_back",
        entity_type="job",
        entity_id=str(job.id),
        actor=owner,
        metadata={
            "fromVersion": previous_version,
            "toVersion": target_version,
            "notes": notes,
        },
    )
    return job


def get_asset(db: Session, asset_id: UUID, owner: Optional[str] = None) -> Optional[ContextAssetModel]:
    q = db.query(ContextAssetModel).filter(ContextAssetModel.id == asset_id)
    if owner:
        q = q.filter(
            (ContextAssetModel.owner == owner) | (ContextAssetModel.owner.is_(None))
        )
    return q.first()


def create_asset(db: Session, owner: str, data: cj_schemas.ContextAssetCreate) -> ContextAssetModel:
    validate_asset_type(data.type)
    validate_asset_content(data.type, data.content)
    payload = data.model_dump(by_alias=False)
    payload["owner"] = owner
    payload["workspace_id"] = payload.get("workspace_id") or default_workspace_id(owner)
    asset = ContextAssetModel(**payload)
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
    if payload.get("type"):
        validate_asset_type(payload["type"])
    if "content" in payload:
        validate_asset_content(payload.get("type") or asset.type, payload["content"])
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
    if (job.status or "draft").lower() != "published":
        raise ValueError("Job must be published before running. Publish the job first.")
    resolve_llm_api_key(db, owner, job.llm_key_id, job.execution_provider)
    run = JobRunModel(
        job_id=job_id,
        user_request=data.user_request or "",
        job_version=job.version,
        workspace_id=getattr(job, "workspace_id", None) or default_workspace_id(owner),
    )
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
        output_template=job.output_template,
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
    _record_job_version(db, duplicated, created_by=owner, change_type="duplicate")
    return duplicated


async def generate_job_from_prompt(
    db: Session,
    owner: str,
    prompt: str,
    agent_type: Optional[str] = None,
) -> cj_schemas.ContextJobCreate:
    import json
    import os

    import anthropic
    from openai import AsyncOpenAI

    prompt = (prompt or "").strip()
    if len(prompt) < 20:
        raise ValueError("Prompt is too short. Please describe what you want the job to do in more detail.")

    valid_workflow_types = {"standard", "research", "analysis", "generation", "review"}
    agent_type = (agent_type or "").strip()
    request_context = prompt
    if agent_type:
        request_context = f"Agent type: {agent_type}\nRequest: {prompt}"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required to verify prompt-to-job requests.")

    client = AsyncOpenAI(api_key=api_key)
    relevance_response = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=10,
        temperature=0,
        messages=[{
            "role": "user",
            "content": (
                "Is this a valid request to create an AI agent or workflow job? "
                "Reply with only YES or NO.\n\n"
                f"{request_context}"
            )
        }],
    )
    verdict = (relevance_response.choices[0].message.content or "").strip().upper()
    if "NO" in verdict:
        raise ValueError(
            "The prompt does not describe a valid job use case. "
            "Please describe what you want the AI agent to do, "
            "for example: 'Create a research agent that summarizes daily AI news'."
        )

    system = """You are a JPO (Jet Prompt Optimizer) job configuration expert.
Convert the user's natural language description into a complete JPO Context Job configuration.

If an agent type is provided, use it as a strong hint for the job's specialization, role, and workflow.

Return ONLY a valid JSON object with these fields (omit fields that don't apply):
{
  "name": "short job name",
  "description": "what this job does",
  "goal": "the primary objective",
  "workflowType": "standard|research|analysis|generation|review",
  "semanticBlueprint": "expected output structure using ## headings",
  "outputTemplate": "optional exact output structure to follow",
  "stableInstructions": "numbered list of rules the agent must follow",
  "roleConfiguration": "the agent's persona and expertise",
  "escalationPolicy": "always_review|never|on_failure",
  "glossaryTerms": [{"term": "", "definition": "", "synonyms": [], "required": false}],
  "relationships": [{"fromTerm": "", "relation": "", "toTerm": ""}],
  "retrievalMode": "jet_kb",
  "retrievalConfig": {"maxDocuments": 8, "queryRewriting": true, "reranking": true},
  "memoryConfig": {"sessionMemory": true, "projectMemory": false, "retentionDays": 30},
  "toolPermissions": [{"toolId": "web-search|doc-reader|calculator|code-exec|api-caller|file-write|docx-generate", "enabled": true, "readOnly": true}],
  "validationRules": [{"name": "", "type": "citation|format|groundedness|policy|custom", "enabled": true, "severity": "warning|error|blocking", "description": ""}],
  "budgetSettings": {"maxTokens": 4096, "maxCostUsd": 0.10, "maxLatencyMs": 60000, "maxToolCalls": 10},
  "executionProvider": "anthropic",
  "executionModel": "claude-haiku-4-5",
  "executionMode": "single_agent",
  "maxAgentTurns": 10,
  "approvalRequired": false
}

Rules:
- Always include name, goal, workflowType, executionProvider, executionModel
- executionProvider must be exactly one of: anthropic, openai, google
- executionModel must be exactly one of: claude-haiku-4-5, claude-sonnet-4-5, claude-opus-4-5, gpt-4o, gpt-4o-mini, gpt-4.1, gpt-4.1-mini, gemini-2.5-pro, gemini-2.5-flash
- retrievalMode must be exactly: jet_kb (never external — external requires a vectorConnectionId which users set manually)
- executionMode must be exactly: single_agent or provider_multi_agent
- workflowType must be exactly one of: standard, research, analysis, generation, review
- toolPermissions.toolId must be exactly one of: web-search, doc-reader, calculator, code-exec, api-caller, file-write, docx-generate
- toolPermissions.readOnly must be false for file-write, docx-generate, and code-exec; true for read/lookup tools (web-search, doc-reader, calculator)
- api-caller: readOnly true unless the job needs POST/PUT/PATCH/DELETE calls
- validationRules.type must be exactly one of: citation, format, groundedness, policy, custom
- validationRules.severity must be exactly one of: warning, error, blocking
- escalationPolicy must be exactly one of: always_review, never, on_failure
- stableInstructions must be a single string with numbered steps, never a list
- roleConfiguration must be a single string, never a list
- semanticBlueprint must be a single string using markdown headings, never a list
- outputTemplate must be a single string, never a list
- maxAgentTurns must be an integer between 1 and 20
- budgetSettings.maxTokens must be between 1000 and 16000
- budgetSettings.maxCostUsd must be between 0.01 and 5.00
- budgetSettings.maxToolCalls must be between 1 and 50
- retrievalConfig.maxDocuments must be between 1 and 50, never 0
- Add tools only if the use case clearly needs them
- Add glossaryTerms only if domain-specific terms are obvious
- Never set llmKeyId, vectorConnectionId, owner, id, version, status, created_at, updated_at
- Return ONLY the JSON, no explanation, no markdown fences"""

    generation_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = generation_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": request_context}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    config = json.loads(raw)
    config.pop("owner", None)

    # Normalize fields that should be strings but LLM may return as lists
    if isinstance(config.get("stableInstructions"), list):
        config["stableInstructions"] = "\n".join(
            f"{i+1}. {item}" for i, item in enumerate(config["stableInstructions"])
        )
    if isinstance(config.get("roleConfiguration"), list):
        config["roleConfiguration"] = " ".join(config["roleConfiguration"])
    if isinstance(config.get("semanticBlueprint"), list):
        config["semanticBlueprint"] = "\n".join(config["semanticBlueprint"])
    if isinstance(config.get("outputTemplate"), list):
        config["outputTemplate"] = "\n".join(config["outputTemplate"])
    if isinstance(config.get("escalationPolicy"), list):
        config["escalationPolicy"] = config["escalationPolicy"][0] if config["escalationPolicy"] else None

    workflow_type = str(config.get("workflowType") or "standard").strip().lower()
    if workflow_type not in valid_workflow_types:
        workflow_type = "standard"
    config["workflowType"] = workflow_type

    # Normalize model names to valid registry values
    valid_anthropic_models = {"claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5"}
    valid_openai_models = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"}
    valid_google_models = {"gemini-2.5-pro", "gemini-2.5-flash"}

    provider = config.get("executionProvider", "anthropic")
    model = config.get("executionModel", "")

    if provider == "anthropic" and model not in valid_anthropic_models:
        config["executionModel"] = "claude-haiku-4-5"
    elif provider == "openai" and model not in valid_openai_models:
        config["executionModel"] = "gpt-4o-mini"
    elif provider == "google" and model not in valid_google_models:
        config["executionModel"] = "gemini-2.5-flash"

    payload = cj_schemas.ContextJobCreate(**config)
    _validate_job_vector_connection(db, payload, owner)
    _validate_llm_key(db, owner, payload.llm_key_id)
    return payload


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


def get_overall_stats(db: Session, owner: str) -> dict:
    jobs = list_jobs(db, owner)
    runs = list_runs(db, owner)
    assets = list_assets(db, owner)
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


def replay_run(db: Session, owner: str, run_id: UUID) -> JobRunModel:
    run = get_run(db, run_id, owner)
    if not run:
        raise ValueError("Run not found")
    if not run.replay_snapshot and run.state not in {"completed", "failed", "escalated", "repair"}:
        raise ValueError("Run is not replayable")
    return create_replay_run(db, owner, run)


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
        raise ValueError("Run not found")
    return resolve_tool_approval(db, run, approval_id, decision, owner, notes)


def confirm_run_memory(
    db: Session,
    owner: str,
    run_id: UUID,
    approved: bool,
) -> JobRunModel:
    run = get_run(db, run_id, owner)
    if not run:
        raise ValueError("Run not found")
    job = get_job(db, run.job_id, owner)
    if not job:
        raise ValueError("Job not found")
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
        raise ValueError("Run not found")
    return list_tool_executions(db, run_id)


def export_run_report(db: Session, owner: str, run_id: UUID) -> str:
    run = get_run(db, run_id, owner)
    if not run:
        raise ValueError("Run not found")
    job = get_job(db, run.job_id, owner)
    return export_run_markdown(run, job)


def import_asset_to_job(
    db: Session, owner: str, job_id: UUID, asset_id: UUID
) -> dict[str, Any]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ValueError("Job not found")
    asset = get_asset(db, asset_id, owner)
    if not asset:
        raise ValueError("Asset not found")
    if getattr(asset, "approval_status", "approved") not in {None, "approved", "active"}:
        raise ValueError("Asset is not approved for import")
    summary = import_asset_into_job(job, asset)
    db.add(job)
    db.commit()
    db.refresh(job)
    return summary


def list_source_packs(db: Session, owner: str) -> list[ContextAssetModel]:
    ws_id = default_workspace_id(owner)
    return list_source_pack_assets(db, owner, ws_id)
