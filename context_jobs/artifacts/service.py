"""Run artifact listing and secure path resolution."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.tools.artifact_paths import artifact_root, run_artifact_dir
from schemas.context_jobs_model import JobRunModel


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
                "sizeBytes": path.stat().st_size,
                "mimeType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
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


def merge_rop_and_disk_artifacts(owner: str, run: JobRunModel) -> list[dict]:
    rop = run.run_output_package or {}
    rop_items = rop.get("artifacts") or []
    disk_items = {item["path"]: item for item in list_run_artifact_files(owner, run)}
    merged: dict[str, dict] = {}

    for item in rop_items:
        if isinstance(item, dict) and item.get("path"):
            merged[item["path"]] = dict(item)

    for path, item in disk_items.items():
        merged[path] = {**merged.get(path, {}), **item}

    return [merged[k] for k in sorted(merged.keys())]
