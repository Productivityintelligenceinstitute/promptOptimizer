"""Sanitize text for PostgreSQL and JSONB persistence."""

from __future__ import annotations

import re
from typing import Any

# Postgres rejects NUL in string literals; strip other C0 controls except common whitespace.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_db_text(value: str | None) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        value = str(value)
    cleaned = _CONTROL_CHAR_RE.sub("", value)
    return cleaned.replace("\x00", "")


def sanitize_for_db(value: Any) -> Any:
    """Recursively strip NUL/control chars from strings in nested structures."""
    if isinstance(value, str):
        return sanitize_db_text(value)
    if isinstance(value, dict):
        return {k: sanitize_for_db(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_db(item) for item in value]
    return value


def compact_tool_arguments_for_db(tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Store a small audit-safe copy of tool args (avoid huge contract bodies in JSONB)."""
    compact = sanitize_for_db(dict(arguments or {}))
    if tool_id != "contract-analyzer":
        return compact
    value = compact.get("value")
    if not isinstance(value, str) or not value:
        return compact
    compact = dict(compact)
    compact["valueChars"] = len(value)
    compact["valuePreview"] = value[:500]
    compact.pop("value", None)
    return compact
