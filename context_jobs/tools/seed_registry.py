"""Seed default tool registry entries."""

from __future__ import annotations

from sqlalchemy.orm import Session

from context_jobs.tools import TOOL_IMPLEMENTATIONS
from schemas.tool_registry_model import ToolRegistryModel


def seed_tool_registry(db: Session) -> None:
    for tool_id, impl in TOOL_IMPLEMENTATIONS.items():
        existing = db.query(ToolRegistryModel).filter(ToolRegistryModel.id == tool_id).first()
        if existing:
            continue
        external_provider = "tavily" if tool_id == "web-search" else None
        db.add(
            ToolRegistryModel(
                id=tool_id,
                name=impl.name,
                description=impl.description,
                category=_category_for(tool_id),
                input_schema=impl.input_schema,
                is_read_only=True,
                requires_approval=False,
                max_timeout_ms=30000,
                enabled=True,
                provider_support={"anthropic": True, "openai": True, "google": True},
                external_provider=external_provider,
            )
        )
    db.commit()


def _category_for(tool_id: str) -> str:
    mapping = {
        "web-search": "search",
        "doc-reader": "read",
        "calculator": "compute",
        "code-exec": "execute",
        "api-caller": "integrate",
    }
    return mapping.get(tool_id, "integrate")
