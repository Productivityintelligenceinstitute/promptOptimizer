from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_context_jobs_owner_with_access
from database import database
from context_jobs import schemas as cj_schemas


router = APIRouter(tags=["Context Jobs"])


@router.get("/workspaces/default")
async def get_default_workspace(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import ensure_default_workspace

    ws = ensure_default_workspace(db, owner)
    return {"id": ws.id, "name": ws.name, "owner": ws.owner}


@router.post("/workspaces/{workspace_id}/members")
async def add_member(
    workspace_id: str,
    payload: cj_schemas.WorkspaceMemberCreate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import add_workspace_member

    try:
        row = add_workspace_member(db, workspace_id, owner, payload.user_id, payload.role)
        return {"workspaceId": row.workspace_id, "userId": row.user_id, "role": row.role}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/workspaces/{workspace_id}/allowlist")
async def get_workspace_allowlist(
    workspace_id: str,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import get_allowlist, require_role

    try:
        require_role(db, workspace_id, owner, "viewer")
        return get_allowlist(db, workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch("/workspaces/{workspace_id}/allowlist")
async def patch_workspace_allowlist(
    workspace_id: str,
    payload: cj_schemas.AllowlistUpdate,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
):
    from context_jobs.workspace import update_allowlist

    try:
        return update_allowlist(db, workspace_id, owner, payload.tools, payload.sources)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
