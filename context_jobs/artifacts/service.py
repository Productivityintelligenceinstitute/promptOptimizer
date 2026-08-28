"""Run artifact listing and secure path resolution."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from sqlalchemy.orm import Session

from context_jobs.artifacts.blob_store import get_blob_artifact, list_blob_artifacts
from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.tools.artifact_paths import run_artifact_dir
from schemas.context_jobs_model import JobRunModel
from schemas.run_artifact_blob_model import RunArtifactBlobModel


def list_run_artifact_files(owner: str, run: JobRunModel) -> list[dict]:
    base = run_artifact_dir(owner, str(run.id))
    if not base.exists():
        return []

    items: list[dict] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        items.append(
            {
                "path": rel,
                "filename": path.name,
                "sizeBytes": path.stat().st_size,
                "mimeType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "purpose": "revised_contract" if "revised-contract" in rel.lower() else "artifact",
            }
        )
    return items


def resolve_download_artifact(owner: str, run: JobRunModel, relative_path: str) -> Path:
    base = run_artifact_dir(owner, str(run.id)).resolve()
    rel = (relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("Invalid artifact path")

    target = (base / rel).resolve()
    if base not in target.parents and target != base:
        raise ValueError("Artifact path escapes run workspace")
    if not target.exists() or not target.is_file():
        raise ContextJobsNotFoundError("Artifact not found")
    return target


def merge_rop_and_disk_artifacts(owner: str, run: JobRunModel, db: Session | None = None) -> list[dict]:
    rop = run.run_output_package or {}
    rop_items = rop.get("artifacts") or []
    disk_items = {item["path"]: item for item in list_run_artifact_files(owner, run)}
    merged: dict[str, dict] = {}

    for item in rop_items:
        if isinstance(item, dict) and item.get("path"):
            merged[item["path"]] = dict(item)

    for path, item in disk_items.items():
        merged[path] = {**merged.get(path, {}), **item}

    if db is not None:
        for item in list_blob_artifacts(owner, run.id, db):
            path = item["path"]
            merged[path] = {**merged.get(path, {}), **item}
        if run.amendment_run_id:
            child = db.query(JobRunModel).filter(JobRunModel.id == run.amendment_run_id).first()
            if child:
                for item in list_run_artifact_files(owner, child):
                    path = item["path"]
                    merged[path] = {**merged.get(path, {}), **item}

    return [merged[k] for k in sorted(merged.keys())]


def resolve_download_blob(
    owner: str,
    run: JobRunModel,
    relative_path: str,
    db: Session,
) -> RunArtifactBlobModel | None:
    return get_blob_artifact(owner, run.id, relative_path, db)
