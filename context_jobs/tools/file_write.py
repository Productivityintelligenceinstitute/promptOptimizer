"""Write text-based artifacts into the per-run workspace."""

from __future__ import annotations

from typing import Any, Optional

from context_jobs.tools.artifact_paths import resolve_artifact_path
from context_jobs.tools.base import BaseTool


class FileWriteTool(BaseTool):
    id = "file-write"
    name = "File Write"
    description = (
        "Create or update a text-based file in the run output workspace. "
        "Use the correct extension for the content type (.md, .txt, .py, .sql, .json, etc.)."
    )
    requires_external_key = False
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path under the run workspace, e.g. deliverables/report.md",
            },
            "content": {"type": "string", "description": "UTF-8 text content to write"},
            "mode": {
                "type": "string",
                "enum": ["overwrite", "append"],
                "default": "overwrite",
                "description": "Write mode",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        api_key: Optional[str] = None,
        *,
        owner: str | None = None,
        run_id: str | None = None,
    ) -> str:
        if not owner or not run_id:
            raise ValueError("file-write requires run context (owner and run_id)")
        path_arg = str(arguments.get("path", "")).strip()
        content = str(arguments.get("content", ""))
        mode = str(arguments.get("mode") or "overwrite").lower()
        if mode not in {"overwrite", "append"}:
            raise ValueError("mode must be 'overwrite' or 'append'")

        target = resolve_artifact_path(owner, run_id, path_arg)
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append" and target.exists():
            existing = target.read_text(encoding="utf-8")
            target.write_text(existing + content, encoding="utf-8")
        else:
            target.write_text(content, encoding="utf-8")

        from context_jobs.artifacts.blob_store import persist_run_artifact_file

        persist_run_artifact_file(
            owner,
            run_id,
            path_arg,
            target,
            tool_id=self.id,
        )
        return (
            f"Wrote file: {path_arg} ({len(content)} chars, mode={mode}). "
            f"artifact_path={target.as_posix()}"
        )
