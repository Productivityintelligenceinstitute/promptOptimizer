"""Resolve enabled tools from job permissions and registry."""

from __future__ import annotations

from sqlalchemy.orm import Session

from context_jobs.providers.base import ToolDefinition
from schemas.tool_registry_model import ToolRegistryModel


def resolve_tools(job_permissions: list[dict] | None, db: Session) -> list[ToolDefinition]:
    enabled = [tp for tp in (job_permissions or []) if isinstance(tp, dict) and tp.get("enabled")]
    if not enabled:
        return []

    tool_ids = [tp.get("toolId") or tp.get("tool_id") for tp in enabled]
    tool_ids = [t for t in tool_ids if t]
    if not tool_ids:
        return []

    registry_rows = (
        db.query(ToolRegistryModel)
        .filter(ToolRegistryModel.id.in_(tool_ids), ToolRegistryModel.enabled == True)
        .all()
    )
    by_id = {row.id: row for row in registry_rows}
    definitions: list[ToolDefinition] = []
    for perm in enabled:
        tool_id = perm.get("toolId") or perm.get("tool_id")
        row = by_id.get(tool_id)
        if not row:
            continue
        definitions.append(
            ToolDefinition(
                id=row.id,
                name=row.name,
                description=row.description,
                input_schema=row.input_schema or {"type": "object", "properties": {}},
                is_read_only=bool(perm.get("readOnly", row.is_read_only)),
            )
        )
    return definitions
