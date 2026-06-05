"""Safe per-run artifact directory helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

ALLOWED_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".yaml",
    ".yml",
    ".sql",
    ".html",
    ".css",
    ".sh",
    ".csv",
}

ALLOWED_BINARY_EXTENSIONS = {".docx"}

ALLOWED_EXTENSIONS = ALLOWED_TEXT_EXTENSIONS | ALLOWED_BINARY_EXTENSIONS

_UNSAFE_SEGMENT = re.compile(r"[^a-zA-Z0-9._-]+")


def artifact_root() -> Path:
    return Path(os.environ.get("RUN_ARTIFACT_ROOT", "data/run-artifacts")).resolve()


def run_artifact_dir(owner: str, run_id: str) -> Path:
    safe_owner = _UNSAFE_SEGMENT.sub("_", (owner or "unknown").strip())[:64] or "unknown"
    return artifact_root() / safe_owner / str(run_id)


def ensure_run_artifact_dir(owner: str, run_id: str) -> Path:
    path = run_artifact_dir(owner, run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_artifact_path(owner: str, run_id: str, relative_path: str) -> Path:
    rel = (relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("path must be relative and cannot contain '..'")

    suffix = Path(rel).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"unsupported file extension '{suffix or '(none)'}'; allowed: {allowed}")

    base = ensure_run_artifact_dir(owner, run_id)
    target = (base / rel).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        raise ValueError("path escapes run artifact directory")
    return target
