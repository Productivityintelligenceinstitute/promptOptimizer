import mimetypes
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from context_jobs.artifacts import merge_rop_and_disk_artifacts, resolve_download_artifact
from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.errors import raise_context_jobs_http
from database import database
from context_jobs import schemas as cj_schemas
from context_jobs import services as cj_services


router = APIRouter(tags=["Context Jobs"])


@router.get("/runs", response_model=list[cj_schemas.JobRunOut])
async def list_runs(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.list_runs(db, owner)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/runs/queue-status")
async def get_runs_queue_status(
    owner: str = Depends(get_context_jobs_owner_with_access),
):
    return cj_services.get_queue_status()


@router.get("/runs/{run_id}", response_model=cj_schemas.JobRunOut)
async def get_run(
    run_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("/runs/{run_id}/chain", response_model=cj_schemas.RunChainOut)
async def get_run_chain(
    run_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    result = cj_services.get_run_chain(db, owner, run_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return result


@router.get("/runs/{run_id}/artifacts", response_model=cj_schemas.RunArtifactsOut)
async def list_run_artifacts(
    run_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {
        "runId": run.id,
        "artifacts": merge_rop_and_disk_artifacts(owner, run),
    }


@router.get("/runs/{run_id}/artifacts/{artifact_path:path}")
async def download_run_artifact(
    run_id: UUID,
    artifact_path: str,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    try:
        target = resolve_download_artifact(owner, run, artifact_path)
    except Exception as exc:
        raise_context_jobs_http(exc)
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(path=target, filename=target.name, media_type=media_type)


@router.patch("/runs/{run_id}/decision", response_model=cj_schemas.JobRunOut)
async def record_run_decision(
    run_id: UUID,
    payload: cj_schemas.RunDecisionRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
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


@router.post(
    "/runs/{run_id}/replay",
    response_model=cj_schemas.JobRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def replay_run(
    run_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.replay_run(db, owner, run_id)
    except ValueError as exc:
        detail = str(exc)
        if "queue is full" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
            ) from exc
        raise_context_jobs_http(exc)


@router.get("/runs/{run_id}/tool-executions")
async def get_run_tool_executions(
    run_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.get_run_tool_executions(db, owner, run_id)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/runs/{run_id}/pending-approvals")
async def get_pending_tool_approvals(
    run_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    from context_jobs.hitl import list_pending_tool_approvals

    run = cj_services.get_run(db, run_id, owner)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return list_pending_tool_approvals(run)


@router.post(
    "/runs/{run_id}/tool-approvals/{approval_id}",
    response_model=cj_schemas.JobRunOut,
)
async def decide_tool_approval(
    run_id: UUID,
    approval_id: str,
    payload: cj_schemas.ToolApprovalRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.resolve_run_tool_approval(
            db, owner, run_id, approval_id, payload.decision, payload.notes
        )
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.post("/runs/{run_id}/memory-confirm", response_model=cj_schemas.JobRunOut)
async def confirm_memory_writes(
    run_id: UUID,
    payload: cj_schemas.MemoryConfirmRequest,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        return cj_services.confirm_run_memory(db, owner, run_id, payload.approved)
    except Exception as exc:
        raise_context_jobs_http(exc)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    try:
        markdown = cj_services.export_run_report(db, owner, run_id)
        return PlainTextResponse(content=markdown, media_type="text/markdown")
    except Exception as exc:
        raise_context_jobs_http(exc)
