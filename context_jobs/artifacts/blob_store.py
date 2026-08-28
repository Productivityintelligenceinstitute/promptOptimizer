"""BYTEA persistence for run artifacts (source of truth for download)."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.database import SessionLocal
from schemas.context_jobs_model import JobRunModel
from schemas.run_artifact_blob_model import RunArtifactBlobModel

logger = logging.getLogger(__name__)

MAX_BLOB_BYTES = 25 * 1024 * 1024
REVISED_CONTRACT_FILENAME = "revised-contract.docx"

_MIME_BY_SUFFIX = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
}


def mime_type_for_path(relative_path: str) -> str:
    suffix = Path(relative_path or "").suffix.lower()
    if suffix in _MIME_BY_SUFFIX:
        return _MIME_BY_SUFFIX[suffix]
    guessed, _ = mimetypes.guess_type(relative_path)
    return guessed or "application/octet-stream"


def purpose_for_path(relative_path: str, *, workflow_type: str | None = None) -> str:
    name = Path(relative_path or "").name.lower()
    if name == REVISED_CONTRACT_FILENAME or name.startswith("revised-contract"):
        return "revised_contract"
    if (workflow_type or "").lower() == "contract_amendment" and name.endswith(".docx"):
        return "revised_contract"
    return "artifact"


def _normalize_path(relative_path: str) -> str:
    rel = (relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("Invalid artifact path")
    return rel


def persist_run_artifact_bytes(
    owner: str,
    run_id: str | UUID,
    relative_path: str,
    content: bytes,
    *,
    tool_id: str | None = None,
    mime_type: str | None = None,
    workflow_type: str | None = None,
    db: Session | None = None,
) -> RunArtifactBlobModel:
    if content is None:
        raise ValueError("Artifact content is required")
    if len(content) > MAX_BLOB_BYTES:
        raise ValueError(
            f"Artifact is too large to store ({len(content)} bytes). Maximum is {MAX_BLOB_BYTES} bytes."
        )
    path = _normalize_path(relative_path)
    filename = Path(path).name
    run_uuid = run_id if isinstance(run_id, UUID) else UUID(str(run_id))
    owns_session = db is None
    session = db or SessionLocal()
    try:
        run = session.query(JobRunModel).filter(JobRunModel.id == run_uuid).first()
        visible_on = run.parent_run_id if run and run.parent_run_id else run_uuid
        job_workflow = workflow_type
        if run and not job_workflow:
            from schemas.context_jobs_model import ContextJobModel

            job = session.query(ContextJobModel).filter(ContextJobModel.id == run.job_id).first()
            job_workflow = getattr(job, "workflow_type", None) if job else None

        row = (
            session.query(RunArtifactBlobModel)
            .filter(RunArtifactBlobModel.run_id == run_uuid, RunArtifactBlobModel.path == path)
            .first()
        )
        purpose = purpose_for_path(path, workflow_type=job_workflow)
        resolved_mime = mime_type or mime_type_for_path(path)
        if row:
            row.owner = owner
            row.visible_on_run_id = visible_on
            row.filename = filename
            row.mime_type = resolved_mime
            row.tool_id = tool_id
            row.purpose = purpose
            row.size_bytes = len(content)
            row.content = content
        else:
            row = RunArtifactBlobModel(
                owner=owner,
                run_id=run_uuid,
                visible_on_run_id=visible_on,
                path=path,
                filename=filename,
                mime_type=resolved_mime,
                tool_id=tool_id,
                purpose=purpose,
                size_bytes=len(content),
                content=content,
            )
            session.add(row)
        session.commit()
        session.refresh(row)
        return row
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def persist_run_artifact_file(
    owner: str,
    run_id: str | UUID,
    relative_path: str,
    file_path: Path,
    *,
    tool_id: str | None = None,
) -> RunArtifactBlobModel | None:
    try:
        content = Path(file_path).read_bytes()
    except OSError as exc:
        logger.exception("Failed to read artifact file %s: %s", file_path, exc)
        raise
    return persist_run_artifact_bytes(
        owner,
        run_id,
        relative_path,
        content,
        tool_id=tool_id,
        mime_type=mime_type_for_path(relative_path),
    )


def list_blob_artifacts(owner: str, run_id: UUID, db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(RunArtifactBlobModel)
        .filter(
            RunArtifactBlobModel.owner == owner,
            or_(
                RunArtifactBlobModel.run_id == run_id,
                RunArtifactBlobModel.visible_on_run_id == run_id,
            ),
        )
        .order_by(RunArtifactBlobModel.created_at.asc())
        .all()
    )
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if row.path in seen:
            continue
        seen.add(row.path)
        items.append(
            {
                "path": row.path,
                "filename": row.filename,
                "sizeBytes": row.size_bytes,
                "mimeType": row.mime_type,
                "toolId": row.tool_id,
                "purpose": row.purpose,
            }
        )
    return items


def get_blob_artifact(
    owner: str,
    run_id: UUID,
    relative_path: str,
    db: Session,
) -> RunArtifactBlobModel | None:
    path = _normalize_path(relative_path)
    return (
        db.query(RunArtifactBlobModel)
        .filter(
            RunArtifactBlobModel.owner == owner,
            RunArtifactBlobModel.path == path,
            or_(
                RunArtifactBlobModel.run_id == run_id,
                RunArtifactBlobModel.visible_on_run_id == run_id,
            ),
        )
        .order_by(RunArtifactBlobModel.created_at.desc())
        .first()
    )
