import mimetypes
from datetime import datetime
from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from context_jobs.agents.catalog import list_specialist_catalog
from context_jobs.agents.execution_modes import (
    EXECUTION_MODE_MULTI,
    EXECUTION_MODE_SINGLE,
    VALID_EXECUTION_MODES,
)
from context_jobs.artifacts import merge_rop_and_disk_artifacts, resolve_download_artifact
from context_jobs.auth import get_authenticated_user_id
from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services
from context_jobs.ingestion.ingestion_service import ingest_documents


context_jobs_router = APIRouter(prefix="/context-jobs")


@context_jobs_router.get(
    "/jobs",
    response_model=list[cj_schemas.ContextJobOut],
    tags=["Context Jobs"],
)
async def list_jobs(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_jobs(db, owner)


@context_jobs_router.get(
    "/jobs/{job_id}",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def get_job(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@context_jobs_router.get(
    "/jobs/{job_id}/versions",
    response_model=list[cj_schemas.ContextJobVersionOut],
    tags=["Context Jobs"],
)
async def list_job_versions(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.list_job_versions(db, owner, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.get(
    "/jobs/{job_id}/versions/latest",
    response_model=cj_schemas.ContextJobVersionOut,
    tags=["Context Jobs"],
)
async def get_latest_job_version(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_latest_job_version(db, owner, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.get(
    "/jobs/{job_id}/versions/{version}",
    response_model=cj_schemas.ContextJobVersionOut,
    tags=["Context Jobs"],
)
async def get_job_version(
    job_id: UUID,
    version: int,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_job_version(db, owner, job_id, version)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs",
    response_model=cj_schemas.ContextJobOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_job(
    payload: cj_schemas.ContextJobCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.create_job(db, owner, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.patch(
    "/jobs/{job_id}",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def update_job(
    job_id: UUID,
    payload: cj_schemas.ContextJobUpdate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    try:
        return cj_services.update_job(db, owner, job, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/duplicate",
    response_model=cj_schemas.ContextJobOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def duplicate_job(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return cj_services.duplicate_job(db, owner, job)


@context_jobs_router.post(
    "/jobs/{job_id}/publish",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def publish_job(
    job_id: UUID,
    payload: cj_schemas.JobLifecycleRequest | None = None,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.publish_job(db, owner, job_id, payload.notes if payload else None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/archive",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def archive_job(
    job_id: UUID,
    payload: cj_schemas.JobLifecycleRequest | None = None,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.archive_job(db, owner, job_id, payload.notes if payload else None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/rollback",
    response_model=cj_schemas.ContextJobOut,
    tags=["Context Jobs"],
)
async def rollback_job_version(
    job_id: UUID,
    payload: cj_schemas.JobVersionRollbackRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.rollback_job_version(db, owner, job_id, payload.version, payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.get(
    "/jobs/{job_id}/publish-history",
    response_model=list[cj_schemas.PublishHistoryOut],
    tags=["Context Jobs"],
)
async def get_job_publish_history(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.list_publish_history(db, owner, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/identity-matches",
    tags=["Context Jobs"],
)
async def suggest_identity_matches(
    job_id: UUID,
    payload: cj_schemas.IdentityMatchRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.suggest_job_identity_matches(db, owner, job_id, payload.query)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/import-asset",
    tags=["Context Jobs"],
)
async def import_asset_into_job(
    job_id: UUID,
    payload: cj_schemas.AssetImportRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.import_asset_to_job(db, owner, job_id, payload.asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.get(
    "/source-packs",
    response_model=list[cj_schemas.ContextAssetOut],
    tags=["Context Jobs"],
)
async def list_source_packs(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_source_packs(db, owner)


@context_jobs_router.get(
    "/audit-events",
    response_model=list[cj_schemas.AuditEventOut],
    tags=["Context Jobs"],
)
async def get_audit_events(
    entity_type: str | None = Query(default=None, alias="entityType"),
    entity_id: str | None = Query(default=None, alias="entityId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    from_date: datetime | None = Query(default=None, alias="fromDate"),
    to_date: datetime | None = Query(default=None, alias="toDate"),
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_audit_events(
        db,
        owner,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        from_ts=from_date,
        to_ts=to_date,
    )


@context_jobs_router.get(
    "/execution-modes",
    response_model=cj_schemas.ExecutionModesOut,
    tags=["Context Jobs"],
)
async def list_execution_modes(
    owner: str = Depends(get_authenticated_user_id),
):
    labels = {
        EXECUTION_MODE_SINGLE: "Single agent (default)",
        EXECUTION_MODE_MULTI: "Provider multi-agent (opt-in delegation)",
    }
    return {
        "modes": [
            {"value": mode, "label": labels.get(mode, mode)}
            for mode in sorted(VALID_EXECUTION_MODES)
        ]
    }


@context_jobs_router.get(
    "/jobs/{job_id}/specialists",
    response_model=list[cj_schemas.SpecialistAgentOut],
    tags=["Context Jobs"],
)
async def list_job_specialists(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return list_specialist_catalog(job)


@context_jobs_router.get(
    "/jobs/{job_id}/stats",
    tags=["Context Jobs"],
)
async def get_job_stats(
    job_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_job_stats(db, owner, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.post(
    "/jobs/from-prompt",
    response_model=cj_schemas.ContextJobCreate,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def generate_job_from_prompt(
    payload: cj_schemas.PromptToJobRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return await cj_services.generate_job_from_prompt(
            db,
            owner,
            payload.prompt,
            payload.agent_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate job config: {exc}",
        ) from exc


@context_jobs_router.post(
    "/jobs/{job_id}/run",
    response_model=cj_schemas.JobRunOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def run_job(
    job_id: UUID,
    payload: cj_schemas.JobRunCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.create_run(db, owner, job_id, payload)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_429_TOO_MANY_REQUESTS if "queue is full" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc


@context_jobs_router.get(
    "/runs",
    response_model=list[cj_schemas.JobRunOut],
    tags=["Context Jobs"],
)
async def list_runs(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_runs(db, owner)


@context_jobs_router.get(
    "/runs/queue-status",
    tags=["Context Jobs"],
)
async def get_runs_queue_status(
    owner: str = Depends(get_authenticated_user_id),
):
    return cj_services.get_queue_status()


@context_jobs_router.get(
    "/runs/{run_id}",
    response_model=cj_schemas.JobRunOut,
    tags=["Context Jobs"],
)
async def get_run(
    run_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@context_jobs_router.get(
    "/runs/{run_id}/artifacts",
    response_model=cj_schemas.RunArtifactsOut,
    tags=["Context Jobs"],
)
async def list_run_artifacts(
    run_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {
        "runId": run.id,
        "artifacts": merge_rop_and_disk_artifacts(owner, run),
    }


@context_jobs_router.get(
    "/runs/{run_id}/artifacts/{artifact_path:path}",
    tags=["Context Jobs"],
)
async def download_run_artifact(
    run_id: UUID,
    artifact_path: str,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    try:
        target = resolve_download_artifact(owner, run, artifact_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(path=target, filename=target.name, media_type=media_type)


@context_jobs_router.patch(
    "/runs/{run_id}/decision",
    response_model=cj_schemas.JobRunOut,
    tags=["Context Jobs"],
)
async def record_run_decision(
    run_id: UUID,
    payload: cj_schemas.RunDecisionRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.state not in {
        "completed",
        "failed",
        "escalated",
        "repair",
        "awaiting_memory_approval",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot record a decision on a run that is still in progress",
        )
    try:
        return cj_services.record_human_decision(db, owner, run, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@context_jobs_router.post(
    "/runs/{run_id}/replay",
    response_model=cj_schemas.JobRunOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def replay_run(
    run_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.replay_run(db, owner, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.get(
    "/runs/{run_id}/tool-executions",
    tags=["Context Jobs"],
)
async def get_run_tool_executions(
    run_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_run_tool_executions(db, owner, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.get(
    "/runs/{run_id}/pending-approvals",
    tags=["Context Jobs"],
)
async def get_pending_tool_approvals(
    run_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    from context_jobs.hitl import list_pending_tool_approvals

    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return list_pending_tool_approvals(run)


@context_jobs_router.post(
    "/runs/{run_id}/tool-approvals/{approval_id}",
    response_model=cj_schemas.JobRunOut,
    tags=["Context Jobs"],
)
async def decide_tool_approval(
    run_id: UUID,
    approval_id: str,
    payload: cj_schemas.ToolApprovalRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.resolve_run_tool_approval(
            db, owner, run_id, approval_id, payload.decision, payload.notes
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.post(
    "/runs/{run_id}/memory-confirm",
    response_model=cj_schemas.JobRunOut,
    tags=["Context Jobs"],
)
async def confirm_memory_writes(
    run_id: UUID,
    payload: cj_schemas.MemoryConfirmRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.confirm_run_memory(db, owner, run_id, payload.approved)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@context_jobs_router.get(
    "/runs/{run_id}/export",
    tags=["Context Jobs"],
)
async def export_run(
    run_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    try:
        markdown = cj_services.export_run_report(db, owner, run_id)
        return PlainTextResponse(content=markdown, media_type="text/markdown")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@context_jobs_router.get(
    "/assets",
    response_model=list[cj_schemas.ContextAssetOut],
    tags=["Context Jobs"],
)
async def list_assets(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.list_assets(db, owner)


@context_jobs_router.post(
    "/assets",
    response_model=cj_schemas.ContextAssetOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Context Jobs"],
)
async def create_asset(
    payload: cj_schemas.ContextAssetCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.create_asset(db, owner, payload)


@context_jobs_router.patch(
    "/assets/{asset_id}",
    response_model=cj_schemas.ContextAssetOut,
    tags=["Context Jobs"],
)
async def update_asset(
    asset_id: UUID,
    payload: cj_schemas.ContextAssetUpdate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    asset = cj_services.get_asset(db, asset_id, owner)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return cj_services.update_asset(db, asset, payload)


@context_jobs_router.delete(
    "/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Context Jobs"],
)
async def delete_asset(
    asset_id: UUID,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    asset = cj_services.get_asset(db, asset_id, owner)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    cj_services.delete_asset(db, asset)
    return None


@context_jobs_router.get(
    "/stats",
    response_model=cj_schemas.ContextJobsStatsOut,
    tags=["Context Jobs"],
)
async def get_context_jobs_stats(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    return cj_services.get_overall_stats(db, owner)


@context_jobs_router.post(
    "/jobs/{job_id}/ingest",
    response_model=dict[str, Any],
    tags=["Context Jobs"],
)
async def ingest_into_job(
    job_id: UUID,
    payload: cj_schemas.IngestionRequest,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    job = cj_services.get_job(db, job_id, owner)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    try:
        doc_payloads = [d.model_dump() for d in payload.documents]
        result = ingest_documents(
            job=job,
            documents=doc_payloads,
            db=db,
            ingestion_config=payload.ingestion_config,
        )

        if result.status in {"escalated", "blocked_by_policy"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result.to_dict())
        if result.status in ("failed", "repair"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.to_dict())

        return result.to_dict()

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Ingestion failed: {exc}"},
        ) from exc


@context_jobs_router.get("/workspaces/default", tags=["Context Jobs"])
async def get_default_workspace(
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import ensure_default_workspace

    ws = ensure_default_workspace(db, owner)
    return {"id": ws.id, "name": ws.name, "owner": ws.owner}


@context_jobs_router.post("/workspaces/{workspace_id}/members", tags=["Context Jobs"])
async def add_member(
    workspace_id: str,
    payload: cj_schemas.WorkspaceMemberCreate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import add_workspace_member

    try:
        row = add_workspace_member(db, workspace_id, owner, payload.user_id, payload.role)
        return {"workspaceId": row.workspace_id, "userId": row.user_id, "role": row.role}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@context_jobs_router.get("/workspaces/{workspace_id}/allowlist", tags=["Context Jobs"])
async def get_workspace_allowlist(
    workspace_id: str,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import get_allowlist, require_role

    try:
        require_role(db, workspace_id, owner, "viewer")
        return get_allowlist(db, workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@context_jobs_router.patch("/workspaces/{workspace_id}/allowlist", tags=["Context Jobs"])
async def patch_workspace_allowlist(
    workspace_id: str,
    payload: cj_schemas.AllowlistUpdate,
    owner: str = Depends(get_authenticated_user_id),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import update_allowlist

    try:
        return update_allowlist(db, workspace_id, owner, payload.tools, payload.sources)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
