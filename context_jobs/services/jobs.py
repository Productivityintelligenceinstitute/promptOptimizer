from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
import context_jobs.audit as cj_audit
from context_jobs.agents.execution_modes import normalize_execution_mode
from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.governance import normalize_escalation_policy, suggest_identity_matches
from context_jobs.services._constants import normalize_workflow_type
from context_jobs.services._validation import (
    maybe_ensure_jet_managed_namespace,
    validate_job_execution_for_plan,
    validate_job_vector_connection,
    validate_tool_permissions_keys,
)
from context_jobs.services.assets import list_assets, import_assets_into_job
from context_jobs.services.job_queries import get_job, get_template_job, list_jobs, list_template_jobs
from context_jobs.services.job_stats import aggregate_job_stats
from context_jobs.services.runs import list_runs
from context_jobs.services.versioning import (
    ensure_job_version_seed,
    latest_job_version_number,
    record_job_version,
    record_publish_history,
)
from context_jobs.plan_entitlements import (
    assert_can_create_job,
    ensure_context_jobs_access,
    record_job_created,
)
from context_jobs.workspace import ensure_default_workspace
from schemas.context_jobs_model import ContextJobModel, JobRunModel


def _normalize_job_payload(payload: dict) -> dict:
    if "execution_mode" in payload and payload["execution_mode"] is not None:
        payload["execution_mode"] = normalize_execution_mode(payload["execution_mode"])
    if "escalation_policy" in payload and payload["escalation_policy"] is not None:
        payload["escalation_policy"] = normalize_escalation_policy(payload["escalation_policy"])
    if "workflow_type" in payload and payload["workflow_type"] is not None:
        payload["workflow_type"] = normalize_workflow_type(payload["workflow_type"])
    return payload


def _normalize_linked_asset_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def create_job(db: Session, owner: str, data: cj_schemas.ContextJobCreate) -> ContextJobModel:
    package_name = ensure_context_jobs_access(db, owner)
    assert_can_create_job(db, owner, package_name)
    ws = ensure_default_workspace(db, owner)
    payload = _normalize_job_payload(data.model_dump(by_alias=False))
    asset_ids = _normalize_linked_asset_ids(payload.pop("asset_ids", None) or [])
    payload["owner"] = owner
    payload["workspace_id"] = payload.get("workspace_id") or ws.id
    payload["status"] = "published"
    provider, model, key_id = validate_job_execution_for_plan(
        db,
        owner,
        package_name,
        payload.get("execution_provider"),
        payload.get("execution_model"),
        payload.get("llm_key_id"),
    )
    payload["execution_provider"] = provider
    payload["execution_model"] = model
    payload["llm_key_id"] = key_id
    check = cj_schemas.ContextJobCreate(**payload)
    validate_job_vector_connection(db, check, owner)
    validate_tool_permissions_keys(db, owner, payload.get("tool_permissions"))
    # Lifecycle chaining is guidance-only; never persist chain wiring on user jobs.
    payload["chain_config"] = None
    payload["linked_child_job_id"] = None
    payload["linked_asset_ids"] = asset_ids
    job = ContextJobModel(**payload)
    if asset_ids:
        import_assets_into_job(db, owner, job, [UUID(item) for item in asset_ids])
    db.add(job)
    db.commit()
    db.refresh(job)
    record_job_version(db, job, created_by=owner, change_type="create")
    record_publish_history(
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
    maybe_ensure_jet_managed_namespace(db, job)
    record_job_created(db, owner)
    return job


def update_job(
    db: Session,
    owner: str,
    job: ContextJobModel,
    data: cj_schemas.ContextJobUpdate,
) -> ContextJobModel:
    package_name = ensure_context_jobs_access(db, owner)
    payload = _normalize_job_payload(data.model_dump(exclude_unset=True, by_alias=False))
    asset_ids_raw = payload.pop("asset_ids", None)
    merged_mode = payload.get("retrieval_mode", job.retrieval_mode)
    merged_conn = payload.get("vector_connection_id", job.vector_connection_id)
    merged_key = payload.get("llm_key_id", job.llm_key_id)
    merged_provider = payload.get("execution_provider", job.execution_provider)
    merged_model = payload.get("execution_model", job.execution_model)
    if merged_mode is not None or merged_conn is not None:
        check = cj_schemas.ContextJobCreate(
            name=job.name,
            retrieval_mode=merged_mode,
            vector_connection_id=merged_conn,
            owner=owner,
            llm_key_id=merged_key,
        )
        validate_job_vector_connection(db, check, owner)
    if (
        "llm_key_id" in payload
        or "execution_provider" in payload
        or "execution_model" in payload
        or merged_key
        or merged_provider
        or merged_model
    ):
        provider, model, key_id = validate_job_execution_for_plan(
            db,
            owner,
            package_name,
            merged_provider,
            merged_model,
            merged_key,
        )
        payload["execution_provider"] = provider
        payload["execution_model"] = model
        payload["llm_key_id"] = key_id
    merged_tools = payload.get("tool_permissions", job.tool_permissions)
    if "tool_permissions" in payload or merged_tools:
        validate_tool_permissions_keys(db, owner, merged_tools)
    ensure_job_version_seed(db, job, created_by=owner)
    for key, value in payload.items():
        setattr(job, key, value)
    if asset_ids_raw is not None:
        asset_ids = _normalize_linked_asset_ids(asset_ids_raw)
        job.linked_asset_ids = asset_ids
        if asset_ids:
            import_assets_into_job(db, owner, job, [UUID(item) for item in asset_ids])
    job.owner = owner
    job.version = latest_job_version_number(db, job.id) + 1
    db.add(job)
    db.commit()
    db.refresh(job)
    record_job_version(db, job, created_by=owner, change_type="save")
    maybe_ensure_jet_managed_namespace(db, job)
    return job


def suggest_job_identity_matches(
    db: Session, owner: str, job_id: UUID, query: str
) -> list[dict[str, Any]]:
    job = get_job(db, job_id, owner)
    if not job:
        raise ContextJobsNotFoundError("Job not found")
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


def duplicate_job(db: Session, owner: str, job: ContextJobModel) -> ContextJobModel:
    package_name = ensure_context_jobs_access(db, owner)
    assert_can_create_job(db, owner, package_name)
    ws = ensure_default_workspace(db, owner)
    provider, model, key_id = validate_job_execution_for_plan(
        db,
        owner,
        package_name,
        job.execution_provider,
        job.execution_model,
        job.llm_key_id,
    )
    validate_tool_permissions_keys(db, owner, job.tool_permissions)
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
        chain_config=None,
        execution_provider=provider,
        execution_model=model,
        llm_key_id=key_id,
        max_agent_turns=job.max_agent_turns,
        execution_mode=job.execution_mode,
        version=1,
        owner=owner,
        approval_required=job.approval_required,
        policy_profile=job.policy_profile,
        workspace_id=job.workspace_id or ws.id,
        linked_asset_ids=list(job.linked_asset_ids or []) if isinstance(job.linked_asset_ids, list) else [],
    )
    db.add(duplicated)
    db.commit()
    db.refresh(duplicated)
    db.add(duplicated)
    db.commit()
    db.refresh(duplicated)
    record_job_version(db, duplicated, created_by=owner, change_type="duplicate")
    record_job_created(db, owner)
    return duplicated


def instantiate_template_job(db: Session, owner: str, template_id: UUID) -> ContextJobModel:
    """Duplicate a system template into the caller's workspace as a published job."""
    template = get_template_job(db, template_id)
    if not template:
        raise ContextJobsNotFoundError("Template not found")

    package_name = ensure_context_jobs_access(db, owner)
    assert_can_create_job(db, owner, package_name)
    ws = ensure_default_workspace(db, owner)
    provider, model, key_id = validate_job_execution_for_plan(
        db,
        owner,
        package_name,
        template.execution_provider,
        template.execution_model,
        template.llm_key_id,
    )
    validate_tool_permissions_keys(db, owner, template.tool_permissions)
    job = ContextJobModel(
        name=template.name,
        description=template.description,
        status="published",
        goal=template.goal,
        semantic_blueprint=template.semantic_blueprint,
        output_template=template.output_template,
        workflow_type=template.workflow_type,
        stable_instructions=template.stable_instructions,
        role_configuration=template.role_configuration,
        retrieval_config=template.retrieval_config,
        retrieval_mode=template.retrieval_mode,
        vector_connection_id=template.vector_connection_id,
        memory_config=template.memory_config,
        tool_permissions=template.tool_permissions,
        validation_rules=template.validation_rules,
        escalation_policy=template.escalation_policy,
        budget_settings=template.budget_settings,
        glossary_terms=template.glossary_terms,
        relationships=template.relationships,
        trusted_sources=template.trusted_sources,
        chain_config=None,
        execution_provider=provider,
        execution_model=model,
        llm_key_id=key_id,
        max_agent_turns=template.max_agent_turns,
        execution_mode=template.execution_mode,
        version=1,
        owner=owner,
        approval_required=template.approval_required,
        policy_profile=template.policy_profile,
        workspace_id=ws.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    record_job_version(db, job, created_by=owner, change_type="instantiate")
    record_publish_history(
        db,
        job_id=job.id,
        from_status="draft",
        to_status="published",
        changed_by=owner,
        notes="Instantiated from system template",
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
            "notes": "Instantiated from system template",
            "templateId": str(template_id),
            "jobVersion": job.version,
        },
    )
    maybe_ensure_jet_managed_namespace(db, job)
    record_job_created(db, owner)
    return job


def build_job_config_from_template(
    db: Session,
    owner: str,
    template_id: UUID,
) -> cj_schemas.ContextJobCreate:
    """Return a job configuration payload from a system template without persisting."""
    template = get_template_job(db, template_id)
    if not template:
        raise ContextJobsNotFoundError("Template not found")

    package_name = ensure_context_jobs_access(db, owner)
    ws = ensure_default_workspace(db, owner)
    provider, model, key_id = validate_job_execution_for_plan(
        db,
        owner,
        package_name,
        template.execution_provider,
        template.execution_model,
        template.llm_key_id,
        allow_model_fallback=True,
        require_key=False,
    )
    payload = _normalize_job_payload(
        {
            "name": template.name,
            "description": template.description,
            "status": "draft",
            "goal": template.goal,
            "semantic_blueprint": template.semantic_blueprint,
            "output_template": template.output_template,
            "workflow_type": template.workflow_type,
            "stable_instructions": template.stable_instructions,
            "role_configuration": template.role_configuration,
            "retrieval_config": template.retrieval_config,
            "retrieval_mode": template.retrieval_mode,
            "vector_connection_id": template.vector_connection_id,
            "memory_config": template.memory_config,
            "tool_permissions": template.tool_permissions,
            "validation_rules": template.validation_rules,
            "escalation_policy": template.escalation_policy,
            "budget_settings": template.budget_settings,
            "glossary_terms": template.glossary_terms,
            "relationships": template.relationships,
            "trusted_sources": template.trusted_sources,
            "chain_config": None,
            "execution_provider": provider,
            "execution_model": model,
            "llm_key_id": key_id,
            "max_agent_turns": template.max_agent_turns,
            "execution_mode": template.execution_mode,
            "version": 1,
            "owner": owner,
            "approval_required": template.approval_required,
            "policy_profile": template.policy_profile,
            "workspace_id": template.workspace_id or ws.id,
        }
    )
    job_create = cj_schemas.ContextJobCreate(**payload)
    validate_job_vector_connection(db, job_create, owner)
    return job_create


def get_job_stats(db: Session, owner: str, job_id: UUID) -> dict:
    if not get_job(db, job_id, owner):
        raise ContextJobsNotFoundError("Job not found")
    runs = db.query(JobRunModel).filter(JobRunModel.job_id == job_id).all()
    return aggregate_job_stats(runs)


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
